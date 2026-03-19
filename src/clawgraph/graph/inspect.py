"""Learning-oriented inspect views built from immutable facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from clawgraph.graph.correlation import correlate_request_groups, infer_branches
from clawgraph.protocol.models import ArtifactRecord, BranchRecord, FactEvent


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
    response_fact_id: str | None
    error_fact_id: str | None

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BranchInspectSummary:
    """Branch summary with request membership and source fidelity."""

    branch_id: str
    branch_type: str
    status: str
    source: str
    parent_branch_id: str | None
    open_reason: str | None
    request_count: int
    request_ids: list[str]
    success_count: int
    failure_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_request_span_summaries(facts: list[FactEvent]) -> list[RequestSpanSummary]:
    """Build request span summaries from correlated fact groups."""

    groups = correlate_request_groups(facts)
    _, request_branch_map = infer_branches(groups, facts=facts)
    summaries: list[RequestSpanSummary] = []
    for group in groups:
        request = group.request
        response_payload = group.response.payload if group.response is not None else {}
        error_payload = group.error.payload if group.error is not None else {}
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
                response_fact_id=group.response.fact_id if group.response is not None else None,
                error_fact_id=group.error.fact_id if group.error is not None else None,
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

    request_summaries = build_request_span_summaries(facts)
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
    )


def build_branch_inspect_summaries(facts: list[FactEvent]) -> list[BranchInspectSummary]:
    """Build inspect summaries for all branches in a session."""

    groups = correlate_request_groups(facts)
    branches, request_branch_map = infer_branches(groups, facts=facts)
    request_summaries = {
        summary.request_id: summary for summary in build_request_span_summaries(facts)
    }
    summaries: list[BranchInspectSummary] = []
    requests_by_branch: dict[str, list[RequestSpanSummary]] = {}
    for group in groups:
        branch_id = request_branch_map.get(group.request.fact_id, "br_main")
        request_id = group.request.request_id or group.request.fact_id
        summary = request_summaries.get(request_id)
        if summary is None:
            continue
        requests_by_branch.setdefault(branch_id, []).append(summary)

    for branch in branches:
        branch_requests = requests_by_branch.get(branch.branch_id, [])
        summaries.append(
            BranchInspectSummary(
                branch_id=branch.branch_id,
                branch_type=branch.branch_type,
                status=branch.status,
                source=branch.source,
                parent_branch_id=branch.parent_branch_id,
                open_reason=branch.open_reason,
                request_count=len(branch_requests),
                request_ids=[summary.request_id for summary in branch_requests],
                success_count=sum(
                    1 for summary in branch_requests if summary.outcome == "succeeded"
                ),
                failure_count=sum(
                    1 for summary in branch_requests if summary.outcome == "failed"
                ),
            )
        )
    return summaries


def get_request_span_summary(
    facts: list[FactEvent],
    request_id: str,
) -> RequestSpanSummary:
    """Return one request span summary by request id."""

    for summary in build_request_span_summaries(facts):
        if summary.request_id == request_id:
            return summary
    raise ValueError(f"request not found: {request_id}")


def get_branch_inspect_summary(
    facts: list[FactEvent],
    branch_id: str,
) -> BranchInspectSummary:
    """Return one branch summary by branch id."""

    for summary in build_branch_inspect_summaries(facts):
        if summary.branch_id == branch_id:
            return summary
    raise ValueError(f"branch not found: {branch_id}")


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
        f"Streamed requests: {summary.streamed_count}",
        f"Avg latency (ms): {summary.avg_latency_ms if summary.avg_latency_ms is not None else '<unknown>'}",
        f"Response bytes: {summary.total_response_bytes}",
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
    ]
    return "\n".join(lines)


def render_branch_inspect(summary: BranchInspectSummary) -> str:
    """Render one branch inspect summary."""

    lines = [
        f"Branch: {summary.branch_id}",
        f"Type: {summary.branch_type}",
        f"Source: {summary.source}",
        f"Status: {summary.status}",
        f"Parent: {summary.parent_branch_id or '<root>'}",
        f"Open reason: {summary.open_reason or '<unknown>'}",
        f"Requests: {summary.request_count}",
        f"Success: {summary.success_count}  Failure: {summary.failure_count}",
        f"Request ids: {', '.join(summary.request_ids) if summary.request_ids else '<none>'}",
    ]
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
