"""Builder interfaces for dataset exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from clawgraph.protocol.models import ArtifactRecord, FactEvent


@dataclass(slots=True)
class BuildContext:
    """Context passed to dataset builders."""

    session_id: str | None = None
    run_id: str | None = None
    selection_query: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class DatasetBuilder(Protocol):
    """Protocol implemented by dataset builders."""

    name: str
    aliases: tuple[str, ...]

    def build_records(
        self,
        *,
        facts: list[FactEvent],
        artifacts: list[ArtifactRecord],
        context: BuildContext | None = None,
    ) -> list[dict[str, Any]]:
        """Build self-contained records from captured facts and artifacts."""

    def blockers(
        self,
        *,
        facts: list[FactEvent],
        artifacts: list[ArtifactRecord],
        records: list[dict[str, Any]],
        context: BuildContext | None = None,
    ) -> list[str]:
        """Return builder-specific blockers for the current scope."""
