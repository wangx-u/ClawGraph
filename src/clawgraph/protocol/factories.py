"""Factory helpers for protocol records."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.protocol.validation import validate_artifact_record, validate_fact_event


def new_fact_event(
    *,
    run_id: str,
    session_id: str,
    actor: str,
    kind: str,
    payload: dict,
    request_id: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
    task_id: str | None = None,
    parent_ref: str | None = None,
    branch_id: str | None = None,
    metadata: dict | None = None,
) -> FactEvent:
    """Create a new immutable fact event with standard defaults."""

    fact = FactEvent(
        fact_id=f"fact_{uuid4().hex}",
        schema_version="v1",
        run_id=run_id,
        session_id=session_id,
        timestamp=datetime.now(UTC),
        actor=actor,
        kind=kind,
        payload=payload,
        request_id=request_id,
        user_id=user_id,
        thread_id=thread_id,
        task_id=task_id,
        parent_ref=parent_ref,
        branch_id=branch_id,
        metadata=metadata or {},
    )
    validate_fact_event(fact)
    return fact


def new_artifact_record(
    *,
    artifact_type: str,
    target_ref: str,
    producer: str,
    payload: dict,
    version: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    status: str = "active",
    confidence: float | None = None,
    supersedes_artifact_id: str | None = None,
    metadata: dict | None = None,
) -> ArtifactRecord:
    """Create a new artifact record with standard defaults."""

    artifact = ArtifactRecord(
        artifact_id=f"art_{uuid4().hex}",
        schema_version="v1",
        artifact_type=artifact_type,
        target_ref=target_ref,
        producer=producer,
        payload=payload,
        version=version,
        session_id=session_id,
        run_id=run_id,
        created_at=datetime.now(UTC),
        status=status,
        confidence=confidence,
        supersedes_artifact_id=supersedes_artifact_id,
        metadata=metadata or {},
    )
    validate_artifact_record(artifact)
    return artifact


def new_semantic_event_fact(
    *,
    run_id: str,
    session_id: str,
    semantic_kind: str,
    fact_ref: str | None = None,
    payload: dict | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
    task_id: str | None = None,
    branch_id: str | None = None,
    metadata: dict | None = None,
) -> FactEvent:
    """Create a semantic event fact with the standard payload shape."""

    return new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="runtime",
        kind="semantic_event",
        payload={
            "semantic_kind": semantic_kind,
            "fact_ref": fact_ref,
            "payload": payload or {},
        },
        request_id=request_id,
        user_id=user_id,
        thread_id=thread_id,
        task_id=task_id,
        branch_id=branch_id,
        metadata=metadata,
    )
