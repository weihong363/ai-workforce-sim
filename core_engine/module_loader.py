"""Load and validate active game module components."""

import re
from importlib import import_module
from typing import Any, Dict, Optional


REQUIRED_EXPORTS = ("agents", "tasks", "evaluation", "asset_transform", "progression")
MODULE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ModuleLoadError(ValueError):
    """Raised when a game module cannot be safely loaded."""


def _validate_module_name(module_name: str) -> None:
    if not module_name:
        raise ModuleLoadError("Module name cannot be empty.")
    if not MODULE_NAME_PATTERN.match(module_name):
        raise ModuleLoadError(
            f"Invalid module name '{module_name}'. Use letters, numbers, and underscores only."
        )


def resolve_module_name(requested_module: Optional[str], active_module: str) -> str:
    """Resolve a module name safely using explicit input or active setting."""
    candidate = requested_module or active_module
    _validate_module_name(candidate)
    return candidate


def load_module(module_name: str) -> Dict[str, Any]:
    """Load and return required components for a game module."""
    _validate_module_name(module_name)
    base = f"game_modules.{module_name}"
    loaded: Dict[str, Any] = {}
    for component in REQUIRED_EXPORTS:
        target = f"{base}.{component}"
        try:
            loaded[component] = import_module(target)
        except Exception as exc:  # pragma: no cover - import error detail only
            raise ModuleLoadError(
                f"Failed to import '{target}' for module '{module_name}': {exc}"
            ) from exc

    if not callable(getattr(loaded["tasks"], "get_task", None)):
        raise ModuleLoadError(f"Module '{module_name}' tasks must define callable get_task(task_id).")
    if not callable(getattr(loaded["evaluation"], "evaluate", None)):
        raise ModuleLoadError(f"Module '{module_name}' evaluation must define callable evaluate(results).")
    if not callable(getattr(loaded["asset_transform"], "to_asset", None)):
        raise ModuleLoadError(
            f"Module '{module_name}' asset_transform must define callable to_asset(results, evaluation)."
        )
    if not hasattr(loaded["agents"], "AGENTS"):
        raise ModuleLoadError(f"Module '{module_name}' agents must define AGENTS.")
    if not callable(getattr(loaded["progression"], "init_user", None)):
        raise ModuleLoadError(
            f"Module '{module_name}' progression must define callable init_user(user_id, ...)."
        )
    if not callable(getattr(loaded["progression"], "list_task_board", None)):
        raise ModuleLoadError(
            f"Module '{module_name}' progression must define callable list_task_board(user_id, tasks)."
        )

    return loaded
