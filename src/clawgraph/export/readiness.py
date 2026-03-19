"""Export readiness helpers for learning-oriented workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.graph import build_branch_inspect_summaries, build_request_span_summaries
from clawgraph.protocol.models import ArtifactRecord, FactEvent

_PREFERENCE_ARTIFACT_TYPES = {
    "ranking",
    "preference",
    "preference_pair",
    "chosen_rejected",
}
_BINARY_RL_ARTIFACT_TYPES = {
    "score",
    "reward",
    "binary_label",
    "label",
}


@dataclass(slots=True)
class DatasetReadinessSummary:
    """Readiness summary for common dataset builders."""

    session_id: str
    request_spans: int
    active_artifacts: int
    sft_ready: bool
    preference_ready: bool
    binary_rl_ready: bool
    preference_artifact_count: int
    binary_rl_artifact_count: int
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_dataset_readiness_summary(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> DatasetReadinessSummary:
    """Build a conservative readiness summary for export builders."""

    if not facts:
        raise ValueError("no facts found")

    request_spans = build_request_span_summaries(facts)
    branches = build_branch_inspect_summaries(facts)
    active_artifacts = [artifact for artifact in artifacts if artifact.status == "active"]
    preference_artifacts = [
        artifact
        for artifact in active_artifacts
        if artifact.artifact_type in _PREFERENCE_ARTIFACT_TYPES
    ]
    binary_rl_artifacts = [
        artifact
        for artifact in active_artifacts
        if artifact.artifact_type in _BINARY_RL_ARTIFACT_TYPES
    ]

    sft_ready = any(summary.outcome == "succeeded" for summary in request_spans)
    preference_ready = bool(preference_artifacts)
    if not preference_ready:
        preference_ready = any(
            summary.branch_type != "mainline" and summary.request_count > 0 for summary in branches
        )
    binary_rl_ready = bool(binary_rl_artifacts)

    reasons: list[str] = []
    if not sft_ready:
        reasons.append("no successful model response pairs found for SFT")
    if not preference_ready:
        reasons.append("no active preference artifacts or comparable branches found")
    if not binary_rl_ready:
        reasons.append("no active score/reward artifacts found for binary RL")

    return DatasetReadinessSummary(
        session_id=facts[0].session_id,
        request_spans=len(request_spans),
        active_artifacts=len(active_artifacts),
        sft_ready=sft_ready,
        preference_ready=preference_ready,
        binary_rl_ready=binary_rl_ready,
        preference_artifact_count=len(preference_artifacts),
        binary_rl_artifact_count=len(binary_rl_artifacts),
        reasons=reasons,
    )


def render_dataset_readiness(summary: DatasetReadinessSummary) -> str:
    """Render a dataset readiness summary."""

    lines = [
        f"Session: {summary.session_id}",
        f"Request spans: {summary.request_spans}",
        f"Active artifacts: {summary.active_artifacts}",
        f"SFT ready: {summary.sft_ready}",
        f"Preference ready: {summary.preference_ready}",
        f"Binary RL ready: {summary.binary_rl_ready}",
        f"Preference artifacts: {summary.preference_artifact_count}",
        f"Binary RL artifacts: {summary.binary_rl_artifact_count}",
    ]
    if summary.reasons:
        lines.extend(["Reasons:"])
        lines.extend(f"- {reason}" for reason in summary.reasons)
    return "\n".join(lines)
