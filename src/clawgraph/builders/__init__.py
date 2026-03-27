"""Dataset builder registry and interfaces."""

from __future__ import annotations

import os
from collections import OrderedDict
from importlib import import_module
from importlib.metadata import entry_points
from threading import Lock
from typing import Any

from clawgraph.builders.interfaces import BuildContext, DatasetBuilder

_REGISTRY_LOCK = Lock()
_BUILDERS_BY_NAME: OrderedDict[str, DatasetBuilder] = OrderedDict()
_ALIASES_TO_NAME: dict[str, str] = {}
_EXTERNAL_BUILDERS_LOADED = False


def _coerce_builder(candidate: Any) -> DatasetBuilder:
    if hasattr(candidate, "build_records"):
        return candidate
    if hasattr(candidate, "build"):
        return _LegacyDatasetBuilderAdapter(candidate)
    if callable(candidate):
        built = candidate()
        if hasattr(built, "build_records") or hasattr(built, "build"):
            return _coerce_builder(built)
    raise TypeError("builder must expose build_records() or legacy build()")


def register_dataset_builder(
    builder: DatasetBuilder | Any,
    *,
    replace: bool = False,
) -> DatasetBuilder:
    """Register a dataset builder by canonical name and aliases."""

    normalized = _coerce_builder(builder)
    canonical_name = str(normalized.name)
    aliases = tuple(str(alias) for alias in getattr(normalized, "aliases", ()) or ())

    with _REGISTRY_LOCK:
        conflicting_names = [canonical_name, *aliases]
        for name in conflicting_names:
            existing_canonical = _ALIASES_TO_NAME.get(name)
            if existing_canonical is None:
                continue
            if replace:
                _unregister_dataset_builder_locked(existing_canonical)
                continue
            raise ValueError(f"dataset builder already registered: {name}")

        _BUILDERS_BY_NAME[canonical_name] = normalized
        _ALIASES_TO_NAME[canonical_name] = canonical_name
        for alias in aliases:
            _ALIASES_TO_NAME[alias] = canonical_name

    return normalized


def unregister_dataset_builder(name: str) -> None:
    """Unregister one dataset builder by canonical name or alias."""

    with _REGISTRY_LOCK:
        canonical_name = _ALIASES_TO_NAME.get(name, name)
        _unregister_dataset_builder_locked(canonical_name)


def get_dataset_builder(name: str) -> DatasetBuilder:
    """Return a registered builder by canonical name or alias."""

    _load_external_builders()
    with _REGISTRY_LOCK:
        canonical_name = _ALIASES_TO_NAME.get(name)
        if canonical_name is None:
            raise ValueError(f"unsupported builder: {name}")
        return _BUILDERS_BY_NAME[canonical_name]


def list_dataset_builders() -> tuple[str, ...]:
    """List canonical builder names in registration order."""

    _load_external_builders()
    with _REGISTRY_LOCK:
        return tuple(_BUILDERS_BY_NAME.keys())


def _load_external_builders() -> None:
    global _EXTERNAL_BUILDERS_LOADED
    with _REGISTRY_LOCK:
        if _EXTERNAL_BUILDERS_LOADED:
            return
        _EXTERNAL_BUILDERS_LOADED = True

    module_names = [
        module_name.strip()
        for module_name in os.environ.get("CLAWGRAPH_BUILDER_MODULES", "").split(",")
        if module_name.strip()
    ]
    for module_name in module_names:
        import_module(module_name)

    try:
        discovered = entry_points(group="clawgraph.builders")
    except TypeError:
        discovered = entry_points().get("clawgraph.builders", ())

    for entry_point in discovered:
        loaded = entry_point.load()
        if loaded is None:
            continue
        register_dataset_builder(loaded)


def _unregister_dataset_builder_locked(name: str) -> None:
    builder = _BUILDERS_BY_NAME.pop(name, None)
    if builder is None:
        return
    aliases = [alias for alias, canonical_name in _ALIASES_TO_NAME.items() if canonical_name == name]
    for alias in aliases:
        _ALIASES_TO_NAME.pop(alias, None)


class _LegacyDatasetBuilderAdapter:
    """Adapter for early builders that only exposed build()."""

    def __init__(self, legacy_builder: Any) -> None:
        self.name = str(legacy_builder.name)
        self.aliases = tuple(
            str(alias) for alias in getattr(legacy_builder, "aliases", ()) or ()
        )
        self._legacy_builder = legacy_builder

    def build_records(
        self,
        *,
        facts: list[Any],
        artifacts: list[Any],
        context: BuildContext | None = None,
    ) -> list[dict[str, Any]]:
        return list(
            self._legacy_builder.build(
                trajectory_view=facts,
                artifact_view=artifacts,
                memory_view=None,
                context=context,
            )
        )

    def blockers(
        self,
        *,
        facts: list[Any],
        artifacts: list[Any],
        records: list[dict[str, Any]],
        context: BuildContext | None = None,
    ) -> list[str]:
        blockers_fn = getattr(self._legacy_builder, "blockers", None)
        if callable(blockers_fn):
            return list(
                blockers_fn(
                    facts=facts,
                    artifacts=artifacts,
                    records=records,
                    context=context,
                )
            )
        return [] if records else [f"builder {self.name} produced no records"]


__all__ = [
    "BuildContext",
    "DatasetBuilder",
    "get_dataset_builder",
    "list_dataset_builders",
    "register_dataset_builder",
    "unregister_dataset_builder",
]
