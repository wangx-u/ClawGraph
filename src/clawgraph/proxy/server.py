"""Minimal HTTP proxy server for ClawGraph."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from clawgraph.protocol.factories import new_fact_event, new_semantic_event_fact
from clawgraph.store import SQLiteFactStore

_HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
}
_STREAM_CHUNK_SIZE = 4096


@dataclass(slots=True)
class ProxyConfig:
    """Configuration for the minimal proxy server."""

    host: str
    port: int
    store_uri: str
    model_upstream: str | None = None
    tool_upstream: str | None = None
    upstream_timeout_seconds: float = 30.0


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
        }:
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def _forward_headers(
    headers: Any,
    *,
    session_id: str,
    request_id: str,
    user_id: str | None,
) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP_HEADERS:
            continue
        forwarded[key] = value
    forwarded.setdefault("x-clawgraph-session-id", session_id)
    forwarded.setdefault("x-clawgraph-request-id", request_id)
    if user_id:
        forwarded.setdefault("x-clawgraph-user-id", user_id)
    return forwarded


def _resolve_upstream_url(upstream: str, path: str) -> str:
    parsed = urlsplit(upstream)
    if parsed.path in {"", "/"}:
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    if parsed.path == path:
        return upstream
    if path.startswith("/v1/") and parsed.path.startswith("/v1/"):
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    if path.startswith("/tools") and parsed.path.startswith("/tools"):
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    return upstream


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
    upstream_request_id: str | None = None,
    total_latency_ms: int | None = None,
    ttfb_ms: int | None = None,
    stream_duration_ms: int | None = None,
) -> dict[str, Any]:
    parsed = _safe_parse_json(response_body)
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
    if parsed is not None:
        payload["json"] = parsed
        canonical = _canonical_response_payload(path=path, response_json=parsed)
        if canonical is not None:
            payload["canonical"] = canonical
    elif response_body:
        payload["text"] = response_body.decode("utf-8", errors="replace")
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
    if response_json is not None:
        payload["json"] = response_json
        canonical = _canonical_response_payload(path=path, response_json=response_json)
        if canonical is not None:
            payload["canonical"] = canonical
    if preview:
        payload["preview"] = preview.decode("utf-8", errors="replace")
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
    handler.send_header("x-clawgraph-request-id", request_id)


def _build_handler(config: ProxyConfig) -> type[BaseHTTPRequestHandler]:
    store = SQLiteFactStore(config.store_uri)

    class ClawGraphProxyHandler(BaseHTTPRequestHandler):
        server_version = "ClawGraphProxy/0.1"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")

        def do_POST(self) -> None:  # noqa: N802
            started_at = perf_counter()
            raw_body = self._read_body()
            request_json = _safe_parse_json(raw_body)
            session_id = self._resolve_session_id(request_json)
            run_id = self._resolve_run_id(request_json, session_id)
            request_id = self._resolve_request_id(request_json)
            user_id = self._resolve_user_id(request_json)
            thread_id = self.headers.get("x-clawgraph-thread-id")
            task_id = self.headers.get("x-clawgraph-task-id")

            if self.path == "/v1/semantic-events":
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

            upstream = _target_upstream(self.path, config)
            request_fact = new_fact_event(
                run_id=run_id,
                session_id=session_id,
                actor=_actor_for_path(self.path),
                kind="request_started",
                payload={
                    "method": "POST",
                    "path": self.path,
                    "headers": _sanitize_headers(self.headers),
                    "json": request_json,
                    "body_size": len(raw_body),
                },
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
                    data=raw_body,
                    headers=_forward_headers(
                        self.headers,
                        session_id=session_id,
                        request_id=request_id,
                        user_id=user_id,
                    ),
                    method="POST",
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
                        response_body = response.read()
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
                            request_id=request_id,
                            response_headers=response.headers,
                        )
            except HTTPError as exc:
                body = exc.read()
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

        def _read_body(self) -> bytes:
            content_length = int(self.headers.get("Content-Length", "0"))
            return self.rfile.read(content_length)

        def _resolve_session_id(self, request_json: dict[str, Any] | list[Any] | None) -> str:
            header_session = self.headers.get("x-clawgraph-session-id")
            if header_session:
                return header_session

            if isinstance(request_json, dict):
                value = request_json.get("session_id")
                if isinstance(value, str) and value:
                    return value

            return f"sess_{uuid4().hex}"

        def _resolve_run_id(self, request_json: dict[str, Any] | list[Any] | None, session_id: str) -> str:
            header_run = self.headers.get("x-clawgraph-run-id")
            if header_run:
                return header_run
            if isinstance(request_json, dict):
                value = request_json.get("run_id")
                if isinstance(value, str) and value:
                    return value
            return session_id

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
                request_id=request_id,
            )

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
            if parsed_body is not None:
                payload["json"] = parsed_body
            elif body_bytes:
                payload["text"] = body_bytes.decode("utf-8", errors="replace")

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

            while True:
                chunk = response.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break

                now = perf_counter()
                if first_chunk_at is None:
                    first_chunk_at = now
                chunk_count += 1
                total_bytes += len(chunk)
                if len(preview) < _STREAM_CHUNK_SIZE:
                    preview.extend(chunk[: _STREAM_CHUNK_SIZE - len(preview)])

                fragments = _extract_complete_sse_fragments(
                    pending=pending_sse,
                    chunk=chunk,
                )
                _update_stream_state(stream_state, fragments)
                if any(fragment.get("type") == "done" for fragment in fragments):
                    stream_complete = True

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
                        "fragments": fragments,
                    },
                    request_id=request_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    parent_ref=request_fact_id,
                )
                store.append_fact(chunk_fact)

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
                ),
                request_id=request_id,
                user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                parent_ref=request_fact_id,
            )
            store.append_fact(response_fact)

        def _send_bytes(
            self,
            *,
            status_code: int,
            body: bytes,
            content_type: str,
            session_id: str,
            request_id: str,
            response_headers: Any | None = None,
        ) -> None:
            self.send_response(status_code)
            if response_headers is None:
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("x-clawgraph-session-id", session_id)
                self.send_header("x-clawgraph-request-id", request_id)
            else:
                _copy_response_headers(
                    self,
                    response_headers=response_headers,
                    session_id=session_id,
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
