"""Builder interfaces for dataset exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class BuildContext:
    """Context passed to dataset builders."""

    selection_query: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class DatasetBuilder(Protocol):
    """Protocol implemented by dataset builders."""

    name: str

    def build(
        self,
        trajectory_view: Any,
        artifact_view: Any,
        memory_view: Any | None = None,
        context: BuildContext | None = None,
    ) -> list[dict[str, Any]]:
        """Build a dataset from graph and artifact views."""
