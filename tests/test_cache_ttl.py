from core_engine import cache as cache_module


def test_ttl_capped_to_three_days() -> None:
    assert cache_module._normalize_ttl(9999999, 60) == 259200


def test_inmemory_agent_cache_has_ttl() -> None:
    cache = cache_module.InMemoryCache(agent_cache_ttl_seconds=1)
    key = cache.agent_key(provider="mock", model="mvp-default", prompt="p")
    cache.set_agent(key, {"output": "x"})
    assert cache.get_agent(key) == {"output": "x"}
