import api.run_task as run_task_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_cost_test")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_cost_test")


def test_cost_calculated_from_provider_rate(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")
    monkeypatch.setenv("COST_PER_1K_BY_PROVIDER_JSON", '{"mock": 2.0}')
    monkeypatch.setenv("LLM_COST_PER_1K_TOKENS_USD", "0")

    result = run_task_module.run_task("tsk_assess_a_city_launch_for_d9bbd92d")
    assert result["total_cost"] > 0
    assert result["comparison_fields"]["cost"] > 0
