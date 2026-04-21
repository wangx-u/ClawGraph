"""Shared read model for store-backed and manifest-backed training assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
    load_manifest,
)
from clawgraph.protocol.factories import new_training_asset_record
from clawgraph.store import SQLiteFactStore


def build_training_registry(
    *,
    manifest_dir: str | None,
    store: SQLiteFactStore | None = None,
    store_uri: str | None = None,
) -> dict[str, Any]:
    """Build one normalized registry for training assets and their lineage."""

    store_instance = store or (SQLiteFactStore(store_uri) if isinstance(store_uri, str) else None)
    inventory = load_training_manifest_inventory(manifest_dir, store=store_instance)

    snapshot_lookup = _snapshot_lookup(store_instance)
    suite_lookup = _suite_lookup(store_instance)
    scorecard_lookup = _scorecard_lookup(store_instance)
    promotion_lookup = _promotion_lookup(store_instance)
    slice_lookup = _slice_lookup(store_instance)

    training_requests: list[dict[str, Any]] = []
    model_candidates: list[dict[str, Any]] = []
    eval_executions: list[dict[str, Any]] = []
    router_handoffs: list[dict[str, Any]] = []

    request_by_id: dict[str, dict[str, Any]] = {}
    candidate_by_id: dict[str, dict[str, Any]] = {}

    for item in inventory["training_requests"]:
        manifest = item["manifest"]
        dataset_snapshot_title = _lookup_title(
            snapshot_lookup,
            manifest.dataset_snapshot_id,
            default=manifest.dataset_snapshot_id or "-",
        )
        request_title = (
            dataset_snapshot_title
            if dataset_snapshot_title.startswith(f"{manifest.recipe_family.upper()} · ")
            else f"{manifest.recipe_family.upper()} · {dataset_snapshot_title}"
        )
        request_payload = {
            "id": manifest.training_request_id,
            "recipeFamily": manifest.recipe_family,
            "recipeName": manifest.recipe_name,
            "title": request_title,
            "summary": describe_training_request(manifest),
            "baseModel": manifest.base_model,
            "datasetSnapshotId": manifest.dataset_snapshot_id,
            "datasetSnapshotTitle": dataset_snapshot_title,
            "datasetBuilder": manifest.dataset_builder,
            "evalSuiteId": manifest.eval_suite_id,
            "evalSuiteTitle": _lookup_title(suite_lookup, manifest.eval_suite_id, default="-"),
            "loadCheckpointPath": manifest.load_checkpoint_path,
            "inputPath": manifest.input_path,
            "testInputPath": manifest.test_input_path,
            "status": "queued",
            "stage": "requested",
            "createdAt": _format_datetime(manifest.created_at),
            "logPath": manifest.log_path,
            "manifestPath": _manifest_location(item, default_id=manifest.training_request_id),
            "candidateIds": [],
            "candidateCount": 0,
            "evalExecutionIds": [],
            "handoffIds": [],
        }
        training_requests.append(request_payload)
        request_by_id[request_payload["id"]] = request_payload

    for item in inventory["model_candidates"]:
        manifest = item["manifest"]
        candidate_payload = {
            "id": manifest.candidate_model_id,
            "title": build_candidate_title(manifest),
            "summary": describe_model_candidate(manifest),
            "trainingRequestId": manifest.training_request_id,
            "trainingRequestTitle": _lookup_title(
                request_by_id,
                manifest.training_request_id,
                default=manifest.training_request_id,
            ),
            "recipeFamily": manifest.recipe_family,
            "baseModel": manifest.base_model,
            "candidateModel": (
                manifest.candidate_model
                or manifest.published_model_path
                or manifest.sampler_path
                or manifest.checkpoint_path
                or manifest.candidate_model_id
            ),
            "datasetSnapshotId": manifest.dataset_snapshot_id,
            "datasetSnapshotTitle": _lookup_title(
                snapshot_lookup,
                manifest.dataset_snapshot_id,
                default="-",
            ),
            "checkpointPath": manifest.checkpoint_path,
            "samplerPath": manifest.sampler_path,
            "publishedModelPath": manifest.published_model_path,
            "logPath": manifest.log_path,
            "createdAt": _format_datetime(manifest.created_at),
            "manifestPath": _manifest_location(item, default_id=manifest.candidate_model_id),
            "evalExecutionIds": [],
            "handoffIds": [],
            "scorecardIds": [],
            "promotionDecisionIds": [],
            "status": "active",
            "stage": "trained",
        }
        model_candidates.append(candidate_payload)
        candidate_by_id[candidate_payload["id"]] = candidate_payload
        request_payload = request_by_id.get(manifest.training_request_id)
        if request_payload is not None:
            request_payload["candidateIds"].append(candidate_payload["id"])

    for item in inventory["eval_executions"]:
        manifest = item["manifest"]
        scorecard = (
            scorecard_lookup.get(manifest.scorecard_id)
            if isinstance(manifest.scorecard_id, str)
            else None
        )
        promotion = (
            promotion_lookup.get(manifest.promotion_decision_id)
            if isinstance(manifest.promotion_decision_id, str)
            else None
        )
        candidate_payload = candidate_by_id.get(manifest.candidate_model_id)
        execution_payload = {
            "id": manifest.eval_execution_id,
            "title": build_eval_execution_title(manifest),
            "summary": describe_eval_execution(manifest),
            "evalSuiteId": manifest.eval_suite_id,
            "evalSuiteTitle": _lookup_title(
                suite_lookup,
                manifest.eval_suite_id,
                default=manifest.eval_suite_id,
            ),
            "candidateModelId": manifest.candidate_model_id,
            "candidateTitle": None if candidate_payload is None else candidate_payload["title"],
            "candidateModel": manifest.candidate_model,
            "baselineModel": manifest.baseline_model,
            "graderName": manifest.grader_name,
            "caseCount": manifest.case_count,
            "scorecardId": manifest.scorecard_id,
            "scorecardVerdict": None if scorecard is None else scorecard["verdict"],
            "promotionDecisionId": manifest.promotion_decision_id,
            "promotionDecision": None if promotion is None else promotion["decision"],
            "promotionStage": None if promotion is None else promotion["stage"],
            "metricsSummary": _scorecard_metrics_summary(scorecard),
            "createdAt": _format_datetime(manifest.created_at),
            "manifestPath": _manifest_location(item, default_id=manifest.eval_execution_id),
        }
        eval_executions.append(execution_payload)
        if candidate_payload is not None:
            candidate_payload["evalExecutionIds"].append(execution_payload["id"])
            if isinstance(manifest.scorecard_id, str):
                candidate_payload["scorecardIds"].append(manifest.scorecard_id)
            if isinstance(manifest.promotion_decision_id, str):
                candidate_payload["promotionDecisionIds"].append(manifest.promotion_decision_id)
            candidate_payload["status"] = "completed"
            candidate_payload["stage"] = "evaluated"
            request_payload = request_by_id.get(candidate_payload["trainingRequestId"])
            if request_payload is not None:
                request_payload["evalExecutionIds"].append(execution_payload["id"])

    for item in inventory["router_handoffs"]:
        manifest = item["manifest"]
        candidate_payload = candidate_by_id.get(manifest.candidate_model_id)
        promotion = promotion_lookup.get(manifest.promotion_decision_id)
        route_mode = None
        if isinstance(manifest.route_config, dict):
            candidate_route_mode = manifest.route_config.get("route_mode")
            if isinstance(candidate_route_mode, str) and candidate_route_mode:
                route_mode = candidate_route_mode
        handoff_payload = {
            "id": manifest.handoff_id,
            "title": build_router_handoff_title(manifest),
            "summary": describe_router_handoff(manifest),
            "candidateModelId": manifest.candidate_model_id,
            "candidateTitle": None if candidate_payload is None else candidate_payload["title"],
            "candidateModel": manifest.candidate_model,
            "promotionDecisionId": manifest.promotion_decision_id,
            "scorecardId": manifest.scorecard_id,
            "sliceId": manifest.slice_id,
            "sliceLabel": _lookup_title(slice_lookup, manifest.slice_id, default=manifest.slice_id),
            "decision": manifest.decision,
            "stage": manifest.stage,
            "coveragePolicyVersion": manifest.coverage_policy_version,
            "rollbackConditions": list(manifest.rollback_conditions),
            "routeConfig": manifest.route_config,
            "routeMode": route_mode,
            "baselineModel": _baseline_model_from_route_config(manifest.route_config),
            "createdAt": _format_datetime(manifest.created_at),
            "manifestPath": _manifest_location(item, default_id=manifest.handoff_id),
            "promotionSummary": None if promotion is None else promotion["summary"],
        }
        router_handoffs.append(handoff_payload)
        if candidate_payload is not None:
            candidate_payload["handoffIds"].append(handoff_payload["id"])
            candidate_payload["status"] = "completed"
            candidate_payload["stage"] = "handoff_ready"
            request_payload = request_by_id.get(candidate_payload["trainingRequestId"])
            if request_payload is not None:
                request_payload["handoffIds"].append(handoff_payload["id"])

    for request_payload in training_requests:
        request_payload["candidateCount"] = len(request_payload["candidateIds"])
        if request_payload["handoffIds"]:
            request_payload["status"] = "completed"
            request_payload["stage"] = "handoff_ready"
        elif request_payload["evalExecutionIds"]:
            request_payload["status"] = "completed"
            request_payload["stage"] = "evaluated"
        elif request_payload["candidateIds"]:
            request_payload["status"] = "running"
            request_payload["stage"] = "trained"
        else:
            request_payload["status"] = "queued"
            request_payload["stage"] = "requested"

    summary = {
        "requestCount": len(training_requests),
        "candidateCount": len(model_candidates),
        "evalExecutionCount": len(eval_executions),
        "handoffCount": len(router_handoffs),
        "linkedRequestCount": sum(1 for item in training_requests if item["candidateIds"]),
        "evaluatedCandidateCount": sum(1 for item in model_candidates if item["evalExecutionIds"]),
        "handedOffCandidateCount": sum(1 for item in model_candidates if item["handoffIds"]),
        "lastUpdated": _last_updated(
            training_requests,
            model_candidates,
            eval_executions,
            router_handoffs,
        ),
    }
    return {
        "summary": summary,
        "training_requests": training_requests,
        "model_candidates": model_candidates,
        "eval_executions": eval_executions,
        "router_handoffs": router_handoffs,
    }


def load_training_manifest_inventory(
    manifest_dir: str | None,
    *,
    store: SQLiteFactStore | None = None,
) -> dict[str, list[dict[str, Any]]]:
    inventory = {
        "training_requests": [],
        "model_candidates": [],
        "eval_executions": [],
        "router_handoffs": [],
    }
    seen_ids: dict[str, set[str]] = {key: set() for key in inventory}
    if store is not None:
        for asset in store.list_training_assets():
            manifest = _manifest_from_payload(asset.manifest)
            if manifest is None:
                continue
            entry_key = _inventory_key_for_manifest(manifest)
            identity = _manifest_identity(manifest)
            inventory[entry_key].append(
                {
                    "path": asset.manifest_path,
                    "manifest": manifest,
                    "source": "store",
                    "status": asset.status,
                }
            )
            seen_ids[entry_key].add(identity)
    if isinstance(manifest_dir, str) and manifest_dir.strip():
        root = Path(manifest_dir).expanduser()
        if root.exists():
            for path in root.rglob("*.json"):
                try:
                    manifest = load_manifest(path)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue
                entry_key = _inventory_key_for_manifest(manifest)
                identity = _manifest_identity(manifest)
                if identity in seen_ids[entry_key]:
                    continue
                inventory[entry_key].append(
                    {"path": str(path), "manifest": manifest, "source": "manifest"}
                )
                seen_ids[entry_key].add(identity)
    for key in inventory:
        inventory[key].sort(key=_manifest_sort_key, reverse=True)
    return inventory


def persist_training_manifest_record(
    *,
    manifest: TrainingRequestManifest
    | ModelCandidateManifest
    | EvalExecutionManifest
    | RouterHandoffManifest,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    manifest_path: str | None = None,
) -> dict[str, Any]:
    """Persist one training manifest into the store-backed training registry."""

    store_instance = store or (SQLiteFactStore(store_uri) if isinstance(store_uri, str) else None)
    if store_instance is None:
        raise ValueError("store or store_uri is required")
    record = _training_asset_record_from_manifest(manifest, manifest_path=manifest_path)
    store_instance.put_training_asset(record)
    return record.to_dict()


def render_training_registry(registry: dict[str, Any]) -> str:
    """Render one concise registry summary for CLI output."""

    summary = registry["summary"]
    lines = [
        "Training registry:",
        (
            f"requests={summary['requestCount']} "
            f"candidates={summary['candidateCount']} "
            f"evals={summary['evalExecutionCount']} "
            f"handoffs={summary['handoffCount']}"
        ),
    ]
    if summary.get("lastUpdated"):
        lines.append(f"last_updated={summary['lastUpdated']}")
    if registry["training_requests"]:
        lines.append("Requests:")
        for item in registry["training_requests"][:5]:
            lines.append(
                f"- {item['title']} status={item['status']} candidates={item['candidateCount']}"
            )
    if registry["model_candidates"]:
        lines.append("Candidates:")
        for item in registry["model_candidates"][:5]:
            lines.append(
                f"- {item['title']} stage={item['stage']} evals={len(item['evalExecutionIds'])}"
            )
    return "\n".join(lines)


def _training_asset_record_from_manifest(
    manifest: TrainingRequestManifest
    | ModelCandidateManifest
    | EvalExecutionManifest
    | RouterHandoffManifest,
    *,
    manifest_path: str | None,
):
    if isinstance(manifest, TrainingRequestManifest):
        return new_training_asset_record(
            asset_id=manifest.training_request_id,
            asset_kind=manifest.kind,
            title=build_training_request_title(manifest),
            status="queued",
            manifest=manifest.to_dict(),
            training_request_id=manifest.training_request_id,
            eval_suite_id=manifest.eval_suite_id,
            dataset_snapshot_id=manifest.dataset_snapshot_id,
            manifest_path=manifest_path,
            metadata={"training_system": manifest.training_system},
        )
    if isinstance(manifest, ModelCandidateManifest):
        return new_training_asset_record(
            asset_id=manifest.candidate_model_id,
            asset_kind=manifest.kind,
            title=build_candidate_title(manifest),
            status="trained",
            manifest=manifest.to_dict(),
            training_request_id=manifest.training_request_id,
            candidate_model_id=manifest.candidate_model_id,
            dataset_snapshot_id=manifest.dataset_snapshot_id,
            manifest_path=manifest_path,
            metadata={"training_system": manifest.training_system},
        )
    if isinstance(manifest, EvalExecutionManifest):
        return new_training_asset_record(
            asset_id=manifest.eval_execution_id,
            asset_kind=manifest.kind,
            title=build_eval_execution_title(manifest),
            status="completed",
            manifest=manifest.to_dict(),
            candidate_model_id=manifest.candidate_model_id,
            eval_suite_id=manifest.eval_suite_id,
            scorecard_id=manifest.scorecard_id,
            promotion_decision_id=manifest.promotion_decision_id,
            manifest_path=manifest_path,
            metadata={"grader_name": manifest.grader_name},
        )
    return new_training_asset_record(
        asset_id=manifest.handoff_id,
        asset_kind=manifest.kind,
        title=build_router_handoff_title(manifest),
        status=manifest.stage or "handoff_ready",
        manifest=manifest.to_dict(),
        candidate_model_id=manifest.candidate_model_id,
        scorecard_id=manifest.scorecard_id,
        promotion_decision_id=manifest.promotion_decision_id,
        slice_id=manifest.slice_id,
        manifest_path=manifest_path,
        metadata={"coverage_policy_version": manifest.coverage_policy_version},
    )


def build_training_request_title(manifest: TrainingRequestManifest) -> str:
    dataset = manifest.dataset_snapshot_id or manifest.eval_suite_id or manifest.training_request_id
    return f"{manifest.recipe_family.upper()} · {dataset}"


def describe_training_request(manifest: TrainingRequestManifest) -> str:
    dataset = manifest.dataset_snapshot_id or "未绑定快照"
    return f"{manifest.base_model} · 数据快照 {dataset}"


def build_candidate_title(manifest: ModelCandidateManifest) -> str:
    candidate_name = (
        manifest.candidate_model
        or manifest.published_model_path
        or manifest.sampler_path
        or manifest.checkpoint_path
        or manifest.candidate_model_id
    )
    return _shorten_text(candidate_name, limit=48)


def describe_model_candidate(manifest: ModelCandidateManifest) -> str:
    dataset = manifest.dataset_snapshot_id or "未绑定快照"
    return f"{manifest.recipe_family.upper()} · 基座 {manifest.base_model} · 快照 {dataset}"


def build_eval_execution_title(manifest: EvalExecutionManifest) -> str:
    return f"{manifest.grader_name} · {manifest.case_count} 个样本"


def describe_eval_execution(manifest: EvalExecutionManifest) -> str:
    return f"验证套件 {manifest.eval_suite_id} · 候选 {manifest.candidate_model}"


def build_router_handoff_title(manifest: RouterHandoffManifest) -> str:
    return f"{manifest.stage} · {manifest.decision}"


def describe_router_handoff(manifest: RouterHandoffManifest) -> str:
    return f"{manifest.slice_id} · {manifest.candidate_model}"


def _snapshot_lookup(store: SQLiteFactStore | None) -> dict[str, dict[str, Any]]:
    if store is None:
        return {}
    cohort_lookup = {
        cohort.cohort_id: cohort.name or cohort.cohort_id for cohort in store.list_cohorts()
    }
    return {
        snapshot.dataset_snapshot_id: {
            "title": (
                f"{snapshot.builder.upper()} · "
                f"{cohort_lookup.get(snapshot.cohort_id, snapshot.dataset_snapshot_id)}"
            ),
            "builder": snapshot.builder,
        }
        for snapshot in store.list_dataset_snapshots()
    }


def _suite_lookup(store: SQLiteFactStore | None) -> dict[str, dict[str, Any]]:
    if store is None:
        return {}
    return {
        suite.eval_suite_id: {
            "title": suite.name or suite.eval_suite_id,
            "kind": suite.suite_kind,
        }
        for suite in store.list_eval_suites()
    }


def _scorecard_lookup(store: SQLiteFactStore | None) -> dict[str, dict[str, Any]]:
    if store is None:
        return {}
    return {
        scorecard.scorecard_id: {
            "verdict": scorecard.verdict,
            "candidateModel": scorecard.candidate_model,
            "baselineModel": scorecard.baseline_model,
            "metrics": scorecard.metrics,
        }
        for scorecard in store.list_scorecards()
    }


def _promotion_lookup(store: SQLiteFactStore | None) -> dict[str, dict[str, Any]]:
    if store is None:
        return {}
    return {
        decision.promotion_decision_id: {
            "decision": decision.decision,
            "stage": decision.stage,
            "summary": decision.summary,
            "rollbackConditions": list(decision.rollback_conditions),
        }
        for decision in store.list_promotion_decisions()
    }


def _slice_lookup(store: SQLiteFactStore | None) -> dict[str, dict[str, Any]]:
    if store is None:
        return {}
    return {
        slice_record.slice_id: {
            "title": _task_label(slice_record.task_family, slice_record.task_type),
        }
        for slice_record in store.list_slices()
    }


def _lookup_title(
    lookup: dict[str, dict[str, Any]],
    key: str | None,
    *,
    default: str,
) -> str:
    if not isinstance(key, str) or not key:
        return default
    payload = lookup.get(key)
    if payload is None:
        return default
    title = payload.get("title")
    return title if isinstance(title, str) and title else default


def _scorecard_metrics_summary(scorecard: dict[str, Any] | None) -> str | None:
    if scorecard is None:
        return None
    metrics = scorecard.get("metrics")
    if not isinstance(metrics, dict):
        return None
    task_success = metrics.get("task_success_rate")
    verifier = metrics.get("verifier_pass_rate")
    parts: list[str] = []
    if isinstance(task_success, (int, float)) and not isinstance(task_success, bool):
        parts.append(f"成功 {round(float(task_success) * 100)}%")
    if isinstance(verifier, (int, float)) and not isinstance(verifier, bool):
        parts.append(f"验证 {round(float(verifier) * 100)}%")
    return " · ".join(parts) if parts else None


def _baseline_model_from_route_config(route_config: Any) -> str | None:
    if not isinstance(route_config, dict):
        return None
    baseline = route_config.get("baseline_model")
    return baseline if isinstance(baseline, str) and baseline else None


def _last_updated(*groups: list[dict[str, Any]]) -> str | None:
    created_values = [
        item["createdAt"]
        for group in groups
        for item in group
        if isinstance(item.get("createdAt"), str) and item["createdAt"] != "-"
    ]
    return max(created_values, default=None)


def _manifest_sort_key(entry: dict[str, Any]) -> str:
    manifest = entry.get("manifest")
    created_at = getattr(manifest, "created_at", None)
    return str(created_at or "")


def _manifest_identity(
    manifest: TrainingRequestManifest
    | ModelCandidateManifest
    | EvalExecutionManifest
    | RouterHandoffManifest,
) -> str:
    if isinstance(manifest, TrainingRequestManifest):
        return manifest.training_request_id
    if isinstance(manifest, ModelCandidateManifest):
        return manifest.candidate_model_id
    if isinstance(manifest, EvalExecutionManifest):
        return manifest.eval_execution_id
    return manifest.handoff_id


def _inventory_key_for_manifest(
    manifest: TrainingRequestManifest
    | ModelCandidateManifest
    | EvalExecutionManifest
    | RouterHandoffManifest,
) -> str:
    if isinstance(manifest, TrainingRequestManifest):
        return "training_requests"
    if isinstance(manifest, ModelCandidateManifest):
        return "model_candidates"
    if isinstance(manifest, EvalExecutionManifest):
        return "eval_executions"
    return "router_handoffs"


def _manifest_from_payload(
    payload: dict[str, Any],
) -> TrainingRequestManifest | ModelCandidateManifest | EvalExecutionManifest | RouterHandoffManifest | None:
    kind = payload.get("kind")
    if kind == "logits_training_request":
        return TrainingRequestManifest.from_dict(payload)
    if kind == "logits_model_candidate":
        return ModelCandidateManifest.from_dict(payload)
    if kind == "logits_eval_execution":
        return EvalExecutionManifest.from_dict(payload)
    if kind == "logits_router_handoff":
        return RouterHandoffManifest.from_dict(payload)
    return None


def _manifest_location(entry: dict[str, Any], *, default_id: str) -> str:
    path = entry.get("path")
    if isinstance(path, str) and path:
        return path
    return f"store://training-assets/{default_id}"


def _task_label(task_family: str | None, task_type: str | None) -> str:
    parts = [
        _humanize_identifier(value)
        for value in (task_family, task_type)
        if isinstance(value, str) and value
    ]
    return " / ".join(parts) if parts else "未命名任务"


def _humanize_identifier(value: str) -> str:
    normalized = value.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return value
    return " ".join(part.capitalize() for part in normalized.split())


def _shorten_text(value: str, *, limit: int = 72) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1]}…"


def _format_datetime(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        return "-"
    text = value.replace("T", " ")
    return text[:16]
