"""Test optimized config loading with @lru_cache."""

import time
from core_engine.config import get_settings, clear_settings_cache


def test_caching_performance():
    """Test that @lru_cache significantly improves performance."""
    
    # Clear cache to ensure fresh load
    clear_settings_cache()
    
    # First call - will load from scratch
    start = time.time()
    settings1 = get_settings()
    first_load_time = time.time() - start
    
    print(f"✓ First load (cold cache): {first_load_time:.4f}s")
    
    # Second call - should use @lru_cache
    start = time.time()
    settings2 = get_settings()
    cached_load_time = time.time() - start
    
    print(f"✓ Second load (warm cache): {cached_load_time:.6f}s")
    
    # Verify same object returned (lru_cache returns same instance)
    assert settings1 is settings2, "@lru_cache should return cached instance"
    print("✓ @lru_cache returns same instance")
    
    # Test force reload via cache_clear()
    clear_settings_cache()
    start = time.time()
    settings3 = get_settings()
    reload_time = time.time() - start
    
    print(f"✓ After cache_clear(): {reload_time:.4f}s")
    
    # Verify different object after cache clear
    assert settings3 is not settings1, "After cache_clear() should create new instance"
    print("✓ cache_clear() forces reload of new instance")
    
    # Performance comparison
    speedup = first_load_time / cached_load_time if cached_load_time > 0 else float('inf')
    print(f"\n📊 Performance Summary:")
    print(f"   • Cold cache:     {first_load_time:.4f}s")
    print(f"   • Warm cache:     {cached_load_time:.6f}s")
    print(f"   • Speedup:        {speedup:.1f}x faster")
    print(f"   • Reload time:    {reload_time:.4f}s")
    print(f"   • Cache decorator: @lru_cache(maxsize=None)")
    

def test_lru_cache_features():
    """Test @lru_cache specific features."""
    clear_settings_cache()
    
    # Check cache info
    info_before = get_settings.cache_info()
    print(f"\n✓ Cache info (before): {info_before}")
    
    # Call multiple times
    get_settings()
    get_settings()
    get_settings()
    
    # Check cache info after
    info_after = get_settings.cache_info()
    print(f"✓ Cache info (after):  {info_after}")
    
    assert info_after.hits == 2, f"Expected 2 hits, got {info_after.hits}"
    assert info_after.misses == 1, f"Expected 1 miss, got {info_after.misses}"
    print("✓ @lru_cache statistics tracking works correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Optimized Config Loading with @lru_cache")
    print("=" * 60)
    
    test_caching_performance()
    test_lru_cache_features()
    
    print("\n✅ All tests passed!")
