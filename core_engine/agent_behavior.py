"""Game-agnostic behavior shaping for agent runtime attributes."""

from typing import Dict


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_effective_attributes(
    profile: Dict[str, object],
    weights: Dict[str, float] | None = None,
) -> Dict[str, float]:
    factors = weights or {}
    obedience_w = float(factors.get("obedience", 1.0))
    initiative_w = float(factors.get("initiative", 1.0))
    effort_w = float(factors.get("effort", 1.0))

    obedience = float(profile.get("obedience", 0.5))
    initiative = float(profile.get("initiative", 0.5))
    effort = float(profile.get("effort", 0.5))
    affinity = float(profile.get("affinity", 0.5))
    clarity = _clamp(float(profile.get("clarity_score", 0.5)))
    level = str(profile.get("level", "mid")).lower()

    affinity_delta = (affinity - 0.5) * 0.4
    clarity_delta = (clarity - 0.5) * 0.35
    low_clarity_penalty = max(0.0, 0.35 - clarity) * 0.4
    level_effort_delta = 0.0
    level_initiative_delta = 0.0
    if level == "junior":
        level_effort_delta = -0.08
        level_initiative_delta = -0.05
    elif level == "senior":
        level_effort_delta = 0.08
        level_initiative_delta = 0.08

    return {
        "obedience": _clamp((obedience + affinity_delta + clarity_delta - (low_clarity_penalty * 0.2)) * obedience_w),
        "initiative": _clamp((initiative + level_initiative_delta) * initiative_w),
        "effort": _clamp((effort + affinity_delta + clarity_delta + level_effort_delta - (low_clarity_penalty * 0.5)) * effort_w),
        "affinity": _clamp(affinity),
    }


def apply_behavior_to_output(output: str, effective: Dict[str, float]) -> str:
    adjusted = str(output or "").strip()

    if effective["effort"] < 0.45:
        words = adjusted.split()
        if len(words) > 6:
            adjusted = " ".join(words[:6]) + " ...[TRUNCATED]"
        elif "...[TRUNCATED]" not in adjusted:
            adjusted = f"{adjusted} ...[TRUNCATED]"
        adjusted = f"LOW_EFFORT_SIGNAL: {adjusted}"

    # Apply control/deviation marker last so output prefix is deterministic.
    if effective["obedience"] <= 0.2 and effective["initiative"] >= 0.8:
        adjusted = f"DEVIATED_FROM_INSTRUCTIONS: {adjusted}"
    elif effective["initiative"] > 0.75:
        adjusted = f"INITIATIVE_EXPANSION: {adjusted}"

    return adjusted
