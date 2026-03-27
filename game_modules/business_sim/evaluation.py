"""Simple evaluation rules for business_sim."""

from typing import Dict, List


def evaluate(workflow_results: List[Dict[str, str]]) -> Dict[str, object]:
    completed_steps = len(workflow_results)
    non_empty_outputs = sum(1 for r in workflow_results if r.get("output"))
    base_score = (non_empty_outputs / completed_steps) * 100 if completed_steps else 0.0

    truncation_penalty = sum(1 for r in workflow_results if "...[TRUNCATED]" in str(r.get("output", ""))) * 15
    deviation_penalty = sum(
        1 for r in workflow_results if str(r.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:")
    ) * 10
    initiative_bonus = sum(
        1 for r in workflow_results if str(r.get("output", "")).startswith("INITIATIVE_EXPANSION:")
    ) * 5

    score = max(0.0, min(100.0, base_score - truncation_penalty - deviation_penalty + initiative_bonus))
    score = round(score, 2)

    return {
        "final_score": score,
        "metrics": {
            "completed_steps": completed_steps,
            "non_empty_outputs": non_empty_outputs,
            "truncation_penalty": truncation_penalty,
            "deviation_penalty": deviation_penalty,
            "initiative_bonus": initiative_bonus,
        },
    }
