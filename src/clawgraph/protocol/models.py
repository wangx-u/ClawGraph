"""Core protocol models for ClawGraph."""

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


@dataclass(slots=True)
class SliceRecord:
    """Stable task slice definition used by cohort curation."""

    slice_id: str
    schema_version: str
    task_family: str
    task_type: str
    taxonomy_version: str
    sample_unit: str
    verifier_contract: str
    risk_level: str
    default_use: str
    owner: str
    description: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "schema_version": self.schema_version,
            "task_family": self.task_family,
            "task_type": self.task_type,
            "taxonomy_version": self.taxonomy_version,
            "sample_unit": self.sample_unit,
            "verifier_contract": self.verifier_contract,
            "risk_level": self.risk_level,
            "default_use": self.default_use,
            "owner": self.owner,
            "description": self.description,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class CohortRecord:
    """Frozen cohort manifest referencing one or more registered slices."""

    cohort_id: str
    schema_version: str
    name: str
    status: str
    slice_ids: list[str]
    manifest: dict[str, Any]
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "schema_version": self.schema_version,
            "name": self.name,
            "status": self.status,
            "slice_ids": list(self.slice_ids),
            "manifest": self.manifest,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class CohortMemberRecord:
    """One run-level member captured inside a frozen cohort."""

    member_id: str
    cohort_id: str
    slice_id: str
    session_id: str
    run_id: str
    annotation_artifact_id: str
    task_instance_key: str
    task_template_hash: str | None = None
    quality_confidence: float | None = None
    verifier_score: float | None = None
    source_channel: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "cohort_id": self.cohort_id,
            "slice_id": self.slice_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "annotation_artifact_id": self.annotation_artifact_id,
            "task_instance_key": self.task_instance_key,
            "task_template_hash": self.task_template_hash,
            "quality_confidence": self.quality_confidence,
            "verifier_score": self.verifier_score,
            "source_channel": self.source_channel,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class DatasetSnapshotRecord:
    """Persisted dataset snapshot manifest for one export."""

    dataset_snapshot_id: str
    schema_version: str
    dataset_recipe_id: str
    builder: str
    sample_unit: str
    cohort_id: str | None = None
    output_path: str | None = None
    record_count: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "schema_version": self.schema_version,
            "dataset_recipe_id": self.dataset_recipe_id,
            "builder": self.builder,
            "sample_unit": self.sample_unit,
            "cohort_id": self.cohort_id,
            "output_path": self.output_path,
            "record_count": self.record_count,
            "manifest": self.manifest,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class EvalSuiteRecord:
    """Persisted evaluation suite bound to one slice and asset source."""

    eval_suite_id: str
    schema_version: str
    slice_id: str
    suite_kind: str
    name: str
    status: str
    cohort_id: str | None = None
    dataset_snapshot_id: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_suite_id": self.eval_suite_id,
            "schema_version": self.schema_version,
            "slice_id": self.slice_id,
            "suite_kind": self.suite_kind,
            "name": self.name,
            "status": self.status,
            "cohort_id": self.cohort_id,
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "manifest": self.manifest,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ScorecardRecord:
    """Persisted evaluation scorecard for one model comparison."""

    scorecard_id: str
    schema_version: str
    eval_suite_id: str
    slice_id: str
    candidate_model: str
    baseline_model: str
    verdict: str
    metrics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scorecard_id": self.scorecard_id,
            "schema_version": self.schema_version,
            "eval_suite_id": self.eval_suite_id,
            "slice_id": self.slice_id,
            "candidate_model": self.candidate_model,
            "baseline_model": self.baseline_model,
            "verdict": self.verdict,
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class PromotionDecisionRecord:
    """Persisted rollout decision produced from one scorecard."""

    promotion_decision_id: str
    schema_version: str
    slice_id: str
    scorecard_id: str
    stage: str
    decision: str
    coverage_policy_version: str
    summary: str
    rollback_conditions: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promotion_decision_id": self.promotion_decision_id,
            "schema_version": self.schema_version,
            "slice_id": self.slice_id,
            "scorecard_id": self.scorecard_id,
            "stage": self.stage,
            "decision": self.decision,
            "coverage_policy_version": self.coverage_policy_version,
            "summary": self.summary,
            "rollback_conditions": list(self.rollback_conditions),
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TrainingAssetRecord:
    """Persisted training asset used to reconstruct request/candidate/eval/handoff lineage."""

    asset_id: str
    schema_version: str
    asset_kind: str
    title: str
    status: str
    manifest: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    training_request_id: str | None = None
    candidate_model_id: str | None = None
    eval_suite_id: str | None = None
    dataset_snapshot_id: str | None = None
    scorecard_id: str | None = None
    promotion_decision_id: str | None = None
    slice_id: str | None = None
    manifest_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "schema_version": self.schema_version,
            "asset_kind": self.asset_kind,
            "title": self.title,
            "status": self.status,
            "manifest": self.manifest,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "training_request_id": self.training_request_id,
            "candidate_model_id": self.candidate_model_id,
            "eval_suite_id": self.eval_suite_id,
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "scorecard_id": self.scorecard_id,
            "promotion_decision_id": self.promotion_decision_id,
            "slice_id": self.slice_id,
            "manifest_path": self.manifest_path,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class FeedbackQueueRecord:
    """Persisted feedback item that should flow back into curation/training."""

    feedback_id: str
    schema_version: str
    slice_id: str
    source: str
    status: str
    target_ref: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "schema_version": self.schema_version,
            "slice_id": self.slice_id,
            "source": self.source,
            "status": self.status,
            "target_ref": self.target_ref,
            "reason": self.reason,
            "payload": self.payload,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
            "metadata": self.metadata,
        }
