"""Agent definitions and minimal affinity updates for business_sim."""

from typing import Dict, List

AGENTS = {
    "market_analyst": {
        "description": "Junior analyst who follows directions closely.",
        "level": "junior",
        "skill": 0.45,
        "overtime_willingness": 0.65,
        "max_output_tokens": 90,
        "cost_weight": 0.8,
        "artificial_delay_ms": 240,
        "obedience": 0.80,
        "initiative": 0.35,
        "effort": 0.65,
        "affinity": 0.50,
    },
    "strategy_writer": {
        "description": "Senior strategist with higher skill and selective compliance.",
        "level": "senior",
        "skill": 0.80,
        "overtime_willingness": 0.35,
        "max_output_tokens": 180,
        "cost_weight": 1.2,
        "artificial_delay_ms": 80,
        "obedience": 0.45,
        "initiative": 0.70,
        "effort": 0.55,
        "affinity": 0.50,
    },
}


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
