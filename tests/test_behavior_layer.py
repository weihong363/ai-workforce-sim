from core_engine.agent_controller import AgentController
from core_engine.config import get_settings
from game_modules.business_sim import agents as business_agents


def test_obedience_and_effort_influence_output_behavior() -> None:
    controller = AgentController(settings=get_settings(), enable_agent_cache=False)

    low_control = controller.run_agent(
        agent_name="market_analyst",
        task_input="Follow exact instruction",
        agent_profile={"obedience": 0.2, "initiative": 0.8, "effort": 0.2, "affinity": 0.5},
    )
    assert low_control["output"].startswith("DEVIATED_FROM_INSTRUCTIONS:")
    assert "...[TRUNCATED]" in low_control["output"]

    high_control = controller.run_agent(
        agent_name="market_analyst",
        task_input="Follow exact instruction",
        agent_profile={"obedience": 0.9, "initiative": 0.2, "effort": 0.9, "affinity": 0.5},
    )
    assert not high_control["output"].startswith("DEVIATED_FROM_INSTRUCTIONS:")
    assert "...[TRUNCATED]" not in high_control["output"]


def test_affinity_influences_effective_behavior() -> None:
    controller = AgentController(settings=get_settings(), enable_agent_cache=False)

    low_affinity = controller.run_agent(
        agent_name="strategy_writer",
        task_input="Create a strategy",
        agent_profile={"obedience": 0.5, "initiative": 0.5, "effort": 0.5, "affinity": 0.1},
    )
    high_affinity = controller.run_agent(
        agent_name="strategy_writer",
        task_input="Create a strategy",
        agent_profile={"obedience": 0.5, "initiative": 0.5, "effort": 0.5, "affinity": 0.9},
    )

    assert low_affinity["effective_attributes"]["obedience"] < high_affinity["effective_attributes"]["obedience"]
    assert low_affinity["effective_attributes"]["effort"] < high_affinity["effective_attributes"]["effort"]


def test_post_run_affinity_update() -> None:
    original = {
        "market_analyst": business_agents.AGENTS["market_analyst"]["affinity"],
        "strategy_writer": business_agents.AGENTS["strategy_writer"]["affinity"],
    }
    try:
        workflow = [
            {"agent_name": "market_analyst", "affinity_before": 0.5},
            {"agent_name": "strategy_writer", "affinity_before": 0.5},
        ]
        updates = business_agents.update_affinity(workflow_results=workflow, run_success=True)

        assert updates["market_analyst"]["after"] > updates["market_analyst"]["before"]
        assert updates["strategy_writer"]["after"] > updates["strategy_writer"]["before"]
        assert workflow[0]["affinity_after"] == updates["market_analyst"]["after"]
        assert workflow[1]["affinity_after"] == updates["strategy_writer"]["after"]
    finally:
        # Restore mutable module state for test isolation.
        business_agents.AGENTS["market_analyst"]["affinity"] = original["market_analyst"]
        business_agents.AGENTS["strategy_writer"]["affinity"] = original["strategy_writer"]
