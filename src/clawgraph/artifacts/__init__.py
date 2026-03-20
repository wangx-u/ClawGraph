"""Artifact ingestion, querying, and bootstrap templates."""

from clawgraph.artifacts.templates import (
    SUPPORTED_ARTIFACT_TEMPLATES,
    ArtifactBootstrapPlan,
    plan_artifact_bootstrap,
)

__all__ = [
    "SUPPORTED_ARTIFACT_TEMPLATES",
    "ArtifactBootstrapPlan",
    "plan_artifact_bootstrap",
]
