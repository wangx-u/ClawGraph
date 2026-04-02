"""Builder-specific readiness helpers for learning-oriented workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.artifacts import summarize_e1_annotations
from clawgraph.builders import BuildContext, get_dataset_builder, list_dataset_builders
from clawgraph.export.dataset import build_records_for_builder
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
    run_id: str | None
    request_spans: int
    active_artifacts: int
    evidence: dict[str, Any]
    builders: list[BuilderReadiness]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "request_spans": self.request_spans,
            "active_artifacts": self.active_artifacts,
            "evidence": self.evidence,
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

    builders = [builder] if builder is not None else list(list_dataset_builders())
    readiness_items: list[BuilderReadiness] = []
    run_ids = sorted({fact.run_id for fact in facts})
    context = BuildContext(
        session_id=facts[0].session_id,
        run_id=run_ids[0] if len(run_ids) == 1 else None,
    )
    for builder_name in builders:
        builder_impl = get_dataset_builder(builder_name)
        canonical_name = builder_impl.name
        records = build_records_for_builder(
            builder=canonical_name,
            facts=facts,
            artifacts=artifacts,
        )
        blockers = list(
            builder_impl.blockers(
                facts=facts,
                artifacts=artifacts,
                records=records,
                context=context,
            )
        )
        readiness_items.append(
            BuilderReadiness(
                builder=canonical_name,
                ready=not blockers and len(records) > 0,
                predicted_records=len(records),
                blockers=blockers,
            )
        )

    active_artifacts = [artifact for artifact in artifacts if artifact.status == "active"]
    evidence = summarize_e1_annotations(facts=facts, artifacts=artifacts)
    return DatasetReadinessSummary(
        session_id=facts[0].session_id,
        run_id=run_ids[0] if len(run_ids) == 1 else None,
        request_spans=len(build_request_span_summaries(facts)),
        active_artifacts=len(active_artifacts),
        evidence=evidence,
        builders=readiness_items,
    )


def render_dataset_readiness(summary: DatasetReadinessSummary) -> str:
    """Render a builder-specific readiness summary."""

    lines = [
        f"Session: {summary.session_id}",
        f"Run: {summary.run_id or '<multiple>'}",
        f"Request spans: {summary.request_spans}",
        f"Active artifacts: {summary.active_artifacts}",
        (
            "Evidence: "
            f"level={summary.evidence['level']} "
            f"annotated_runs={summary.evidence['annotated_runs']}/{summary.evidence['run_count']} "
            f"annotation_artifacts={summary.evidence['annotation_artifacts']}"
        ),
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
