"""Sequential workflow runner."""

from typing import Dict, List

from core_engine.agent_controller import AgentController
from core_engine.logging_utils import log_event


def run_sequential_workflow(
    workflow_steps: List[str],
    task_input: str,
    agent_controller: AgentController,
    agent_profiles: Dict[str, Dict[str, object]] = None,
    logger: object = None,
) -> List[Dict[str, object]]:
    """Run agents in order, passing prior output forward."""
    results: List[Dict[str, str]] = []
    previous_output = ""

    for index, agent_name in enumerate(workflow_steps):
        if logger is not None:
            log_event(logger, "step_execution_start", step_index=index, agent_name=agent_name)
        result = agent_controller.run_agent(
            agent_name=agent_name,
            task_input=task_input,
            previous_output=previous_output,
            agent_profile=(agent_profiles or {}).get(agent_name, {}),
        )
        results.append(result)
        previous_output = result["output"]
        if logger is not None:
            log_event(
                logger,
                "step_execution_end",
                step_index=index,
                agent_name=agent_name,
                output_length=len(result["output"]),
                provider=result.get("provider"),
                model=result.get("model"),
                token_usage=result.get("token_usage", {}),
                cache_hit=bool(result.get("cache_hit", False)),
            )

    return results
