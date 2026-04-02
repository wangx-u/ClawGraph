"""Runtime validation for persisted protocol records."""

from __future__ import annotations

from typing import Any

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
)

_LEGACY_BODY_REF_ENCODINGS = {"gzip", None}
_SUPPORTED_SAMPLE_UNITS = {"request", "branch", "run"}
_SUPPORTED_DEFAULT_USES = {"training_candidate", "eval_only", "diagnostics_only"}
_SUPPORTED_RISK_LEVELS = {"low", "medium", "high", "critical"}
_SUPPORTED_COHORT_STATUSES = {"draft", "frozen"}
_SUPPORTED_EVAL_SUITE_KINDS = {"offline_test", "golden", "shadow"}
_SUPPORTED_EVAL_SUITE_STATUSES = {"active", "archived"}
_SUPPORTED_SCORECARD_VERDICTS = {"pass", "hold", "fail"}
_SUPPORTED_PROMOTION_STAGES = {"offline", "shadow", "canary", "rollout"}
_SUPPORTED_PROMOTION_DECISIONS = {"promote", "hold", "rollback"}
_SUPPORTED_FEEDBACK_STATUSES = {"queued", "reviewed", "resolved"}


def validate_fact_event(fact: FactEvent) -> None:
    """Validate one fact event before it is persisted."""

    _require_non_empty_string(fact.fact_id, label="fact_id")
    _require_non_empty_string(fact.schema_version, label="schema_version")
    _require_non_empty_string(fact.run_id, label="run_id")
    _require_non_empty_string(fact.session_id, label="session_id")
    _require_non_empty_string(fact.actor, label="actor")
    _require_non_empty_string(fact.kind, label="kind")
    if not isinstance(fact.payload, dict):
        raise ValueError("fact payload must be a JSON object")
    if not isinstance(fact.metadata, dict):
        raise ValueError("fact metadata must be a JSON object")
    _validate_common_fact_payload(fact.payload)
    if fact.kind == "semantic_event":
        _validate_semantic_event_payload(fact.payload)


def validate_artifact_record(artifact: ArtifactRecord) -> None:
    """Validate one artifact record before it is persisted."""

    _require_non_empty_string(artifact.artifact_id, label="artifact_id")
    _require_non_empty_string(artifact.schema_version, label="schema_version")
    _require_non_empty_string(artifact.artifact_type, label="artifact_type")
    _require_non_empty_string(artifact.target_ref, label="target_ref")
    _require_non_empty_string(artifact.producer, label="producer")
    _require_non_empty_string(artifact.status, label="status")
    if not isinstance(artifact.payload, dict):
        raise ValueError("artifact payload must be a JSON object")
    if not isinstance(artifact.metadata, dict):
        raise ValueError("artifact metadata must be a JSON object")
    if artifact.confidence is not None and (
        not isinstance(artifact.confidence, (int, float)) or isinstance(artifact.confidence, bool)
    ):
        raise ValueError("artifact confidence must be numeric when provided")
    if artifact.artifact_type == "annotation":
        _validate_annotation_artifact_payload(artifact.payload)


def validate_body_ref(body_ref: dict[str, Any]) -> None:
    """Validate one sidecar body reference."""

    storage = body_ref.get("storage")
    if storage != "local_file":
        raise ValueError("body_ref storage must be 'local_file'")
    relative_path = body_ref.get("relative_path")
    absolute_path = body_ref.get("path")
    if not isinstance(relative_path, str) and not isinstance(absolute_path, str):
        raise ValueError("body_ref must include a relative_path or path")
    if isinstance(relative_path, str) and not relative_path:
        raise ValueError("body_ref relative_path must not be empty")
    if isinstance(absolute_path, str) and not absolute_path:
        raise ValueError("body_ref path must not be empty")
    encoding = body_ref.get("encoding")
    if encoding not in _LEGACY_BODY_REF_ENCODINGS:
        raise ValueError("body_ref encoding must be gzip when provided")
    content_type = body_ref.get("content_type")
    if content_type is not None and not isinstance(content_type, str):
        raise ValueError("body_ref content_type must be a string when provided")
    for key in ("byte_size", "compressed_size"):
        value = body_ref.get(key)
        if value is None:
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"body_ref {key} must be a non-negative integer when provided")
    sha256 = body_ref.get("sha256")
    if sha256 is not None and (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise ValueError("body_ref sha256 must be a lowercase 64-character hex string")


def validate_slice_record(slice_record: SliceRecord) -> None:
    """Validate one slice registry record before it is persisted."""

    _require_non_empty_string(slice_record.slice_id, label="slice_id")
    _require_non_empty_string(slice_record.schema_version, label="schema_version")
    _require_non_empty_string(slice_record.task_family, label="task_family")
    _require_non_empty_string(slice_record.task_type, label="task_type")
    _require_non_empty_string(slice_record.taxonomy_version, label="taxonomy_version")
    _require_non_empty_string(slice_record.sample_unit, label="sample_unit")
    _require_non_empty_string(slice_record.verifier_contract, label="verifier_contract")
    _require_non_empty_string(slice_record.risk_level, label="risk_level")
    _require_non_empty_string(slice_record.default_use, label="default_use")
    _require_non_empty_string(slice_record.owner, label="owner")
    if slice_record.sample_unit not in _SUPPORTED_SAMPLE_UNITS:
        raise ValueError(
            "slice sample_unit must be one of "
            + ", ".join(sorted(_SUPPORTED_SAMPLE_UNITS))
        )
    if slice_record.default_use not in _SUPPORTED_DEFAULT_USES:
        raise ValueError(
            "slice default_use must be one of "
            + ", ".join(sorted(_SUPPORTED_DEFAULT_USES))
        )
    if slice_record.risk_level not in _SUPPORTED_RISK_LEVELS:
        raise ValueError(
            "slice risk_level must be one of "
            + ", ".join(sorted(_SUPPORTED_RISK_LEVELS))
        )
    if slice_record.description is not None and not isinstance(slice_record.description, str):
        raise ValueError("slice description must be a string when provided")
    if not isinstance(slice_record.metadata, dict):
        raise ValueError("slice metadata must be a JSON object")


def validate_cohort_record(cohort: CohortRecord) -> None:
    """Validate one frozen cohort record before it is persisted."""

    _require_non_empty_string(cohort.cohort_id, label="cohort_id")
    _require_non_empty_string(cohort.schema_version, label="schema_version")
    _require_non_empty_string(cohort.name, label="name")
    _require_non_empty_string(cohort.status, label="status")
    if cohort.status not in _SUPPORTED_COHORT_STATUSES:
        raise ValueError(
            "cohort status must be one of "
            + ", ".join(sorted(_SUPPORTED_COHORT_STATUSES))
        )
    if not isinstance(cohort.slice_ids, list) or not cohort.slice_ids:
        raise ValueError("cohort slice_ids must be a non-empty list")
    for index, slice_id in enumerate(cohort.slice_ids):
        _require_non_empty_string(slice_id, label=f"slice_ids[{index}]")
    if len(set(cohort.slice_ids)) != len(cohort.slice_ids):
        raise ValueError("cohort slice_ids must not contain duplicates")
    if not isinstance(cohort.manifest, dict):
        raise ValueError("cohort manifest must be a JSON object")
    if not isinstance(cohort.metadata, dict):
        raise ValueError("cohort metadata must be a JSON object")


def validate_cohort_member_record(member: CohortMemberRecord) -> None:
    """Validate one cohort membership record before it is persisted."""

    _require_non_empty_string(member.member_id, label="member_id")
    _require_non_empty_string(member.cohort_id, label="cohort_id")
    _require_non_empty_string(member.slice_id, label="slice_id")
    _require_non_empty_string(member.session_id, label="session_id")
    _require_non_empty_string(member.run_id, label="run_id")
    _require_non_empty_string(member.annotation_artifact_id, label="annotation_artifact_id")
    _require_non_empty_string(member.task_instance_key, label="task_instance_key")
    if member.task_template_hash is not None:
        _require_non_empty_string(member.task_template_hash, label="task_template_hash")
    for value, label in (
        (member.quality_confidence, "quality_confidence"),
        (member.verifier_score, "verifier_score"),
    ):
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{label} must be numeric when provided")
    if member.source_channel is not None:
        _require_non_empty_string(member.source_channel, label="source_channel")
    if not isinstance(member.metadata, dict):
        raise ValueError("cohort member metadata must be a JSON object")


def validate_dataset_snapshot_record(snapshot: DatasetSnapshotRecord) -> None:
    """Validate one dataset snapshot manifest before it is persisted."""

    _require_non_empty_string(snapshot.dataset_snapshot_id, label="dataset_snapshot_id")
    _require_non_empty_string(snapshot.schema_version, label="schema_version")
    _require_non_empty_string(snapshot.dataset_recipe_id, label="dataset_recipe_id")
    _require_non_empty_string(snapshot.builder, label="builder")
    _require_non_empty_string(snapshot.sample_unit, label="sample_unit")
    if snapshot.cohort_id is not None:
        _require_non_empty_string(snapshot.cohort_id, label="cohort_id")
    if snapshot.output_path is not None and (
        not isinstance(snapshot.output_path, str) or not snapshot.output_path
    ):
        raise ValueError("output_path must be a non-empty string when provided")
    if not isinstance(snapshot.record_count, int) or snapshot.record_count < 0:
        raise ValueError("record_count must be a non-negative integer")
    if not isinstance(snapshot.manifest, dict):
        raise ValueError("dataset snapshot manifest must be a JSON object")
    if not isinstance(snapshot.metadata, dict):
        raise ValueError("dataset snapshot metadata must be a JSON object")


def validate_eval_suite_record(suite: EvalSuiteRecord) -> None:
    """Validate one eval suite manifest before it is persisted."""

    _require_non_empty_string(suite.eval_suite_id, label="eval_suite_id")
    _require_non_empty_string(suite.schema_version, label="schema_version")
    _require_non_empty_string(suite.slice_id, label="slice_id")
    _require_non_empty_string(suite.suite_kind, label="suite_kind")
    _require_non_empty_string(suite.name, label="name")
    _require_non_empty_string(suite.status, label="status")
    if suite.suite_kind not in _SUPPORTED_EVAL_SUITE_KINDS:
        raise ValueError(
            "suite_kind must be one of " + ", ".join(sorted(_SUPPORTED_EVAL_SUITE_KINDS))
        )
    if suite.status not in _SUPPORTED_EVAL_SUITE_STATUSES:
        raise ValueError(
            "eval suite status must be one of "
            + ", ".join(sorted(_SUPPORTED_EVAL_SUITE_STATUSES))
        )
    if suite.cohort_id is not None:
        _require_non_empty_string(suite.cohort_id, label="cohort_id")
    if suite.dataset_snapshot_id is not None:
        _require_non_empty_string(suite.dataset_snapshot_id, label="dataset_snapshot_id")
    if not isinstance(suite.manifest, dict):
        raise ValueError("eval suite manifest must be a JSON object")
    if not isinstance(suite.metadata, dict):
        raise ValueError("eval suite metadata must be a JSON object")


def validate_scorecard_record(scorecard: ScorecardRecord) -> None:
    """Validate one scorecard before it is persisted."""

    _require_non_empty_string(scorecard.scorecard_id, label="scorecard_id")
    _require_non_empty_string(scorecard.schema_version, label="schema_version")
    _require_non_empty_string(scorecard.eval_suite_id, label="eval_suite_id")
    _require_non_empty_string(scorecard.slice_id, label="slice_id")
    _require_non_empty_string(scorecard.candidate_model, label="candidate_model")
    _require_non_empty_string(scorecard.baseline_model, label="baseline_model")
    _require_non_empty_string(scorecard.verdict, label="verdict")
    if scorecard.verdict not in _SUPPORTED_SCORECARD_VERDICTS:
        raise ValueError(
            "scorecard verdict must be one of "
            + ", ".join(sorted(_SUPPORTED_SCORECARD_VERDICTS))
        )
    if not isinstance(scorecard.metrics, dict):
        raise ValueError("scorecard metrics must be a JSON object")
    if not isinstance(scorecard.thresholds, dict):
        raise ValueError("scorecard thresholds must be a JSON object")
    if not isinstance(scorecard.metadata, dict):
        raise ValueError("scorecard metadata must be a JSON object")


def validate_promotion_decision_record(decision: PromotionDecisionRecord) -> None:
    """Validate one promotion decision before it is persisted."""

    _require_non_empty_string(decision.promotion_decision_id, label="promotion_decision_id")
    _require_non_empty_string(decision.schema_version, label="schema_version")
    _require_non_empty_string(decision.slice_id, label="slice_id")
    _require_non_empty_string(decision.scorecard_id, label="scorecard_id")
    _require_non_empty_string(decision.stage, label="stage")
    _require_non_empty_string(decision.decision, label="decision")
    _require_non_empty_string(
        decision.coverage_policy_version,
        label="coverage_policy_version",
    )
    _require_non_empty_string(decision.summary, label="summary")
    if decision.stage not in _SUPPORTED_PROMOTION_STAGES:
        raise ValueError(
            "promotion stage must be one of "
            + ", ".join(sorted(_SUPPORTED_PROMOTION_STAGES))
        )
    if decision.decision not in _SUPPORTED_PROMOTION_DECISIONS:
        raise ValueError(
            "promotion decision must be one of "
            + ", ".join(sorted(_SUPPORTED_PROMOTION_DECISIONS))
        )
    if not isinstance(decision.rollback_conditions, list):
        raise ValueError("rollback_conditions must be a list")
    for index, condition in enumerate(decision.rollback_conditions):
        _require_non_empty_string(condition, label=f"rollback_conditions[{index}]")
    if not isinstance(decision.metadata, dict):
        raise ValueError("promotion decision metadata must be a JSON object")


def validate_feedback_queue_record(feedback: FeedbackQueueRecord) -> None:
    """Validate one feedback queue item before it is persisted."""

    _require_non_empty_string(feedback.feedback_id, label="feedback_id")
    _require_non_empty_string(feedback.schema_version, label="schema_version")
    _require_non_empty_string(feedback.slice_id, label="slice_id")
    _require_non_empty_string(feedback.source, label="source")
    _require_non_empty_string(feedback.status, label="status")
    _require_non_empty_string(feedback.target_ref, label="target_ref")
    _require_non_empty_string(feedback.reason, label="reason")
    if feedback.status not in _SUPPORTED_FEEDBACK_STATUSES:
        raise ValueError(
            "feedback status must be one of "
            + ", ".join(sorted(_SUPPORTED_FEEDBACK_STATUSES))
        )
    if not isinstance(feedback.payload, dict):
        raise ValueError("feedback payload must be a JSON object")
    if not isinstance(feedback.metadata, dict):
        raise ValueError("feedback metadata must be a JSON object")


def _validate_common_fact_payload(payload: dict[str, Any]) -> None:
    body_ref = payload.get("body_ref")
    if isinstance(body_ref, dict):
        validate_body_ref(body_ref)
    elif body_ref is not None:
        raise ValueError("body_ref must be a JSON object when provided")

    headers = payload.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise ValueError("fact payload headers must be a JSON object when provided")

    if "input_messages" in payload:
        input_messages = payload.get("input_messages")
        if not isinstance(input_messages, list) or any(
            not isinstance(item, dict) for item in input_messages
        ):
            raise ValueError("fact payload input_messages must be a list of message objects")

    request_fingerprint = payload.get("request_fingerprint")
    if request_fingerprint is not None and not isinstance(request_fingerprint, str):
        raise ValueError("fact payload request_fingerprint must be a string when provided")

    canonical = payload.get("canonical")
    if canonical is not None and not isinstance(canonical, dict):
        raise ValueError("fact payload canonical must be a JSON object when provided")


def _validate_semantic_event_payload(payload: dict[str, Any]) -> None:
    semantic_kind = payload.get("semantic_kind")
    if not isinstance(semantic_kind, str) or not semantic_kind:
        raise ValueError("semantic_event payload semantic_kind is required")
    nested_payload = payload.get("payload")
    if not isinstance(nested_payload, dict):
        raise ValueError("semantic_event payload payload must be a JSON object")
    fact_ref = payload.get("fact_ref")
    if fact_ref is not None and (not isinstance(fact_ref, str) or not fact_ref):
        raise ValueError("semantic_event payload fact_ref must be a non-empty string when provided")


def _validate_annotation_artifact_payload(payload: dict[str, Any]) -> None:
    annotation_kind = payload.get("annotation_kind")
    if annotation_kind != "e1":
        raise ValueError("annotation artifact payload annotation_kind must be 'e1'")
    for label in (
        "task_family",
        "task_type",
        "task_template_hash",
        "task_instance_key",
        "verifier_name",
        "taxonomy_version",
        "annotation_version",
        "source_channel",
    ):
        _require_non_empty_string(payload.get(label), label=label)
    for numeric_label in ("verifier_score", "quality_confidence"):
        value = payload.get(numeric_label)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{numeric_label} must be numeric")


def _require_non_empty_string(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
