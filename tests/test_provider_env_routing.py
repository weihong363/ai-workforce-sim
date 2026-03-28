import core_engine.config as config_module


def test_default_provider_and_env_connection_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_OPENAI_API_KEY", "test-key-123")
    monkeypatch.setenv("PROVIDER_OPENAI_BASE_URL", "https://example-llm.local/v1")
    base = {
        "openai": {
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
        }
    }
    merged = config_module._apply_provider_env_overrides(base)
    assert merged["openai"]["api_key"] == "test-key-123"
    assert merged["openai"]["base_url"] == "https://example-llm.local/v1"

    # Keep this test focused on provider connection env overrides.


def test_provider_connection_env_override_without_auto_discovery(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    merged = config_module._apply_provider_env_overrides({"mock": {"type": "mock"}})
    # Current behavior: env vars override existing provider configs only.
    # Unknown providers are not auto-discovered from env.
    assert "siliconflow" not in merged
    assert "mock" in merged


def test_model_routing_by_role_and_purpose(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FOR_TASK", "model-base")
    monkeypatch.setenv("MODEL_FOR_EVALUATION", "model-eval")
    monkeypatch.setenv("MODEL_EVALUATOR", "model-eval")
    monkeypatch.setenv("MODEL_TASK_JUNIOR", "model-jr")
    monkeypatch.setenv("MODEL_TASK_MID", "model-mid")
    monkeypatch.setenv("MODEL_TASK_SENIOR", "model-sr")
    config_module.get_settings.cache_clear()
    settings = config_module.get_settings()
    assert settings.get_model_for_role("task", "junior") == "model-jr"
    assert settings.get_model_for_role("task", "mid") == "model-mid"
    assert settings.get_model_for_role("task", "senior") == "model-sr"
    assert settings.get_model_for_role("evaluation", "junior") == "model-eval"
    assert settings.get_model_for_role("evaluation", "senior") == "model-eval"
