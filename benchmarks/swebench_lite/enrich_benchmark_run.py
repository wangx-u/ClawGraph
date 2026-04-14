#!/usr/bin/env python3
"""Attach SWE-bench run metadata to one captured ClawGraph run via generic artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.artifacts import (  # noqa: E402
    E1_ANNOTATION_ARTIFACT_TYPE,
    E1_ANNOTATION_KIND,
    resolve_e1_annotation_for_run,
)
from clawgraph.protocol.factories import new_artifact_record  # noqa: E402
from clawgraph.protocol.models import ArtifactRecord  # noqa: E402
from clawgraph.store import SQLiteFactStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--instance-json", required=True, type=Path)
    parser.add_argument("--traj-json", required=True, type=Path)
    parser.add_argument(
        "--annotation-producer",
        default="benchmark.swebench_lite.metadata",
    )
    parser.add_argument(
        "--score-producer",
        default="benchmark.swebench_lite.metadata",
    )
    parser.add_argument("--version", default="benchmark.swebench.v1")
    parser.add_argument("--task-family", default="benchmark_coding_task")
    parser.add_argument("--task-type", default="swebench_issue_fix")
    parser.add_argument("--taxonomy-version", default="benchmark.swebench.v1")
    parser.add_argument("--annotation-version", default="benchmark.swebench.e1.v1")
    parser.add_argument("--source-channel", default="benchmark.swebench_lite")
    parser.add_argument("--quality-confidence", type=float, default=0.98)
    parser.add_argument("--verifier-score", type=float, default=1.0)
    parser.add_argument("--verifier-name", default="benchmark.instance_metadata.v1")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instance_payload = json.loads(args.instance_json.read_text(encoding="utf-8"))
    traj_payload = json.loads(args.traj_json.read_text(encoding="utf-8"))

    store = SQLiteFactStore(args.store)
    artifacts = store.list_artifacts(
        session_id=args.session_id,
        run_id=args.run_id,
        latest_only=True,
    )
    supersedes_artifact_id = _resolve_current_e1_artifact_id(
        session_id=args.session_id,
        run_id=args.run_id,
        artifacts=artifacts,
    )

    template_hash = _task_template_hash(instance_payload)
    submission = _string_value(traj_payload.get("info", {}).get("submission")) or ""
    message_count = len(traj_payload.get("messages") or [])
    api_calls = _float_value(traj_payload.get("info", {}).get("model_stats", {}).get("api_calls"))
    annotation_payload = {
        "annotation_kind": E1_ANNOTATION_KIND,
        "task_family": args.task_family,
        "task_type": args.task_type,
        "task_template_hash": template_hash,
        "task_instance_key": instance_payload["instance_id"],
        "verifier_name": args.verifier_name,
        "verifier_score": round(args.verifier_score, 4),
        "quality_confidence": round(args.quality_confidence, 4),
        "taxonomy_version": args.taxonomy_version,
        "annotation_version": args.annotation_version,
        "source_channel": args.source_channel,
        "difficulty": "benchmark",
        "repo": instance_payload.get("repo"),
        "base_commit": instance_payload.get("base_commit"),
        "review_reasons": [],
        "judge_summary": (
            "SWE-bench Lite instance metadata and mini trajectory linked to captured run."
        ),
    }
    existing_annotation = _find_matching_active_artifact(
        artifacts=artifacts,
        artifact_type="annotation",
        producer=args.annotation_producer,
        version=args.version,
        payload=annotation_payload,
    )
    annotation_artifact = None if existing_annotation is not None else new_artifact_record(
        artifact_type="annotation",
        target_ref=f"run:{args.run_id}",
        producer=args.annotation_producer,
        payload=annotation_payload,
        version=args.version,
        session_id=args.session_id,
        run_id=args.run_id,
        confidence=args.quality_confidence,
        supersedes_artifact_id=supersedes_artifact_id,
        metadata={
            "instance_id": instance_payload.get("instance_id"),
            "workspace": instance_payload.get("workspace"),
            "problem_statement_hash": hashlib.sha256(
                (_string_value(instance_payload.get("problem_statement")) or "").encode("utf-8")
            ).hexdigest(),
            "submission_present": bool(submission),
            "submission_length": len(submission),
            "submission_sha256": hashlib.sha256(submission.encode("utf-8")).hexdigest()
            if submission
            else None,
            "exit_status": _string_value(traj_payload.get("info", {}).get("exit_status")),
            "message_count": message_count,
            "api_calls": api_calls,
            "mini_version": _string_value(traj_payload.get("info", {}).get("mini_version")),
            "trajectory_format": _string_value(traj_payload.get("trajectory_format")),
        },
    )
    score_payload = {
        "score": 1.0 if submission else 0.0,
        "label": bool(submission),
        "outcome": "submitted_patch" if submission else "no_submission",
        "metric_name": "agent_submission_present",
    }
    existing_score = _find_matching_active_artifact(
        artifacts=artifacts,
        artifact_type="score",
        producer=args.score_producer,
        version=args.version,
        payload=score_payload,
    )
    score_artifact = None if existing_score is not None else new_artifact_record(
        artifact_type="score",
        target_ref=f"run:{args.run_id}",
        producer=args.score_producer,
        payload=score_payload,
        version=args.version,
        session_id=args.session_id,
        run_id=args.run_id,
        confidence=0.9,
        metadata={
            "instance_id": instance_payload.get("instance_id"),
            "exit_status": _string_value(traj_payload.get("info", {}).get("exit_status")),
            "submission_length": len(submission),
        },
    )

    persisted = _persist_unique_artifacts(
        store=store,
        session_id=args.session_id,
        run_id=args.run_id,
        artifacts=[
            artifact
            for artifact in [annotation_artifact, score_artifact]
            if artifact is not None
        ],
    )
    payload = {
        "store": args.store,
        "session_id": args.session_id,
        "run_id": args.run_id,
        "instance_id": instance_payload.get("instance_id"),
        "persisted_count": len(persisted),
        "artifact_ids": [artifact.artifact_id for artifact in persisted],
        "task_family": annotation_payload["task_family"],
        "task_type": annotation_payload["task_type"],
        "task_instance_key": annotation_payload["task_instance_key"],
        "task_template_hash": annotation_payload["task_template_hash"],
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(
            "enriched "
            f"{args.run_id} with {len(persisted)} artifact(s) for "
            f"{annotation_payload['task_instance_key']}\n"
        )
    return 0


def _resolve_current_e1_artifact_id(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> str | None:
    resolved, artifact_ids = resolve_e1_annotation_for_run(
        session_id=session_id,
        run_id=run_id,
        artifacts=artifacts,
    )
    if not resolved:
        return None
    active_lookup = {
        artifact.artifact_id: artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == E1_ANNOTATION_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == E1_ANNOTATION_KIND
    }
    for artifact_id in reversed(artifact_ids):
        if artifact_id in active_lookup:
            return artifact_id
    return None


def _persist_unique_artifacts(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> list[ArtifactRecord]:
    existing = store.list_artifacts(session_id=session_id, run_id=run_id, latest_only=True)
    seen = {_artifact_signature(artifact) for artifact in existing}
    persisted: list[ArtifactRecord] = []
    for artifact in artifacts:
        signature = _artifact_signature(artifact)
        if signature in seen:
            continue
        persisted.append(artifact)
        seen.add(signature)
    if persisted:
        store.append_artifacts(persisted)
    return persisted


def _find_matching_active_artifact(
    *,
    artifacts: list[ArtifactRecord],
    artifact_type: str,
    producer: str,
    version: str | None,
    payload: dict[str, Any],
) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.status != "active":
            continue
        if artifact.artifact_type != artifact_type:
            continue
        if artifact.producer != producer:
            continue
        if artifact.version != version:
            continue
        if artifact.payload == payload:
            return artifact
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


def _task_template_hash(instance_payload: dict[str, Any]) -> str:
    problem_statement = _string_value(instance_payload.get("problem_statement")) or ""
    repo = _string_value(instance_payload.get("repo")) or "unknown-repo"
    return hashlib.sha256(f"{repo}\n{problem_statement}".encode("utf-8")).hexdigest()


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
