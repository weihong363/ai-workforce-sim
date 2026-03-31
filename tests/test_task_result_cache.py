import api.run_task as run_task_module
import core_engine.cache as cache_module


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_cache_test")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_cache_test")


def test_task_result_cached_and_reused(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    cache_module.GLOBAL_CACHE = cache_module.InMemoryCache()
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")
    monkeypatch.setenv("TASK_RESULT_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("TASK_CACHE_DELAY_MIN_MS", "1")
    monkeypatch.setenv("TASK_CACHE_DELAY_MAX_MS", "2")

    first = run_task_module.run_task("tsk_assess_a_city_launch_for_d9bbd92d")
    second = run_task_module.run_task("tsk_assess_a_city_launch_for_d9bbd92d")

    assert first.get("cache_reused") is not True
    assert second.get("cache_reused") is True
    assert second.get("cache_wait_seconds", 0) > 0
