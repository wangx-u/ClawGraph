"""Shared control-plane actions for dashboard and training workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawgraph.dashboard_bundle import build_web_dashboard_bundle, normalize_store_uri
from clawgraph.evaluation import update_feedback_queue_status
from clawgraph.integrations.logits._compat import load_dotted_object
from clawgraph.integrations.logits.eval_bridge import evaluate_candidate_on_suite
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
    load_manifest,
)
from clawgraph.integrations.logits.registry import (
    build_training_registry,
    load_training_manifest_inventory,
)
from clawgraph.integrations.logits.router_bridge import create_router_handoff_manifest
from clawgraph.integrations.logits.training_bridge import submit_training_request
from clawgraph.judge import plan_review_override
from clawgraph.protocol.models import ArtifactRecord
from clawgraph.store import SQLiteFactStore


def build_dashboard_bundle_action(
    *,
    store_uri: str,
    manifest_dir: str | None = None,
    session_limit: int = 12,
    run_limit: int = 24,
    artifact_limit: int = 40,
) -> dict[str, Any]:
    return build_web_dashboard_bundle(
        store_uri=normalize_store_uri(store_uri),
        manifest_dir=manifest_dir,
        session_limit=session_limit,
        run_limit=run_limit,
        artifact_limit=artifact_limit,
    )


def resolve_feedback_action(
    *,
    store_uri: str,
    feedback_id: str,
    status: str,
    note: str | None,
    reviewer: str,
) -> dict[str, Any]:
    items = update_feedback_queue_status(
        store_uri=store_uri,
        feedback_id=feedback_id,
        status=status,
        note=note,
        reviewer=reviewer,
    )
    return {
        "action": "resolve-feedback",
        "items": [item.to_dict() for item in items],
        "reviewer": reviewer,
    }


def review_override_action(
    *,
    store_uri: str,
    session_id: str,
    run_id: str,
    reviewer: str,
    feedback_id: str | None = None,
    feedback_status: str = "resolved",
    producer: str = "dashboard.human_review",
    version: str = "dashboard.review.v1",
    review_note: str | None = None,
    quality_confidence: float = 1.0,
    verifier_score: float = 1.0,
) -> dict[str, Any]:
    store = SQLiteFactStore(store_uri)
    facts = store.list_facts(session_id=session_id, run_id=run_id)
    if not facts:
        raise ValueError(f"no facts found for {session_id}/{run_id}")
    artifacts = store.list_artifacts(
        session_id=session_id,
        run_id=run_id,
        latest_only=True,
    )
    plan = plan_review_override(
        facts=facts,
        artifacts=artifacts,
        producer=producer,
        version=version,
        review_note=review_note,
        payload_patch={
            "quality_confidence": quality_confidence,
            "verifier_score": verifier_score,
        },
    )
    persisted, skipped = _persist_unique_artifacts(
        store=store,
        session_id=session_id,
        run_id=run_id,
        artifacts=[plan.artifact],
    )
    feedback_items = []
    if feedback_id:
        feedback_items = [
            item.to_dict()
            for item in update_feedback_queue_status(
                store=store,
                feedback_id=feedback_id,
                status=feedback_status,
                note=review_note,
                reviewer=reviewer,
            )
        ]
    return {
        "action": "review-override",
        "persisted_count": len(persisted),
        "skipped_duplicates": skipped,
        "artifact_id": persisted[0].artifact_id if persisted else None,
        "run_id": run_id,
        "session_id": session_id,
        "feedback_items": feedback_items,
        "reviewer": reviewer,
    }


def submit_training_request_action(
    *,
    store_uri: str,
    manifest_dir: str | None,
    request_id: str | None = None,
    manifest_path: str | None = None,
    executor_ref: str | None = None,
    candidate_out: str | None = None,
) -> dict[str, Any]:
    request_manifest = _load_training_request_manifest(
        store_uri=store_uri,
        manifest_dir=manifest_dir,
        request_id=request_id,
        manifest_path=manifest_path,
    )
    if executor_ref:
        request_manifest.runtime_config["executor_ref"] = executor_ref
    candidate = submit_training_request(
        request_manifest,
        store_uri=store_uri,
        candidate_path=None if not candidate_out else Path(candidate_out),
    )
    return {
        "action": "submit-training-request",
        "request_id": request_manifest.training_request_id,
        "candidate": candidate.to_dict(),
    }


def evaluate_candidate_action(
    *,
    store_uri: str,
    manifest_dir: str | None,
    candidate_id: str | None = None,
    manifest_path: str | None = None,
    eval_suite_id: str | None = None,
    baseline_model: str | None = None,
    baseline_model_path: str | None = None,
    sample_ref: str | None = None,
    grader_name: str = "exact-match",
    grader_ref: str | None = None,
    thresholds: dict[str, Any] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
    top_p: float = 1.0,
    base_url: str | None = None,
    scorecard_metadata: dict[str, Any] | None = None,
    record_promotion: bool = True,
    promotion_stage: str = "offline",
    coverage_policy_version: str = "logits.eval.v1",
    promotion_summary: str | None = None,
    rollback_conditions: list[str] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    inventory = load_training_manifest_inventory(
        manifest_dir,
        store=SQLiteFactStore(store_uri),
    )
    candidate_manifest = _load_candidate_manifest(
        inventory=inventory,
        candidate_id=candidate_id,
        manifest_path=manifest_path,
    )
    request_manifest = _related_training_request(inventory, candidate_manifest.training_request_id)
    resolved_eval_suite_id = eval_suite_id or request_manifest.eval_suite_id
    if not isinstance(resolved_eval_suite_id, str) or not resolved_eval_suite_id:
        raise ValueError("eval_suite_id is required")
    resolved_baseline_model = baseline_model or candidate_manifest.base_model or request_manifest.base_model
    if not isinstance(resolved_baseline_model, str) or not resolved_baseline_model:
        raise ValueError("baseline_model is required")
    sample_fn = None
    if isinstance(sample_ref, str) and sample_ref:
        loaded_sample = load_dotted_object(sample_ref)
        if not callable(loaded_sample):
            raise ValueError(f"sample_ref is not callable: {sample_ref}")
        sample_fn = loaded_sample
    manifest, scorecard, promotion = evaluate_candidate_on_suite(
        store_uri=store_uri,
        eval_suite_id=resolved_eval_suite_id,
        candidate_manifest=candidate_manifest,
        baseline_model=resolved_baseline_model,
        baseline_model_path=baseline_model_path,
        sample_fn=sample_fn,
        grader_name=grader_name,
        grader_ref=grader_ref,
        thresholds=thresholds,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        base_url=base_url,
        scorecard_metadata=scorecard_metadata,
        record_promotion=record_promotion,
        promotion_stage=promotion_stage,
        coverage_policy_version=coverage_policy_version,
        promotion_summary=promotion_summary,
        rollback_conditions=rollback_conditions,
        output_path=None if not output_path else Path(output_path),
    )
    return {
        "action": "evaluate-candidate",
        "eval_execution": manifest.to_dict(),
        "scorecard": scorecard.to_dict(),
        "promotion": None if promotion is None else promotion.to_dict(),
    }


def create_handoff_action(
    *,
    store_uri: str,
    manifest_dir: str | None,
    candidate_id: str | None = None,
    manifest_path: str | None = None,
    promotion_decision_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    inventory = load_training_manifest_inventory(
        manifest_dir,
        store=SQLiteFactStore(store_uri),
    )
    candidate_manifest = _load_candidate_manifest(
        inventory=inventory,
        candidate_id=candidate_id,
        manifest_path=manifest_path,
    )
    resolved_promotion_id = promotion_decision_id or _latest_promotion_for_candidate(
        inventory=inventory,
        candidate_id=candidate_manifest.candidate_model_id,
    )
    if not isinstance(resolved_promotion_id, str) or not resolved_promotion_id:
        raise ValueError("promotion_decision_id is required")
    handoff = create_router_handoff_manifest(
        store_uri=store_uri,
        candidate_manifest=candidate_manifest,
        promotion_decision_id=resolved_promotion_id,
        output_path=None if not output_path else Path(output_path),
        metadata=metadata,
    )
    return {
        "action": "create-handoff",
        "handoff": handoff.to_dict(),
    }


def _load_training_request_manifest(
    *,
    store_uri: str,
    manifest_dir: str | None,
    request_id: str | None,
    manifest_path: str | None,
) -> TrainingRequestManifest:
    if manifest_path:
        loaded = load_manifest(manifest_path)
        if not isinstance(loaded, TrainingRequestManifest):
            raise ValueError("manifest_path must point to a training request manifest")
        return loaded
    if not request_id:
        raise ValueError("request_id or manifest_path is required")
    inventory = load_training_manifest_inventory(
        manifest_dir,
        store=SQLiteFactStore(store_uri),
    )
    for item in inventory["training_requests"]:
        manifest = item["manifest"]
        if isinstance(manifest, TrainingRequestManifest) and manifest.training_request_id == request_id:
            return manifest
    raise ValueError(f"training request not found: {request_id}")


def _load_candidate_manifest(
    *,
    inventory: dict[str, list[dict[str, Any]]],
    candidate_id: str | None,
    manifest_path: str | None,
) -> ModelCandidateManifest:
    if manifest_path:
        loaded = load_manifest(manifest_path)
        if not isinstance(loaded, ModelCandidateManifest):
            raise ValueError("manifest_path must point to a model candidate manifest")
        return loaded
    if not candidate_id:
        raise ValueError("candidate_id or manifest_path is required")
    for item in inventory["model_candidates"]:
        manifest = item["manifest"]
        if isinstance(manifest, ModelCandidateManifest) and manifest.candidate_model_id == candidate_id:
            return manifest
    raise ValueError(f"model candidate not found: {candidate_id}")


def _related_training_request(
    inventory: dict[str, list[dict[str, Any]]],
    request_id: str,
) -> TrainingRequestManifest:
    for item in inventory["training_requests"]:
        manifest = item["manifest"]
        if isinstance(manifest, TrainingRequestManifest) and manifest.training_request_id == request_id:
            return manifest
    raise ValueError(f"training request not found: {request_id}")


def _latest_promotion_for_candidate(
    *,
    inventory: dict[str, list[dict[str, Any]]],
    candidate_id: str,
) -> str | None:
    for item in inventory["eval_executions"]:
        manifest = item["manifest"]
        if (
            isinstance(manifest, EvalExecutionManifest)
            and manifest.candidate_model_id == candidate_id
            and isinstance(manifest.promotion_decision_id, str)
            and manifest.promotion_decision_id
        ):
            return manifest.promotion_decision_id
    return None


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
