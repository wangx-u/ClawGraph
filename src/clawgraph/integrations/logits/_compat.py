"""Compatibility helpers for optional local Logits / Cookbook imports."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any


_DEFAULT_REQUIRED_LOGITS_MODULES = ("logits", "logits_cookbook", "tinker")
_WORKSPACE_DISCOVERY_ENV = "CLAWGRAPH_ALLOW_WORKSPACE_LOGITS_DISCOVERY"


def workspace_logits_discovery_enabled() -> bool:
    value = os.environ.get(_WORKSPACE_DISCOVERY_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def ensure_workspace_logits_paths() -> Path | None:
    """Add explicit or opt-in workspace paths for `logits` and `logits-cookbook`."""

    configured_logits_src = os.environ.get("CLAWGRAPH_LOGITS_SRC")
    configured_cookbook_src = os.environ.get("CLAWGRAPH_LOGITS_COOKBOOK_SRC")
    if configured_logits_src or configured_cookbook_src:
        for configured in (configured_logits_src, configured_cookbook_src):
            if not configured:
                continue
            candidate = Path(configured).expanduser().resolve()
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        return None

    if not workspace_logits_discovery_enabled():
        return None

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


def _module_import_status(module_name: str) -> dict[str, str | bool | None]:
    try:
        module = importlib.import_module(module_name)
        return {
            "module": module_name,
            "available": True,
            "location": str(getattr(module, "__file__", "")) or None,
            "error": None,
        }
    except Exception as exc:  # pragma: no cover - exercised in integration envs
        return {
            "module": module_name,
            "available": False,
            "location": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def import_logits_stack(required_modules: tuple[str, ...] = _DEFAULT_REQUIRED_LOGITS_MODULES) -> None:
    """Ensure the local Logits workspace is importable."""

    ensure_workspace_logits_paths()
    failures = [
        status
        for status in (_module_import_status(module_name) for module_name in required_modules)
        if not status["available"]
    ]
    if not failures:
        return
    missing = ", ".join(str(item["module"]) for item in failures)
    raise RuntimeError(
        "Logits runtime is incomplete. "
        f"Missing modules: {missing}. "
        "Run `clawgraph logits doctor --json` to inspect the environment, and set "
        "`CLAWGRAPH_LOGITS_SRC` / `CLAWGRAPH_LOGITS_COOKBOOK_SRC` when the runtime "
        "packages are not importable from the current Python environment. "
        "Sibling workspace auto-discovery is disabled by default; enable it only for "
        "local development with `CLAWGRAPH_ALLOW_WORKSPACE_LOGITS_DISCOVERY=1`."
    )


def describe_logits_runtime() -> dict[str, Any]:
    """Report how the Logits bridge resolves its runtime dependencies."""

    workspace_root = ensure_workspace_logits_paths()
    module_statuses = [
        _module_import_status(module_name) for module_name in _DEFAULT_REQUIRED_LOGITS_MODULES
    ]
    return {
        "workspace_root": None if workspace_root is None else str(workspace_root),
        "workspace_auto_discovery_enabled": workspace_logits_discovery_enabled(),
        "configured_logits_src": os.environ.get("CLAWGRAPH_LOGITS_SRC"),
        "configured_cookbook_src": os.environ.get("CLAWGRAPH_LOGITS_COOKBOOK_SRC"),
        "python_path_head": list(sys.path[:8]),
        "modules": module_statuses,
    }


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
