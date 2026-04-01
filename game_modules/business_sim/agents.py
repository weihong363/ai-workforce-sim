"""Agent definitions and minimal affinity updates for business_sim."""

from copy import deepcopy
from typing import Dict, List

AGENTS: Dict[str, Dict[str, object]] = {}

PLAYER_JUNIOR_ARCHETYPES = {
    "operator": {
        "name": "Operator",
        "role_label": "Reliable Operator",
        "description": "Follows instructions carefully, but rarely exceeds expectations.",
        "player_feel": "Safe pick for basic tasks, weak for high-score pushes.",
        "strengths": ["High obedience", "High stability"],
        "weaknesses": ["Low creativity", "Low potential"],
        "cost_level": "medium",
        "cost_icons": 2,
        "visible_attributes": {
            "execution": 58,
            "creativity": 30,
            "stability": 82,
            "diligence": 63,
            "obedience": 86,
            "potential": 34,
        },
        "hidden": {"volatility": 0.12},
    },
    "maverick": {
        "name": "Maverick",
        "role_label": "High-Risk Creative",
        "description": "Can deliver brilliant work, but vague prompts often send it off track.",
        "player_feel": "Great when you know what you want. Dangerous when you do not.",
        "strengths": ["High creativity", "High potential"],
        "weaknesses": ["Low obedience", "Low stability"],
        "cost_level": "medium",
        "cost_icons": 2,
        "visible_attributes": {
            "execution": 62,
            "creativity": 90,
            "stability": 34,
            "diligence": 56,
            "obedience": 38,
            "potential": 86,
        },
        "hidden": {"volatility": 0.42},
    },
    "slacker": {
        "name": "Slacker",
        "role_label": "Cheap but Unstable",
        "description": "Cheap to run, but often skips details and drifts during execution.",
        "player_feel": "Useful when you need to save money, risky when constraints matter.",
        "strengths": ["Low cost", "Some creative sparks"],
        "weaknesses": ["Low diligence", "Low stability"],
        "cost_level": "low",
        "cost_icons": 1,
        "visible_attributes": {
            "execution": 36,
            "creativity": 52,
            "stability": 28,
            "diligence": 25,
            "obedience": 32,
            "potential": 55,
        },
        "hidden": {"volatility": 0.56},
    },
}


def _to_runtime_profile(archetype: Dict[str, object]) -> Dict[str, object]:
    attrs = archetype.get("visible_attributes", {}) if isinstance(archetype, dict) else {}
    execution = float(attrs.get("execution", 50)) / 100.0
    creativity = float(attrs.get("creativity", 50)) / 100.0
    stability = float(attrs.get("stability", 50)) / 100.0
    diligence = float(attrs.get("diligence", 50)) / 100.0
    obedience = float(attrs.get("obedience", 50)) / 100.0
    potential = float(attrs.get("potential", 50)) / 100.0
    volatility = float((archetype.get("hidden", {}) or {}).get("volatility", 0.2) or 0.2)
    cost_icons = int(archetype.get("cost_icons", 2) or 2)
    fixed_run_cost = 0.12 if cost_icons <= 1 else (0.22 if cost_icons == 2 else 0.35)

    return {
        "description": str(archetype.get("description", "")),
        "level": "junior",
        "skill": round((execution * 0.65) + (potential * 0.35), 4),
        "overtime_willingness": round((diligence * 0.7) + (stability * 0.3), 4),
        "max_output_tokens": int(100 + (execution * 40) + (potential * 30)),
        "cost_weight": round(0.55 + (cost_icons * 0.2), 4),
        "fixed_run_cost": round(fixed_run_cost, 4),
        "artificial_delay_ms": int(160 + ((1.0 - stability) * 160)),
        "obedience": round(obedience, 4),
        "initiative": round((creativity * 0.7) + (potential * 0.3), 4),
        "effort": round((diligence * 0.75) + (execution * 0.25), 4),
        "affinity": 0.5,
        "volatility": round(max(0.0, min(1.0, volatility)), 4),
        "visible_attributes": attrs,
    }


def list_selectable_agents() -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for key, item in PLAYER_JUNIOR_ARCHETYPES.items():
        card = deepcopy(item)
        card.pop("hidden", None)
        card["agent_name"] = key
        card["hidden_trait"] = "volatility"
        output.append(card)
    return output


def supported_workflow_agent_names() -> List[str]:
    return sorted(set(AGENTS.keys()))


def build_default_workflow_overrides(workflow_steps: List[str]) -> Dict[str, Dict[str, object]]:
    defaults = ["operator", "maverick"]
    profiles = [_to_runtime_profile(PLAYER_JUNIOR_ARCHETYPES[name]) for name in defaults]
    overrides: Dict[str, Dict[str, object]] = {}
    for idx, step_name in enumerate(workflow_steps or []):
        overrides[str(step_name)] = dict(profiles[idx % len(profiles)])
    return overrides


def build_user_workflow_overrides(
        owned_agents: List[Dict[str, object]],
        workflow_steps: List[str],
) -> Dict[str, Dict[str, object]]:
    presets: List[str] = []
    for item in owned_agents or []:
        if not isinstance(item, dict):
            continue
        preset = str(item.get("preset", "")).strip().lower()
        if preset in PLAYER_JUNIOR_ARCHETYPES:
            presets.append(preset)
    if not presets:
        return {}
    runtime_profiles = [_to_runtime_profile(PLAYER_JUNIOR_ARCHETYPES[name]) for name in presets]
    overrides: Dict[str, Dict[str, object]] = {}
    for idx, step_name in enumerate(workflow_steps or []):
        overrides[str(step_name)] = dict(runtime_profiles[idx % len(runtime_profiles)])
    return overrides


def get_agent_profile(agent_name: str) -> Dict[str, object]:
    if agent_name not in AGENTS:
        raise ValueError(f"Unknown agent preset: {agent_name}")
    return AGENTS[agent_name]


def update_affinity(workflow_results: List[Dict[str, object]], run_success: bool) -> Dict[str, Dict[str, float]]:
    """Update affinity slightly after each run and return before/after values."""
    delta = 0.03 if run_success else -0.04
    updates: Dict[str, Dict[str, float]] = {}

    for step in workflow_results:
        name = step.get("agent_name")
        if name not in AGENTS:
            continue

        before = float(step.get("affinity_before", AGENTS[name].get("affinity", 0.5)))
        after = max(0.0, min(1.0, before + delta))
        AGENTS[name]["affinity"] = after
        step["affinity_after"] = after

        updates[name] = {"before": before, "after": after}

    return updates


AGENTS = {
    name: _to_runtime_profile(card)
    for name, card in PLAYER_JUNIOR_ARCHETYPES.items()
}
