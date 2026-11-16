"""
Unit Tests for Two-Tier Caching System and SHA-256 Fingerprinting.
"""

import pytest

from cerberus.core.cache import CacheManager


@pytest.mark.asyncio
async def test_cache_hashing_and_lifecycle():
    manager = CacheManager()

    code1 = "def add(a, b):\n    return a + b"
    code2 = "def add(a, b):\n    return a + b  # extra comment"

    key1 = manager.compute_cache_key(code1, "python", ["security", "performance"])
    key2 = manager.compute_cache_key(code2, "python", ["security", "performance"])

    assert key1 != key2
    assert key1.startswith("cvai:cache:")

    # Test set and get
    sample_data = {"score": 95, "status": "completed"}
    await manager.set(key1, sample_data, ttl_seconds=60)

    cached_val = await manager.get(key1)
    assert cached_val is not None
    assert cached_val["score"] == 95

    # Test cache miss
    miss_val = await manager.get("cvai:cache:non_existent_key")
    assert miss_val is None

    # Check hit rate calculation
    assert manager.hit_rate == 50.0  # 1 hit, 1 miss
