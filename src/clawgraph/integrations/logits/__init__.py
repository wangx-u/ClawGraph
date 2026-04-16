"""Logits integration bridges for training, evaluation, and rollout handoff."""

from clawgraph.integrations.logits.eval_bridge import (
    EvalCase,
    evaluate_candidate_on_suite,
    load_builtin_grader,
    load_eval_cases_for_suite,
)
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
    load_manifest,
    save_manifest,
)
from clawgraph.integrations.logits.preference_adapter import (
    export_preference_snapshot_for_logits,
)
from clawgraph.integrations.logits.router_bridge import create_router_handoff_manifest
from clawgraph.integrations.logits.sft_adapter import export_sft_snapshot_for_logits
from clawgraph.integrations.logits.training_bridge import (
    prepare_dpo_training_request,
    prepare_rl_training_request,
    prepare_sft_training_request,
    submit_training_request,
)

__all__ = [
    "EvalCase",
    "EvalExecutionManifest",
    "ModelCandidateManifest",
    "RouterHandoffManifest",
    "TrainingRequestManifest",
    "create_router_handoff_manifest",
    "evaluate_candidate_on_suite",
    "export_preference_snapshot_for_logits",
    "export_sft_snapshot_for_logits",
    "load_builtin_grader",
    "load_eval_cases_for_suite",
    "load_manifest",
    "prepare_dpo_training_request",
    "prepare_rl_training_request",
    "prepare_sft_training_request",
    "save_manifest",
    "submit_training_request",
]

