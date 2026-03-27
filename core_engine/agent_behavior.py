"""Game-agnostic behavior shaping for agent runtime attributes."""

from typing import Dict


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_effective_attributes(profile: Dict[str, object]) -> Dict[str, float]:
    obedience = float(profile.get("obedience", 0.5))
    initiative = float(profile.get("initiative", 0.5))
    effort = float(profile.get("effort", 0.5))
    affinity = float(profile.get("affinity", 0.5))

    affinity_delta = (affinity - 0.5) * 0.4
    return {
        "obedience": _clamp(obedience + affinity_delta),
        "initiative": _clamp(initiative),
        "effort": _clamp(effort + affinity_delta),
        "affinity": _clamp(affinity),
    }


def apply_behavior_to_output(output: str, effective: Dict[str, float]) -> str:
    adjusted = output

    if effective["obedience"] < 0.4 and effective["initiative"] >= 0.5:
        adjusted = f"DEVIATED_FROM_INSTRUCTIONS: {adjusted}"
    elif effective["initiative"] > 0.75:
        adjusted = f"INITIATIVE_EXPANSION: {adjusted}"

    if effective["effort"] < 0.45:
        keep = max(12, int(len(adjusted) * (0.55 + effective["effort"] * 0.35)))
        if keep < len(adjusted):
            adjusted = adjusted[:keep].rstrip() + " ...[TRUNCATED]"

    return adjusted
