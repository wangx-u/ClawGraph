"""Minimal HTTP proxy server for ClawGraph."""

from __future__ import annotations

import json
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
                with urlopen(request) as response:
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
                        "fragments": _extract_sse_fragments(chunk),
                    },
                    request_id=request_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    parent_ref=request_fact_id,
                )
                store.append_fact(chunk_fact)

                self.wfile.write(chunk)
                self.wfile.flush()

            finished_at = perf_counter()
            ttfb_start = first_chunk_at or headers_received_at
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
            self.wfile.write(body)

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
