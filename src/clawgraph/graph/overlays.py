"""Artifact overlay helpers for replay and inspect views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.graph.correlation import CorrelatedRequestGroup
from clawgraph.protocol.models import ArtifactRecord


@dataclass(slots=True)
class ArtifactInspectSummary:
    """Compact artifact summary for overlay-oriented surfaces."""

    artifact_id: str
    artifact_type: str
    target_ref: str
    producer: str
    status: str
    confidence: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_artifact(artifact: ArtifactRecord) -> ArtifactInspectSummary:
    """Convert one artifact to a compact inspect summary."""

    return ArtifactInspectSummary(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        target_ref=artifact.target_ref,
        producer=artifact.producer,
        status=artifact.status,
        confidence=artifact.confidence,
    )


def request_artifact_overlays(
    group: CorrelatedRequestGroup,
    artifacts: list[ArtifactRecord] | None,
) -> list[ArtifactInspectSummary]:
    """Return direct fact-level artifacts related to one request lifecycle."""

    if not artifacts:
        return []

    fact_refs = {f"fact:{group.request.fact_id}"}
    if group.response is not None:
        fact_refs.add(f"fact:{group.response.fact_id}")
    if group.error is not None:
        fact_refs.add(f"fact:{group.error.fact_id}")

    matches = [
        summarize_artifact(artifact)
        for artifact in artifacts
        if artifact.target_ref in fact_refs
    ]
    return _dedupe_artifacts(matches)


def branch_artifact_overlays(
    *,
    branch_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord] | None,
) -> list[ArtifactInspectSummary]:
    """Return artifacts directly attached to or semantically mentioning one branch."""

    if not artifacts:
        return []

    matches: list[ArtifactInspectSummary] = []
    for artifact in artifacts:
        if artifact.run_id not in {None, run_id}:
            continue
        if artifact.target_ref == f"branch:{branch_id}":
            matches.append(summarize_artifact(artifact))
            continue
        if _artifact_mentions_branch(artifact.payload, branch_id):
            matches.append(summarize_artifact(artifact))
    return _dedupe_artifacts(matches)


def run_artifact_overlays(
    *,
    run_id: str,
    artifacts: list[ArtifactRecord] | None,
) -> list[ArtifactInspectSummary]:
    """Return artifacts attached directly to one run."""

    if not artifacts:
        return []
    matches = [
        summarize_artifact(artifact)
        for artifact in artifacts
        if artifact.target_ref == f"run:{run_id}"
    ]
    return _dedupe_artifacts(matches)


def session_artifact_overlays(
    *,
    session_id: str,
    artifacts: list[ArtifactRecord] | None,
) -> list[ArtifactInspectSummary]:
    """Return artifacts attached directly to one session."""

    if not artifacts:
        return []
    matches = [
        summarize_artifact(artifact)
        for artifact in artifacts
        if artifact.target_ref == f"session:{session_id}"
    ]
    return _dedupe_artifacts(matches)


def _artifact_mentions_branch(value: Any, branch_id: str) -> bool:
    if isinstance(value, str):
        return value == branch_id
    if isinstance(value, list):
        return any(_artifact_mentions_branch(item, branch_id) for item in value)
    if isinstance(value, dict):
        return any(_artifact_mentions_branch(item, branch_id) for item in value.values())
    return False


def _dedupe_artifacts(
    artifacts: list[ArtifactInspectSummary],
) -> list[ArtifactInspectSummary]:
    deduped: dict[str, ArtifactInspectSummary] = {}
    for artifact in artifacts:
        deduped[artifact.artifact_id] = artifact
    return list(deduped.values())
