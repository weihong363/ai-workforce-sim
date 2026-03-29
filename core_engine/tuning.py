"""Runtime gameplay tuning overrides (in-memory, MVP-safe)."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Dict


_LOCK = threading.Lock()
_OVERRIDES: Dict[str, Any] = {}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_effective_tuning(settings: Any) -> Dict[str, Any]:
    defaults = {
        "clarity_penalty_weight": 34.0,
        "constraint_penalty_weight": 16.0,
        "reward_multiplier": 1.0,
        "agent_trait_weights": {
            "obedience": float(getattr(settings, "obedience_weight", 1.0)),
            "initiative": float(getattr(settings, "initiative_weight", 1.0)),
            "effort": float(getattr(settings, "effort_weight", 1.0)),
        },
        "artificial_delay_multiplier": 1.0,
        "token_budget": {
            "task_multiplier": float(getattr(settings, "task_token_budget_multiplier", 1.0)),
            "agent_multiplier": float(getattr(settings, "agent_token_budget_multiplier", 1.0)),
        },
        "cost_weight_multiplier": 1.0,
    }
    with _LOCK:
        effective = _merge_dict(defaults, _OVERRIDES)

    # Normalize numeric fields to keep deterministic behavior.
    effective["clarity_penalty_weight"] = max(0.0, _to_float(effective.get("clarity_penalty_weight"), 34.0))
    effective["constraint_penalty_weight"] = max(0.0, _to_float(effective.get("constraint_penalty_weight"), 16.0))
    effective["reward_multiplier"] = max(0.0, _to_float(effective.get("reward_multiplier"), 1.0))
    effective["artificial_delay_multiplier"] = max(0.0, _to_float(effective.get("artificial_delay_multiplier"), 1.0))
    effective["cost_weight_multiplier"] = max(0.0, _to_float(effective.get("cost_weight_multiplier"), 1.0))

    traits = effective.get("agent_trait_weights", {}) if isinstance(effective.get("agent_trait_weights"), dict) else {}
    effective["agent_trait_weights"] = {
        "obedience": max(0.0, _to_float(traits.get("obedience"), defaults["agent_trait_weights"]["obedience"])),
        "initiative": max(0.0, _to_float(traits.get("initiative"), defaults["agent_trait_weights"]["initiative"])),
        "effort": max(0.0, _to_float(traits.get("effort"), defaults["agent_trait_weights"]["effort"])),
    }

    budgets = effective.get("token_budget", {}) if isinstance(effective.get("token_budget"), dict) else {}
    effective["token_budget"] = {
        "task_multiplier": max(0.1, _to_float(budgets.get("task_multiplier"), defaults["token_budget"]["task_multiplier"])),
        "agent_multiplier": max(0.1, _to_float(budgets.get("agent_multiplier"), defaults["token_budget"]["agent_multiplier"])),
    }
    return effective


def update_tuning(patch: Dict[str, Any], settings: Any) -> Dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("tuning patch must be an object")
    with _LOCK:
        global _OVERRIDES
        _OVERRIDES = _merge_dict(_OVERRIDES, patch)
    return get_effective_tuning(settings)


def get_tuning_overrides() -> Dict[str, Any]:
    with _LOCK:
        return deepcopy(_OVERRIDES)


def set_tuning_overrides(overrides: Dict[str, Any], settings: Any) -> Dict[str, Any]:
    if not isinstance(overrides, dict):
        raise ValueError("tuning overrides must be an object")
    with _LOCK:
        global _OVERRIDES
        _OVERRIDES = deepcopy(overrides)
    return get_effective_tuning(settings)
