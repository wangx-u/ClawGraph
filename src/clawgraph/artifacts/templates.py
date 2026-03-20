"""Built-in artifact templates for first-run supervision bootstrap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_comparable_branch_pairs,
    build_request_span_summaries,
)
from clawgraph.protocol.factories import new_artifact_record
from clawgraph.protocol.models import ArtifactRecord, FactEvent


SUPPORTED_ARTIFACT_TEMPLATES = (
    "request-outcome-scores",
    "branch-outcome-preference",
    "openclaw-defaults",
)


@dataclass(slots=True)
class ArtifactBootstrapPlan:
    """Planned artifact generation from a built-in supervision template."""

    template: str
    session_id: str
    producer: str
    version: str | None
    blockers: list[str]
    artifacts: list[ArtifactRecord]

    @property
    def ready(self) -> bool:
        return not self.blockers and len(self.artifacts) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "session_id": self.session_id,
            "producer": self.producer,
            "version": self.version,
            "ready": self.ready,
            "artifact_count": len(self.artifacts),
            "blockers": list(self.blockers),
            "artifacts": [
                {
                    **asdict(artifact),
                    "created_at": artifact.created_at.isoformat()
                    if artifact.created_at is not None
                    else None,
                }
                for artifact in self.artifacts
            ],
        }


def plan_artifact_bootstrap(
    *,
    template: str,
    facts: list[FactEvent],
    producer: str,
    version: str | None = None,
    status: str = "active",
) -> ArtifactBootstrapPlan:
    """Build artifact records from a first-party template without persisting them."""

    if not facts:
        raise ValueError("no facts found")

    normalized_template = _canonical_template(template)
    session_id = facts[0].session_id
    run_ids = sorted({fact.run_id for fact in facts})
    run_id = run_ids[0] if len(run_ids) == 1 else None
    artifacts: list[ArtifactRecord] = []
    blockers: list[str] = []

    if normalized_template in {"request-outcome-scores", "openclaw-defaults"}:
        request_artifacts = _request_outcome_score_artifacts(
            facts=facts,
            producer=producer,
            version=version,
            session_id=session_id,
            run_id=run_id,
            status=status,
        )
        if request_artifacts:
            artifacts.extend(request_artifacts)
        elif normalized_template == "request-outcome-scores":
            blockers.append("no closed requests with response or error facts were found")

    if normalized_template in {"branch-outcome-preference", "openclaw-defaults"}:
        branch_artifacts = _branch_outcome_preference_artifacts(
            facts=facts,
            producer=producer,
            version=version,
            session_id=session_id,
            run_id=run_id,
            status=status,
        )
        if branch_artifacts:
            artifacts.extend(branch_artifacts)
        elif normalized_template == "branch-outcome-preference":
            blockers.append("no comparable succeeded-versus-failed branches were found")

    if normalized_template == "openclaw-defaults" and not artifacts:
        blockers.extend(
            [
                "no closed requests with response or error facts were found",
                "no comparable succeeded-versus-failed branches were found",
            ]
        )

    return ArtifactBootstrapPlan(
        template=normalized_template,
        session_id=session_id,
        producer=producer,
        version=version,
        blockers=_dedupe(blockers),
        artifacts=artifacts,
    )


def _request_outcome_score_artifacts(
    *,
    facts: list[FactEvent],
    producer: str,
    version: str | None,
    session_id: str,
    run_id: str,
    status: str,
) -> list[ArtifactRecord]:
    artifacts: list[ArtifactRecord] = []
    for summary in build_request_span_summaries(facts):
        if summary.outcome == "open":
            continue
        target_fact_id = summary.response_fact_id or summary.error_fact_id
        if target_fact_id is None:
            continue
        score = 1.0 if summary.outcome == "succeeded" else 0.0
        artifacts.append(
            new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{target_fact_id}",
                producer=producer,
                version=version,
                payload={
                    "score": score,
                    "label": summary.outcome == "succeeded",
                    "outcome": summary.outcome,
                    "request_id": summary.request_id,
                    "status_code": summary.status_code,
                },
                session_id=session_id,
                run_id=run_id,
                status=status,
                confidence=0.8,
                metadata={"template": "request-outcome-scores"},
            )
        )
    return artifacts


def _branch_outcome_preference_artifacts(
    *,
    facts: list[FactEvent],
    producer: str,
    version: str | None,
    session_id: str,
    run_id: str,
    status: str,
) -> list[ArtifactRecord]:
    branch_summaries = build_branch_inspect_summaries(facts)
    comparable_pairs = build_comparable_branch_pairs(branch_summaries)
    artifacts: list[ArtifactRecord] = []
    for pair in comparable_pairs:
        artifacts.append(
            new_artifact_record(
                artifact_type="preference",
                target_ref=f"session:{session_id}",
                producer=producer,
                version=version,
                payload={
                    "chosen": pair.chosen_branch_id,
                    "rejected": pair.rejected_branch_id,
                    "reason": pair.reason,
                },
                session_id=session_id,
                run_id=run_id,
                status=status,
                confidence=0.7,
                metadata={
                    "template": "branch-outcome-preference",
                    "pair_source": pair.source,
                },
            )
        )
    return artifacts


def _canonical_template(template: str) -> str:
    if template not in SUPPORTED_ARTIFACT_TEMPLATES:
        raise ValueError(f"unsupported artifact template: {template}")
    return template


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return ordered
