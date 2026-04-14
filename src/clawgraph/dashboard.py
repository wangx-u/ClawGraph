"""Dashboard-oriented read models built from existing ClawGraph objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from clawgraph.artifacts import (
    E1_ANNOTATION_ARTIFACT_TYPE,
    E1_ANNOTATION_KIND,
    E1_REQUIRED_FIELDS,
    resolve_e1_annotation_for_run,
    summarize_e1_annotations,
)
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.graph import build_session_inspect_summary
from clawgraph.prepare import get_prepare_artifact_for_run, resolve_prepare_annotation_for_run
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore

E2_DECISION_SIGNAL_KINDS = frozenset(
    {
        "task_opened",
        "route_decided",
        "retry_declared",
        "fallback_declared",
        "branch_opened",
        "task_completed",
        "verifier_completed",
        "human_review_requested",
    }
)
WORKFLOW_QUALITY_THRESHOLD = 0.8
WORKFLOW_VERIFIER_THRESHOLD = 0.8
NON_BLOCKING_WORKFLOW_REVIEW_REASONS = {"inferred_only_branching"}


@dataclass(slots=True)
class DashboardOverview:
    """Top-level KPI row for the dashboard overview."""

    captured_sessions: int
    captured_runs: int
    e1_ready_runs: int
    e2_ready_runs: int
    export_ready_runs: int
    frozen_cohorts: int
    dataset_snapshots: int
    active_eval_suites: int
    scorecards_pass: int
    scorecards_hold: int
    scorecards_fail: int
    feedback_queue_open: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardSessionRow:
    """Session inbox row for dashboard-style inspection."""

    session_id: str
    latest_run_id: str | None
    latest_timestamp: str | None
    run_count: int
    e1_ready_runs: int
    e2_ready_runs: int
    export_ready_runs: int
    request_count: int
    success_count: int
    failure_count: int
    open_count: int
    branch_count: int
    artifact_count: int
    semantic_event_count: int
    avg_latency_ms: float | None
    evidence_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardRunRow:
    """Run-level readiness and evidence row."""

    session_id: str
    run_id: str
    latest_timestamp: str | None
    request_count: int
    success_count: int
    failure_count: int
    open_count: int
    branch_count: int
    artifact_count: int
    semantic_event_count: int
    semantic_kinds: list[str]
    evidence_level: str
    task_family: str | None
    task_type: str | None
    task_instance_key: str | None
    ready_builders: list[str]
    builder_readiness: dict[str, bool]
    readiness_blockers: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardWorkflowOverview:
    """Phase-2 workflow summary built from run-scoped governance signals."""

    in_progress_runs: int
    needs_annotation_runs: int
    needs_review_runs: int
    ready_for_dataset_runs: int
    ready_for_eval_runs: int
    evaluation_assets: int
    feedback_open_runs: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardWorkflowRunRow:
    """User-facing workflow status for one run."""

    session_id: str
    run_id: str
    latest_timestamp: str | None
    evidence_level: str
    stage: str
    stage_label: str
    stage_detail: str
    next_action: str
    trajectory_status: str
    review_status: str
    feedback_count: int
    quality_confidence: float | None
    verifier_score: float | None
    annotation_artifact_id: str | None
    annotation_producer: str | None
    annotation_version: str | None
    supersedes_artifact_id: str | None
    source_channel: str | None
    ready_builders: list[str]
    blockers: list[str]
    review_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardSliceRow:
    """Governance-oriented row for one registered slice."""

    slice_id: str
    task_family: str
    task_type: str
    default_use: str
    risk_level: str
    frozen_cohorts: int
    dataset_snapshots: int
    active_eval_suites: int
    scorecards: int
    latest_scorecard_verdict: str | None
    promotion_decisions: int
    latest_promotion_decision: str | None
    feedback_open: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardSnapshot:
    """Rendered snapshot for CLI or future dashboard backends."""

    generated_at: str
    builder_filter: str | None
    session_limit: int
    run_limit: int
    overview: DashboardOverview
    workflow_overview: DashboardWorkflowOverview
    recent_sessions: list[DashboardSessionRow]
    recent_runs: list[DashboardRunRow]
    workflow_runs: list[DashboardWorkflowRunRow]
    slices: list[DashboardSliceRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "builder_filter": self.builder_filter,
            "session_limit": self.session_limit,
            "run_limit": self.run_limit,
            "overview": self.overview.to_dict(),
            "workflow_overview": self.workflow_overview.to_dict(),
            "recent_sessions": [row.to_dict() for row in self.recent_sessions],
            "recent_runs": [row.to_dict() for row in self.recent_runs],
            "workflow_runs": [row.to_dict() for row in self.workflow_runs],
            "slices": [row.to_dict() for row in self.slices],
        }


@dataclass(slots=True)
class _RunEvidence:
    """Internal run-scoped evidence classification."""

    level: str
    e1_ready: bool
    e2_ready: bool
    semantic_kinds: list[str]
    task_family: str | None
    task_type: str | None
    task_instance_key: str | None


def inspect_run_workflow(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    session: str | None = "latest",
    run_id: str | None = None,
    builder: str | None = None,
) -> DashboardWorkflowRunRow:
    """Inspect one run-scoped workflow/gate row using the same dashboard logic."""

    if store is None and store_uri is None:
        raise ValueError("store or store_uri is required")

    resolved_store = store or SQLiteFactStore(str(store_uri))
    query = ClawGraphQueryService(store=resolved_store)
    scope = query.load_scope(
        session=session,
        run_id=run_id,
        default_latest_run=True,
    )
    effective_run_id = scope.run_id or scope.facts[0].run_id
    run_row, inspect_summary, artifacts = _build_run_dashboard_row(
        store=resolved_store,
        session_id=scope.session_id,
        run_id=effective_run_id,
        builder=builder,
    )
    feedback_reasons = _feedback_by_run(query.list_feedback_queue()).get(effective_run_id, [])
    return _build_workflow_run_row(
        run_row=run_row,
        session_inspect_summary=inspect_summary,
        artifacts=artifacts,
        feedback_reasons=feedback_reasons,
    )


def build_dashboard_snapshot(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    builder: str | None = None,
    session_limit: int = 10,
    run_limit: int = 20,
) -> DashboardSnapshot:
    """Build a single dashboard snapshot from current persisted objects."""

    if store is None and store_uri is None:
        raise ValueError("store or store_uri is required")

    resolved_store = store or SQLiteFactStore(str(store_uri))
    query = ClawGraphQueryService(store=resolved_store)
    session_ids = list(resolved_store.iter_sessions())
    run_ids = list(resolved_store.iter_runs())

    run_rows: list[DashboardRunRow] = []
    run_rows_by_session: dict[str, list[DashboardRunRow]] = {}
    run_contexts: dict[str, dict[str, Any]] = {}
    for run_id in run_ids:
        session_id = resolved_store.get_session_id_for_run(run_id)
        if session_id is None:
            continue
        try:
            row, inspect_summary, artifacts = _build_run_dashboard_row(
                store=resolved_store,
                session_id=session_id,
                run_id=run_id,
                builder=builder,
            )
        except ValueError:
            continue
        facts = resolved_store.list_facts(session_id=session_id, run_id=run_id)
        run_rows.append(row)
        run_rows_by_session.setdefault(session_id, []).append(row)
        run_contexts[run_id] = {
            "session_id": session_id,
            "facts": facts,
            "artifacts": artifacts,
            "inspect_summary": inspect_summary,
        }

    recent_sessions: list[DashboardSessionRow] = []
    for session_id in session_ids[:session_limit]:
        facts = resolved_store.list_facts(session_id=session_id)
        if not facts:
            continue
        artifacts = resolved_store.list_artifacts(session_id=session_id, latest_only=True)
        inspect_summary = build_session_inspect_summary(facts, artifacts)
        session_run_rows = run_rows_by_session.get(session_id, [])
        recent_sessions.append(
            DashboardSessionRow(
                session_id=session_id,
                latest_run_id=resolved_store.get_latest_run_id(session_id=session_id),
                latest_timestamp=_latest_timestamp(facts),
                run_count=len(session_run_rows),
                e1_ready_runs=sum(1 for row in session_run_rows if row.evidence_level in {"E1", "E2"}),
                e2_ready_runs=sum(1 for row in session_run_rows if row.evidence_level == "E2"),
                export_ready_runs=sum(1 for row in session_run_rows if row.ready_builders),
                request_count=inspect_summary.request_count,
                success_count=inspect_summary.success_count,
                failure_count=inspect_summary.failure_count,
                open_count=inspect_summary.open_count,
                branch_count=inspect_summary.branch_count,
                artifact_count=inspect_summary.artifact_count,
                semantic_event_count=sum(1 for fact in facts if fact.kind == "semantic_event"),
                avg_latency_ms=inspect_summary.avg_latency_ms,
                evidence_level=_aggregate_session_evidence(session_run_rows),
            )
        )

    slices = query.list_slices()
    all_cohorts = query.list_cohorts()
    all_snapshots = query.list_dataset_snapshots()
    all_eval_suites = query.list_eval_suites()
    all_scorecards = query.list_scorecards()
    all_decisions = query.list_promotion_decisions()
    all_feedback = query.list_feedback_queue()
    feedback_by_run = _feedback_by_run(all_feedback)

    workflow_rows = [
        _build_workflow_run_row(
            run_row=row,
            session_inspect_summary=run_contexts[row.run_id]["inspect_summary"],
            artifacts=run_contexts[row.run_id]["artifacts"],
            feedback_reasons=feedback_by_run.get(row.run_id, []),
        )
        for row in run_rows
        if row.run_id in run_contexts
    ]

    slice_rows: list[DashboardSliceRow] = []
    for slice_record in sorted(slices, key=lambda item: item.slice_id):
        slice_cohorts = [cohort for cohort in all_cohorts if slice_record.slice_id in cohort.slice_ids]
        cohort_ids = {cohort.cohort_id for cohort in slice_cohorts}
        slice_snapshots = [snapshot for snapshot in all_snapshots if snapshot.cohort_id in cohort_ids]
        slice_eval_suites = [suite for suite in all_eval_suites if suite.slice_id == slice_record.slice_id]
        slice_scorecards = [scorecard for scorecard in all_scorecards if scorecard.slice_id == slice_record.slice_id]
        slice_decisions = [decision for decision in all_decisions if decision.slice_id == slice_record.slice_id]
        slice_feedback = [item for item in all_feedback if item.slice_id == slice_record.slice_id]
        latest_scorecard = slice_scorecards[0] if slice_scorecards else None
        latest_decision = slice_decisions[0] if slice_decisions else None
        slice_rows.append(
            DashboardSliceRow(
                slice_id=slice_record.slice_id,
                task_family=slice_record.task_family,
                task_type=slice_record.task_type,
                default_use=slice_record.default_use,
                risk_level=slice_record.risk_level,
                frozen_cohorts=sum(1 for cohort in slice_cohorts if cohort.status == "frozen"),
                dataset_snapshots=len(slice_snapshots),
                active_eval_suites=sum(1 for suite in slice_eval_suites if suite.status == "active"),
                scorecards=len(slice_scorecards),
                latest_scorecard_verdict=None if latest_scorecard is None else latest_scorecard.verdict,
                promotion_decisions=len(slice_decisions),
                latest_promotion_decision=(
                    None if latest_decision is None else latest_decision.decision
                ),
                feedback_open=sum(1 for item in slice_feedback if item.status == "queued"),
            )
        )

    overview = DashboardOverview(
        captured_sessions=len(session_ids),
        captured_runs=len(run_rows),
        e1_ready_runs=sum(1 for row in run_rows if row.evidence_level in {"E1", "E2"}),
        e2_ready_runs=sum(1 for row in run_rows if row.evidence_level == "E2"),
        export_ready_runs=sum(1 for row in run_rows if row.ready_builders),
        frozen_cohorts=sum(1 for cohort in all_cohorts if cohort.status == "frozen"),
        dataset_snapshots=len(all_snapshots),
        active_eval_suites=sum(1 for suite in all_eval_suites if suite.status == "active"),
        scorecards_pass=sum(1 for scorecard in all_scorecards if scorecard.verdict == "pass"),
        scorecards_hold=sum(1 for scorecard in all_scorecards if scorecard.verdict == "hold"),
        scorecards_fail=sum(1 for scorecard in all_scorecards if scorecard.verdict == "fail"),
        feedback_queue_open=sum(1 for item in all_feedback if item.status == "queued"),
    )
    workflow_overview = DashboardWorkflowOverview(
        in_progress_runs=sum(1 for row in workflow_rows if row.stage == "capture"),
        needs_annotation_runs=sum(
            1 for row in workflow_rows if row.stage in {"annotate", "augment"}
        ),
        needs_review_runs=sum(1 for row in workflow_rows if row.stage == "review"),
        ready_for_dataset_runs=sum(
            1 for row in workflow_rows if row.stage in {"dataset", "evaluate"}
        ),
        ready_for_eval_runs=sum(1 for row in workflow_rows if row.stage == "evaluate"),
        evaluation_assets=sum(1 for suite in all_eval_suites if suite.status == "active"),
        feedback_open_runs=sum(1 for row in workflow_rows if row.review_status == "feedback"),
    )
    return DashboardSnapshot(
        generated_at=datetime.now(UTC).isoformat(),
        builder_filter=builder,
        session_limit=session_limit,
        run_limit=run_limit,
        overview=overview,
        workflow_overview=workflow_overview,
        recent_sessions=recent_sessions,
        recent_runs=run_rows[:run_limit],
        workflow_runs=_sort_workflow_rows(workflow_rows)[:run_limit],
        slices=slice_rows,
    )


def _build_run_dashboard_row(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str,
    builder: str | None = None,
) -> tuple[DashboardRunRow, Any, list[ArtifactRecord]]:
    facts = store.list_facts(session_id=session_id, run_id=run_id)
    if not facts:
        raise ValueError(f"no facts found for run: {run_id}")
    artifacts = _load_run_scope_artifacts(
        store=store,
        session_id=session_id,
        run_id=run_id,
    )
    inspect_summary = build_session_inspect_summary(facts, artifacts)
    readiness = build_dataset_readiness_summary(facts, artifacts, builder=builder)
    evidence = _build_run_evidence(facts=facts, artifacts=artifacts)
    readiness_items = _select_dashboard_builders(readiness.builders, builder=builder)
    row = DashboardRunRow(
        session_id=session_id,
        run_id=run_id,
        latest_timestamp=_latest_timestamp(facts),
        request_count=inspect_summary.request_count,
        success_count=inspect_summary.success_count,
        failure_count=inspect_summary.failure_count,
        open_count=inspect_summary.open_count,
        branch_count=inspect_summary.branch_count,
        artifact_count=inspect_summary.artifact_count,
        semantic_event_count=sum(1 for fact in facts if fact.kind == "semantic_event"),
        semantic_kinds=evidence.semantic_kinds,
        evidence_level=evidence.level,
        task_family=evidence.task_family,
        task_type=evidence.task_type,
        task_instance_key=evidence.task_instance_key,
        ready_builders=[item.builder for item in readiness_items if item.ready],
        builder_readiness={item.builder: item.ready for item in readiness_items},
        readiness_blockers={item.builder: list(item.blockers) for item in readiness_items},
    )
    return row, inspect_summary, artifacts


def render_dashboard_snapshot(snapshot: DashboardSnapshot) -> str:
    """Render one dashboard snapshot as a compact text report."""

    overview = snapshot.overview
    lines = [
        "Overview:",
        f"Generated at: {snapshot.generated_at}",
        f"Builder filter: {snapshot.builder_filter or '<all>'}",
        (
            "KPI: "
            f"sessions={overview.captured_sessions} "
            f"runs={overview.captured_runs} "
            f"e1_ready={overview.e1_ready_runs} "
            f"e2_ready={overview.e2_ready_runs} "
            f"export_ready={overview.export_ready_runs}"
        ),
        (
            "Assets: "
            f"cohorts={overview.frozen_cohorts} "
            f"snapshots={overview.dataset_snapshots} "
            f"eval_suites={overview.active_eval_suites} "
            f"scorecards(pass/hold/fail)="
            f"{overview.scorecards_pass}/{overview.scorecards_hold}/{overview.scorecards_fail} "
            f"feedback_open={overview.feedback_queue_open}"
        ),
        (
            "Workflow: "
            f"in_progress={snapshot.workflow_overview.in_progress_runs} "
            f"needs_annotation={snapshot.workflow_overview.needs_annotation_runs} "
            f"needs_review={snapshot.workflow_overview.needs_review_runs} "
            f"ready_dataset={snapshot.workflow_overview.ready_for_dataset_runs} "
            f"ready_eval={snapshot.workflow_overview.ready_for_eval_runs} "
            f"eval_assets={snapshot.workflow_overview.evaluation_assets}"
        ),
        "",
        "Recent sessions:",
    ]
    if not snapshot.recent_sessions:
        lines.append("No sessions captured.")
    else:
        for row in snapshot.recent_sessions:
            lines.append(
                f"- {row.session_id} level={row.evidence_level} "
                f"runs={row.run_count} e1={row.e1_ready_runs} e2={row.e2_ready_runs} "
                f"export_ready={row.export_ready_runs} requests={row.request_count} "
                f"ok={row.success_count} fail={row.failure_count} open={row.open_count} "
                f"branches={row.branch_count} updated={row.latest_timestamp or '<unknown>'}"
            )

    lines.extend(["", "Recent runs:"])
    if not snapshot.recent_runs:
        lines.append("No runs captured.")
    else:
        for row in snapshot.recent_runs:
            task_label = "/".join(
                value for value in (row.task_family, row.task_type) if isinstance(value, str) and value
            ) or "<unclassified>"
            builders = ",".join(row.ready_builders) if row.ready_builders else "<none>"
            semantics = ",".join(row.semantic_kinds) if row.semantic_kinds else "<none>"
            lines.append(
                f"- {row.run_id} session={row.session_id} level={row.evidence_level} "
                f"task={task_label} builders={builders} semantics={semantics}"
            )

    lines.extend(["", "Workflow runs:"])
    if not snapshot.workflow_runs:
        lines.append("No workflow rows computed.")
    else:
        for row in snapshot.workflow_runs:
            blockers = ", ".join(row.blockers[:2]) if row.blockers else "<none>"
            lines.append(
                f"- {row.run_id} stage={row.stage} review={row.review_status} "
                f"next={row.next_action} blockers={blockers}"
            )

    lines.extend(["", "Slices:"])
    if not snapshot.slices:
        lines.append("No slices registered.")
    else:
        for row in snapshot.slices:
            lines.append(
                f"- {row.slice_id} risk={row.risk_level} use={row.default_use} "
                f"cohorts={row.frozen_cohorts} snapshots={row.dataset_snapshots} "
                f"eval={row.active_eval_suites} verdict={row.latest_scorecard_verdict or '<none>'} "
                f"promotion={row.latest_promotion_decision or '<none>'} "
                f"feedback_open={row.feedback_open}"
            )
    return "\n".join(lines)


def _aggregate_session_evidence(run_rows: list[DashboardRunRow]) -> str:
    if not run_rows:
        return "E0"
    if all(row.evidence_level == "E2" for row in run_rows):
        return "E2"
    if all(row.evidence_level in {"E1", "E2"} for row in run_rows):
        return "E1"
    return "E0"


def _select_dashboard_builders(builders: list, *, builder: str | None) -> list:
    if builder is not None:
        return list(builders)
    return [item for item in builders if item.builder != "facts"]


def _build_run_evidence(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> _RunEvidence:
    e1_summary = summarize_e1_annotations(facts=facts, artifacts=artifacts)
    if len(e1_summary["runs"]) != 1:
        raise ValueError("run evidence expects one run scope")
    run_id = next(iter(e1_summary["runs"]))
    run_summary = e1_summary["runs"][run_id]
    fields = run_summary["fields"]
    semantic_kinds = _semantic_kinds(facts)
    decision_signals = set(semantic_kinds) & E2_DECISION_SIGNAL_KINDS
    e1_ready = bool(run_summary["ready"])
    e2_ready = e1_ready and "task_completed" in decision_signals and len(decision_signals) >= 2
    return _RunEvidence(
        level="E2" if e2_ready else ("E1" if e1_ready else "E0"),
        e1_ready=e1_ready,
        e2_ready=e2_ready,
        semantic_kinds=semantic_kinds,
        task_family=_string_value(fields.get("task_family")),
        task_type=_string_value(fields.get("task_type")),
        task_instance_key=_string_value(fields.get("task_instance_key")),
    )


def _build_workflow_run_row(
    *,
    run_row: DashboardRunRow,
    session_inspect_summary: Any,
    artifacts: list[ArtifactRecord],
    feedback_reasons: list[str],
) -> DashboardWorkflowRunRow:
    annotation_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == E1_ANNOTATION_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == E1_ANNOTATION_KIND
    ]
    resolved_fields, annotation_artifact_ids = resolve_e1_annotation_for_run(
        session_id=run_row.session_id,
        run_id=run_row.run_id,
        artifacts=annotation_artifacts,
    )
    annotation_lookup = {artifact.artifact_id: artifact for artifact in annotation_artifacts}
    current_annotation = next(
        (
            annotation_lookup[artifact_id]
            for artifact_id in reversed(annotation_artifact_ids)
            if artifact_id in annotation_lookup
        ),
        None,
    )
    quality_confidence = _float_value(resolved_fields.get("quality_confidence"))
    verifier_score = _float_value(resolved_fields.get("verifier_score"))
    prepare_payload, _ = resolve_prepare_annotation_for_run(
        session_id=run_row.session_id,
        run_id=run_row.run_id,
        artifacts=artifacts,
    )
    prepare_artifact = get_prepare_artifact_for_run(
        session_id=run_row.session_id,
        run_id=run_row.run_id,
        artifacts=artifacts,
    )
    prepare_status = _string_value(prepare_payload.get("prepare_status"))
    prepare_blockers = _string_list(prepare_payload.get("blocker_reasons"))
    prepare_reviews = _string_list(prepare_payload.get("review_reasons"))
    review_reasons = list(feedback_reasons)
    annotation_review_reasons = resolved_fields.get("review_reasons")
    if isinstance(annotation_review_reasons, list):
        review_reasons.extend(
            value
            for value in annotation_review_reasons
            if isinstance(value, str) and value
        )
    review_reasons.extend(prepare_reviews)
    if (
        quality_confidence is not None
        and quality_confidence < WORKFLOW_QUALITY_THRESHOLD
    ):
        review_reasons.append(
            f"quality_confidence={quality_confidence:.2f} 低于 {WORKFLOW_QUALITY_THRESHOLD:.2f}"
        )
    if verifier_score is not None and verifier_score < WORKFLOW_VERIFIER_THRESHOLD:
        review_reasons.append(
            f"verifier_score={verifier_score:.2f} 低于 {WORKFLOW_VERIFIER_THRESHOLD:.2f}"
        )

    blockers: list[str] = []
    trajectory_status = "ready"
    if prepare_blockers:
        blockers.extend(prepare_blockers)
        trajectory_status = "blocked"
    if run_row.request_count == 0:
        blockers.append("没有捕获到请求跨度")
        trajectory_status = "blocked"
    if run_row.open_count > 0:
        blockers.append(f"仍有 {run_row.open_count} 个请求未闭合")
        trajectory_status = "blocked"
    if (
        session_inspect_summary.branch_count > 0
        and session_inspect_summary.declared_branch_count == 0
    ):
        blockers.append("关键分支仍主要依赖推断恢复")
    if run_row.evidence_level == "E0":
        missing_fields = [
            field
            for field in E1_REQUIRED_FIELDS
            if resolved_fields.get(field) in {None, ""}
        ]
        if missing_fields:
            blockers.append(f"缺少标签字段：{', '.join(missing_fields[:3])}")
    if not run_row.ready_builders and run_row.evidence_level in {"E1", "E2"}:
        readiness_blockers = sorted(
            {
                blocker
                for values in run_row.readiness_blockers.values()
                for blocker in values
            }
        )
        blockers.extend(readiness_blockers[:2])
    secret_match_count = int(prepare_payload.get("secret_match_count") or 0)
    if secret_match_count > 0:
        review_reasons.append(f"检测到 {secret_match_count} 处疑似敏感信息")
    if prepare_status == "review" and prepare_artifact is not None and not prepare_reviews:
        review_reasons.append("数据准备环节要求人工复核")

    blocking_review_reasons = [
        reason
        for reason in _dedupe(review_reasons)
        if reason not in NON_BLOCKING_WORKFLOW_REVIEW_REASONS
    ]

    human_reviewed = (
        current_annotation is not None
        and (
            current_annotation.supersedes_artifact_id is not None
            or current_annotation.producer.startswith("human")
            or current_annotation.producer.startswith("manual")
        )
    )
    review_status = (
        "feedback"
        if feedback_reasons
        else "human"
        if human_reviewed and not blocking_review_reasons
        else "review"
        if blocking_review_reasons
        else "clean"
    )
    has_review = bool(blocking_review_reasons)
    if trajectory_status == "blocked":
        stage = "capture"
        stage_label = "采集中"
        stage_detail = "真实请求已经进入系统，但这次运行还没形成稳定闭环。"
        next_action = "先等待运行闭合，或在回放里定位 open span。"
    elif run_row.evidence_level == "E0":
        stage = "annotate"
        stage_label = "待补标签"
        stage_detail = "运行已经采集完成，但还不能直接进入训练样本池。"
        next_action = "补 task_instance、模板 hash、质量分和 verifier。"
    elif has_review:
        stage = "review"
        stage_label = "待复核"
        stage_detail = "自动判断已给出低置信或回流信号，需要人工确认。"
        next_action = "复核 judge 结果，必要时 supersede 或送回反馈队列。"
    elif run_row.evidence_level == "E2" and run_row.ready_builders:
        stage = "evaluate"
        stage_label = "可评估"
        stage_detail = "这次运行的数据和决策证据都已齐，可以进入导出与评测。"
        next_action = "冻结 cohort，导出快照，并发起对比评测。"
    elif run_row.ready_builders:
        stage = "dataset"
        stage_label = "可导出"
        stage_detail = "这次运行已经满足训练样本的最小要求。"
        next_action = "检查样本口径后导出数据，或送入候选池。"
    else:
        stage = "augment"
        stage_label = "待补监督"
        stage_detail = "任务标签已齐，但当前 builder 仍受阻。"
        next_action = "补 score、preference 或 run 级 reward，再进入导出。"

    return DashboardWorkflowRunRow(
        session_id=run_row.session_id,
        run_id=run_row.run_id,
        latest_timestamp=run_row.latest_timestamp,
        evidence_level=run_row.evidence_level,
        stage=stage,
        stage_label=stage_label,
        stage_detail=stage_detail,
        next_action=next_action,
        trajectory_status=trajectory_status,
        review_status=review_status,
        feedback_count=len(feedback_reasons),
        quality_confidence=quality_confidence,
        verifier_score=verifier_score,
        annotation_artifact_id=current_annotation.artifact_id if current_annotation else None,
        annotation_producer=current_annotation.producer if current_annotation else None,
        annotation_version=(
            _string_value(resolved_fields.get("annotation_version"))
            or (current_annotation.version if current_annotation is not None else None)
        ),
        supersedes_artifact_id=(
            current_annotation.supersedes_artifact_id if current_annotation is not None else None
        ),
        source_channel=_string_value(resolved_fields.get("source_channel")),
        ready_builders=list(run_row.ready_builders),
        blockers=_dedupe(blockers),
        review_reasons=_dedupe(review_reasons),
    )


def _semantic_kinds(facts: list[FactEvent]) -> list[str]:
    return sorted(
        {
            semantic_kind
            for fact in facts
            for semantic_kind in [_semantic_kind(fact)]
            if semantic_kind is not None
        }
    )


def _semantic_kind(fact: FactEvent) -> str | None:
    if fact.kind != "semantic_event":
        return None
    value = fact.payload.get("semantic_kind")
    return value if isinstance(value, str) and value else None


def _load_run_scope_artifacts(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str,
) -> list[ArtifactRecord]:
    session_artifacts = store.list_artifacts(session_id=session_id, latest_only=True)
    session_target = f"session:{session_id}"
    run_target = f"run:{run_id}"
    filtered: list[ArtifactRecord] = []
    for artifact in session_artifacts:
        if artifact.run_id == run_id:
            filtered.append(artifact)
            continue
        if artifact.target_ref == run_target:
            filtered.append(artifact)
            continue
        if artifact.run_id is None and (
            artifact.target_ref == session_target or not artifact.target_ref.startswith("run:")
        ):
            filtered.append(artifact)
    return filtered


def _latest_timestamp(facts: list[FactEvent]) -> str | None:
    if not facts:
        return None
    return max(fact.timestamp for fact in facts).isoformat()


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _feedback_by_run(feedback_items: list[Any]) -> dict[str, list[str]]:
    feedback_by_run: dict[str, list[str]] = {}
    for item in feedback_items:
        if getattr(item, "status", None) != "queued":
            continue
        run_id = _run_id_from_target_ref(item.target_ref)
        if run_id is None:
            continue
        feedback_by_run.setdefault(run_id, []).append(item.reason)
    return feedback_by_run


def _run_id_from_target_ref(target_ref: str | None) -> str | None:
    if not isinstance(target_ref, str) or not target_ref.startswith("run:"):
        return None
    return target_ref.removeprefix("run:") or None


def _sort_workflow_rows(rows: list[DashboardWorkflowRunRow]) -> list[DashboardWorkflowRunRow]:
    priority = {
        "review": 0,
        "capture": 1,
        "annotate": 2,
        "augment": 3,
        "dataset": 4,
        "evaluate": 5,
    }
    return sorted(
        rows,
        key=lambda row: (
            priority.get(row.stage, 99),
            "" if row.latest_timestamp is None else f"-{row.latest_timestamp}",
            row.run_id,
        ),
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
