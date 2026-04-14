"""End-to-end orchestration helpers for the phase-2 governance workflow."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from clawgraph.artifacts import (
    E1_ANNOTATION_ARTIFACT_TYPE,
    E1_ANNOTATION_KIND,
    E1_REQUIRED_FIELDS,
    resolve_e1_annotation_for_run,
)
from clawgraph.curation import CohortFreezeResult, freeze_cohort, preview_slice_review_queue
from clawgraph.dashboard import inspect_run_workflow
from clawgraph.evaluation import (
    create_eval_suite_from_cohort,
    derive_eval_scorecard_inputs,
    record_promotion_decision,
    record_scorecard,
    sync_feedback_queue_from_slice_review,
)
from clawgraph.export import export_dataset, plan_dataset_export
from clawgraph.judge import plan_judge_annotation
from clawgraph.prepare import (
    DEFAULT_PREPARE_VERSION,
    PrepareRunPlan,
    get_prepare_artifact_for_run,
    plan_prepare_run_artifact,
)
from clawgraph.protocol.factories import new_cohort_member_record, new_cohort_record, new_slice_record
from clawgraph.protocol.models import (
    ArtifactRecord,
    CohortMemberRecord,
    CohortRecord,
    DatasetSnapshotRecord,
    EvalSuiteRecord,
    FeedbackQueueRecord,
    PromotionDecisionRecord,
    ScorecardRecord,
    SliceRecord,
)
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


@dataclass(slots=True)
class Phase2ExportResult:
    """One dataset export result inside the automated phase-2 workflow."""

    builder: str
    planned: dict[str, Any]
    exported: bool
    record_count: int
    output_path: str
    manifest_path: str
    dataset_snapshot: DatasetSnapshotRecord | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder": self.builder,
            "planned": dict(self.planned),
            "exported": self.exported,
            "record_count": self.record_count,
            "output_path": self.output_path,
            "manifest_path": self.manifest_path,
            "dataset_snapshot": None if self.dataset_snapshot is None else self.dataset_snapshot.to_dict(),
        }


@dataclass(slots=True)
class Phase2RunResult:
    """Complete outcome of one phase-2 automation run."""

    session_id: str
    run_id: str
    selection_scope: str
    dry_run: bool
    prepare_plan: PrepareRunPlan
    prepare_persisted: bool
    judge_plan: dict[str, Any] | None
    judge_persisted: bool
    slice_record: SliceRecord | None
    slice_created: bool
    feedback_sync: dict[str, Any] | None
    workflow_before: dict[str, Any]
    workflow_after: dict[str, Any]
    training_cohort: CohortRecord | None
    training_members: list[CohortMemberRecord]
    exports: list[Phase2ExportResult]
    evaluation_cohort: CohortRecord | None
    evaluation_members: list[CohortMemberRecord]
    eval_suite: EvalSuiteRecord | None
    scorecard: ScorecardRecord | None
    promotion: PromotionDecisionRecord | None
    warnings: list[str]
    next_action: str
    stopped_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "selection_scope": self.selection_scope,
            "dry_run": self.dry_run,
            "prepare": {
                "persisted": self.prepare_persisted,
                **self.prepare_plan.to_dict(),
            },
            "judge": None
            if self.judge_plan is None
            else {
                "persisted": self.judge_persisted,
                **self.judge_plan,
            },
            "slice": None
            if self.slice_record is None
            else {
                "created": self.slice_created,
                "record": self.slice_record.to_dict(),
            },
            "feedback_sync": self.feedback_sync,
            "workflow_before": dict(self.workflow_before),
            "workflow_after": dict(self.workflow_after),
            "training_cohort": None if self.training_cohort is None else self.training_cohort.to_dict(),
            "training_member_count": len(self.training_members),
            "exports": [item.to_dict() for item in self.exports],
            "evaluation_cohort": (
                None if self.evaluation_cohort is None else self.evaluation_cohort.to_dict()
            ),
            "evaluation_member_count": len(self.evaluation_members),
            "eval_suite": None if self.eval_suite is None else self.eval_suite.to_dict(),
            "scorecard": None if self.scorecard is None else self.scorecard.to_dict(),
            "promotion": None if self.promotion is None else self.promotion.to_dict(),
            "warnings": list(self.warnings),
            "next_action": self.next_action,
            "stopped_reason": self.stopped_reason,
        }


def run_phase2_workflow(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    session: str | None = "latest",
    run_id: str | None = None,
    selection_scope: str = "run",
    slice_id: str | None = None,
    slice_owner: str = "clawgraph.phase2",
    slice_default_use: str = "training_candidate",
    slice_risk_level: str = "medium",
    prepare_producer: str = "clawgraph.prepare",
    prepare_version: str | None = DEFAULT_PREPARE_VERSION,
    force_prepare: bool = False,
    judge_provider: str = "heuristic",
    judge_model: str | None = None,
    judge_api_base: str | None = None,
    judge_api_key: str | None = None,
    judge_instructions: str | None = None,
    judge_producer: str = "clawgraph.judge",
    judge_version: str | None = None,
    force_judge: bool = False,
    builders: list[str] | None = None,
    output_dir: Path | None = None,
    cohort_name: str | None = None,
    holdout_fraction: float | None = None,
    max_members_per_task_instance: int = 1,
    max_members_per_template: int | None = None,
    min_quality_confidence: float | None = None,
    min_verifier_score: float | None = None,
    create_eval_suite: bool = False,
    suite_kind: str = "offline_test",
    eval_cohort_name: str | None = None,
    eval_suite_name: str | None = None,
    scorecard_metrics: dict[str, Any] | None = None,
    scorecard_thresholds: dict[str, Any] | None = None,
    candidate_model: str | None = None,
    baseline_model: str | None = None,
    promotion_stage: str | None = None,
    coverage_policy_version: str | None = None,
    promotion_summary: str | None = None,
    feedback_source: str = "phase2.auto_review",
    dry_run: bool = False,
) -> Phase2RunResult:
    """Execute the complete phase-2 automation flow for one run or slice scope."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    query = ClawGraphQueryService(store=store_instance)
    scope = query.load_scope(session=session, run_id=run_id, default_latest_run=True)
    session_id = scope.session_id
    effective_run_id = scope.run_id or scope.facts[0].run_id
    workflow_before = inspect_run_workflow(
        store=store_instance,
        session=session_id,
        run_id=effective_run_id,
    ).to_dict()
    warnings: list[str] = []

    current_prepare = get_prepare_artifact_for_run(
        session_id=session_id,
        run_id=effective_run_id,
        artifacts=scope.artifacts,
    )
    if current_prepare is not None and not force_prepare:
        prepare_plan = PrepareRunPlan(
            session_id=session_id,
            run_id=effective_run_id,
            producer=current_prepare.producer,
            summary={
                key: value
                for key, value in current_prepare.payload.items()
                if key not in {"annotation_kind", "prepare_version", "prepare_status", "blocker_reasons", "review_reasons"}
            },
            blocker_reasons=_string_list(current_prepare.payload.get("blocker_reasons")),
            review_reasons=_string_list(current_prepare.payload.get("review_reasons")),
            artifact=current_prepare,
        )
        prepare_persisted = False
    else:
        prepare_plan = plan_prepare_run_artifact(
            facts=scope.facts,
            artifacts=scope.artifacts,
            producer=prepare_producer,
            version=prepare_version,
        )
        prepare_persisted = False
        if not dry_run:
            persisted, _ = _persist_unique_artifacts(
                store=store_instance,
                session_id=session_id,
                run_id=effective_run_id,
                artifacts=[prepare_plan.artifact],
            )
            prepare_persisted = bool(persisted)

    scope = query.load_scope(session=session_id, run_id=effective_run_id, default_latest_run=True)
    e1_fields, e1_artifact_ids = resolve_e1_annotation_for_run(
        session_id=session_id,
        run_id=effective_run_id,
        artifacts=scope.artifacts,
    )
    current_judge_artifact = _resolve_current_e1_artifact(
        session_id=session_id,
        run_id=effective_run_id,
        artifacts=scope.artifacts,
        artifact_ids=e1_artifact_ids,
    )
    judge_plan_dict: dict[str, Any] | None = None
    judge_persisted = False
    if force_judge or not e1_fields:
        judge_plan = plan_judge_annotation(
            facts=scope.facts,
            artifacts=scope.artifacts,
            producer=judge_producer,
            provider=judge_provider,
            version=judge_version,
            model=judge_model,
            api_base=judge_api_base,
            api_key=judge_api_key,
            instructions=judge_instructions,
            supersedes_artifact_id=(
                current_judge_artifact.artifact_id if current_judge_artifact is not None else None
            ),
        )
        judge_plan_dict = judge_plan.to_dict()
        if not dry_run:
            persisted, _ = _persist_unique_artifacts(
                store=store_instance,
                session_id=session_id,
                run_id=effective_run_id,
                artifacts=[judge_plan.artifact],
            )
            judge_persisted = bool(persisted)
        scope = query.load_scope(session=session_id, run_id=effective_run_id, default_latest_run=True)
        e1_fields, e1_artifact_ids = resolve_e1_annotation_for_run(
            session_id=session_id,
            run_id=effective_run_id,
            artifacts=scope.artifacts,
        )
        current_judge_artifact = _resolve_current_e1_artifact(
            session_id=session_id,
            run_id=effective_run_id,
            artifacts=scope.artifacts,
            artifact_ids=e1_artifact_ids,
        )

    slice_record = None
    slice_created = False
    e1_ready = _has_required_e1_fields(e1_fields)
    if e1_fields and not e1_ready:
        warnings.append(
            "judge annotation exists but is still missing required fields; run remains in annotate/review until those fields are complete"
        )
    if e1_ready:
        slice_record, slice_created = _ensure_slice_for_annotation(
            store=store_instance,
            fields=e1_fields,
            requested_slice_id=slice_id,
            owner=slice_owner,
            default_use=slice_default_use,
            risk_level=slice_risk_level,
        )
    elif slice_id is not None:
        slice_record = store_instance.get_slice(slice_id)

    feedback_sync = None
    if slice_record is not None:
        if dry_run:
            preview = preview_slice_review_queue(
                store=store_instance,
                slice_id=slice_record.slice_id,
                run_id=effective_run_id,
            )
            feedback_sync = {
                **preview.to_dict(),
                "persisted": False,
            }
        else:
            result = sync_feedback_queue_from_slice_review(
                store=store_instance,
                slice_id=slice_record.slice_id,
                source=feedback_source,
                run_id=effective_run_id,
            )
            feedback_sync = {
                **result.to_dict(),
                "persisted": True,
            }

    workflow_after_row = inspect_run_workflow(
        store=store_instance,
        session=session_id,
        run_id=effective_run_id,
    )
    workflow_after = workflow_after_row.to_dict()
    stopped_reason = None
    next_action = workflow_after_row.next_action
    if workflow_after_row.stage in {"capture", "annotate", "augment", "review"}:
        stopped_reason = workflow_after_row.stage
        return Phase2RunResult(
            session_id=session_id,
            run_id=effective_run_id,
            selection_scope=selection_scope,
            dry_run=dry_run,
            prepare_plan=prepare_plan,
            prepare_persisted=prepare_persisted,
            judge_plan=judge_plan_dict,
            judge_persisted=judge_persisted,
            slice_record=slice_record,
            slice_created=slice_created,
            feedback_sync=feedback_sync,
            workflow_before=workflow_before,
            workflow_after=workflow_after,
            training_cohort=None,
            training_members=[],
            exports=[],
            evaluation_cohort=None,
            evaluation_members=[],
            eval_suite=None,
            scorecard=None,
            promotion=None,
            warnings=warnings,
            next_action=next_action,
            stopped_reason=stopped_reason,
        )

    if slice_record is None:
        raise ValueError("phase2 requires either an existing or derived slice once the run is ready")

    export_builders = list(builders or workflow_after_row.ready_builders)
    if not export_builders:
        warnings.append("no ready builders were available for export")

    resolved_holdout_fraction = holdout_fraction
    if create_eval_suite and selection_scope == "slice" and resolved_holdout_fraction is None:
        resolved_holdout_fraction = 0.2

    training_result = _freeze_training_scope(
        store=store_instance,
        slice_id=slice_record.slice_id,
        selection_scope=selection_scope,
        session_id=session_id,
        run_id=effective_run_id,
        cohort_name=cohort_name,
        min_quality_confidence=min_quality_confidence,
        min_verifier_score=min_verifier_score,
        max_members_per_task_instance=max_members_per_task_instance,
        max_members_per_template=max_members_per_template,
        holdout_fraction=resolved_holdout_fraction,
        dry_run=dry_run,
    )

    exports: list[Phase2ExportResult] = []
    output_root = (output_dir or Path("out") / "phase2").resolve()
    training_snapshot = None
    if training_result is not None:
        for builder in export_builders:
            export_result = _export_for_cohort(
                store=store_instance,
                cohort=training_result.cohort,
                builder=builder,
                output_root=output_root,
                dry_run=dry_run,
            )
            exports.append(export_result)
            if training_snapshot is None and export_result.dataset_snapshot is not None:
                training_snapshot = export_result.dataset_snapshot

    evaluation_cohort = None
    evaluation_members: list[CohortMemberRecord] = []
    eval_suite = None
    scorecard = None
    promotion = None
    if create_eval_suite and training_result is not None:
        if not training_result.holdout_candidates:
            warnings.append("evaluation suite skipped because no holdout candidates were produced")
        elif training_snapshot is None and not dry_run:
            warnings.append("evaluation suite skipped because no training snapshot was exported")
        else:
            evaluation_cohort, evaluation_members = _freeze_holdout_candidates(
                store=store_instance,
                source=training_result,
                name=eval_cohort_name,
                dry_run=dry_run,
            )
            if evaluation_cohort is not None and not dry_run:
                eval_suite = create_eval_suite_from_cohort(
                    store=store_instance,
                    slice_id=slice_record.slice_id,
                    suite_kind=suite_kind,
                    cohort_id=evaluation_cohort.cohort_id,
                    name=eval_suite_name,
                    dataset_snapshot_id=(
                        training_snapshot.dataset_snapshot_id
                        if training_snapshot is not None
                        else None
                    ),
                )
                resolved_scorecard_metrics = (
                    dict(scorecard_metrics) if scorecard_metrics is not None else None
                )
                resolved_scorecard_thresholds = (
                    dict(scorecard_thresholds) if scorecard_thresholds is not None else None
                )
                scorecard_metadata: dict[str, Any] | None = None
                if resolved_scorecard_metrics is None or resolved_scorecard_thresholds is None:
                    try:
                        (
                            derived_metrics,
                            derived_thresholds,
                            derived_metadata,
                        ) = derive_eval_scorecard_inputs(
                            store=store_instance,
                            eval_suite_id=eval_suite.eval_suite_id,
                            thresholds=resolved_scorecard_thresholds,
                        )
                        if resolved_scorecard_metrics is None:
                            resolved_scorecard_metrics = derived_metrics
                        if resolved_scorecard_thresholds is None:
                            resolved_scorecard_thresholds = derived_thresholds
                        scorecard_metadata = derived_metadata
                    except ValueError as exc:
                        warnings.append(str(exc))
                if (
                    resolved_scorecard_metrics is not None
                    and resolved_scorecard_thresholds is not None
                ):
                    scorecard = record_scorecard(
                        store=store_instance,
                        eval_suite_id=eval_suite.eval_suite_id,
                        candidate_model=candidate_model or "candidate",
                        baseline_model=baseline_model or "baseline",
                        metrics=resolved_scorecard_metrics,
                        thresholds=resolved_scorecard_thresholds,
                        metadata=scorecard_metadata,
                    )
                    promotion = record_promotion_decision(
                        store=store_instance,
                        scorecard_id=scorecard.scorecard_id,
                        stage=promotion_stage or "offline",
                        coverage_policy_version=(
                            coverage_policy_version or "clawgraph.coverage.default.v1"
                        ),
                        summary=promotion_summary or f"phase2 {scorecard.verdict}",
                    )

    workflow_final = inspect_run_workflow(
        store=store_instance,
        session=session_id,
        run_id=effective_run_id,
    ).to_dict()
    return Phase2RunResult(
        session_id=session_id,
        run_id=effective_run_id,
        selection_scope=selection_scope,
        dry_run=dry_run,
        prepare_plan=prepare_plan,
        prepare_persisted=prepare_persisted,
        judge_plan=judge_plan_dict,
        judge_persisted=judge_persisted,
        slice_record=slice_record,
        slice_created=slice_created,
        feedback_sync=feedback_sync,
        workflow_before=workflow_before,
        workflow_after=workflow_final,
        training_cohort=None if training_result is None else training_result.cohort,
        training_members=[] if training_result is None else list(training_result.members),
        exports=exports,
        evaluation_cohort=evaluation_cohort,
        evaluation_members=evaluation_members,
        eval_suite=eval_suite,
        scorecard=scorecard,
        promotion=promotion,
        warnings=warnings,
        next_action=workflow_final.get("next_action") or next_action,
        stopped_reason=stopped_reason,
    )


def _freeze_training_scope(
    *,
    store: SQLiteFactStore,
    slice_id: str,
    selection_scope: str,
    session_id: str,
    run_id: str,
    cohort_name: str | None,
    min_quality_confidence: float | None,
    min_verifier_score: float | None,
    max_members_per_task_instance: int,
    max_members_per_template: int | None,
    holdout_fraction: float | None,
    dry_run: bool,
) -> CohortFreezeResult | None:
    if dry_run:
        return None
    if selection_scope not in {"run", "slice"}:
        raise ValueError("selection_scope must be one of: run, slice")
    return freeze_cohort(
        store=store,
        slice_id=slice_id,
        name=cohort_name,
        session=None if selection_scope == "slice" else session_id,
        run_id=run_id if selection_scope == "run" else None,
        min_quality_confidence=min_quality_confidence,
        min_verifier_score=min_verifier_score,
        max_members_per_task_instance=max_members_per_task_instance,
        max_members_per_template=max_members_per_template,
        holdout_fraction=holdout_fraction,
    )


def _export_for_cohort(
    *,
    store: SQLiteFactStore,
    cohort: CohortRecord,
    builder: str,
    output_root: Path,
    dry_run: bool,
) -> Phase2ExportResult:
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{cohort.cohort_id}.{builder}.jsonl"
    plan = plan_dataset_export(
        store_uri=store.store_uri,
        builder=builder,
        cohort_id=cohort.cohort_id,
        out=output_path,
    )
    exported = False
    record_count = 0
    dataset_snapshot = None
    if not dry_run and plan.ready:
        record_count = export_dataset(
            store_uri=store.store_uri,
            builder=builder,
            cohort_id=cohort.cohort_id,
            out=output_path,
        )
        exported = True
        snapshots = store.list_dataset_snapshots(cohort_id=cohort.cohort_id, builder=builder)
        dataset_snapshot = snapshots[0] if snapshots else None
    return Phase2ExportResult(
        builder=builder,
        planned=plan.to_dict(),
        exported=exported,
        record_count=record_count,
        output_path=str(output_path),
        manifest_path=str(output_path.with_name(f"{output_path.name}.manifest.json")),
        dataset_snapshot=dataset_snapshot,
    )


def _freeze_holdout_candidates(
    *,
    store: SQLiteFactStore,
    source: CohortFreezeResult,
    name: str | None,
    dry_run: bool,
) -> tuple[CohortRecord | None, list[CohortMemberRecord]]:
    if dry_run or not source.holdout_candidates:
        return None, []
    manifest = {
        "slice_ids": [source.slice_record.slice_id],
        "taxonomy_version": source.slice_record.taxonomy_version,
        "sample_unit": source.slice_record.sample_unit,
        "expected_use": "evaluation",
        "source_cohort_id": source.cohort.cohort_id,
        "source_holdout_count": len(source.holdout_candidates),
        "frozen_from": "training_holdout_feed",
        "artifact_view": {
            "strategy": "holdout_candidates",
            "annotation_artifact_ids": sorted(
                {
                    candidate.annotation_artifact_id
                    for candidate in source.holdout_candidates
                }
            ),
        },
    }
    cohort = new_cohort_record(
        name=name or f"{source.cohort.name}-eval",
        slice_ids=[source.slice_record.slice_id],
        manifest=manifest,
        metadata={
            "created_from": "phase2.holdout_feed",
            "source_cohort_id": source.cohort.cohort_id,
        },
    )
    members = [
        new_cohort_member_record(
            cohort_id=cohort.cohort_id,
            slice_id=source.slice_record.slice_id,
            session_id=candidate.session_id,
            run_id=candidate.run_id,
            annotation_artifact_id=candidate.annotation_artifact_id,
            task_instance_key=candidate.task_instance_key,
            task_template_hash=candidate.task_template_hash,
            quality_confidence=candidate.quality_confidence,
            verifier_score=candidate.verifier_score,
            source_channel=candidate.source_channel,
            metadata={
                "annotation_artifact_ids": list(candidate.annotation_artifact_ids),
                **candidate.metadata,
            },
        )
        for candidate in source.holdout_candidates
    ]
    store.append_cohort(cohort, members=members)
    return cohort, members


def _ensure_slice_for_annotation(
    *,
    store: SQLiteFactStore,
    fields: dict[str, Any],
    requested_slice_id: str | None,
    owner: str,
    default_use: str,
    risk_level: str,
) -> tuple[SliceRecord, bool]:
    task_family = _required_string(fields.get("task_family"), label="task_family")
    task_type = _required_string(fields.get("task_type"), label="task_type")
    taxonomy_version = _required_string(fields.get("taxonomy_version"), label="taxonomy_version")
    verifier_name = _required_string(fields.get("verifier_name"), label="verifier_name")
    resolved_slice_id = requested_slice_id or _derive_slice_id(
        task_family=task_family,
        task_type=task_type,
        taxonomy_version=taxonomy_version,
    )
    existing = store.get_slice(resolved_slice_id)
    slice_record = new_slice_record(
        slice_id=resolved_slice_id,
        task_family=task_family,
        task_type=task_type,
        taxonomy_version=taxonomy_version,
        sample_unit="run",
        verifier_contract=verifier_name,
        risk_level=risk_level,
        default_use=default_use,
        owner=owner,
        description=f"Auto-registered slice for {task_family}/{task_type}",
        metadata={
            "auto_registered": True,
            "source_channel": fields.get("source_channel"),
            "annotation_version": fields.get("annotation_version"),
            "min_quality_confidence": 0.8,
            "min_verifier_score": 0.8,
        },
    )
    persisted = store.put_slice(slice_record)
    return persisted, existing is None


def _derive_slice_id(*, task_family: str, task_type: str, taxonomy_version: str) -> str:
    prefix = _slug(task_family)
    suffix = _slug(task_type)
    digest = hashlib.sha1(
        f"{task_family}|{task_type}|{taxonomy_version}".encode("utf-8")
    ).hexdigest()[:8]
    return f"slice.{prefix}.{suffix}.{digest}"


def _slug(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = normalized.strip("_")
    return normalized or "unknown"


def _resolve_current_e1_artifact(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
    artifact_ids: Iterable[str],
) -> ArtifactRecord | None:
    artifact_lookup = {
        artifact.artifact_id: artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == E1_ANNOTATION_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == E1_ANNOTATION_KIND
        and artifact.session_id == session_id
        and artifact.run_id == run_id
    }
    for artifact_id in reversed(list(artifact_ids)):
        if artifact_id in artifact_lookup:
            return artifact_lookup[artifact_id]
    return None


def _artifact_signature(artifact: ArtifactRecord) -> str:
    return json.dumps(
        {
            "artifact_type": artifact.artifact_type,
            "target_ref": artifact.target_ref,
            "producer": artifact.producer,
            "version": artifact.version,
            "session_id": artifact.session_id,
            "run_id": artifact.run_id,
            "status": artifact.status,
            "payload": artifact.payload,
            "metadata": artifact.metadata,
            "supersedes_artifact_id": artifact.supersedes_artifact_id,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _persist_unique_artifacts(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> tuple[list[ArtifactRecord], int]:
    existing = store.list_artifacts(session_id=session_id, run_id=run_id, latest_only=True)
    seen = {_artifact_signature(artifact) for artifact in existing}
    persisted: list[ArtifactRecord] = []
    skipped = 0
    for artifact in artifacts:
        signature = _artifact_signature(artifact)
        if signature in seen:
            skipped += 1
            continue
        persisted.append(artifact)
        seen.add(signature)
    if persisted:
        store.append_artifacts(persisted)
    return persisted, skipped


def _required_string(value: Any, *, label: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{label} is required to build the phase2 slice")


def _has_required_e1_fields(fields: dict[str, Any]) -> bool:
    if not fields:
        return False
    return all(fields.get(field) not in {None, ""} for field in E1_REQUIRED_FIELDS)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
