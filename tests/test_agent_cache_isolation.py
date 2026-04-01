from core_engine.cache import InMemoryCache


def test_agent_cache_key_isolated_by_agent_name() -> None:
    cache = InMemoryCache()
    key_a = cache.agent_key(
        provider="mock",
        model="mvp-default",
        prompt="same prompt",
        behavior_signature="same",
        agent_name="operator",
    )
    key_b = cache.agent_key(
        provider="mock",
        model="mvp-default",
        prompt="same prompt",
        behavior_signature="same",
        agent_name="maverick",
    )
    assert key_a != key_b
