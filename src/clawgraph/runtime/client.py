"""Runtime-side helpers for ClawGraph proxy and semantic ingress."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


def _normalize_base_url(base_url: str) -> str:
    if not base_url.endswith("/"):
        return f"{base_url}/"
    return base_url


def _normalize_path(path: str) -> str:
    if path.startswith("/"):
        return path
    return f"/{path}"


@dataclass(slots=True)
class ClawGraphSession:
    """Mutable session context reused across runtime requests."""

    session_id: str | None = None
    run_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    task_id: str | None = None

    def ensure_identity(self) -> tuple[str, str]:
        if not self.session_id:
            self.session_id = f"sess_{uuid4().hex}"
        if not self.run_id:
            self.run_id = self.session_id
        return self.session_id, self.run_id

    def make_request_id(self) -> str:
        return f"req_{uuid4().hex}"

    def absorb_explicit_headers(self, headers: dict[str, str] | None) -> None:
        if not headers:
            return

        previous_session_id = self.session_id
        explicit_session_id = headers.get("x-clawgraph-session-id")
        explicit_run_id = headers.get("x-clawgraph-run-id")
        explicit_user_id = headers.get("x-clawgraph-user-id")
        explicit_thread_id = headers.get("x-clawgraph-thread-id")
        explicit_task_id = headers.get("x-clawgraph-task-id")

        if explicit_session_id:
            self.session_id = explicit_session_id
            if explicit_run_id is None and (
                self.run_id is None or self.run_id == previous_session_id
            ):
                self.run_id = explicit_session_id
        if explicit_run_id:
            self.run_id = explicit_run_id
        if explicit_user_id:
            self.user_id = explicit_user_id
        if explicit_thread_id:
            self.thread_id = explicit_thread_id
        if explicit_task_id:
            self.task_id = explicit_task_id

    def request_headers(
        self,
        *,
        request_id: str | None = None,
        parent_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        self.absorb_explicit_headers(extra_headers)
        headers: dict[str, str] = {}
        session_id, run_id = self.ensure_identity()
        headers["x-clawgraph-session-id"] = session_id
        headers["x-clawgraph-run-id"] = run_id
        if request_id:
            headers["x-clawgraph-request-id"] = request_id
        if self.user_id:
            headers["x-clawgraph-user-id"] = self.user_id
        if self.thread_id:
            headers["x-clawgraph-thread-id"] = self.thread_id
        if self.task_id:
            headers["x-clawgraph-task-id"] = self.task_id
        if parent_id:
            headers["x-clawgraph-parent-id"] = parent_id
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def absorb_response_headers(self, headers: Any) -> None:
        session_id = headers.get("x-clawgraph-session-id")
        run_id = headers.get("x-clawgraph-run-id")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
        if isinstance(run_id, str) and run_id:
            self.run_id = run_id


@dataclass(slots=True)
class ClawGraphRuntimeResponse:
    """Minimal HTTP response wrapper for runtime calls."""

    status_code: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any] | list[Any] | None:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class ClawGraphRuntimeClient:
    """Small helper that makes ClawGraph proxy adoption low-friction."""

    def __init__(
        self,
        *,
        base_url: str,
        session: ClawGraphSession | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.session = session or ClawGraphSession()
        self.timeout_seconds = timeout_seconds
        self._cookie_jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        parent_id: str | None = None,
    ) -> ClawGraphRuntimeResponse:
        request_id_value = request_id or self.session.make_request_id()
        merged_headers = {
            "Content-Type": "application/json",
            **self.session.request_headers(
                request_id=request_id_value,
                parent_id=parent_id,
                extra_headers=headers,
            ),
        }
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = Request(
            urljoin(self.base_url, _normalize_path(path).lstrip("/")),
            data=body,
            headers=merged_headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
                self.session.absorb_response_headers(response.headers)
                return ClawGraphRuntimeResponse(
                    status_code=response.getcode(),
                    headers=dict(response.headers.items()),
                    body=response_body,
                )
        except HTTPError as exc:
            response_body = exc.read()
            self.session.absorb_response_headers(exc.headers)
            return ClawGraphRuntimeResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                body=response_body,
            )

    def chat_completions(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        parent_id: str | None = None,
    ) -> ClawGraphRuntimeResponse:
        return self.post_json(
            "/v1/chat/completions",
            payload,
            headers=headers,
            request_id=request_id,
            parent_id=parent_id,
        )

    def responses(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        parent_id: str | None = None,
    ) -> ClawGraphRuntimeResponse:
        return self.post_json(
            "/v1/responses",
            payload,
            headers=headers,
            request_id=request_id,
            parent_id=parent_id,
        )

    def tool(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        parent_id: str | None = None,
    ) -> ClawGraphRuntimeResponse:
        return self.post_json(
            path,
            payload,
            headers=headers,
            request_id=request_id,
            parent_id=parent_id,
        )

    def emit_semantic(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        fact_ref: str | None = None,
        branch_id: str | None = None,
        request_id: str | None = None,
    ) -> ClawGraphRuntimeResponse:
        body: dict[str, Any] = {
            "kind": kind,
            "payload": payload,
        }
        if fact_ref is not None:
            body["fact_ref"] = fact_ref
        if branch_id is not None:
            body["branch_id"] = branch_id
        return self.post_json(
            "/v1/semantic-events",
            body,
            request_id=request_id,
        )
