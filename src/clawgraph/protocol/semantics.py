"""Shared normalization helpers for compact training semantics."""

from __future__ import annotations

import json
from typing import Any

_REQUEST_FINGERPRINT_EXCLUDED_KEYS = {
    "stream",
    "request_id",
    "session_id",
    "run_id",
    "conversation_id",
    "thread_id",
    "task_id",
    "user_id",
}


def extract_prompt_messages(request_json: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Normalize request-side prompt messages from chat or responses payloads."""

    messages = request_json.get("messages")
    if isinstance(messages, list):
        normalized = _normalize_messages(messages)
        return normalized if normalized else None

    input_value = request_json.get("input")
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if isinstance(input_value, dict):
        normalized = _normalize_messages([input_value])
        return normalized if normalized else None
    if isinstance(input_value, list):
        normalized = _normalize_messages(input_value)
        return normalized if normalized else None
    return None


def normalize_request_json(request_json: dict[str, Any]) -> dict[str, Any]:
    """Remove volatile request identifiers before computing a retry signature."""

    filtered: dict[str, Any] = {}
    for key, value in request_json.items():
        if key in _REQUEST_FINGERPRINT_EXCLUDED_KEYS:
            continue
        filtered[key] = value
    return filtered


def request_payload_fingerprint(request_json: dict[str, Any]) -> str | None:
    """Return a stable retry fingerprint for one normalized request payload."""

    normalized = normalize_request_json(request_json)
    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=True, sort_keys=True)


def _normalize_messages(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        normalized.extend(_normalize_input_item(item))
    return normalized


def _normalize_input_item(item: Any) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []

    role = _string_value(item.get("role"))
    if role is not None:
        return _normalize_role_message_item(item, role=role)

    item_type = _string_value(item.get("type"))
    if item_type == "message":
        role = _string_value(item.get("role")) or "user"
        return _normalize_role_message_item(item, role=role)
    if item_type == "function_call":
        normalized_tool_call = _normalize_function_call_item(item)
        if normalized_tool_call is None:
            return []
        return [{"role": "assistant", "tool_calls": [normalized_tool_call]}]
    if item_type in {"function_call_output", "tool_result"}:
        normalized_tool_result = _normalize_tool_result_item(item)
        return [normalized_tool_result] if normalized_tool_result is not None else []
    return []


def _normalize_role_message_item(
    item: dict[str, Any],
    *,
    role: str,
) -> list[dict[str, Any]]:
    content = _normalize_content(item.get("content") or item.get("output"))
    tool_calls = _normalize_tool_calls(item.get("tool_calls"))
    if role == "assistant":
        function_tool_call = _normalize_function_call_item(item)
        if function_tool_call is not None and not tool_calls:
            tool_calls = [function_tool_call]

    if content is None and not tool_calls:
        return []

    message: dict[str, Any] = {"role": role}
    if content is not None:
        message["content"] = content
    if tool_calls:
        message["tool_calls"] = tool_calls
    if role == "tool":
        tool_call_id = _string_value(item.get("tool_call_id") or item.get("call_id"))
        if tool_call_id is not None:
            message["tool_call_id"] = tool_call_id
        name = _string_value(item.get("name"))
        if name is not None:
            message["name"] = name
    return [message]


def _normalize_function_call_item(item: dict[str, Any]) -> dict[str, Any] | None:
    function_name = _string_value(item.get("name"))
    arguments = _normalize_content(item.get("arguments"))
    tool_call_id = _string_value(item.get("id"))
    call_id = _string_value(item.get("call_id"))
    if function_name is None and arguments is None and tool_call_id is None and call_id is None:
        return None
    return {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": function_name or "",
            "arguments": arguments or "",
        },
        **({"call_id": call_id} if call_id is not None else {}),
    }


def _normalize_tool_result_item(item: dict[str, Any]) -> dict[str, Any] | None:
    content = _normalize_content(item.get("output") or item.get("content"))
    tool_call_id = _string_value(item.get("tool_call_id") or item.get("call_id"))
    name = _string_value(item.get("name"))
    if content is None and tool_call_id is None and name is None:
        return None
    message: dict[str, Any] = {
        "role": "tool",
        "content": content or "",
    }
    if tool_call_id is not None:
        message["tool_call_id"] = tool_call_id
    if name is not None:
        message["name"] = name
    return message


def _normalize_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        normalized.append(
            {
                "id": _string_value(item.get("id")),
                "type": _string_value(item.get("type")) or "function",
                "function": {
                    "name": _string_value(function.get("name")) or "",
                    "arguments": _normalize_content(function.get("arguments")) or "",
                },
                **(
                    {"call_id": _string_value(item.get("call_id"))}
                    if _string_value(item.get("call_id")) is not None
                    else {}
                ),
            }
        )
    return normalized


def _normalize_content(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "content", "value", "output"):
            nested = _normalize_content(value.get(key))
            if nested is not None:
                return nested
        if value:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        return None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = None
            if isinstance(item, dict):
                text = _normalize_content(
                    item.get("text")
                    or item.get("content")
                    or item.get("value")
                    or item.get("output")
                )
            elif isinstance(item, str):
                text = item
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
        if value:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
