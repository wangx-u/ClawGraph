"""Learning-oriented inspect views built from immutable facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from clawgraph.graph.correlation import correlate_request_groups, infer_branches
from clawgraph.graph.overlays import (
    ArtifactInspectSummary,
    branch_artifact_overlays,
    request_artifact_overlays,
    session_artifact_overlays,
)
from clawgraph.protocol.models import ArtifactRecord, BranchRecord, FactEvent


@dataclass(slots=True)
class PayloadSpillSummary:
    """Summary of one spilled request or response payload sidecar."""

    fact_id: str
    storage: str
    relative_path: str | None
    content_type: str | None
    byte_size: int | None
    compressed_size: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RequestSpanSummary:
    """Operational and learning summary for a single request lifecycle."""

    request_id: str
    request_fact_id: str
    session_id: str
    run_id: str
    user_id: str | None
    actor: str
    path: str
    branch_id: str | None
    outcome: str
    status_code: int | None
    error_code: str | None
    request_body_size: int
    response_body_size: int
    chunk_count: int
    total_latency_ms: int | None
    ttfb_ms: int | None
    stream_duration_ms: int | None
    upstream_request_id: str | None
    request_payload_spill: PayloadSpillSummary | None
    response_payload_spill: PayloadSpillSummary | None
    response_fact_id: str | None
    error_fact_id: str | None
    artifact_count: int = 0
    artifacts: list[ArtifactInspectSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionInspectSummary:
    """Session-level summary tuned for export and learning readiness."""

    session_id: str
    run_ids: list[str]
    user_ids: list[str]
    request_count: int
    success_count: int
    failure_count: int
    open_count: int
    streamed_count: int
    artifact_count: int
    branch_count: int
    declared_branch_count: int
    inferred_branch_count: int
    avg_latency_ms: float | None
    total_response_bytes: int
    request_payload_spill_count: int
    response_payload_spill_count: int
    spilled_payload_bytes: int
    session_artifact_count: int = 0
    run_artifact_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BranchInspectSummary:
    """Branch summary with request membership and source fidelity."""

    run_id: str
    branch_id: str
    branch_type: str
    status: str
    source: str
    parent_branch_id: str | None
    open_reason: str | None
    request_count: int
    request_ids: list[str]
    request_fact_ids: list[str]
    success_count: int
    failure_count: int
    artifact_count: int = 0
    artifacts: list[ArtifactInspectSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_request_span_summaries(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord] | None = None,
) -> list[RequestSpanSummary]:
    """Build request span summaries from correlated fact groups."""

    groups = correlate_request_groups(facts)
    _, request_branch_map = infer_branches(groups, facts=facts)
    summaries: list[RequestSpanSummary] = []
    for group in groups:
        request = group.request
        response_payload = group.response.payload if group.response is not None else {}
        error_payload = group.error.payload if group.error is not None else {}
        overlay_artifacts = request_artifact_overlays(group, artifacts)
        request_payload_spill = _payload_spill_summary(request)
        response_payload_spill = _payload_spill_summary(group.response) or _payload_spill_summary(
            group.error
        )
        summaries.append(
            RequestSpanSummary(
                request_id=request.request_id or request.fact_id,
                request_fact_id=request.fact_id,
                session_id=request.session_id,
                run_id=request.run_id,
                user_id=request.user_id,
                actor=group.actor,
                path=group.path,
                branch_id=request_branch_map.get(request.fact_id),
                outcome=group.outcome,
                status_code=group.status_code,
                error_code=_value_as_str(error_payload.get("error_code")),
                request_body_size=_value_as_int(request.payload.get("body_size")) or 0,
                response_body_size=(
                    _value_as_int(response_payload.get("body_size"))
                    or _value_as_int(error_payload.get("body_size"))
                    or 0
                ),
                chunk_count=(
                    _value_as_int(response_payload.get("chunk_count"))
                    or len(group.response_chunks)
                ),
                total_latency_ms=(
                    _value_as_int(response_payload.get("total_latency_ms"))
                    or _value_as_int(error_payload.get("total_latency_ms"))
                ),
                ttfb_ms=(
                    _value_as_int(response_payload.get("ttfb_ms"))
                    or _value_as_int(error_payload.get("ttfb_ms"))
                ),
                stream_duration_ms=_value_as_int(response_payload.get("stream_duration_ms")),
                upstream_request_id=(
                    _value_as_str(response_payload.get("upstream_request_id"))
                    or _value_as_str(error_payload.get("upstream_request_id"))
                ),
                request_payload_spill=request_payload_spill,
                response_payload_spill=response_payload_spill,
                response_fact_id=group.response.fact_id if group.response is not None else None,
                error_fact_id=group.error.fact_id if group.error is not None else None,
                artifact_count=len(overlay_artifacts),
                artifacts=overlay_artifacts,
            )
        )
    return summaries


def build_session_inspect_summary(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord] | None = None,
) -> SessionInspectSummary:
    """Build a session-level inspect summary."""

    if not facts:
        raise ValueError("no facts found")

    request_summaries = build_request_span_summaries(facts, artifacts)
    branches, _ = infer_branches(correlate_request_groups(facts), facts=facts)
    latencies = [
        float(summary.total_latency_ms)
        for summary in request_summaries
        if summary.total_latency_ms is not None
    ]
    user_ids = sorted(
        {
            fact.user_id
            for fact in facts
            if isinstance(fact.user_id, str) and fact.user_id
        }
    )
    run_ids = sorted({fact.run_id for fact in facts})
    session_overlays = session_artifact_overlays(session_id=facts[0].session_id, artifacts=artifacts)
    run_artifact_count = sum(
        1
        for artifact in artifacts or []
        if isinstance(artifact.run_id, str) and artifact.target_ref == f"run:{artifact.run_id}"
    )
    return SessionInspectSummary(
        session_id=facts[0].session_id,
        run_ids=run_ids,
        user_ids=user_ids,
        request_count=len(request_summaries),
        success_count=sum(1 for summary in request_summaries if summary.outcome == "succeeded"),
        failure_count=sum(1 for summary in request_summaries if summary.outcome == "failed"),
        open_count=sum(1 for summary in request_summaries if summary.outcome == "open"),
        streamed_count=sum(1 for summary in request_summaries if summary.chunk_count > 0),
        artifact_count=len(artifacts or []),
        branch_count=len(branches),
        declared_branch_count=sum(1 for branch in branches if branch.source == "declared"),
        inferred_branch_count=sum(1 for branch in branches if branch.source != "declared"),
        avg_latency_ms=round(mean(latencies), 1) if latencies else None,
        total_response_bytes=sum(summary.response_body_size for summary in request_summaries),
        request_payload_spill_count=sum(
            1 for summary in request_summaries if summary.request_payload_spill is not None
        ),
        response_payload_spill_count=sum(
            1 for summary in request_summaries if summary.response_payload_spill is not None
        ),
        spilled_payload_bytes=sum(
            (
                (summary.request_payload_spill.byte_size or 0)
                if summary.request_payload_spill is not None
                else 0
            )
            + (
                (summary.response_payload_spill.byte_size or 0)
                if summary.response_payload_spill is not None
                else 0
            )
            for summary in request_summaries
        ),
        session_artifact_count=len(session_overlays),
        run_artifact_count=run_artifact_count,
    )


def build_branch_inspect_summaries(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord] | None = None,
) -> list[BranchInspectSummary]:
    """Build inspect summaries for all branches in a session."""

    groups = correlate_request_groups(facts)
    branches, request_branch_map = infer_branches(groups, facts=facts)
    request_summaries = {
        summary.request_fact_id: summary for summary in build_request_span_summaries(facts, artifacts)
    }
    summaries: list[BranchInspectSummary] = []
    request_fact_ids_by_branch: dict[tuple[str, str], list[str]] = {}
    requests_by_branch: dict[tuple[str, str], list[RequestSpanSummary]] = {}
    for group in groups:
        branch_id = request_branch_map.get(group.request.fact_id, "br_main")
        branch_key = (group.request.run_id, branch_id)
        summary = request_summaries.get(group.request.fact_id)
        if summary is None:
            continue
        requests_by_branch.setdefault(branch_key, []).append(summary)
        request_fact_ids_by_branch.setdefault(branch_key, []).append(group.request.fact_id)

    for branch in branches:
        branch_key = (branch.run_id, branch.branch_id)
        branch_requests = requests_by_branch.get(branch_key, [])
        overlay_artifacts = branch_artifact_overlays(
            branch_id=branch.branch_id,
            run_id=branch.run_id,
            artifacts=artifacts,
        )
        summaries.append(
            BranchInspectSummary(
                run_id=branch.run_id,
                branch_id=branch.branch_id,
                branch_type=branch.branch_type,
                status=branch.status,
                source=branch.source,
                parent_branch_id=branch.parent_branch_id,
                open_reason=branch.open_reason,
                request_count=len(branch_requests),
                request_ids=[summary.request_id for summary in branch_requests],
                request_fact_ids=request_fact_ids_by_branch.get(branch_key, []),
                success_count=sum(
                    1 for summary in branch_requests if summary.outcome == "succeeded"
                ),
                failure_count=sum(
                    1 for summary in branch_requests if summary.outcome == "failed"
                ),
                artifact_count=len(overlay_artifacts),
                artifacts=overlay_artifacts,
            )
        )
    return summaries


def get_request_span_summary(
    facts: list[FactEvent],
    request_id: str,
    artifacts: list[ArtifactRecord] | None = None,
) -> RequestSpanSummary:
    """Return one request span summary by request id."""

    matches = [
        summary
        for summary in build_request_span_summaries(facts, artifacts)
        if summary.request_id == request_id
    ]
    if not matches:
        raise ValueError(f"request not found: {request_id}")
    if len(matches) > 1:
        raise ValueError(
            f"request is ambiguous across runs: {request_id}; specify a run-scoped query"
        )
    return matches[0]


def get_branch_inspect_summary(
    facts: list[FactEvent],
    branch_id: str,
    artifacts: list[ArtifactRecord] | None = None,
) -> BranchInspectSummary:
    """Return one branch summary by branch id."""

    matches = [
        summary
        for summary in build_branch_inspect_summaries(facts, artifacts)
        if summary.branch_id == branch_id
    ]
    if not matches:
        raise ValueError(f"branch not found: {branch_id}")
    if len(matches) > 1:
        raise ValueError(
            f"branch is ambiguous across runs: {branch_id}; specify a run-scoped query"
        )
    return matches[0]


def render_session_inspect(summary: SessionInspectSummary) -> str:
    """Render a session inspect summary."""

    lines = [
        f"Session: {summary.session_id}",
        f"Runs: {', '.join(summary.run_ids)}",
        f"Users: {', '.join(summary.user_ids) if summary.user_ids else '<unknown>'}",
        f"Requests: {summary.request_count}",
        f"Success: {summary.success_count}  Failure: {summary.failure_count}  Open: {summary.open_count}",
        f"Branches: {summary.branch_count}  Declared: {summary.declared_branch_count}  Inferred: {summary.inferred_branch_count}",
        f"Artifacts: {summary.artifact_count}",
        f"Session-scoped artifacts: {summary.session_artifact_count}",
        f"Run-scoped artifacts: {summary.run_artifact_count}",
        f"Streamed requests: {summary.streamed_count}",
        f"Avg latency (ms): {summary.avg_latency_ms if summary.avg_latency_ms is not None else '<unknown>'}",
        f"Response bytes: {summary.total_response_bytes}",
        f"Request payload spills: {summary.request_payload_spill_count}",
        f"Response payload spills: {summary.response_payload_spill_count}",
        f"Spilled payload bytes: {summary.spilled_payload_bytes}",
    ]
    return "\n".join(lines)


def render_request_inspect(summary: RequestSpanSummary) -> str:
    """Render one request inspect summary."""

    lines = [
        f"Request: {summary.request_id}",
        f"Session: {summary.session_id}",
        f"Run: {summary.run_id}",
        f"User: {summary.user_id or '<unknown>'}",
        f"Actor: {summary.actor}",
        f"Path: {summary.path}",
        f"Branch: {summary.branch_id or '<unknown>'}",
        f"Outcome: {summary.outcome}",
        f"HTTP status: {summary.status_code if summary.status_code is not None else '<unknown>'}",
        f"Error code: {summary.error_code or '<none>'}",
        f"Request bytes: {summary.request_body_size}",
        f"Response bytes: {summary.response_body_size}",
        f"Chunks: {summary.chunk_count}",
        f"Latency ms: {summary.total_latency_ms if summary.total_latency_ms is not None else '<unknown>'}",
        f"TTFB ms: {summary.ttfb_ms if summary.ttfb_ms is not None else '<unknown>'}",
        f"Stream duration ms: {summary.stream_duration_ms if summary.stream_duration_ms is not None else '<unknown>'}",
        f"Upstream request id: {summary.upstream_request_id or '<unknown>'}",
        f"Request payload spill: {_render_payload_spill(summary.request_payload_spill)}",
        f"Response payload spill: {_render_payload_spill(summary.response_payload_spill)}",
        f"Artifacts: {summary.artifact_count}",
    ]
    if summary.artifacts:
        lines.append("Artifact overlay:")
        for artifact in summary.artifacts:
            lines.append(
                f"- {artifact.artifact_type} target={artifact.target_ref} "
                f"producer={artifact.producer} status={artifact.status}"
            )
    return "\n".join(lines)


def render_branch_inspect(summary: BranchInspectSummary) -> str:
    """Render one branch inspect summary."""

    lines = [
        f"Branch: {summary.branch_id}",
        f"Run: {summary.run_id}",
        f"Type: {summary.branch_type}",
        f"Source: {summary.source}",
        f"Status: {summary.status}",
        f"Parent: {summary.parent_branch_id or '<root>'}",
        f"Open reason: {summary.open_reason or '<unknown>'}",
        f"Requests: {summary.request_count}",
        f"Success: {summary.success_count}  Failure: {summary.failure_count}",
        f"Request ids: {', '.join(summary.request_ids) if summary.request_ids else '<none>'}",
        f"Artifacts: {summary.artifact_count}",
    ]
    if summary.artifacts:
        lines.append("Artifact overlay:")
        for artifact in summary.artifacts:
            lines.append(
                f"- {artifact.artifact_type} target={artifact.target_ref} "
                f"producer={artifact.producer} status={artifact.status}"
            )
    return "\n".join(lines)


def _value_as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _value_as_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _payload_spill_summary(fact: FactEvent | None) -> PayloadSpillSummary | None:
    if fact is None:
        return None
    body_ref = fact.payload.get("body_ref")
    if not isinstance(body_ref, dict):
        return None
    return PayloadSpillSummary(
        fact_id=fact.fact_id,
        storage=_value_as_str(body_ref.get("storage")) or "unknown",
        relative_path=_value_as_str(body_ref.get("relative_path")),
        content_type=_value_as_str(body_ref.get("content_type")),
        byte_size=_value_as_int(body_ref.get("byte_size")),
        compressed_size=_value_as_int(body_ref.get("compressed_size")),
    )


def _render_payload_spill(summary: PayloadSpillSummary | None) -> str:
    if summary is None:
        return "<none>"
    parts = [summary.storage, f"fact={summary.fact_id}"]
    if summary.byte_size is not None:
        parts.append(f"bytes={summary.byte_size}")
    if summary.relative_path is not None:
        parts.append(f"path={summary.relative_path}")
    return " ".join(parts)
