"""Duck-typed wrappers for OpenAI-compatible Python SDK clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clawgraph.runtime.client import ClawGraphRuntimeClient, ClawGraphSession


def _merge_extra_headers(
    *,
    session: ClawGraphSession,
    request_id: str | None = None,
    parent_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    return session.request_headers(
        request_id=request_id or session.make_request_id(),
        parent_id=parent_id,
        extra_headers=extra_headers,
    )


def _as_text_base_url(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    stringified = str(value) if value is not None else ""
    return stringified or None


@dataclass(slots=True)
class _WrappedEndpoint:
    session: ClawGraphSession
    create_callable: Any

    def create(
        self,
        *args: Any,
        parent_id: str | None = None,
        request_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_headers = _merge_extra_headers(
            session=self.session,
            request_id=request_id,
            parent_id=parent_id,
            extra_headers=kwargs.pop("extra_headers", None) or extra_headers,
        )
        self.session.last_request_id = merged_headers.get("x-clawgraph-request-id")
        return self.create_callable(*args, extra_headers=merged_headers, **kwargs)


@dataclass(slots=True)
class _WrappedCompletions:
    session: ClawGraphSession
    create_callable: Any

    def create(
        self,
        *args: Any,
        parent_id: str | None = None,
        request_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        return _WrappedEndpoint(
            session=self.session,
            create_callable=self.create_callable,
        ).create(
            *args,
            parent_id=parent_id,
            request_id=request_id,
            extra_headers=extra_headers,
            **kwargs,
        )


@dataclass(slots=True)
class _WrappedChat:
    completions: _WrappedCompletions


@dataclass(slots=True)
class _WrappedResponses:
    session: ClawGraphSession
    create_callable: Any

    def create(
        self,
        *args: Any,
        parent_id: str | None = None,
        request_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        return _WrappedEndpoint(
            session=self.session,
            create_callable=self.create_callable,
        ).create(
            *args,
            parent_id=parent_id,
            request_id=request_id,
            extra_headers=extra_headers,
            **kwargs,
        )


class _UnavailableResponses:
    def create(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise ValueError("wrapped client does not expose responses.create")


class ClawGraphOpenAIClient:
    """Wrap an OpenAI-compatible client and inject ClawGraph headers automatically."""

    def __init__(
        self,
        client: Any,
        *,
        session: ClawGraphSession | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self.session = session or ClawGraphSession()
        self.chat = _WrappedChat(
            completions=_WrappedCompletions(
                session=self.session,
                create_callable=client.chat.completions.create,
            )
        )
        responses_namespace = getattr(client, "responses", None)
        responses_create = getattr(responses_namespace, "create", None)
        if callable(responses_create):
            self.responses = _WrappedResponses(
                session=self.session,
                create_callable=responses_create,
            )
        else:
            self.responses = _UnavailableResponses()
        resolved_base_url = base_url or _as_text_base_url(getattr(client, "base_url", None))
        self._semantic_client = (
            ClawGraphRuntimeClient(
                base_url=resolved_base_url,
                session=self.session,
                timeout_seconds=timeout_seconds,
            )
            if resolved_base_url
            else None
        )

    def start_new_run(self, run_id: str | None = None) -> str:
        return self.session.start_new_run(run_id=run_id)

    def emit_semantic(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        fact_ref: str | None = None,
        branch_id: str | None = None,
        request_id: str | None = None,
        target_request_id: str | None = None,
        event_request_id: str | None = None,
    ) -> Any:
        if self._semantic_client is None:
            raise ValueError("base_url is required to emit semantic events from the wrapper")
        return self._semantic_client.emit_semantic(
            kind=kind,
            payload=payload,
            fact_ref=fact_ref,
            branch_id=branch_id,
            request_id=request_id,
            target_request_id=target_request_id,
            event_request_id=event_request_id,
        )
