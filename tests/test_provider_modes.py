import os

import pytest

import api.run_task as run_task_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_test_001")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_test_001")


def test_mock_mode_smoke(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("USE_MOCK_PROVIDER", "true")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")
    monkeypatch.setenv("LLM_COST_PER_1K_TOKENS_USD", "0.5")

    result = run_task_module.run_task("launch_coffee_subscription")

    assert result["status"] == "completed"
    assert result["workflow_results"][0]["provider"] == "mock"
    assert "comparison_fields" in result
    assert "token_usage" in result["comparison_fields"]
    assert "cost" in result["comparison_fields"]


@pytest.mark.integration
def test_real_provider_mode_integration_path(monkeypatch) -> None:
    if os.getenv("RUN_REAL_PROVIDER_TEST") != "1":
        pytest.skip("Set RUN_REAL_PROVIDER_TEST=1 to run real provider integration path.")
    if not (os.getenv("PROVIDER_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        pytest.skip("PROVIDER_OPENAI_API_KEY or OPENAI_API_KEY is required for real provider integration path.")

    _patch_persistence(monkeypatch)
    monkeypatch.setenv("USE_MOCK_PROVIDER", "false")
    monkeypatch.setenv("DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "openai")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    comparison = run_task_module.run_junior_vs_senior_comparison("launch_coffee_subscription")

    assert comparison["provider"] == "openai"
    assert "junior" in comparison
    assert "senior" in comparison
    assert "final_score" in comparison["junior"]
    assert "token_usage" in comparison["senior"]
