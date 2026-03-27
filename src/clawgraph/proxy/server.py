"""Minimal HTTP proxy server for ClawGraph."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from clawgraph.protocol.factories import new_fact_event, new_semantic_event_fact
from clawgraph.protocol.semantics import extract_prompt_messages, request_payload_fingerprint
from clawgraph.proxy.payload_store import LocalPayloadStore
from clawgraph.store import SQLiteFactStore

_HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
}
_STREAM_CHUNK_SIZE = 4096
_SESSION_COOKIE_NAME = "clawgraph_session_id"
_RUN_COOKIE_NAME = "clawgraph_run_id"
_INTERNAL_COOKIE_NAMES = {_SESSION_COOKIE_NAME, _RUN_COOKIE_NAME}
_RUN_ROTATION_HEADER = "x-clawgraph-new-run"
_PROXY_AUTH_HEADER = "x-clawgraph-proxy-auth"
_LEGACY_PROXY_AUTH_HEADER = "x-clawgraph-api-key"
_INTERNAL_AUTH_HEADERS = {_PROXY_AUTH_HEADER, _LEGACY_PROXY_AUTH_HEADER}
_DEFAULT_MAX_REQUEST_BODY_BYTES = 1024 * 1024
_DEFAULT_MAX_RESPONSE_BODY_BYTES = 4 * 1024 * 1024
_DEFAULT_MAX_CAPTURE_BYTES = 16 * 1024
_DEFAULT_MAX_STREAM_CHUNK_FACTS = 32


@dataclass(slots=True)
class ProxyConfig:
    """Configuration for the minimal proxy server."""

    host: str
    port: int
    store_uri: str
    model_upstream: str | None = None
    tool_upstream: str | None = None
    upstream_timeout_seconds: float = 30.0
    auth_token: str | None = None
    max_request_body_bytes: int = _DEFAULT_MAX_REQUEST_BODY_BYTES
    max_response_body_bytes: int = _DEFAULT_MAX_RESPONSE_BODY_BYTES
    max_capture_bytes: int = _DEFAULT_MAX_CAPTURE_BYTES
    max_stream_chunk_facts: int = _DEFAULT_MAX_STREAM_CHUNK_FACTS
    enforce_session_user_binding: bool = True
    payload_dir: str | None = None


class RequestBodyTooLargeError(ValueError):
    """Raised when a request body exceeds the configured proxy limit."""


class ResponseBodyTooLargeError(ValueError):
    """Raised when an upstream response body exceeds the configured proxy limit."""


def _safe_parse_json(raw_body: bytes) -> dict[str, Any] | list[Any] | None:
    if not raw_body:
        return None
    try:
        value = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(value, (dict, list)):
        return value
    return None


def _preview_text(raw_body: bytes, *, max_capture_bytes: int) -> str:
    return raw_body[:max_capture_bytes].decode("utf-8", errors="replace")


def _apply_request_capture_semantics(
    *,
    payload: dict[str, Any],
    request_json: dict[str, Any] | list[Any] | None,
) -> None:
    if not isinstance(request_json, dict):
        return
    input_messages = extract_prompt_messages(request_json)
    if input_messages:
        payload["input_messages"] = input_messages
    fingerprint = request_payload_fingerprint(request_json)
    if fingerprint is not None:
        payload["request_fingerprint"] = fingerprint


def _capture_payload_body(
    *,
    payload: dict[str, Any],
    raw_body: bytes,
    path: str,
    max_capture_bytes: int,
    canonical_from_json: bool = False,
    body_ref: dict[str, Any] | None = None,
    parsed_json: dict[str, Any] | list[Any] | None = None,
) -> None:
    if not raw_body:
        return
    parsed = (
        parsed_json
        if isinstance(parsed_json, (dict, list))
        else _safe_parse_json(raw_body)
    )
    if len(raw_body) > max_capture_bytes:
        if canonical_from_json and isinstance(parsed, dict):
            canonical = _canonical_response_payload(path=path, response_json=parsed)
            if canonical is not None:
                payload["canonical"] = canonical
        payload["preview"] = _preview_text(raw_body, max_capture_bytes=max_capture_bytes)
        payload["capture_truncated"] = True
        if body_ref is not None:
            payload["body_ref"] = body_ref
        return

    if parsed is not None:
        payload["json"] = parsed
        if canonical_from_json and isinstance(parsed, dict):
            canonical = _canonical_response_payload(path=path, response_json=parsed)
            if canonical is not None:
                payload["canonical"] = canonical
        return

    payload["text"] = raw_body.decode("utf-8", errors="replace")


def _request_capture_payload(
    *,
    method: str,
    path: str,
    request_target: str,
    headers: Any,
    content_type: str,
    raw_body: bytes,
    request_json: dict[str, Any] | list[Any] | None,
    max_capture_bytes: int,
    body_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": method,
        "path": path,
        **({"request_target": request_target} if request_target != path else {}),
        "headers": _sanitize_headers(headers),
        "content_type": content_type,
        "body_size": len(raw_body),
    }
    _apply_request_capture_semantics(payload=payload, request_json=request_json)
    if isinstance(request_json, (dict, list)) and len(raw_body) <= max_capture_bytes:
        payload["json"] = request_json
    elif raw_body:
        _capture_payload_body(
            payload=payload,
            raw_body=raw_body,
            path=path,
            max_capture_bytes=max_capture_bytes,
            body_ref=body_ref,
            parsed_json=request_json,
        )
    return payload


def _owner_key(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return f"user:{user_id}"


def _sanitize_stream_fragments(
    fragments: list[dict[str, Any]],
    *,
    max_capture_bytes: int,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        item = dict(fragment)
        data = item.get("data")
        if isinstance(data, str) and len(data) > max_capture_bytes:
            item["data"] = data[:max_capture_bytes]
            item["truncated"] = True
        elif isinstance(data, dict):
            rendered = json.dumps(data, ensure_ascii=True, sort_keys=True)
            if len(rendered) > max_capture_bytes:
                item["data"] = rendered[:max_capture_bytes]
                item["truncated"] = True
        sanitized.append(item)
    return sanitized


def _read_bounded_response_body(response: Any, *, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if isinstance(content_length, str) and content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise ValueError("invalid upstream Content-Length") from exc
        if declared_length > max_bytes:
            raise ResponseBodyTooLargeError(
                f"upstream response body exceeds {max_bytes} bytes"
            )

    body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ResponseBodyTooLargeError(f"upstream response body exceeds {max_bytes} bytes")
    return body


def _request_is_authorized(headers: Any, *, auth_token: str | None) -> bool:
    if auth_token is None:
        return True
    proxy_auth = headers.get(_PROXY_AUTH_HEADER)
    if isinstance(proxy_auth, str) and proxy_auth == auth_token:
        return True
    api_key = headers.get(_LEGACY_PROXY_AUTH_HEADER)
    if isinstance(api_key, str) and api_key == auth_token:
        return True
    return False


def _sanitize_headers(headers: Any) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {
            "authorization",
            "proxy-authorization",
            "x-api-key",
            "cookie",
            "set-cookie",
            *_INTERNAL_AUTH_HEADERS,
        }:
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def _forward_headers(
    headers: Any,
    *,
    session_id: str,
    run_id: str,
    request_id: str,
    user_id: str | None,
    thread_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP_HEADERS:
            continue
        if lower in _INTERNAL_AUTH_HEADERS:
            continue
        if lower == _RUN_ROTATION_HEADER:
            continue
        if lower == "cookie":
            forwarded_cookie = _forward_cookie_value(headers)
            if forwarded_cookie:
                forwarded[key] = forwarded_cookie
            continue
        forwarded[key] = value
    forwarded.setdefault("x-clawgraph-session-id", session_id)
    forwarded.setdefault("x-clawgraph-run-id", run_id)
    forwarded.setdefault("x-clawgraph-request-id", request_id)
    if user_id:
        forwarded.setdefault("x-clawgraph-user-id", user_id)
    if thread_id:
        forwarded.setdefault("x-clawgraph-thread-id", thread_id)
    if task_id:
        forwarded.setdefault("x-clawgraph-task-id", task_id)
    return forwarded


def _cookie_value(headers: Any, name: str) -> str | None:
    raw_cookie = headers.get("Cookie")
    if not isinstance(raw_cookie, str) or not raw_cookie:
        return None
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    morsel = cookie.get(name)
    if morsel is None:
        return None
    value = morsel.value.strip()
    return value or None


def _forward_cookie_value(headers: Any) -> str | None:
    """Forward client cookies except the internal ClawGraph identity cookies."""

    raw_cookie = headers.get("Cookie")
    if not isinstance(raw_cookie, str) or not raw_cookie:
        return None
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    forwarded_parts = []
    for morsel_name, morsel in cookie.items():
        if morsel_name in _INTERNAL_COOKIE_NAMES:
            continue
        forwarded_parts.append(f"{morsel_name}={morsel.value}")
    if forwarded_parts:
        return "; ".join(forwarded_parts)
    return None


def _set_identity_cookies(handler: BaseHTTPRequestHandler, *, session_id: str, run_id: str) -> None:
    handler.send_header(
        "Set-Cookie",
        f"{_SESSION_COOKIE_NAME}={session_id}; Path=/; HttpOnly; SameSite=Lax",
    )
    handler.send_header(
        "Set-Cookie",
        f"{_RUN_COOKIE_NAME}={run_id}; Path=/; HttpOnly; SameSite=Lax",
    )


def _header_truthy(headers: Any, name: str) -> bool:
    value = headers.get(name)
    if not isinstance(value, str):
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _resolve_upstream_url(upstream: str, path: str) -> str:
    requested = urlsplit(path)
    requested_path = requested.path or "/"
    parsed = urlsplit(upstream)
    merged_query = _merge_query_strings(parsed.query, requested.query)
    if parsed.path in {"", "/"}:
        return urlunsplit(
            (parsed.scheme, parsed.netloc, requested_path, merged_query, parsed.fragment)
        )
    if parsed.path == requested_path:
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, merged_query, parsed.fragment)
        )
    rewritten_path = _rewrite_upstream_path(parsed.path, requested_path)
    if rewritten_path is not None:
        return urlunsplit(
            (parsed.scheme, parsed.netloc, rewritten_path, merged_query, parsed.fragment)
        )
    return upstream


def _merge_query_strings(base_query: str, requested_query: str) -> str:
    if base_query and requested_query:
        return f"{base_query}&{requested_query}"
    return requested_query or base_query


def _rewrite_upstream_path(base_path: str, requested_path: str) -> str | None:
    """Rewrite a requested path while preserving any upstream path prefix."""

    if requested_path.startswith("/v1/"):
        marker = "/v1/"
    elif requested_path.startswith("/tools"):
        marker = "/tools"
    else:
        return None

    marker_index = base_path.find(marker)
    if marker_index < 0:
        return None
    prefix = base_path[:marker_index]
    return f"{prefix}{requested_path}"


def _target_upstream(path: str, config: ProxyConfig) -> str | None:
    if path.startswith("/v1/") and path != "/v1/semantic-events":
        return config.model_upstream
    if path.startswith("/tools"):
        return config.tool_upstream
    return None


def _actor_for_path(path: str) -> str:
    if path.startswith("/v1/") and path != "/v1/semantic-events":
        return "model"
    if path.startswith("/tools"):
        return "tool"
    return "runtime"


def _payload_from_response(
    *,
    path: str,
    status_code: int,
    content_type: str,
    response_body: bytes,
    max_capture_bytes: int,
    body_ref: dict[str, Any] | None = None,
    upstream_request_id: str | None = None,
    total_latency_ms: int | None = None,
    ttfb_ms: int | None = None,
    stream_duration_ms: int | None = None,
) -> dict[str, Any]:
    response_json = _safe_parse_json(response_body)
    payload: dict[str, Any] = {
        "path": path,
        "status_code": status_code,
        "content_type": content_type,
        "body_size": len(response_body),
    }
    if upstream_request_id is not None:
        payload["upstream_request_id"] = upstream_request_id
    if total_latency_ms is not None:
        payload["total_latency_ms"] = total_latency_ms
    if ttfb_ms is not None:
        payload["ttfb_ms"] = ttfb_ms
    if stream_duration_ms is not None:
        payload["stream_duration_ms"] = stream_duration_ms
    _capture_payload_body(
        payload=payload,
        raw_body=response_body,
        path=path,
        max_capture_bytes=max_capture_bytes,
        canonical_from_json=True,
        body_ref=body_ref,
        parsed_json=response_json,
    )
    return payload


def _is_streaming_request(request_json: dict[str, Any] | list[Any] | None) -> bool:
    if not isinstance(request_json, dict):
        return False
    return bool(request_json.get("stream"))


def _is_streaming_content_type(content_type: str) -> bool:
    return "text/event-stream" in content_type.lower()


def _extract_sse_fragments(chunk: bytes) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            fragments.append({"type": "done"})
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            fragments.append({"type": "text", "data": data})
        else:
            fragments.append({"type": "json", "data": parsed})
    return fragments


def _extract_complete_sse_fragments(
    *,
    pending: bytearray,
    chunk: bytes,
) -> list[dict[str, Any]]:
    pending.extend(chunk)
    fragments: list[dict[str, Any]] = []
    while True:
        separator_index, separator_length = _find_sse_separator(pending)
        if separator_index < 0:
            break
        event_bytes = bytes(pending[:separator_index])
        del pending[: separator_index + separator_length]
        if event_bytes:
            fragments.extend(_extract_sse_fragments(event_bytes))
    return fragments


def _find_sse_separator(buffer: bytearray) -> tuple[int, int]:
    candidates: list[tuple[int, int]] = []
    for separator in (b"\r\n\r\n", b"\n\n"):
        index = buffer.find(separator)
        if index >= 0:
            candidates.append((index, len(separator)))
    if not candidates:
        return -1, 0
    return min(candidates, key=lambda item: item[0])


def _extract_text_fragment(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "value", "delta"):
            nested = _extract_text_fragment(value.get(key))
            if nested:
                return nested
        return None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _extract_text_fragment(item)
            if text:
                parts.append(text)
        if parts:
            return "".join(parts)
    return None


def _new_stream_state() -> dict[str, Any]:
    return {
        "role": "assistant",
        "delta_parts": [],
        "fallback_text": None,
        "tool_calls": {},
        "response_output_items": {},
        "response_output_order": [],
        "output_text_parts": [],
    }


def _update_stream_state(
    state: dict[str, Any],
    fragments: list[dict[str, Any]],
) -> None:
    for fragment in fragments:
        if fragment.get("type") != "json":
            continue
        data = fragment.get("data")
        if not isinstance(data, dict):
            continue

        choices = data.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message_like = choice.get("delta") or choice.get("message")
                if not isinstance(message_like, dict):
                    continue
                role = message_like.get("role")
                if isinstance(role, str) and role:
                    state["role"] = role
                text = _extract_text_fragment(message_like.get("content"))
                if text:
                    state["delta_parts"].append(text)
                _update_chat_tool_calls(state, message_like.get("tool_calls"))

        event_type = data.get("type")
        if event_type == "response.output_text.delta":
            text = _extract_text_fragment(data.get("delta") or data.get("text"))
            if text:
                state["delta_parts"].append(text)
                state["output_text_parts"].append(text)
            _update_response_output_message(
                state,
                item_id=_response_item_id(data),
                role="assistant",
                text=text,
            )
        elif event_type == "response.function_call_arguments.delta":
            arguments_delta = _extract_text_fragment(data.get("delta") or data.get("arguments"))
            if arguments_delta:
                _update_response_function_call(
                    state,
                    item_id=_response_item_id(data),
                    name=_string_value(data.get("name")),
                    arguments_delta=arguments_delta,
                    call_id=_string_value(data.get("call_id")),
                )
        elif event_type == "response.output_item.added":
            _merge_response_output_item(state, data.get("item"), fallback_id=_response_item_id(data))
        elif event_type == "response.output_item.done":
            _merge_response_output_item(state, data.get("item"), fallback_id=_response_item_id(data))

        fallback_text = _extract_text_fragment(data.get("output_text") or data.get("output"))
        if fallback_text and not state["fallback_text"]:
            state["fallback_text"] = fallback_text

        response_obj = data.get("response")
        if isinstance(response_obj, dict):
            _merge_response_output_list(state, response_obj.get("output"))
            response_text = _extract_text_fragment(
                response_obj.get("output_text") or response_obj.get("output")
            )
            if response_text and not state["fallback_text"]:
                state["fallback_text"] = response_text


def _build_stream_response_json(path: str, state: dict[str, Any]) -> dict[str, Any] | None:
    text = "".join(part for part in state["delta_parts"] if isinstance(part, str))
    if not text:
        output_text = "".join(
            part for part in state.get("output_text_parts", []) if isinstance(part, str)
        )
        text = output_text
    if not text:
        fallback = state.get("fallback_text")
        text = fallback if isinstance(fallback, str) else ""
    role = state["role"] if isinstance(state.get("role"), str) and state["role"] else "assistant"
    if path.startswith("/v1/responses"):
        output_items = _build_responses_output_items(state)
        if not text and not output_items:
            return None
        payload: dict[str, Any] = {}
        if text:
            payload["output_text"] = text
        if output_items:
            payload["output"] = output_items
        return payload
    tool_calls = _build_chat_tool_calls(state)
    if not text and not tool_calls:
        return None
    message: dict[str, Any] = {
        "role": role,
        "content": text if text else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [
            {
                "message": message
            }
        ]
    }


def _canonical_response_payload(
    *,
    path: str,
    response_json: dict[str, Any],
) -> dict[str, Any] | None:
    assistant_message = _canonical_assistant_message_from_response_json(
        path=path,
        response_json=response_json,
    )
    if assistant_message is None:
        return None
    return {"assistant_message": assistant_message}


def _canonical_assistant_message_from_response_json(
    *,
    path: str,
    response_json: dict[str, Any],
) -> dict[str, Any] | None:
    if path.startswith("/v1/responses"):
        return _canonical_assistant_message_from_responses_output(response_json)
    return _canonical_assistant_message_from_chat_response(response_json)


def _canonical_assistant_message_from_chat_response(
    response_json: dict[str, Any],
) -> dict[str, Any] | None:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    role = _string_value(message.get("role")) or "assistant"
    content = _extract_text_fragment(message.get("content"))
    tool_calls = _normalize_chat_tool_calls(message.get("tool_calls"))
    if content is None and not tool_calls:
        return None
    canonical: dict[str, Any] = {"role": role}
    if content is not None:
        canonical["content"] = content
    if tool_calls:
        canonical["tool_calls"] = tool_calls
    return canonical


def _canonical_assistant_message_from_responses_output(
    response_json: dict[str, Any],
) -> dict[str, Any] | None:
    output_items = response_json.get("output")
    output_text = _extract_text_fragment(response_json.get("output_text"))
    tool_calls = _normalize_responses_tool_calls(output_items)
    if output_text is None:
        output_text = _extract_output_text_from_responses_items(output_items)
    if output_text is None and not tool_calls:
        return None
    canonical: dict[str, Any] = {"role": "assistant"}
    if output_text is not None:
        canonical["content"] = output_text
    if tool_calls:
        canonical["tool_calls"] = tool_calls
    return canonical


def _normalize_chat_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(tool_calls, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in tool_calls:
        if not isinstance(item, dict):
            continue
        function_payload = item.get("function")
        if not isinstance(function_payload, dict):
            continue
        normalized.append(
            {
                "id": _string_value(item.get("id")),
                "type": _string_value(item.get("type")) or "function",
                "function": {
                    "name": _string_value(function_payload.get("name")) or "",
                    "arguments": _extract_text_fragment(function_payload.get("arguments")) or "",
                },
            }
        )
    return normalized


def _normalize_responses_tool_calls(output_items: Any) -> list[dict[str, Any]]:
    if not isinstance(output_items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "function_call":
            continue
        normalized.append(
            {
                "id": _string_value(item.get("id")),
                "type": "function",
                "function": {
                    "name": _string_value(item.get("name")) or "",
                    "arguments": _extract_text_fragment(item.get("arguments")) or "",
                },
                "call_id": _string_value(item.get("call_id")),
            }
        )
    return normalized


def _extract_output_text_from_responses_items(output_items: Any) -> str | None:
    if not isinstance(output_items, list):
        return None
    parts: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        text = _extract_text_fragment(item.get("content"))
        if text:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    return None


def _update_chat_tool_calls(state: dict[str, Any], tool_calls: Any) -> None:
    if not isinstance(tool_calls, list):
        return
    state_tool_calls = state.setdefault("tool_calls", {})
    for raw_tool_call in tool_calls:
        if not isinstance(raw_tool_call, dict):
            continue
        index = raw_tool_call.get("index")
        if not isinstance(index, int):
            index = len(state_tool_calls)
        entry = state_tool_calls.setdefault(
            index,
            {
                "index": index,
                "id": None,
                "type": "function",
                "name_parts": [],
                "arguments_parts": [],
            },
        )
        tool_call_id = raw_tool_call.get("id")
        if isinstance(tool_call_id, str) and tool_call_id:
            entry["id"] = tool_call_id
        tool_call_type = raw_tool_call.get("type")
        if isinstance(tool_call_type, str) and tool_call_type:
            entry["type"] = tool_call_type
        function_payload = raw_tool_call.get("function")
        if not isinstance(function_payload, dict):
            continue
        function_name = function_payload.get("name")
        if isinstance(function_name, str) and function_name:
            entry["name_parts"].append(function_name)
        function_arguments = function_payload.get("arguments")
        if isinstance(function_arguments, str) and function_arguments:
            entry["arguments_parts"].append(function_arguments)


def _build_chat_tool_calls(state: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = state.get("tool_calls")
    if not isinstance(tool_calls, dict):
        return []
    normalized: list[dict[str, Any]] = []
    for index in sorted(tool_calls):
        entry = tool_calls[index]
        if not isinstance(entry, dict):
            continue
        name = "".join(part for part in entry.get("name_parts", []) if isinstance(part, str))
        arguments = "".join(
            part for part in entry.get("arguments_parts", []) if isinstance(part, str)
        )
        normalized.append(
            {
                "id": entry.get("id"),
                "type": entry.get("type") or "function",
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )
    return normalized


def _response_item_id(data: dict[str, Any]) -> str | None:
    for key in ("item_id", "output_item_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    output_index = data.get("output_index")
    if isinstance(output_index, int):
        return f"output_{output_index}"
    return None


def _ensure_response_output_item(
    state: dict[str, Any],
    *,
    item_id: str,
    item_type: str,
) -> dict[str, Any]:
    output_items = state.setdefault("response_output_items", {})
    entry = output_items.get(item_id)
    if not isinstance(entry, dict):
        entry = {
            "id": item_id,
            "type": item_type,
            "role": "assistant",
            "text_parts": [],
            "name": None,
            "arguments_parts": [],
            "call_id": None,
        }
        output_items[item_id] = entry
        state.setdefault("response_output_order", []).append(item_id)
    else:
        entry["type"] = item_type or entry.get("type") or "message"
    return entry


def _update_response_output_message(
    state: dict[str, Any],
    *,
    item_id: str | None,
    role: str,
    text: str | None,
) -> None:
    if item_id is None:
        item_id = "output_message_0"
    entry = _ensure_response_output_item(state, item_id=item_id, item_type="message")
    entry["role"] = role
    if text:
        entry["text_parts"].append(text)


def _update_response_function_call(
    state: dict[str, Any],
    *,
    item_id: str | None,
    name: str | None,
    arguments_delta: str | None,
    call_id: str | None,
) -> None:
    if item_id is None:
        item_id = "output_function_call_0"
    entry = _ensure_response_output_item(state, item_id=item_id, item_type="function_call")
    if name:
        entry["name"] = name
    if arguments_delta:
        entry["arguments_parts"].append(arguments_delta)
    if call_id:
        entry["call_id"] = call_id


def _merge_response_output_item(
    state: dict[str, Any],
    item: Any,
    *,
    fallback_id: str | None,
) -> None:
    if not isinstance(item, dict):
        return
    item_id = _string_value(item.get("id")) or fallback_id
    item_type = _string_value(item.get("type")) or "message"
    if item_id is None:
        item_id = f"output_{len(state.setdefault('response_output_order', []))}"
    entry = _ensure_response_output_item(state, item_id=item_id, item_type=item_type)
    if item_type == "message":
        role = _string_value(item.get("role")) or "assistant"
        text = _extract_text_fragment(item.get("content"))
        entry["role"] = role
        if text:
            entry["text_parts"].append(text)
    elif item_type == "function_call":
        name = _string_value(item.get("name"))
        arguments = _extract_text_fragment(item.get("arguments"))
        call_id = _string_value(item.get("call_id"))
        if name:
            entry["name"] = name
        if arguments:
            entry["arguments_parts"].append(arguments)
        if call_id:
            entry["call_id"] = call_id


def _merge_response_output_list(state: dict[str, Any], output_items: Any) -> None:
    if not isinstance(output_items, list):
        return
    for item in output_items:
        _merge_response_output_item(state, item, fallback_id=None)


def _build_responses_output_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    output_items = state.get("response_output_items")
    order = state.get("response_output_order")
    if not isinstance(output_items, dict) or not isinstance(order, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item_id in order:
        entry = output_items.get(item_id)
        if not isinstance(entry, dict):
            continue
        item_type = entry.get("type") or "message"
        if item_type == "message":
            text = "".join(part for part in entry.get("text_parts", []) if isinstance(part, str))
            if not text:
                continue
            normalized.append(
                {
                    "id": entry.get("id"),
                    "type": "message",
                    "role": entry.get("role") or "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            )
        elif item_type == "function_call":
            arguments = "".join(
                part for part in entry.get("arguments_parts", []) if isinstance(part, str)
            )
            normalized.append(
                {
                    "id": entry.get("id"),
                    "type": "function_call",
                    "name": entry.get("name"),
                    "arguments": arguments,
                    "call_id": entry.get("call_id"),
                }
            )
    return normalized


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _stream_summary_payload(
    *,
    path: str,
    status_code: int,
    content_type: str,
    total_bytes: int,
    chunk_count: int,
    preview: bytes,
    upstream_request_id: str | None = None,
    total_latency_ms: int | None = None,
    ttfb_ms: int | None = None,
    stream_duration_ms: int | None = None,
    response_json: dict[str, Any] | None = None,
    stream_complete: bool | None = None,
    client_disconnected: bool | None = None,
    stored_chunk_count: int | None = None,
    omitted_chunk_count: int | None = None,
    body_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": path,
        "status_code": status_code,
        "content_type": content_type,
        "body_size": total_bytes,
        "chunk_count": chunk_count,
        "streamed": True,
    }
    if upstream_request_id is not None:
        payload["upstream_request_id"] = upstream_request_id
    if total_latency_ms is not None:
        payload["total_latency_ms"] = total_latency_ms
    if ttfb_ms is not None:
        payload["ttfb_ms"] = ttfb_ms
    if stream_duration_ms is not None:
        payload["stream_duration_ms"] = stream_duration_ms
    if stream_complete is not None:
        payload["stream_complete"] = stream_complete
    if client_disconnected is not None:
        payload["client_disconnected"] = client_disconnected
    if stored_chunk_count is not None:
        payload["stored_chunk_count"] = stored_chunk_count
    if omitted_chunk_count is not None:
        payload["omitted_chunk_count"] = omitted_chunk_count
    if response_json is not None:
        payload["json"] = response_json
        canonical = _canonical_response_payload(path=path, response_json=response_json)
        if canonical is not None:
            payload["canonical"] = canonical
    if preview:
        payload["preview"] = preview.decode("utf-8", errors="replace")
    if total_bytes > len(preview):
        payload["capture_truncated"] = True
    if body_ref is not None:
        payload["body_ref"] = body_ref
    return payload


def _extract_upstream_request_id(response_headers: Any) -> str | None:
    for name in (
        "x-request-id",
        "request-id",
        "openai-request-id",
        "anthropic-request-id",
    ):
        value = response_headers.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _copy_response_headers(
    handler: BaseHTTPRequestHandler,
    *,
    response_headers: Any,
    session_id: str,
    run_id: str,
    request_id: str,
    streaming: bool,
    content_length: int | None = None,
) -> None:
    for key, value in response_headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP_HEADERS:
            continue
        if lower == "content-length":
            continue
        handler.send_header(key, value)
    if not streaming and content_length is not None:
        handler.send_header("Content-Length", str(content_length))
    handler.send_header("x-clawgraph-session-id", session_id)
    handler.send_header("x-clawgraph-run-id", run_id)
    handler.send_header("x-clawgraph-request-id", request_id)
    _set_identity_cookies(handler, session_id=session_id, run_id=run_id)


def _build_handler(config: ProxyConfig) -> type[BaseHTTPRequestHandler]:
    store = SQLiteFactStore(config.store_uri)
    payload_store = LocalPayloadStore(
        root_dir=config.payload_dir,
        store_uri=config.store_uri,
    )

    class ClawGraphProxyHandler(BaseHTTPRequestHandler):
        server_version = "ClawGraphProxy/0.1"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            request_path = urlsplit(self.path).path or self.path
            if request_path == "/health":
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._handle_proxy_request()

        def do_POST(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_PUT(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_PATCH(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def _handle_proxy_request(self) -> None:
            started_at = perf_counter()
            request_path = urlsplit(self.path).path or self.path
            if not self._authorize_request():
                return
            try:
                raw_body = self._read_body()
            except RequestBodyTooLargeError as exc:
                session_id = self._resolve_session_id(None)
                run_id = self._resolve_run_id(None, session_id)
                request_id = self._resolve_request_id(None)
                self._send_bytes(
                    status_code=int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
                    body=json.dumps({"error": str(exc)}).encode("utf-8"),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return
            except ValueError as exc:
                session_id = self._resolve_session_id(None)
                run_id = self._resolve_run_id(None, session_id)
                request_id = self._resolve_request_id(None)
                self._send_bytes(
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    body=json.dumps({"error": str(exc)}).encode("utf-8"),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return
            request_json = _safe_parse_json(raw_body)
            session_id = self._resolve_session_id(request_json)
            run_id = self._resolve_run_id(request_json, session_id)
            request_id = self._resolve_request_id(request_json)
            user_id = self._resolve_user_id(request_json)
            thread_id = self.headers.get("x-clawgraph-thread-id")
            task_id = self._resolve_task_id(request_json)
            request_content_type = self.headers.get(
                "Content-Type",
                "application/octet-stream",
            )
            if not self._enforce_session_owner(
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
                user_id=user_id,
            ):
                return

            if request_path == "/v1/semantic-events":
                if self.command != "POST":
                    self._send_bytes(
                        status_code=int(HTTPStatus.METHOD_NOT_ALLOWED),
                        body=json.dumps({"error": "semantic events require POST"}).encode("utf-8"),
                        content_type="application/json",
                        session_id=session_id,
                        run_id=run_id,
                        request_id=request_id,
                    )
                    return
                self._handle_semantic_event(
                    request_json=request_json,
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    task_id=task_id,
                )
                return

            upstream = _target_upstream(request_path, config)
            request_fact = new_fact_event(
                run_id=run_id,
                session_id=session_id,
                actor=_actor_for_path(request_path),
                kind="request_started",
                payload=_request_capture_payload(
                    method=self.command,
                    path=request_path,
                    request_target=self.path,
                    headers=self.headers,
                    content_type=request_content_type,
                    raw_body=raw_body,
                    request_json=request_json,
                    max_capture_bytes=config.max_capture_bytes,
                    body_ref=self._spill_payload_body(
                        session_id=session_id,
                        run_id=run_id,
                        request_id=request_id,
                        body_kind="request_body",
                        request_path=request_path,
                        content_type=request_content_type,
                        raw_body=raw_body,
                    ),
                ),
                request_id=request_id,
                user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                metadata={"capture_source": "proxy"},
            )
            store.append_fact(request_fact)

            if upstream is None:
                self._write_error(
                    status=HTTPStatus.NOT_FOUND,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=f"no upstream configured for path {self.path}",
                    error_code="upstream_not_configured",
                    started_at=started_at,
                    thread_id=thread_id,
                    task_id=task_id,
                )
                return

            target_url = _resolve_upstream_url(upstream, self.path)
            try:
                request = Request(
                    target_url,
                    data=raw_body or None,
                    headers=_forward_headers(
                        self.headers,
                        session_id=session_id,
                        run_id=run_id,
                        request_id=request_id,
                        user_id=user_id,
                        thread_id=thread_id,
                        task_id=task_id,
                    ),
                    method=self.command,
                )
                with urlopen(request, timeout=config.upstream_timeout_seconds) as response:
                    headers_received_at = perf_counter()
                    status_code = response.getcode()
                    content_type = response.headers.get(
                        "Content-Type",
                        "application/octet-stream",
                    )
                    should_stream = _is_streaming_request(request_json) or _is_streaming_content_type(
                        content_type
                    )
                    if should_stream:
                        self._forward_streaming_response(
                            response=response,
                            status_code=status_code,
                            content_type=content_type,
                            response_headers=response.headers,
                            session_id=session_id,
                            run_id=run_id,
                            request_id=request_id,
                            user_id=user_id,
                            thread_id=thread_id,
                            task_id=task_id,
                            request_fact_id=request_fact.fact_id,
                            actor=request_fact.actor,
                            started_at=started_at,
                            headers_received_at=headers_received_at,
                        )
                    else:
                        response_body = _read_bounded_response_body(
                            response,
                            max_bytes=config.max_response_body_bytes,
                        )
                        finished_at = perf_counter()
                        response_fact = new_fact_event(
                            run_id=run_id,
                            session_id=session_id,
                            actor=request_fact.actor,
                            kind="response_finished",
                            payload=_payload_from_response(
                                path=self.path,
                                status_code=status_code,
                                content_type=content_type,
                                response_body=response_body,
                                max_capture_bytes=config.max_capture_bytes,
                                body_ref=self._spill_payload_body(
                                    session_id=session_id,
                                    run_id=run_id,
                                    request_id=request_id,
                                    body_kind="response_body",
                                    request_path=self.path,
                                    content_type=content_type,
                                    raw_body=response_body,
                                ),
                                upstream_request_id=_extract_upstream_request_id(
                                    response.headers
                                ),
                                total_latency_ms=round((finished_at - started_at) * 1000),
                                ttfb_ms=round((headers_received_at - started_at) * 1000),
                            ),
                            request_id=request_id,
                            user_id=user_id,
                            thread_id=thread_id,
                            task_id=task_id,
                            parent_ref=request_fact.fact_id,
                        )
                        store.append_fact(response_fact)
                        self._send_bytes(
                            status_code=status_code,
                            body=response_body,
                            content_type=content_type,
                            session_id=session_id,
                            run_id=run_id,
                            request_id=request_id,
                            response_headers=response.headers,
                        )
            except HTTPError as exc:
                try:
                    body = _read_bounded_response_body(
                        exc,
                        max_bytes=config.max_response_body_bytes,
                    )
                except ResponseBodyTooLargeError:
                    body = None
                self._write_error(
                    status=exc.code,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=f"upstream returned HTTP {exc.code}",
                    error_code="upstream_http_error",
                    response_body=body,
                    content_type=exc.headers.get("Content-Type", "application/json"),
                    started_at=started_at,
                    headers_received_at=perf_counter(),
                    upstream_request_id=_extract_upstream_request_id(exc.headers),
                    thread_id=thread_id,
                    task_id=task_id,
                )
            except ResponseBodyTooLargeError as exc:
                self._write_error(
                    status=HTTPStatus.BAD_GATEWAY,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=str(exc),
                    error_code="upstream_response_too_large",
                    started_at=started_at,
                    thread_id=thread_id,
                    task_id=task_id,
                )
            except ValueError as exc:
                self._write_error(
                    status=HTTPStatus.BAD_GATEWAY,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=str(exc),
                    error_code="upstream_invalid_response",
                    started_at=started_at,
                    thread_id=thread_id,
                    task_id=task_id,
                )
            except URLError as exc:
                reason = exc.reason
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    self._write_error(
                        status=HTTPStatus.GATEWAY_TIMEOUT,
                        session_id=session_id,
                        run_id=run_id,
                        request_fact_id=request_fact.fact_id,
                        request_id=request_id,
                        user_id=user_id,
                        message=f"upstream request timed out: {reason}",
                        error_code="upstream_timeout",
                        started_at=started_at,
                        thread_id=thread_id,
                        task_id=task_id,
                    )
                    return
                self._write_error(
                    status=HTTPStatus.BAD_GATEWAY,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=f"upstream request failed: {exc.reason}",
                    error_code="upstream_transport_error",
                    started_at=started_at,
                    thread_id=thread_id,
                    task_id=task_id,
                )
            except TimeoutError as exc:
                self._write_error(
                    status=HTTPStatus.GATEWAY_TIMEOUT,
                    session_id=session_id,
                    run_id=run_id,
                    request_fact_id=request_fact.fact_id,
                    request_id=request_id,
                    user_id=user_id,
                    message=f"upstream request timed out: {exc}",
                    error_code="upstream_timeout",
                    started_at=started_at,
                    thread_id=thread_id,
                    task_id=task_id,
                )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _authorize_request(self) -> bool:
            if _request_is_authorized(self.headers, auth_token=config.auth_token):
                return True
            session_id = self._resolve_session_id(None)
            run_id = self._resolve_run_id(None, session_id)
            request_id = self._resolve_request_id(None)
            self._send_bytes(
                status_code=int(HTTPStatus.UNAUTHORIZED),
                body=json.dumps({"error": "proxy authentication failed"}).encode("utf-8"),
                content_type="application/json",
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
            )
            return False

        def _spill_payload_body(
            self,
            *,
            session_id: str,
            run_id: str,
            request_id: str,
            body_kind: str,
            request_path: str,
            content_type: str,
            raw_body: bytes,
        ) -> dict[str, Any] | None:
            if not raw_body or len(raw_body) <= config.max_capture_bytes:
                return None
            try:
                return payload_store.write_bytes(
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                    body_kind=body_kind,
                    request_path=request_path,
                    content_type=content_type,
                    body=raw_body,
                )
            except OSError:
                return None

        def _start_payload_writer(
            self,
            *,
            session_id: str,
            run_id: str,
            request_id: str,
            body_kind: str,
            request_path: str,
            content_type: str,
        ) -> Any:
            try:
                return payload_store.start_writer(
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                    body_kind=body_kind,
                    request_path=request_path,
                    content_type=content_type,
                )
            except OSError:
                return None

        def _enforce_session_owner(
            self,
            *,
            session_id: str,
            run_id: str,
            request_id: str,
            user_id: str | None,
        ) -> bool:
            if not config.enforce_session_user_binding:
                return True
            owner_key = _owner_key(user_id)
            existing_owner = store.get_session_owner(session_id)
            if owner_key is None:
                if existing_owner is None:
                    return True
                self._send_bytes(
                    status_code=int(HTTPStatus.CONFLICT),
                    body=json.dumps(
                        {
                            "error": "session requires the bound user identity",
                            "error_code": "session_owner_required",
                        }
                    ).encode("utf-8"),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return False
            if existing_owner == owner_key:
                return True
            conflicting_owner = store.claim_session_owner(
                session_id=session_id,
                owner_key=owner_key,
            )
            if conflicting_owner is None:
                return True
            self._send_bytes(
                status_code=int(HTTPStatus.CONFLICT),
                body=json.dumps(
                    {
                        "error": "session is already bound to a different user",
                        "error_code": "session_owner_mismatch",
                    }
                ).encode("utf-8"),
                content_type="application/json",
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
            )
            return False

        def _read_body(self) -> bytes:
            raw_content_length = self.headers.get("Content-Length", "0")
            try:
                content_length = int(raw_content_length)
            except ValueError as exc:
                raise ValueError("invalid Content-Length header") from exc
            if content_length < 0:
                raise ValueError("invalid Content-Length header")
            if content_length > config.max_request_body_bytes:
                raise RequestBodyTooLargeError(
                    f"request body exceeds {config.max_request_body_bytes} bytes"
                )
            return self.rfile.read(content_length)

        def _resolve_session_id(self, request_json: dict[str, Any] | list[Any] | None) -> str:
            header_session = self.headers.get("x-clawgraph-session-id")
            if header_session:
                return header_session

            cookie_session = _cookie_value(self.headers, _SESSION_COOKIE_NAME)
            if cookie_session:
                return cookie_session

            if isinstance(request_json, dict):
                for key in ("session_id", "conversation_id", "thread_id"):
                    value = request_json.get(key)
                    if isinstance(value, str) and value:
                        return value

            return f"sess_{uuid4().hex}"

        def _resolve_run_id(self, request_json: dict[str, Any] | list[Any] | None, session_id: str) -> str:
            del session_id
            header_run = self.headers.get("x-clawgraph-run-id")
            if header_run:
                return header_run
            if _header_truthy(self.headers, _RUN_ROTATION_HEADER):
                return f"run_{uuid4().hex}"
            cookie_run = _cookie_value(self.headers, _RUN_COOKIE_NAME)
            if cookie_run:
                return cookie_run
            if isinstance(request_json, dict):
                value = request_json.get("run_id")
                if isinstance(value, str) and value:
                    return value
            return f"run_{uuid4().hex}"

        def _resolve_request_id(self, request_json: dict[str, Any] | list[Any] | None) -> str:
            header_request = self.headers.get("x-clawgraph-request-id")
            if header_request:
                return header_request
            if isinstance(request_json, dict):
                value = request_json.get("request_id")
                if isinstance(value, str) and value:
                    return value
            return f"req_{uuid4().hex}"

        def _resolve_user_id(self, request_json: dict[str, Any] | list[Any] | None) -> str | None:
            header_user = self.headers.get("x-clawgraph-user-id")
            if header_user:
                return header_user
            if isinstance(request_json, dict):
                value = request_json.get("user_id")
                if isinstance(value, str) and value:
                    return value
            return None

        def _resolve_task_id(self, request_json: dict[str, Any] | list[Any] | None) -> str | None:
            header_task = self.headers.get("x-clawgraph-task-id")
            if header_task:
                return header_task
            if isinstance(request_json, dict):
                value = request_json.get("task_id")
                if isinstance(value, str) and value:
                    return value
            return None

        def _handle_semantic_event(
            self,
            *,
            request_json: dict[str, Any] | list[Any] | None,
            session_id: str,
            run_id: str,
            request_id: str,
            user_id: str | None,
            thread_id: str | None,
            task_id: str | None,
        ) -> None:
            if not isinstance(request_json, dict):
                self._send_bytes(
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    body=json.dumps({"error": "semantic request body must be a JSON object"}).encode(
                        "utf-8"
                    ),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return

            semantic_kind = request_json.get("kind")
            semantic_payload = request_json.get("payload", {})
            fact_ref = request_json.get("fact_ref")
            if not isinstance(semantic_kind, str) or not semantic_kind:
                self._send_bytes(
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    body=json.dumps({"error": "semantic kind is required"}).encode("utf-8"),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return
            if not isinstance(semantic_payload, dict):
                self._send_bytes(
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    body=json.dumps({"error": "semantic payload must be a JSON object"}).encode(
                        "utf-8"
                    ),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return
            semantic_error = self._validate_semantic_targets(
                session_id=session_id,
                run_id=run_id,
                semantic_payload=semantic_payload,
                fact_ref=fact_ref if isinstance(fact_ref, str) else None,
            )
            if semantic_error is not None:
                self._send_bytes(
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    body=json.dumps({"error": semantic_error}).encode("utf-8"),
                    content_type="application/json",
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                return

            semantic_fact = new_semantic_event_fact(
                run_id=run_id,
                session_id=session_id,
                semantic_kind=semantic_kind,
                fact_ref=fact_ref if isinstance(fact_ref, str) else None,
                payload=semantic_payload,
                request_id=request_id,
                user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                branch_id=request_json.get("branch_id")
                if isinstance(request_json.get("branch_id"), str)
                else None,
                metadata={"capture_source": "semantic_ingress"},
            )
            store.append_fact(semantic_fact)
            body = json.dumps(
                {
                    "ok": True,
                    "fact_id": semantic_fact.fact_id,
                    "semantic_kind": semantic_kind,
                    "session_id": session_id,
                }
            ).encode("utf-8")
            self._send_bytes(
                status_code=int(HTTPStatus.ACCEPTED),
                body=body,
                content_type="application/json",
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
            )

        def _validate_semantic_targets(
            self,
            *,
            session_id: str,
            run_id: str,
            semantic_payload: dict[str, Any],
            fact_ref: str | None,
        ) -> str | None:
            if fact_ref is not None:
                target_fact = store.get_fact(fact_ref)
                if target_fact is None:
                    return f"fact_ref not found: {fact_ref}"
                if target_fact.session_id != session_id or target_fact.run_id != run_id:
                    return f"fact_ref {fact_ref} is outside the current session/run scope"

            for key in ("request_fact_id", "parent_request_fact_id"):
                value = semantic_payload.get(key)
                if not isinstance(value, str) or not value:
                    continue
                target_fact = store.get_fact(value)
                if target_fact is None:
                    return f"{key} not found: {value}"
                if target_fact.session_id != session_id or target_fact.run_id != run_id:
                    return f"{key} {value} is outside the current session/run scope"
                if target_fact.kind != "request_started":
                    return f"{key} must point to a request_started fact"

            target_request_id = semantic_payload.get("request_id")
            if isinstance(target_request_id, str) and target_request_id:
                request_fact = store.get_request_fact(
                    session_id=session_id,
                    run_id=run_id,
                    request_id=target_request_id,
                )
                if request_fact is None:
                    return f"target request_id not found in session/run scope: {target_request_id}"
            return None

        def _write_error(
            self,
            *,
            status: int,
            session_id: str,
            run_id: str,
            request_fact_id: str,
            request_id: str,
            user_id: str | None,
            message: str,
            error_code: str,
            started_at: float,
            thread_id: str | None = None,
            task_id: str | None = None,
            response_body: bytes | None = None,
            content_type: str = "application/json",
            headers_received_at: float | None = None,
            upstream_request_id: str | None = None,
        ) -> None:
            body_bytes: bytes
            if response_body is None:
                body_bytes = json.dumps({"error": message}).encode("utf-8")
            else:
                body_bytes = response_body

            parsed_body = _safe_parse_json(body_bytes)
            payload: dict[str, Any] = {
                "path": self.path,
                "status_code": int(status),
                "error": message,
                "error_code": error_code,
                "content_type": content_type,
                "body_size": len(body_bytes),
                "total_latency_ms": round((perf_counter() - started_at) * 1000),
            }
            if headers_received_at is not None:
                payload["ttfb_ms"] = round((headers_received_at - started_at) * 1000)
            if upstream_request_id is not None:
                payload["upstream_request_id"] = upstream_request_id
            if parsed_body is not None and len(body_bytes) <= config.max_capture_bytes:
                payload["json"] = parsed_body
            elif body_bytes:
                _capture_payload_body(
                    payload=payload,
                    raw_body=body_bytes,
                    path=self.path,
                    max_capture_bytes=config.max_capture_bytes,
                    body_ref=self._spill_payload_body(
                        session_id=session_id,
                        run_id=run_id,
                        request_id=request_id,
                        body_kind="error_body",
                        request_path=self.path,
                        content_type=content_type,
                        raw_body=body_bytes,
                    ),
                )

            error_fact = new_fact_event(
                run_id=run_id,
                session_id=session_id,
                actor="proxy",
                kind="error_raised",
                payload=payload,
                request_id=request_id,
                user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                parent_ref=request_fact_id,
            )
            store.append_fact(error_fact)

            self._send_bytes(
                status_code=int(status),
                body=body_bytes,
                content_type=content_type,
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
            )

        def _forward_streaming_response(
            self,
            *,
            response: Any,
            status_code: int,
            content_type: str,
            response_headers: Any,
            session_id: str,
            run_id: str,
            request_id: str,
            user_id: str | None,
            thread_id: str | None,
            task_id: str | None,
            request_fact_id: str,
            actor: str,
            started_at: float,
            headers_received_at: float,
        ) -> None:
            upstream_request_id = _extract_upstream_request_id(response_headers)
            self.send_response(status_code)
            _copy_response_headers(
                self,
                response_headers=response_headers,
                session_id=session_id,
                run_id=run_id,
                request_id=request_id,
                streaming=True,
            )
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            total_bytes = 0
            chunk_count = 0
            preview = bytearray()
            first_chunk_at: float | None = None
            pending_sse = bytearray()
            stream_state = _new_stream_state()
            stream_complete = False
            client_disconnected = False
            chunk_facts = []
            payload_writer = None

            while True:
                chunk = response.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break

                now = perf_counter()
                if first_chunk_at is None:
                    first_chunk_at = now
                chunk_count += 1
                total_bytes += len(chunk)
                preview_before_len = len(preview)
                if len(preview) < config.max_capture_bytes:
                    preview.extend(chunk[: config.max_capture_bytes - len(preview)])
                if payload_writer is not None:
                    try:
                        payload_writer.write(chunk)
                    except OSError:
                        payload_writer.discard()
                        payload_writer = None
                elif total_bytes > config.max_capture_bytes:
                    payload_writer = self._start_payload_writer(
                        session_id=session_id,
                        run_id=run_id,
                        request_id=request_id,
                        body_kind="response_stream",
                        request_path=self.path,
                        content_type=content_type,
                    )
                    if payload_writer is not None:
                        try:
                            payload_writer.write(bytes(preview))
                            captured_from_chunk = max(0, len(preview) - preview_before_len)
                            if captured_from_chunk < len(chunk):
                                payload_writer.write(chunk[captured_from_chunk:])
                        except OSError:
                            payload_writer.discard()
                            payload_writer = None

                fragments = _extract_complete_sse_fragments(
                    pending=pending_sse,
                    chunk=chunk,
                )
                _update_stream_state(stream_state, fragments)
                if any(fragment.get("type") == "done" for fragment in fragments):
                    stream_complete = True

                if chunk_count <= config.max_stream_chunk_facts:
                    chunk_fact = new_fact_event(
                        run_id=run_id,
                        session_id=session_id,
                        actor=actor,
                        kind="response_chunk",
                        payload={
                            "path": self.path,
                            "chunk_index": chunk_count,
                            "chunk_size": len(chunk),
                            "content_type": content_type,
                            "elapsed_ms": round((now - started_at) * 1000),
                            "fragments": _sanitize_stream_fragments(
                                fragments,
                                max_capture_bytes=config.max_capture_bytes,
                            ),
                        },
                        request_id=request_id,
                        user_id=user_id,
                        thread_id=thread_id,
                        task_id=task_id,
                        parent_ref=request_fact_id,
                    )
                    chunk_facts.append(chunk_fact)

                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    client_disconnected = True
                    break

            finished_at = perf_counter()
            ttfb_start = first_chunk_at or headers_received_at
            if pending_sse:
                final_fragments = _extract_sse_fragments(bytes(pending_sse))
                _update_stream_state(stream_state, final_fragments)
                if any(fragment.get("type") == "done" for fragment in final_fragments):
                    stream_complete = True
            body_ref = None
            if payload_writer is not None:
                try:
                    if total_bytes > config.max_capture_bytes:
                        body_ref = payload_writer.commit()
                    else:
                        payload_writer.discard()
                except OSError:
                    payload_writer.discard()
            response_fact = new_fact_event(
                run_id=run_id,
                session_id=session_id,
                actor=actor,
                kind="response_finished",
                payload=_stream_summary_payload(
                    path=self.path,
                    status_code=status_code,
                    content_type=content_type,
                    total_bytes=total_bytes,
                    chunk_count=chunk_count,
                    preview=bytes(preview),
                    upstream_request_id=upstream_request_id,
                    total_latency_ms=round((finished_at - started_at) * 1000),
                    ttfb_ms=round((ttfb_start - started_at) * 1000),
                    stream_duration_ms=round((finished_at - ttfb_start) * 1000),
                    response_json=_build_stream_response_json(self.path, stream_state),
                    stream_complete=stream_complete,
                    client_disconnected=client_disconnected,
                    stored_chunk_count=len(chunk_facts),
                    omitted_chunk_count=max(0, chunk_count - len(chunk_facts)),
                    body_ref=body_ref,
                ),
                request_id=request_id,
                user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                parent_ref=request_fact_id,
            )
            store.append_facts([*chunk_facts, response_fact])

        def _send_bytes(
            self,
            *,
            status_code: int,
            body: bytes,
            content_type: str,
            session_id: str,
            run_id: str,
            request_id: str,
            response_headers: Any | None = None,
        ) -> None:
            self.send_response(status_code)
            if response_headers is None:
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("x-clawgraph-session-id", session_id)
                self.send_header("x-clawgraph-run-id", run_id)
                self.send_header("x-clawgraph-request-id", request_id)
                _set_identity_cookies(self, session_id=session_id, run_id=run_id)
            else:
                _copy_response_headers(
                    self,
                    response_headers=response_headers,
                    session_id=session_id,
                    run_id=run_id,
                    request_id=request_id,
                    streaming=False,
                    content_length=len(body),
                )
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.close_connection = True

    return ClawGraphProxyHandler


def run_proxy_server(config: ProxyConfig) -> None:
    """Run the minimal ClawGraph proxy server."""

    server = ThreadingHTTPServer((config.host, config.port), _build_handler(config))
    print(
        "ClawGraph proxy listening on "
        f"http://{config.host}:{config.port} "
        f"(store={config.store_uri})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
