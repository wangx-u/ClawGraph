"""Slice registry and cohort curation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from clawgraph.artifacts import E1_REQUIRED_FIELDS
from clawgraph.graph import build_branch_inspect_summaries
from clawgraph.protocol.factories import (
    new_cohort_member_record,
    new_cohort_record,
)
from clawgraph.protocol.models import ArtifactRecord, CohortMemberRecord, CohortRecord, SliceRecord
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


@dataclass(slots=True)
class CandidateRun:
    """Resolved run-level candidate for one registered slice."""

    slice_id: str
    session_id: str
    run_id: str
    task_family: str
    task_type: str
    taxonomy_version: str
    task_instance_key: str
    task_template_hash: str
    verifier_name: str
    verifier_score: float
    quality_confidence: float
    source_channel: str
    annotation_artifact_id: str
    annotation_artifact_ids: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "task_family": self.task_family,
            "task_type": self.task_type,
            "taxonomy_version": self.taxonomy_version,
            "task_instance_key": self.task_instance_key,
            "task_template_hash": self.task_template_hash,
            "verifier_name": self.verifier_name,
            "verifier_score": self.verifier_score,
            "quality_confidence": self.quality_confidence,
            "source_channel": self.source_channel,
            "annotation_artifact_id": self.annotation_artifact_id,
            "annotation_artifact_ids": list(self.annotation_artifact_ids),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class CohortFreezeResult:
    """Structured output for one cohort freeze operation."""

    slice_record: SliceRecord
    cohort: CohortRecord
    members: list[CohortMemberRecord]
    candidates: list[CandidateRun]
    holdout_candidates: list[CandidateRun]
    review_queue: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice": self.slice_record.to_dict(),
            "cohort": self.cohort.to_dict(),
            "members": [member.to_dict() for member in self.members],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "holdout_candidates": [
                candidate.to_dict() for candidate in self.holdout_candidates
            ],
            "review_queue": list(self.review_queue),
        }


def list_slice_candidates(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    slice_id: str,
    session: str | None = None,
    run_id: str | None = None,
    task_instance_key: str | None = None,
    task_template_hash: str | None = None,
    min_quality_confidence: float | None = None,
    min_verifier_score: float | None = None,
    source_channel: str | None = None,
    limit: int | None = None,
) -> tuple[SliceRecord, list[CandidateRun]]:
    """Resolve the explicit candidate pool for one registered slice."""

    service = ClawGraphQueryService(store=store, store_uri=store_uri)
    slice_record = service.get_slice(slice_id)
    if slice_record is None:
        raise ValueError(f"slice not found: {slice_id}")

    resolved_session_id = (
        service.resolve_session_id(session=session, run_id=run_id)
        if session is not None or run_id is not None
        else None
    )
    indexed_candidates = service.store.list_e1_candidate_annotations(
        session_id=resolved_session_id,
        run_id=run_id,
        task_family=slice_record.task_family,
        task_type=slice_record.task_type,
        taxonomy_version=slice_record.taxonomy_version,
        task_instance_key=task_instance_key,
        task_template_hash=task_template_hash,
        min_quality_confidence=min_quality_confidence,
        min_verifier_score=min_verifier_score,
        source_channel=source_channel,
        limit=limit,
    )

    candidates: list[CandidateRun] = []
    for indexed_candidate in indexed_candidates:
        resolved_fields = indexed_candidate["fields"]
        artifact_ids = list(indexed_candidate["artifact_ids"])
        if any(field not in resolved_fields for field in E1_REQUIRED_FIELDS):
            continue
        primary_artifact_id = artifact_ids[-1] if artifact_ids else ""
        candidates.append(
            CandidateRun(
                slice_id=slice_record.slice_id,
                session_id=str(indexed_candidate["session_id"]),
                run_id=str(indexed_candidate["run_id"]),
                task_family=str(resolved_fields["task_family"]),
                task_type=str(resolved_fields["task_type"]),
                taxonomy_version=str(resolved_fields["taxonomy_version"]),
                task_instance_key=str(resolved_fields["task_instance_key"]),
                task_template_hash=str(resolved_fields["task_template_hash"]),
                verifier_name=str(resolved_fields["verifier_name"]),
                verifier_score=float(resolved_fields["verifier_score"]),
                quality_confidence=float(resolved_fields["quality_confidence"]),
                source_channel=str(resolved_fields["source_channel"]),
                annotation_artifact_id=primary_artifact_id,
                annotation_artifact_ids=list(artifact_ids),
                metadata={
                    **{
                        key: value
                        for key, value in resolved_fields.items()
                        if key
                        not in {
                            "task_family",
                            "task_type",
                            "taxonomy_version",
                            "task_instance_key",
                            "task_template_hash",
                            "verifier_name",
                            "verifier_score",
                            "quality_confidence",
                            "source_channel",
                        }
                    },
                    "cluster_keys": {
                        "task_instance": str(resolved_fields["task_instance_key"]),
                        "task_template": str(resolved_fields["task_template_hash"]),
                    },
                },
            )
        )
    return slice_record, candidates


def freeze_cohort(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    slice_id: str,
    name: str | None = None,
    cohort_id: str | None = None,
    session: str | None = None,
    run_id: str | None = None,
    task_instance_key: str | None = None,
    task_template_hash: str | None = None,
    min_quality_confidence: float | None = None,
    min_verifier_score: float | None = None,
    source_channel: str | None = None,
    limit: int | None = None,
    purpose: str | None = None,
    max_members_per_task_instance: int = 1,
    max_members_per_template: int | None = None,
    holdout_fraction: float | None = None,
) -> CohortFreezeResult:
    """Freeze a cohort from the explicit candidate pool of one registered slice."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    slice_record, candidates = list_slice_candidates(
        store=store_instance,
        slice_id=slice_id,
        session=session,
        run_id=run_id,
        task_instance_key=task_instance_key,
        task_template_hash=task_template_hash,
        min_quality_confidence=min_quality_confidence,
        min_verifier_score=min_verifier_score,
        source_channel=source_channel,
        limit=limit,
    )
    if not candidates:
        raise ValueError(f"no candidates matched slice: {slice_id}")

    resolved_purpose = _resolve_purpose(slice_record=slice_record, purpose=purpose)
    quality_threshold = _default_quality_threshold(
        slice_record=slice_record,
        explicit=min_quality_confidence,
        purpose=resolved_purpose,
    )
    verifier_threshold = _default_verifier_threshold(
        slice_record=slice_record,
        explicit=min_verifier_score,
        purpose=resolved_purpose,
    )
    resolved_holdout_fraction = _default_holdout_fraction(
        slice_record=slice_record,
        explicit=holdout_fraction,
        purpose=resolved_purpose,
    )

    run_facts: dict[str, list[Any]] = {}
    review_queue: list[dict[str, Any]] = []
    eligible_candidates: list[CandidateRun] = []
    for candidate in candidates:
        facts = store_instance.list_facts(run_id=candidate.run_id)
        run_facts[candidate.run_id] = facts
        review_reasons = _review_reasons(
            candidate=candidate,
            slice_record=slice_record,
            quality_threshold=quality_threshold,
            verifier_threshold=verifier_threshold,
        )
        candidate.metadata["run_fact_summary"] = _run_fact_summary(facts)
        if review_reasons:
            review_queue.append(
                {
                    "slice_id": slice_record.slice_id,
                    "session_id": candidate.session_id,
                    "run_id": candidate.run_id,
                    "task_instance_key": candidate.task_instance_key,
                    "task_template_hash": candidate.task_template_hash,
                    "reasons": review_reasons,
                }
            )
            continue
        eligible_candidates.append(candidate)

    clustered_candidates, quota_holdout = _apply_cluster_quotas(
        candidates=eligible_candidates,
        max_members_per_task_instance=max_members_per_task_instance,
        max_members_per_template=max_members_per_template,
    )
    selected_candidates, fractional_holdout = _partition_holdout_candidates(
        candidates=clustered_candidates,
        holdout_fraction=resolved_holdout_fraction,
        purpose=resolved_purpose,
    )
    holdout_candidates = [*quota_holdout, *fractional_holdout]
    if resolved_purpose == "evaluation":
        selected_candidates = clustered_candidates
        holdout_candidates = []
    if not selected_candidates:
        raise ValueError(f"no candidates remained after curation for slice: {slice_id}")

    frozen_at = datetime.now(UTC)
    selection_query = {
        key: value
        for key, value in {
            "slice_id": slice_id,
            "session": session,
            "run_id": run_id,
            "task_instance_key": task_instance_key,
            "task_template_hash": task_template_hash,
            "min_quality_confidence": min_quality_confidence,
            "min_verifier_score": min_verifier_score,
            "source_channel": source_channel,
            "limit": limit,
            "purpose": resolved_purpose,
            "max_members_per_task_instance": max_members_per_task_instance,
            "max_members_per_template": max_members_per_template,
            "holdout_fraction": resolved_holdout_fraction,
        }.items()
        if value is not None
    }
    time_bounds = _time_bounds(
        [run_facts[candidate.run_id] for candidate in selected_candidates if candidate.run_id in run_facts]
    )
    frozen_artifact_ids = _frozen_artifact_ids_by_run(
        store=store_instance,
        candidates=selected_candidates,
        run_facts=run_facts,
    )
    manifest = {
        "slice_ids": [slice_record.slice_id],
        "taxonomy_version": slice_record.taxonomy_version,
        "sample_unit": slice_record.sample_unit,
        "expected_use": resolved_purpose,
        "selection_query": selection_query,
        "time_range": time_bounds,
        "coverage": {
            "candidate_count": len(candidates),
            "selected_count": len(selected_candidates),
            "session_count": len({candidate.session_id for candidate in selected_candidates}),
            "run_count": len({candidate.run_id for candidate in selected_candidates}),
            "task_instance_count": len(
                {candidate.task_instance_key for candidate in selected_candidates}
            ),
            "task_template_count": len(
                {candidate.task_template_hash for candidate in selected_candidates}
            ),
        },
        "cluster_rules": {
            "version": "clawgraph.curation.cluster.v1",
            "max_members_per_task_instance": max_members_per_task_instance,
            "max_members_per_template": max_members_per_template,
        },
        "cluster_stats": {
            "selected_task_instance_keys": _frequency_map(
                candidate.task_instance_key for candidate in selected_candidates
            ),
            "selected_task_template_hashes": _frequency_map(
                candidate.task_template_hash for candidate in selected_candidates
            ),
            "selected_source_channels": _frequency_map(
                candidate.source_channel for candidate in selected_candidates
            ),
            "holdout_count": len(holdout_candidates),
            "review_count": len(review_queue),
        },
        "quality": {
            "min_quality_confidence": min(
                candidate.quality_confidence for candidate in selected_candidates
            ),
            "max_quality_confidence": max(
                candidate.quality_confidence for candidate in selected_candidates
            ),
            "avg_quality_confidence": round(
                sum(candidate.quality_confidence for candidate in selected_candidates)
                / len(selected_candidates),
                4,
            ),
            "min_verifier_score": min(
                candidate.verifier_score for candidate in selected_candidates
            ),
            "max_verifier_score": max(
                candidate.verifier_score for candidate in selected_candidates
            ),
            "avg_verifier_score": round(
                sum(candidate.verifier_score for candidate in selected_candidates)
                / len(selected_candidates),
                4,
            ),
            "quality_gate": {
                "min_quality_confidence": quality_threshold,
                "min_verifier_score": verifier_threshold,
                "version": "clawgraph.curation.quality_gate.v1",
            },
        },
        "review": {
            "status": "required" if review_queue else "clear",
            "required": bool(review_queue),
            "queue": review_queue,
        },
        "holdout_feed": {
            "status": "available" if holdout_candidates else "empty",
            "count": len(holdout_candidates),
            "runs": [candidate.to_dict() for candidate in holdout_candidates],
        },
        "artifact_view": {
            "strategy": "frozen_artifact_ids",
            "artifact_ids": sorted(
                {
                    artifact_id
                    for artifact_ids in frozen_artifact_ids.values()
                    for artifact_id in artifact_ids
                }
            ),
        },
        "frozen_at": frozen_at.isoformat(),
    }
    cohort = new_cohort_record(
        name=name or f"{slice_record.slice_id}-{frozen_at.strftime('%Y%m%d%H%M%S')}",
        slice_ids=[slice_record.slice_id],
        manifest=manifest,
        cohort_id=cohort_id,
        metadata={
            "created_from": "slice_candidate_pool",
            "slice_id": slice_record.slice_id,
        },
    )
    cohort.manifest["cohort_id"] = cohort.cohort_id
    members = [
        new_cohort_member_record(
            cohort_id=cohort.cohort_id,
            slice_id=slice_record.slice_id,
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
                "frozen_artifact_ids": frozen_artifact_ids.get(candidate.run_id, []),
                "task_family": candidate.task_family,
                "task_type": candidate.task_type,
                "taxonomy_version": candidate.taxonomy_version,
                "verifier_name": candidate.verifier_name,
                **candidate.metadata,
            },
        )
        for candidate in selected_candidates
    ]
    store_instance.append_cohort(cohort, members=members)
    return CohortFreezeResult(
        slice_record=slice_record,
        cohort=cohort,
        members=members,
        candidates=selected_candidates,
        holdout_candidates=holdout_candidates,
        review_queue=review_queue,
    )


def _frequency_map(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _resolve_purpose(*, slice_record: SliceRecord, purpose: str | None) -> str:
    if purpose is not None:
        return purpose
    if slice_record.default_use == "eval_only":
        return "evaluation"
    if slice_record.default_use == "diagnostics_only":
        return "diagnostics"
    return "training"


def _default_quality_threshold(
    *,
    slice_record: SliceRecord,
    explicit: float | None,
    purpose: str,
) -> float:
    if explicit is not None:
        return explicit
    if purpose == "training":
        value = slice_record.metadata.get("min_quality_confidence")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0.75
    return 0.0


def _default_verifier_threshold(
    *,
    slice_record: SliceRecord,
    explicit: float | None,
    purpose: str,
) -> float:
    if explicit is not None:
        return explicit
    if purpose == "training":
        value = slice_record.metadata.get("min_verifier_score")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0.5
    return 0.0


def _default_holdout_fraction(
    *,
    slice_record: SliceRecord,
    explicit: float | None,
    purpose: str,
) -> float:
    if explicit is not None:
        return explicit
    if purpose != "training":
        return 0.0
    value = slice_record.metadata.get("holdout_fraction")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def _review_reasons(
    *,
    candidate: CandidateRun,
    slice_record: SliceRecord,
    quality_threshold: float,
    verifier_threshold: float,
) -> list[str]:
    reasons: list[str] = []
    if candidate.task_type in {"unknown", "new_subtype"}:
        reasons.append("unresolved_task_type")
    if candidate.quality_confidence < quality_threshold:
        reasons.append("low_quality_confidence")
    if candidate.verifier_score < verifier_threshold:
        reasons.append("low_verifier_score")
    if candidate.metadata.get("new_subtype") is True:
        reasons.append("new_subtype")
    if candidate.metadata.get("new_path") is True or candidate.metadata.get("novel_path") is True:
        reasons.append("novel_path")
    if slice_record.default_use == "training_candidate" and candidate.source_channel == "shadow":
        reasons.append("shadow_only_candidate")
    return reasons


def _sorted_candidates(candidates: list[CandidateRun]) -> list[CandidateRun]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.verifier_score,
            -candidate.quality_confidence,
            candidate.run_id,
        ),
    )


def _apply_cluster_quotas(
    *,
    candidates: list[CandidateRun],
    max_members_per_task_instance: int,
    max_members_per_template: int | None,
) -> tuple[list[CandidateRun], list[CandidateRun]]:
    holdout: list[CandidateRun] = []
    per_instance_selected: list[CandidateRun] = []
    instance_groups: dict[str, list[CandidateRun]] = {}
    for candidate in candidates:
        instance_groups.setdefault(candidate.task_instance_key, []).append(candidate)
    for group in instance_groups.values():
        ranked = _sorted_candidates(group)
        per_instance_selected.extend(ranked[:max_members_per_task_instance])
        for candidate in ranked[max_members_per_task_instance:]:
            candidate.metadata["holdout_reason"] = "task_instance_quota"
            holdout.append(candidate)

    if max_members_per_template is None:
        return per_instance_selected, holdout

    template_selected: list[CandidateRun] = []
    template_groups: dict[str, list[CandidateRun]] = {}
    for candidate in per_instance_selected:
        template_groups.setdefault(candidate.task_template_hash, []).append(candidate)
    for group in template_groups.values():
        ranked = _sorted_candidates(group)
        template_selected.extend(ranked[:max_members_per_template])
        for candidate in ranked[max_members_per_template:]:
            candidate.metadata["holdout_reason"] = "task_template_quota"
            holdout.append(candidate)
    return template_selected, holdout


def _partition_holdout_candidates(
    *,
    candidates: list[CandidateRun],
    holdout_fraction: float,
    purpose: str,
) -> tuple[list[CandidateRun], list[CandidateRun]]:
    if purpose != "training" or holdout_fraction <= 0.0 or len(candidates) < 2:
        return candidates, []
    holdout_count = int(round(len(candidates) * holdout_fraction))
    holdout_count = max(1, holdout_count)
    holdout_count = min(len(candidates) - 1, holdout_count)
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.metadata.get("run_fact_summary", {}).get("latest_timestamp") or "",
            candidate.run_id,
        ),
    )
    selected = ranked[:-holdout_count]
    holdout = ranked[-holdout_count:]
    for candidate in holdout:
        candidate.metadata["holdout_reason"] = "holdout_fraction"
    return selected, holdout


def _run_fact_summary(facts: list[Any]) -> dict[str, Any]:
    if not facts:
        return {
            "earliest_timestamp": None,
            "latest_timestamp": None,
            "fact_count": 0,
        }
    timestamps = sorted(fact.timestamp.isoformat() for fact in facts)
    return {
        "earliest_timestamp": timestamps[0],
        "latest_timestamp": timestamps[-1],
        "fact_count": len(facts),
    }


def _time_bounds(fact_groups: list[list[Any]]) -> dict[str, Any]:
    timestamps = sorted(
        fact.timestamp.isoformat()
        for facts in fact_groups
        for fact in facts
    )
    if not timestamps:
        return {"start": None, "end": None}
    return {"start": timestamps[0], "end": timestamps[-1]}


def _frozen_artifact_ids_by_run(
    *,
    store: SQLiteFactStore,
    candidates: list[CandidateRun],
    run_facts: dict[str, list[Any]],
) -> dict[str, list[str]]:
    session_artifacts = {
        session_id: store.list_artifacts(
            session_id=session_id,
            latest_only=True,
        )
        for session_id in sorted({candidate.session_id for candidate in candidates})
    }
    branch_ids_by_run = {
        run_id: {
            summary.branch_id
            for summary in build_branch_inspect_summaries(facts)
            if isinstance(summary.branch_id, str) and summary.branch_id
        }
        for run_id, facts in run_facts.items()
    }
    frozen: dict[str, list[str]] = {}
    for candidate in candidates:
        facts = run_facts.get(candidate.run_id, [])
        fact_ids = {fact.fact_id for fact in facts}
        frozen[candidate.run_id] = [
            artifact.artifact_id
            for artifact in session_artifacts.get(candidate.session_id, [])
            if _artifact_in_candidate_scope(
                artifact=artifact,
                candidate=candidate,
                fact_ids=fact_ids,
                branch_ids=branch_ids_by_run.get(candidate.run_id, set()),
            )
        ]
    return frozen


def _artifact_in_candidate_scope(
    *,
    artifact: ArtifactRecord,
    candidate: CandidateRun,
    fact_ids: set[str],
    branch_ids: set[str],
) -> bool:
    if artifact.target_ref.startswith("fact:"):
        return artifact.target_ref.split(":", 1)[1] in fact_ids
    if artifact.target_ref.startswith("branch:"):
        branch_id = artifact.target_ref.split(":", 1)[1]
        return branch_id in branch_ids
    if artifact.run_id is not None and artifact.run_id == candidate.run_id:
        return True
    if artifact.target_ref == f"run:{candidate.run_id}":
        return True
    if artifact.target_ref == f"session:{candidate.session_id}":
        return True
    if artifact.session_id == candidate.session_id and artifact.run_id is None and (
        ":" not in artifact.target_ref
    ):
        return True
    return artifact.session_id == candidate.session_id and artifact.run_id == candidate.run_id
