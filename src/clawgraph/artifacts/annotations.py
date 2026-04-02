"""Helpers for E1 evidence annotation artifacts."""

from __future__ import annotations

import hashlib
from typing import Any

from clawgraph.graph import build_branch_inspect_summaries, build_request_span_summaries
from clawgraph.protocol.factories import new_artifact_record
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.protocol.semantics import request_payload_fingerprint

E1_ANNOTATION_ARTIFACT_TYPE = "annotation"
E1_ANNOTATION_KIND = "e1"
E1_REQUIRED_FIELDS = (
    "task_family",
    "task_type",
    "task_template_hash",
    "task_instance_key",
    "verifier_name",
    "verifier_score",
    "quality_confidence",
    "taxonomy_version",
    "annotation_version",
    "source_channel",
)


def build_e1_annotation_artifacts(
    *,
    facts: list[FactEvent],
    producer: str,
    version: str | None,
    session_id: str,
    run_id: str,
    status: str,
    template_name: str,
) -> list[ArtifactRecord]:
    """Derive one weak but explicit E1 annotation artifact for one run."""

    request_summaries = build_request_span_summaries(facts)
    if not request_summaries:
        return []

    branch_summaries = build_branch_inspect_summaries(facts)
    primary_request = next((fact for fact in facts if fact.kind == "request_started"), None)
    template_hash = _task_template_hash(primary_request)
    closed_requests = [summary for summary in request_summaries if summary.outcome != "open"]
    succeeded_requests = [summary for summary in closed_requests if summary.outcome == "succeeded"]
    verifier_score = (
        round(len(succeeded_requests) / len(closed_requests), 3) if closed_requests else 0.0
    )
    quality_confidence = 0.65 if closed_requests else 0.5

    artifact = new_artifact_record(
        artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
        target_ref=f"run:{run_id}",
        producer=producer,
        version=version,
        payload={
            "annotation_kind": E1_ANNOTATION_KIND,
            "task_family": "captured_agent_task",
            "task_type": "generic_proxy_capture",
            "task_template_hash": template_hash,
            "task_instance_key": f"run:{run_id}",
            "difficulty": _difficulty_label(
                request_count=len(request_summaries),
                branch_count=len(branch_summaries),
            ),
            "verifier_name": "clawgraph.request_outcome_ratio.v1",
            "verifier_score": verifier_score,
            "quality_confidence": quality_confidence,
            "taxonomy_version": "clawgraph.bootstrap.v1",
            "annotation_version": "clawgraph.e1.v1",
            "source_channel": _source_channel(facts),
            "request_count": len(request_summaries),
            "branch_count": len(branch_summaries),
        },
        session_id=session_id,
        run_id=run_id,
        status=status,
        confidence=quality_confidence,
        metadata={
            "template": template_name,
            "annotation_kind": E1_ANNOTATION_KIND,
        },
    )
    return [artifact]


def summarize_e1_annotations(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> dict[str, Any]:
    """Return one merged E1 annotation summary for the current fact scope."""

    if not facts:
        raise ValueError("no facts found")

    run_ids = sorted({fact.run_id for fact in facts})
    run_session_map = _run_session_map(facts)
    active_annotation_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == E1_ANNOTATION_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == E1_ANNOTATION_KIND
    ]
    per_run: dict[str, dict[str, Any]] = {}
    annotated_runs = 0
    referenced_artifact_ids: list[str] = []

    for run_id in run_ids:
        session_id = run_session_map.get(run_id)
        if session_id is None:
            per_run[run_id] = {
                "artifact_ids": [],
                "fields": {},
                "missing_fields": list(E1_REQUIRED_FIELDS),
                "ready": False,
            }
            continue
        resolved, artifact_ids = resolve_e1_annotation_for_run(
            session_id=session_id,
            run_id=run_id,
            artifacts=active_annotation_artifacts,
        )
        missing_fields = [field for field in E1_REQUIRED_FIELDS if field not in resolved]
        if not missing_fields:
            annotated_runs += 1
        per_run[run_id] = {
            "artifact_ids": artifact_ids,
            "fields": resolved,
            "missing_fields": missing_fields,
            "ready": not missing_fields,
        }
        referenced_artifact_ids.extend(artifact_ids)

    unique_artifact_ids = list(dict.fromkeys(referenced_artifact_ids))
    return {
        "level": "E1" if annotated_runs == len(run_ids) and run_ids else "E0",
        "ready": annotated_runs == len(run_ids) and bool(run_ids),
        "annotation_artifacts": len(active_annotation_artifacts),
        "annotated_runs": annotated_runs,
        "run_count": len(run_ids),
        "required_fields": list(E1_REQUIRED_FIELDS),
        "artifact_ids": unique_artifact_ids,
        "runs": per_run,
    }


def resolve_e1_annotation_for_run(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> tuple[dict[str, Any], list[str]]:
    """Resolve the merged E1 annotation payload for one run."""

    session_scoped = [
        artifact
        for artifact in artifacts
        if artifact.target_ref == f"session:{session_id}"
        or (
            artifact.session_id == session_id
            and artifact.run_id is None
            and not artifact.target_ref.startswith("run:")
        )
    ]
    run_scoped = [
        artifact
        for artifact in artifacts
        if artifact.target_ref == f"run:{run_id}" or artifact.run_id == run_id
    ]

    resolved: dict[str, Any] = {}
    artifact_ids: list[str] = []
    for artifact in [*session_scoped, *run_scoped]:
        resolved.update(
            {
                key: value
                for key, value in artifact.payload.items()
                if key != "annotation_kind" and value is not None
            }
        )
        artifact_ids.append(artifact.artifact_id)
    return resolved, artifact_ids


def annotate_records_with_e1(
    *,
    records: list[dict[str, Any]],
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    """Attach resolved E1 annotations to exported records when available."""

    if not records or not facts:
        return records

    summary = summarize_e1_annotations(facts=facts, artifacts=artifacts)
    runs = summary["runs"]
    annotated: list[dict[str, Any]] = []
    for record in records:
        record_copy = dict(record)
        record_run_id = _record_run_id(record_copy)
        if record_run_id is None or record_run_id not in runs:
            annotated.append(record_copy)
            continue
        run_summary = runs[record_run_id]
        if run_summary["fields"]:
            record_copy["annotation"] = dict(run_summary["fields"])
            record_copy["annotation_artifact_ids"] = list(run_summary["artifact_ids"])
            record_copy["evidence_level"] = "E1" if run_summary["ready"] else "E0"
            if "task_family" in run_summary["fields"]:
                record_copy.setdefault("task_family", run_summary["fields"]["task_family"])
            if "task_type" in run_summary["fields"]:
                record_copy.setdefault("task_type", run_summary["fields"]["task_type"])
            if "task_instance_key" in run_summary["fields"]:
                record_copy.setdefault(
                    "task_instance_key",
                    run_summary["fields"]["task_instance_key"],
                )
        annotated.append(record_copy)
    return annotated


def _task_template_hash(request_fact: FactEvent | None) -> str:
    if request_fact is None:
        return "unknown"
    request_json = request_fact.payload.get("json")
    if isinstance(request_json, dict):
        fingerprint = request_payload_fingerprint(request_json)
        if fingerprint:
            return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    path = request_fact.payload.get("path")
    if isinstance(path, str) and path:
        return hashlib.sha256(path.encode("utf-8")).hexdigest()
    return "unknown"


def _difficulty_label(*, request_count: int, branch_count: int) -> str:
    if request_count <= 1 and branch_count <= 1:
        return "low"
    if request_count <= 3 and branch_count <= 2:
        return "medium"
    return "high"


def _source_channel(facts: list[FactEvent]) -> str:
    channels = sorted(
        {
            value
            for fact in facts
            for value in [fact.metadata.get("capture_source")]
            if isinstance(value, str) and value
        }
    )
    if not channels:
        return "captured"
    if len(channels) == 1:
        return channels[0]
    return "mixed"


def _record_run_id(record: dict[str, Any]) -> str | None:
    value = record.get("run_id")
    if isinstance(value, str) and value:
        return value
    target = record.get("target")
    if isinstance(target, dict):
        target_run_id = target.get("run_id")
        if isinstance(target_run_id, str) and target_run_id:
            return target_run_id
    return None


def _run_session_map(facts: list[FactEvent]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for fact in facts:
        mapping.setdefault(fact.run_id, fact.session_id)
    return mapping
