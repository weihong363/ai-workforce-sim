import api.run_task as run_task_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_test_001")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_test_001")
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("PROVIDER_FOR_EVALUATION", "mock")
    monkeypatch.setenv("PROVIDER_TASK_JUNIOR", "mock")
    monkeypatch.setenv("PROVIDER_TASK_MID", "mock")
    monkeypatch.setenv("PROVIDER_TASK_SENIOR", "mock")
    monkeypatch.setenv("PROVIDER_EVALUATOR", "mock")
    monkeypatch.setenv("MODEL_FOR_TASK", "mvp-default")
    monkeypatch.setenv("MODEL_FOR_EVALUATION", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_JUNIOR", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_MID", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_SENIOR", "mvp-default")
    monkeypatch.setenv("MODEL_EVALUATOR", "mvp-default")
    from core_engine.config import get_settings

    get_settings.cache_clear()
    import game_modules.business_sim.tasks as task_module

    seed_tasks = task_module.get_seed_tasks()
    monkeypatch.setattr(task_module, "list_tasks", lambda: seed_tasks)

    def _get_task(name: str):
        if name not in seed_tasks:
            raise ValueError(f"Unknown task: {name}")
        return seed_tasks[name]

    monkeypatch.setattr(task_module, "get_task", _get_task)


def test_token_budget_enforcement(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    import game_modules.business_sim.tasks as task_module

    seed_tasks = task_module.list_tasks()
    original_budget = seed_tasks["launch_coffee_subscription"].get("max_total_tokens")
    seed_tasks["launch_coffee_subscription"]["max_total_tokens"] = 20
    try:
        result = run_task_module.run_task("launch_coffee_subscription")
    finally:
        seed_tasks["launch_coffee_subscription"]["max_total_tokens"] = original_budget

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
