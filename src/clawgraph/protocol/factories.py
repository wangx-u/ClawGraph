"""Factory helpers for protocol records."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from clawgraph.protocol.models import (
    ArtifactRecord,
    CohortMemberRecord,
    CohortRecord,
    DatasetSnapshotRecord,
    EvalSuiteRecord,
    FactEvent,
    FeedbackQueueRecord,
    PromotionDecisionRecord,
    ScorecardRecord,
    SliceRecord,
    TrainingAssetRecord,
)
from clawgraph.protocol.validation import (
    validate_artifact_record,
    validate_cohort_member_record,
    validate_cohort_record,
    validate_dataset_snapshot_record,
    validate_eval_suite_record,
    validate_fact_event,
    validate_feedback_queue_record,
    validate_promotion_decision_record,
    validate_scorecard_record,
    validate_slice_record,
    validate_training_asset_record,
)


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


def new_slice_record(
    *,
    slice_id: str,
    task_family: str,
    task_type: str,
    taxonomy_version: str,
    sample_unit: str,
    verifier_contract: str,
    risk_level: str,
    default_use: str,
    owner: str,
    description: str | None = None,
    metadata: dict | None = None,
) -> SliceRecord:
    """Create one slice registry record with standard defaults."""

    slice_record = SliceRecord(
        slice_id=slice_id,
        schema_version="v1",
        task_family=task_family,
        task_type=task_type,
        taxonomy_version=taxonomy_version,
        sample_unit=sample_unit,
        verifier_contract=verifier_contract,
        risk_level=risk_level,
        default_use=default_use,
        owner=owner,
        description=description,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_slice_record(slice_record)
    return slice_record


def new_cohort_record(
    *,
    name: str,
    slice_ids: list[str],
    manifest: dict,
    cohort_id: str | None = None,
    status: str = "frozen",
    metadata: dict | None = None,
) -> CohortRecord:
    """Create one frozen cohort record with standard defaults."""

    cohort = CohortRecord(
        cohort_id=cohort_id or f"cohort_{uuid4().hex}",
        schema_version="v1",
        name=name,
        status=status,
        slice_ids=list(slice_ids),
        manifest=manifest,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_cohort_record(cohort)
    return cohort


def new_cohort_member_record(
    *,
    cohort_id: str,
    slice_id: str,
    session_id: str,
    run_id: str,
    annotation_artifact_id: str,
    task_instance_key: str,
    task_template_hash: str | None = None,
    quality_confidence: float | None = None,
    verifier_score: float | None = None,
    source_channel: str | None = None,
    metadata: dict | None = None,
) -> CohortMemberRecord:
    """Create one cohort membership record with standard defaults."""

    member = CohortMemberRecord(
        member_id=f"cm_{uuid4().hex}",
        cohort_id=cohort_id,
        slice_id=slice_id,
        session_id=session_id,
        run_id=run_id,
        annotation_artifact_id=annotation_artifact_id,
        task_instance_key=task_instance_key,
        task_template_hash=task_template_hash,
        quality_confidence=quality_confidence,
        verifier_score=verifier_score,
        source_channel=source_channel,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_cohort_member_record(member)
    return member


def new_dataset_snapshot_record(
    *,
    dataset_recipe_id: str,
    builder: str,
    sample_unit: str,
    output_path: str | None,
    record_count: int,
    manifest: dict,
    cohort_id: str | None = None,
    metadata: dict | None = None,
    dataset_snapshot_id: str | None = None,
) -> DatasetSnapshotRecord:
    """Create one dataset snapshot record with standard defaults."""

    snapshot = DatasetSnapshotRecord(
        dataset_snapshot_id=dataset_snapshot_id or f"ds_{uuid4().hex}",
        schema_version="v1",
        dataset_recipe_id=dataset_recipe_id,
        builder=builder,
        sample_unit=sample_unit,
        cohort_id=cohort_id,
        output_path=output_path,
        record_count=record_count,
        manifest=manifest,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_dataset_snapshot_record(snapshot)
    return snapshot


def new_eval_suite_record(
    *,
    slice_id: str,
    suite_kind: str,
    name: str,
    status: str = "active",
    cohort_id: str | None = None,
    dataset_snapshot_id: str | None = None,
    manifest: dict | None = None,
    metadata: dict | None = None,
    eval_suite_id: str | None = None,
) -> EvalSuiteRecord:
    """Create one evaluation suite record with standard defaults."""

    suite = EvalSuiteRecord(
        eval_suite_id=eval_suite_id or f"eval_{uuid4().hex}",
        schema_version="v1",
        slice_id=slice_id,
        suite_kind=suite_kind,
        name=name,
        status=status,
        cohort_id=cohort_id,
        dataset_snapshot_id=dataset_snapshot_id,
        manifest=manifest or {},
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_eval_suite_record(suite)
    return suite


def new_scorecard_record(
    *,
    eval_suite_id: str,
    slice_id: str,
    candidate_model: str,
    baseline_model: str,
    verdict: str,
    metrics: dict,
    thresholds: dict,
    metadata: dict | None = None,
    scorecard_id: str | None = None,
) -> ScorecardRecord:
    """Create one scorecard record with standard defaults."""

    scorecard = ScorecardRecord(
        scorecard_id=scorecard_id or f"score_{uuid4().hex}",
        schema_version="v1",
        eval_suite_id=eval_suite_id,
        slice_id=slice_id,
        candidate_model=candidate_model,
        baseline_model=baseline_model,
        verdict=verdict,
        metrics=metrics,
        thresholds=thresholds,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_scorecard_record(scorecard)
    return scorecard


def new_promotion_decision_record(
    *,
    slice_id: str,
    scorecard_id: str,
    stage: str,
    decision: str,
    coverage_policy_version: str,
    summary: str,
    rollback_conditions: list[str] | None = None,
    metadata: dict | None = None,
    promotion_decision_id: str | None = None,
) -> PromotionDecisionRecord:
    """Create one promotion decision with standard defaults."""

    record = PromotionDecisionRecord(
        promotion_decision_id=promotion_decision_id or f"promo_{uuid4().hex}",
        schema_version="v1",
        slice_id=slice_id,
        scorecard_id=scorecard_id,
        stage=stage,
        decision=decision,
        coverage_policy_version=coverage_policy_version,
        summary=summary,
        rollback_conditions=rollback_conditions or [],
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_promotion_decision_record(record)
    return record


def new_training_asset_record(
    *,
    asset_id: str,
    asset_kind: str,
    title: str,
    status: str,
    manifest: dict,
    training_request_id: str | None = None,
    candidate_model_id: str | None = None,
    eval_suite_id: str | None = None,
    dataset_snapshot_id: str | None = None,
    scorecard_id: str | None = None,
    promotion_decision_id: str | None = None,
    slice_id: str | None = None,
    manifest_path: str | None = None,
    metadata: dict | None = None,
) -> TrainingAssetRecord:
    """Create one persisted training asset record with standard defaults."""

    record = TrainingAssetRecord(
        asset_id=asset_id,
        schema_version="v1",
        asset_kind=asset_kind,
        title=title,
        status=status,
        manifest=manifest,
        created_at=datetime.now(UTC),
        training_request_id=training_request_id,
        candidate_model_id=candidate_model_id,
        eval_suite_id=eval_suite_id,
        dataset_snapshot_id=dataset_snapshot_id,
        scorecard_id=scorecard_id,
        promotion_decision_id=promotion_decision_id,
        slice_id=slice_id,
        manifest_path=manifest_path,
        metadata=metadata or {},
    )
    validate_training_asset_record(record)
    return record


def new_feedback_queue_record(
    *,
    slice_id: str,
    source: str,
    target_ref: str,
    reason: str,
    payload: dict | None = None,
    status: str = "queued",
    metadata: dict | None = None,
    feedback_id: str | None = None,
) -> FeedbackQueueRecord:
    """Create one feedback queue item with standard defaults."""

    record = FeedbackQueueRecord(
        feedback_id=feedback_id or f"fb_{uuid4().hex}",
        schema_version="v1",
        slice_id=slice_id,
        source=source,
        status=status,
        target_ref=target_ref,
        reason=reason,
        payload=payload or {},
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )
    validate_feedback_queue_record(record)
    return record
