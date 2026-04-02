"""Artifact ingestion, querying, and bootstrap templates."""

from clawgraph.artifacts.annotations import (
    E1_ANNOTATION_ARTIFACT_TYPE,
    E1_ANNOTATION_KIND,
    E1_REQUIRED_FIELDS,
    annotate_records_with_e1,
    build_e1_annotation_artifacts,
    resolve_e1_annotation_for_run,
    summarize_e1_annotations,
)
from clawgraph.artifacts.templates import (
    SUPPORTED_ARTIFACT_TEMPLATES,
    ArtifactBootstrapPlan,
    plan_artifact_bootstrap,
)

__all__ = [
    "E1_ANNOTATION_ARTIFACT_TYPE",
    "E1_ANNOTATION_KIND",
    "E1_REQUIRED_FIELDS",
    "SUPPORTED_ARTIFACT_TEMPLATES",
    "ArtifactBootstrapPlan",
    "annotate_records_with_e1",
    "build_e1_annotation_artifacts",
    "plan_artifact_bootstrap",
    "resolve_e1_annotation_for_run",
    "summarize_e1_annotations",
]
