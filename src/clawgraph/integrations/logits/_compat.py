"""Compatibility helpers for optional local Logits / Cookbook imports."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


def ensure_workspace_logits_paths() -> Path | None:
    """Add sibling workspace paths for `logits` and `logits-cookbook` when present."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        logits_root = parent / "logits"
        cookbook_root = parent / "logits-cookbook"
        if not logits_root.exists() or not cookbook_root.exists():
            continue
        candidates = (logits_root / "src", cookbook_root)
        for candidate in candidates:
            candidate_str = str(candidate)
            if candidate.exists() and candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
        return parent
    return None


def import_logits_stack() -> None:
    """Ensure the local Logits workspace is importable."""

    ensure_workspace_logits_paths()


def load_dotted_object(ref: str) -> Any:
    """Load one object from a `module:attr` reference."""

    if ":" not in ref:
        raise ValueError("dotted reference must look like module:object")
    module_name, attr_path = ref.split(":", 1)
    if not module_name or not attr_path:
        raise ValueError("dotted reference must include both module and object")
    module = importlib.import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise ValueError(f"object not found for reference: {ref}")
        target = getattr(target, part)
    return target

