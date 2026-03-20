"""Builder-specific readiness helpers for learning-oriented workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.export.dataset import SUPPORTED_BUILDERS, build_records_for_builder
from clawgraph.graph import build_request_span_summaries
from clawgraph.protocol.models import ArtifactRecord, FactEvent


@dataclass(slots=True)
class BuilderReadiness:
    """Readiness state for one dataset builder."""

    builder: str
    ready: bool
    predicted_records: int
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DatasetReadinessSummary:
    """Readiness summary across supported builders."""

    session_id: str
    request_spans: int
    active_artifacts: int
    builders: list[BuilderReadiness]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_spans": self.request_spans,
            "active_artifacts": self.active_artifacts,
            "builders": [builder.to_dict() for builder in self.builders],
        }


def build_dataset_readiness_summary(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    *,
    builder: str | None = None,
) -> DatasetReadinessSummary:
    """Build an exact readiness summary from the same builder logic as export."""

    if not facts:
        raise ValueError("no facts found")

    builders = [builder] if builder is not None else list(SUPPORTED_BUILDERS)
    readiness_items: list[BuilderReadiness] = []
    for builder_name in builders:
        normalized = "binary_rl" if builder_name == "binary-rl" else builder_name
        if normalized not in SUPPORTED_BUILDERS:
            raise ValueError(f"unsupported builder: {builder_name}")
        records = build_records_for_builder(
            builder=normalized,
            facts=facts,
            artifacts=artifacts,
        )
        blockers = _blockers_for_builder(
            builder=normalized,
            facts=facts,
            artifacts=artifacts,
            records=records,
        )
        readiness_items.append(
            BuilderReadiness(
                builder=normalized,
                ready=not blockers and len(records) > 0,
                predicted_records=len(records),
                blockers=blockers,
            )
        )

    active_artifacts = [artifact for artifact in artifacts if artifact.status == "active"]
    return DatasetReadinessSummary(
        session_id=facts[0].session_id,
        request_spans=len(build_request_span_summaries(facts)),
        active_artifacts=len(active_artifacts),
        builders=readiness_items,
    )


def render_dataset_readiness(summary: DatasetReadinessSummary) -> str:
    """Render a builder-specific readiness summary."""

    lines = [
        f"Session: {summary.session_id}",
        f"Request spans: {summary.request_spans}",
        f"Active artifacts: {summary.active_artifacts}",
        "",
        "Builders:",
    ]
    for builder in summary.builders:
        blocker_text = ", ".join(builder.blockers) if builder.blockers else "<none>"
        lines.append(
            f"- {builder.builder}: ready={builder.ready} "
            f"predicted_records={builder.predicted_records} blockers={blocker_text}"
        )
    return "\n".join(lines)


def _blockers_for_builder(
    *,
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    records: list[dict[str, Any]],
) -> list[str]:
    if builder == "facts":
        return [] if facts else ["no facts found"]
    if builder == "sft":
        return [] if records else ["no successful model response pairs found for SFT"]
    if builder == "preference":
        active_preference_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active"
            and artifact.artifact_type in {"ranking", "preference", "preference_pair", "chosen_rejected"}
        ]
        if records:
            return []
        if active_preference_artifacts:
            return ["active preference artifacts did not resolve to known branches"]
        return ["no active preference artifacts or comparable related branch pairs found"]
    if builder == "binary_rl":
        active_binary_rl_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active"
            and artifact.artifact_type in {"score", "reward", "binary_label", "label"}
        ]
        if records:
            return []
        if active_binary_rl_artifacts:
            return ["active binary RL artifacts did not contain numeric rewards"]
        return ["no active score/reward artifacts found for binary RL"]
    raise ValueError(f"unsupported builder: {builder}")
