"""Transform workflow results into business_sim asset payload."""

from typing import Dict, List


def to_asset(workflow_results: List[Dict[str, str]], evaluation: Dict[str, object]) -> Dict[str, object]:
    final_output = workflow_results[-1]["output"] if workflow_results else ""
    return {
        "summary": final_output,
        "score": evaluation["final_score"],
        "steps": [result["agent_name"] for result in workflow_results],
    }
