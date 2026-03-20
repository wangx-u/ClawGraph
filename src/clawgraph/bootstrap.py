"""Bootstrap helpers for first-run ClawGraph workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from clawgraph.protocol.factories import new_artifact_record, new_fact_event, new_semantic_event_fact
from clawgraph.store import SQLiteFactStore


@dataclass(slots=True)
class BootstrapResult:
    """Structured result for seeded first-run sessions."""

    store_uri: str
    session_id: str
    run_id: str
    request_ids: list[str]
    response_fact_id: str
    branch_ids: list[str]
    artifact_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bootstrap_openclaw_session(
    *,
    store_uri: str,
    session_id: str | None = None,
    run_id: str | None = None,
    user_id: str = "user_seed",
) -> BootstrapResult:
    """Seed a realistic OpenClaw-style session into the local store."""

    session_id = session_id or f"sess_openclaw_seed_{uuid4().hex[:12]}"
    run_id = run_id or session_id
    store = SQLiteFactStore(store_uri)
    if session_id in set(store.iter_sessions()):
        raise ValueError(f"session already exists: {session_id}")

    main_request = new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="model",
        kind="request_started",
        payload={
            "method": "POST",
            "path": "/v1/chat/completions",
            "body_size": 241,
            "json": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Compare two agent RL repos and summarize the differences.",
                    }
                ]
            },
        },
        request_id="req_main_1",
        user_id=user_id,
        metadata={"capture_source": "bootstrap"},
    )
    main_error = new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="proxy",
        kind="error_raised",
        payload={
            "path": "/v1/chat/completions",
            "status_code": 502,
            "error": "upstream returned HTTP 502",
            "error_code": "upstream_http_error",
            "total_latency_ms": 412,
            "ttfb_ms": 167,
        },
        request_id="req_main_1",
        user_id=user_id,
        parent_ref=main_request.fact_id,
        metadata={"capture_source": "bootstrap"},
    )
    retry_request = new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="model",
        kind="request_started",
        payload={
            "method": "POST",
            "path": "/v1/chat/completions",
            "body_size": 253,
            "json": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Compare two agent RL repos and summarize the differences.",
                    }
                ],
                "stream": True,
            },
        },
        request_id="req_retry_1",
        user_id=user_id,
        metadata={"capture_source": "bootstrap"},
    )
    retry_declared = new_semantic_event_fact(
        run_id=run_id,
        session_id=session_id,
        semantic_kind="retry_declared",
        fact_ref=retry_request.fact_id,
        payload={
            "request_fact_id": retry_request.fact_id,
            "request_id": "req_retry_1",
            "parent_request_id": "req_main_1",
            "branch_id": "br_retry_declared_1",
            "branch_type": "retry",
            "status": "succeeded",
        },
        request_id="req_retry_1",
        user_id=user_id,
        metadata={"capture_source": "bootstrap"},
    )
    retry_response = new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="model",
        kind="response_finished",
        payload={
            "path": "/v1/chat/completions",
            "status_code": 200,
            "content_type": "application/json",
            "body_size": 688,
            "chunk_count": 4,
            "streamed": True,
            "total_latency_ms": 923,
            "ttfb_ms": 208,
            "stream_duration_ms": 715,
            "json": {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Repo A focuses on proxy-first RL capture, while Repo B is more SDK-centric.",
                        }
                    }
                ]
            },
        },
        request_id="req_retry_1",
        user_id=user_id,
        parent_ref=retry_request.fact_id,
        metadata={"capture_source": "bootstrap"},
    )
    score_artifact = new_artifact_record(
        artifact_type="score",
        target_ref=f"fact:{retry_response.fact_id}",
        producer="bootstrap.branch_outcome",
        payload={"score": 1.0, "label": True},
        session_id=session_id,
        run_id=run_id,
        confidence=0.95,
        metadata={"capture_source": "bootstrap"},
    )
    preference_artifact = new_artifact_record(
        artifact_type="preference",
        target_ref=f"session:{session_id}",
        producer="bootstrap.branch_outcome",
        payload={
            "chosen": "br_retry_declared_1",
            "rejected": "br_main",
            "reason": "Declared retry succeeded after the main request failed.",
        },
        session_id=session_id,
        run_id=run_id,
        metadata={"capture_source": "bootstrap"},
    )

    for fact in (main_request, main_error, retry_request, retry_declared, retry_response):
        store.append_fact(fact)
    for artifact in (score_artifact, preference_artifact):
        store.append_artifact(artifact)

    return BootstrapResult(
        store_uri=store_uri,
        session_id=session_id,
        run_id=run_id,
        request_ids=["req_main_1", "req_retry_1"],
        response_fact_id=retry_response.fact_id,
        branch_ids=["br_main", "br_retry_declared_1"],
        artifact_ids=[score_artifact.artifact_id, preference_artifact.artifact_id],
    )
