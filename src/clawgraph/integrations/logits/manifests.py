"""Typed manifests for the ClawGraph x Logits integration layer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class TrainingRequestManifest:
    """One frozen request to train a candidate model in Logits."""

    kind: str = "logits_training_request"
    manifest_version: str = "v1"
    training_request_id: str = field(default_factory=lambda: f"train_{uuid4().hex}")
    created_at: str = field(default_factory=_utcnow_iso)
    training_system: str = "logits"
    recipe_family: str = "sft"
    recipe_name: str = "supervised.chat_sl"
    base_model: str = ""
    renderer_name: str | None = None
    dataset_snapshot_id: str | None = None
    dataset_builder: str | None = None
    input_path: str | None = None
    test_input_path: str | None = None
    eval_suite_id: str | None = None
    load_checkpoint_path: str | None = None
    log_path: str = ""
    base_url: str | None = None
    api_key_env: str = "LOGITS_API_KEY"
    training_config: dict[str, Any] = field(default_factory=dict)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrainingRequestManifest":
        return cls(**payload)


@dataclass(slots=True)
class ModelCandidateManifest:
    """One candidate model produced from a frozen training request."""

    kind: str = "logits_model_candidate"
    manifest_version: str = "v1"
    candidate_model_id: str = field(default_factory=lambda: f"cand_{uuid4().hex}")
    created_at: str = field(default_factory=_utcnow_iso)
    training_request_id: str = ""
    training_system: str = "logits"
    recipe_family: str = "sft"
    training_recipe: str = ""
    base_model: str = ""
    renderer_name: str | None = None
    dataset_snapshot_id: str | None = None
    dataset_builder: str | None = None
    candidate_model: str | None = None
    checkpoint_path: str | None = None
    sampler_path: str | None = None
    published_model_path: str | None = None
    log_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelCandidateManifest":
        return cls(**payload)


@dataclass(slots=True)
class EvalExecutionManifest:
    """One explicit evaluation execution against a frozen eval suite."""

    kind: str = "logits_eval_execution"
    manifest_version: str = "v1"
    eval_execution_id: str = field(default_factory=lambda: f"evalexec_{uuid4().hex}")
    created_at: str = field(default_factory=_utcnow_iso)
    eval_suite_id: str = ""
    candidate_model_id: str = ""
    candidate_model: str = ""
    candidate_model_path: str | None = None
    baseline_model: str = ""
    baseline_model_path: str | None = None
    evaluator_name: str = "clawgraph.integrations.logits.generic_eval"
    grader_name: str = "exact-match"
    case_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    scorecard_id: str | None = None
    promotion_decision_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvalExecutionManifest":
        return cls(**payload)


@dataclass(slots=True)
class RouterHandoffManifest:
    """One dry-run or real handoff package for serving / router integration."""

    kind: str = "logits_router_handoff"
    manifest_version: str = "v1"
    handoff_id: str = field(default_factory=lambda: f"handoff_{uuid4().hex}")
    created_at: str = field(default_factory=_utcnow_iso)
    promotion_decision_id: str = ""
    scorecard_id: str = ""
    candidate_model_id: str = ""
    candidate_model: str = ""
    candidate_model_path: str | None = None
    slice_id: str = ""
    stage: str = ""
    decision: str = ""
    coverage_policy_version: str = ""
    route_config: dict[str, Any] = field(default_factory=dict)
    rollback_conditions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RouterHandoffManifest":
        return cls(**payload)


_MANIFEST_TYPES: dict[str, type] = {
    "logits_training_request": TrainingRequestManifest,
    "logits_model_candidate": ModelCandidateManifest,
    "logits_eval_execution": EvalExecutionManifest,
    "logits_router_handoff": RouterHandoffManifest,
}


def save_manifest(manifest: Any, path: str | Path) -> Path:
    """Persist one typed manifest as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_manifest(path: str | Path) -> TrainingRequestManifest | ModelCandidateManifest | EvalExecutionManifest | RouterHandoffManifest:
    """Load one typed manifest from disk."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    kind = payload.get("kind")
    manifest_cls = _MANIFEST_TYPES.get(kind)
    if manifest_cls is None:
        raise ValueError(f"unsupported manifest kind: {kind}")
    return manifest_cls.from_dict(payload)

