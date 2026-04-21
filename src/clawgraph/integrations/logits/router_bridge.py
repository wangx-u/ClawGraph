"""Router handoff builder for scorecard- and promotion-backed candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawgraph.integrations.logits.manifests import (
    ModelCandidateManifest,
    RouterHandoffManifest,
    save_manifest,
)
from clawgraph.integrations.logits.registry import persist_training_manifest_record
from clawgraph.store import SQLiteFactStore


def create_router_handoff_manifest(
    *,
    store_uri: str,
    candidate_manifest: ModelCandidateManifest,
    promotion_decision_id: str,
    output_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> RouterHandoffManifest:
    """Create one dry-run router handoff package from a promotion decision."""

    store = SQLiteFactStore(store_uri)
    promotion = store.get_promotion_decision(promotion_decision_id)
    if promotion is None:
        raise ValueError(f"promotion decision not found: {promotion_decision_id}")
    scorecard = store.get_scorecard(promotion.scorecard_id)
    if scorecard is None:
        raise ValueError(f"scorecard not found: {promotion.scorecard_id}")

    route_mode = {
        "offline": "offline_only",
        "shadow": "shadow",
        "canary": "canary",
        "rollout": "rollout",
    }.get(promotion.stage, "custom")
    handoff = RouterHandoffManifest(
        promotion_decision_id=promotion.promotion_decision_id,
        scorecard_id=promotion.scorecard_id,
        candidate_model_id=candidate_manifest.candidate_model_id,
        candidate_model=candidate_manifest.candidate_model
        or candidate_manifest.sampler_path
        or candidate_manifest.checkpoint_path
        or candidate_manifest.candidate_model_id,
        candidate_model_path=candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
        slice_id=promotion.slice_id,
        stage=promotion.stage,
        decision=promotion.decision,
        coverage_policy_version=promotion.coverage_policy_version,
        route_config={
            "slice_id": promotion.slice_id,
            "route_mode": route_mode,
            "decision": promotion.decision,
            "candidate_model": candidate_manifest.candidate_model
            or candidate_manifest.candidate_model_id,
            "candidate_model_path": candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
            "baseline_model": scorecard.baseline_model,
            "fallback": {
                "target_model": scorecard.baseline_model,
                "conditions": list(promotion.rollback_conditions),
            },
        },
        rollback_conditions=list(promotion.rollback_conditions),
        metadata={
            "scorecard_verdict": scorecard.verdict,
            "scorecard_metrics": scorecard.metrics,
            "scorecard_thresholds": scorecard.thresholds,
            **(metadata or {}),
        },
    )
    if output_path is not None:
        destination = save_manifest(handoff, output_path)
        persist_training_manifest_record(
            manifest=handoff,
            store_uri=store_uri,
            manifest_path=str(destination),
        )
    else:
        persist_training_manifest_record(
            manifest=handoff,
            store_uri=store_uri,
            manifest_path=None,
        )
    return handoff
