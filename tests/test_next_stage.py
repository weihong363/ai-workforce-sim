import time

from fastapi.testclient import TestClient

import api.app as app_module
import api.run_task as run_task_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_test_001")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_test_001")


def test_async_run_task_flow_returns_immediately(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "create_run", lambda *args, **kwargs: "run_async_001")

    def fake_run_task(*args, **kwargs):
        time.sleep(0.05)
        return {"storage": {"run_id": "run_async_001"}, "status": "completed"}

    monkeypatch.setattr(app_module, "run_task", fake_run_task)

    client = TestClient(app_module.app)
    response = client.post("/run-task", json={"task_name": "launch_coffee_subscription"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run_async_001"
    assert body["status"] == "pending"


def test_token_budget_enforcement(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    import game_modules.business_sim.tasks as task_module

    original_budget = task_module.TASKS["launch_coffee_subscription"].get("max_total_tokens")
    task_module.TASKS["launch_coffee_subscription"]["max_total_tokens"] = 20
    try:
        result = run_task_module.run_task("launch_coffee_subscription")
    finally:
        task_module.TASKS["launch_coffee_subscription"]["max_total_tokens"] = original_budget

    assert any(step.get("budget_action") == "task_total_budget_truncated" for step in result["workflow_results"])


def test_cost_calculation(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("LLM_COST_PER_1K_TOKENS_USD", "0.5")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    result = run_task_module.run_task("launch_coffee_subscription")
    assert result["total_cost"] > 0
    assert all(float(step.get("cost", 0.0)) >= 0 for step in result["workflow_results"])


def test_delay_simulation_present(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    result = run_task_module.run_task("launch_coffee_subscription")
    assert all(float(step.get("result_delay_seconds", 0.0)) > 0 for step in result["workflow_results"])


def test_junior_vs_senior_comparison(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    # Make delay deterministic for stable comparison.
    monkeypatch.setattr("core_engine.agent_controller.random.uniform", lambda a, b: (a + b) / 2)

    debug = run_task_module.debug_compare_agents("launch_coffee_subscription")
    junior = next(item for item in debug["results"] if item["agent_level"] == "junior")
    senior = next(item for item in debug["results"] if item["agent_level"] == "senior")

    assert senior["evaluation"]["final_score"] >= junior["evaluation"]["final_score"]
    assert junior["latency_ms"] > senior["latency_ms"]
