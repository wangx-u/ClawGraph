"""Core protocol models for the early ClawGraph scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FactEvent:
    """Immutable source event captured from runtime execution."""

    fact_id: str
    schema_version: str
    run_id: str
    session_id: str
    timestamp: datetime
    actor: str
    kind: str
    payload: dict[str, Any]
    request_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    task_id: str | None = None
    parent_ref: str | None = None
    branch_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BranchRecord:
    """Derived or declared branch metadata."""

    branch_id: str
    schema_version: str
    run_id: str
    branch_type: str
    status: str
    source: str = "inferred"
    parent_branch_id: str | None = None
    opened_at_fact_id: str | None = None
    closed_at_fact_id: str | None = None
    open_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactRecord:
    """External supervision attached to facts or branches."""

    artifact_id: str
    schema_version: str
    artifact_type: str
    target_ref: str
    producer: str
    payload: dict[str, Any]
    version: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    created_at: datetime | None = None
    status: str = "active"
    confidence: float | None = None
    supersedes_artifact_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
