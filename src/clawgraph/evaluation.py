"""Evaluation, promotion, and feedback helpers."""

from __future__ import annotations

from typing import Any

from clawgraph.protocol.factories import (
    new_eval_suite_record,
    new_feedback_queue_record,
    new_promotion_decision_record,
    new_scorecard_record,
)
from clawgraph.protocol.models import (
    EvalSuiteRecord,
    FeedbackQueueRecord,
    PromotionDecisionRecord,
    ScorecardRecord,
)
from clawgraph.store import SQLiteFactStore


def create_eval_suite_from_cohort(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    slice_id: str,
    suite_kind: str,
    cohort_id: str,
    name: str | None = None,
    dataset_snapshot_id: str | None = None,
) -> EvalSuiteRecord:
    """Create and persist one eval suite sourced from a frozen cohort."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    slice_record = store_instance.get_slice(slice_id)
    if slice_record is None:
        raise ValueError(f"slice not found: {slice_id}")
    cohort = store_instance.get_cohort(cohort_id)
    if cohort is None:
        raise ValueError(f"cohort not found: {cohort_id}")
    if slice_id not in cohort.slice_ids:
        raise ValueError(f"cohort {cohort_id} does not cover slice {slice_id}")
    expected_use = str(cohort.manifest.get("expected_use") or "training")
    if expected_use != "evaluation":
        raise ValueError(
            "eval suites must be created from evaluation cohorts or holdout feeds"
        )
    members = store_instance.list_cohort_members(cohort_id, slice_id=slice_id)
    if not members:
        raise ValueError(f"cohort {cohort_id} has no members for slice {slice_id}")
    if suite_kind in {"offline_test", "golden", "shadow"}:
        if dataset_snapshot_id is None:
            raise ValueError(
                f"{suite_kind} suites require dataset_snapshot_id for training isolation checks"
            )
        snapshot = store_instance.get_dataset_snapshot(dataset_snapshot_id)
        if snapshot is None:
            raise ValueError(f"dataset snapshot not found: {dataset_snapshot_id}")
        overlap = _training_overlap(snapshot_manifest=snapshot.manifest, members=members)
        if any(overlap.values()):
            raise ValueError(
                "eval cohort overlaps training snapshot on frozen governance keys: "
                f"{overlap}"
            )
        if suite_kind == "shadow" and _time_window_not_later(
            training_range=snapshot.manifest.get("time_range"),
            eval_range=cohort.manifest.get("time_range"),
        ):
            raise ValueError("shadow suite must come from a later time window than training")
    else:
        snapshot = (
            store_instance.get_dataset_snapshot(dataset_snapshot_id)
            if dataset_snapshot_id is not None
            else None
        )

    suite = new_eval_suite_record(
        slice_id=slice_id,
        suite_kind=suite_kind,
        name=name or f"{slice_id}-{suite_kind}",
        cohort_id=cohort_id,
        dataset_snapshot_id=dataset_snapshot_id,
        manifest={
            "slice_id": slice_id,
            "cohort_id": cohort_id,
            "dataset_snapshot_id": dataset_snapshot_id,
            "run_count": len({member.run_id for member in members}),
            "session_count": len({member.session_id for member in members}),
            "task_instance_count": len(
                {member.task_instance_key for member in members}
            ),
            "suite_kind": suite_kind,
            "expected_use": expected_use,
            "time_range": cohort.manifest.get("time_range"),
            "training_isolation": (
                {
                    "dataset_snapshot_id": dataset_snapshot_id,
                    "source_cohort_id": snapshot.cohort_id if snapshot is not None else None,
                    "overlap": {
                        "run_ids": [],
                        "task_instance_keys": [],
                        "task_template_hashes": [],
                    },
                }
                if dataset_snapshot_id is not None
                else None
            ),
        },
        metadata={
            "source": "cohort",
            "default_use": slice_record.default_use,
        },
    )
    store_instance.append_eval_suite(suite)
    return suite


def record_scorecard(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    eval_suite_id: str,
    candidate_model: str,
    baseline_model: str,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> ScorecardRecord:
    """Create and persist one scorecard with a derived verdict."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    suite = store_instance.get_eval_suite(eval_suite_id)
    if suite is None:
        raise ValueError(f"eval suite not found: {eval_suite_id}")
    verdict = _resolve_scorecard_verdict(metrics=metrics, thresholds=thresholds)
    scorecard = new_scorecard_record(
        eval_suite_id=eval_suite_id,
        slice_id=suite.slice_id,
        candidate_model=candidate_model,
        baseline_model=baseline_model,
        verdict=verdict,
        metrics=metrics,
        thresholds=thresholds,
    )
    store_instance.append_scorecard(scorecard)
    return scorecard


def record_promotion_decision(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    scorecard_id: str,
    stage: str,
    coverage_policy_version: str,
    summary: str,
    rollback_conditions: list[str] | None = None,
    decision: str | None = None,
) -> PromotionDecisionRecord:
    """Create and persist one promotion decision from a scorecard."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    scorecard = store_instance.get_scorecard(scorecard_id)
    if scorecard is None:
        raise ValueError(f"scorecard not found: {scorecard_id}")
    resolved_decision = decision or {
        "pass": "promote",
        "hold": "hold",
        "fail": "rollback",
    }[scorecard.verdict]
    record = new_promotion_decision_record(
        slice_id=scorecard.slice_id,
        scorecard_id=scorecard_id,
        stage=stage,
        decision=resolved_decision,
        coverage_policy_version=coverage_policy_version,
        summary=summary,
        rollback_conditions=rollback_conditions or [],
        metadata={
            "eval_suite_id": scorecard.eval_suite_id,
            "scorecard_verdict": scorecard.verdict,
        },
    )
    store_instance.append_promotion_decision(record)
    return record


def enqueue_feedback(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    slice_id: str,
    source: str,
    target_ref: str,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> FeedbackQueueRecord:
    """Create and persist one feedback queue item."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    if store_instance.get_slice(slice_id) is None:
        raise ValueError(f"slice not found: {slice_id}")
    feedback = new_feedback_queue_record(
        slice_id=slice_id,
        source=source,
        target_ref=target_ref,
        reason=reason,
        payload=payload or {},
    )
    store_instance.append_feedback_queue_item(feedback)
    return feedback


def _resolve_scorecard_verdict(
    *,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> str:
    if not thresholds:
        return "hold"
    for metric_name, threshold in thresholds.items():
        metric_value = metrics.get(metric_name)
        if not isinstance(metric_value, (int, float)) or isinstance(metric_value, bool):
            return "fail"
        if not isinstance(threshold, dict):
            return "hold"
        op = threshold.get("op")
        threshold_value = threshold.get("value")
        if not isinstance(threshold_value, (int, float)) or isinstance(threshold_value, bool):
            return "hold"
        if op == "gte" and metric_value < threshold_value:
            return "fail"
        if op == "lte" and metric_value > threshold_value:
            return "fail"
        if op not in {"gte", "lte"}:
            return "hold"
    return "pass"


def _training_overlap(
    *,
    snapshot_manifest: dict[str, Any],
    members: list[Any],
) -> dict[str, list[str]]:
    training_run_ids = _manifest_values(snapshot_manifest, "source_run_ids")
    training_instance_keys = _manifest_values(snapshot_manifest, "task_instance_keys")
    training_template_hashes = _manifest_values(snapshot_manifest, "task_template_hashes")
    eval_run_ids = {member.run_id for member in members}
    eval_instance_keys = {member.task_instance_key for member in members}
    eval_template_hashes = {
        member.task_template_hash
        for member in members
        if isinstance(member.task_template_hash, str) and member.task_template_hash
    }
    return {
        "run_ids": sorted(training_run_ids & eval_run_ids),
        "task_instance_keys": sorted(training_instance_keys & eval_instance_keys),
        "task_template_hashes": sorted(training_template_hashes & eval_template_hashes),
    }


def _manifest_values(manifest: dict[str, Any], key: str) -> set[str]:
    values = manifest.get(key)
    if not isinstance(values, list):
        return set()
    return {
        value
        for value in values
        if isinstance(value, str) and value
    }


def _time_window_not_later(
    *,
    training_range: Any,
    eval_range: Any,
) -> bool:
    if not isinstance(training_range, dict) or not isinstance(eval_range, dict):
        return False
    training_end = training_range.get("end")
    eval_start = eval_range.get("start")
    if not isinstance(training_end, str) or not isinstance(eval_start, str):
        return False
    return eval_start <= training_end
