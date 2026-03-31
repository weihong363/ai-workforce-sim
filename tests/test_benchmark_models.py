import api.run_task as run_task_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_bench_test")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_bench_test")
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


def test_benchmark_models_smoke(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    payload = run_task_module.benchmark_models(
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        module_name="business_sim",
        agent_level="junior",
        models=["bench-model-a", "bench-model-b"],
    )

    assert payload["agent_level"] == "junior"
    assert "player_summary" in payload
    assert len(payload["results"]) == 2
    assert payload["results"][0]["model"] == "bench-model-a"
    assert payload["results"][1]["model"] == "bench-model-b"
    for item in payload["results"]:
        assert "output_length" in item
        assert "missed_constraints" in item
        assert "deviation_detected" in item
        assert "final_score" in item
        assert "token_usage" in item
        assert "cost" in item
        assert "latency_ms" in item
        assert "actual_models" in item
        assert "actual_providers" in item
        assert "fallback_detected" in item
        assert "failed_constraints" in item
        assert "player_score" in item
        assert "player_grade" in item
        assert "constraint_pass_rate" in item
        assert "verdict" in item


def test_benchmark_hard_task_shows_constraint_misses(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    payload = run_task_module.benchmark_models(
        task_id="tsk_hard_mode_structured_str_31cee1d4",
        module_name="business_sim",
        agent_level="junior",
        models=["bench-hard-a"],
    )

    item = payload["results"][0]
    assert item["missed_constraints"] > 0
    assert item["final_score"] < 100.0


def test_benchmark_advice_handles_smaller_model_beating_bigger_model() -> None:
    rows = [
        {"model": "Qwen/Qwen3-8B", "player_score": 82.0, "cost": 0.4, "latency_ms": 200},
        {"model": "Qwen/Qwen3-14B", "player_score": 70.0, "cost": 0.7, "latency_ms": 1200},
    ]
    advice = run_task_module._build_benchmark_advice(rows)
    assert advice["recommended_model"] == "Qwen/Qwen3-8B"
    assert advice["anomaly_detected"] is True
    assert advice["confidence"] == "low"


def test_benchmark_does_not_mutate_wallet_state(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")

    import game_modules.business_sim.progression as progression_module

    monkeypatch.setattr(
        progression_module,
        "finalize_task_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("benchmark should not mutate wallet")),
    )

    payload = run_task_module.benchmark_models(
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        module_name="business_sim",
        agent_level="junior",
        models=["bench-model-a"],
    )
    assert payload["results"][0]["model"] == "bench-model-a"
