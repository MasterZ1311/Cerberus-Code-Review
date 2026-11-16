"""
Milestone 2 Empirical Challenge Test Suite: Memory Safety & Resource Management.

Author: Challenger 1 (critic, specialist)
Archetype: teamwork_preview_challenger

Adversarially tests and validates:
1. CacheManager:
   - Bounded memory under massive load (inserts beyond CACHE_MAX_ITEMS).
   - Strict LRU eviction order (oldest unaccessed item evicted first; accessing an item protects it).
   - Key updates move entry to MRU position and protect against eviction.
   - Passive TTL expiration on get() and active batch pruning via prune_expired().
   - Single-item boundary capacity (max_items=1).
   - Clear resets cache storage and hit/miss statistics.
   - Concurrent asynchronous set/get resilience.
2. RateLimiter:
   - Flooding with 20,000 random token/IP identifiers bounds memory to max_tracked.
   - Empty timestamp lists are purged and never persist in tracking dictionary.
   - Strict sliding-window rate limiting accuracy (quota enforcement, retry_after calculation).
   - Multi-burst rolling window accuracy over simulated time.
   - LRU identifier eviction protects recently active clients under capacity pressure.
   - Boundary capacity (max_tracked=1).
   - Invariant: all tracking lists are strictly non-empty.
"""

import asyncio
import time
import uuid
import pytest
from cerberus.config import settings
from cerberus.core.cache import CacheManager
from cerberus.core.security import RateLimiter


# =====================================================================
# 1. CacheManager Empirical Stress & LRU Eviction Tests
# =====================================================================


@pytest.mark.asyncio
async def test_cache_insert_beyond_capacity_invariant():
    """CacheManager must strictly cap items at max_items under heavy sequential load."""
    capacity = 50
    manager = CacheManager(max_items=capacity)

    for i in range(2500):
        key = f"key_stream_{i}"
        await manager.set(key, {"index": i, "data": "x" * 64}, ttl_seconds=300)
        # Verify invariant on every insertion
        assert len(manager._memory_cache) <= capacity

    assert len(manager._memory_cache) == capacity

    # Oldest 2450 keys (0 to 2449) must be evicted
    for i in range(0, 2450, 50):
        assert await manager.get(f"key_stream_{i}") is None

    # Last 50 keys (2450 to 2499) must be present
    for i in range(2450, 2500):
        val = await manager.get(f"key_stream_{i}")
        assert val is not None
        assert val["index"] == i


@pytest.mark.asyncio
async def test_cache_insert_beyond_default_capacity_stress():
    """Default CacheManager with settings.CACHE_MAX_ITEMS bounds memory under 3,000 insertions."""
    manager = CacheManager()
    default_capacity = settings.CACHE_MAX_ITEMS  # 1000

    for i in range(3000):
        await manager.set(f"stress_key_{i}", {"val": i}, ttl_seconds=600)

    assert len(manager._memory_cache) == default_capacity
    # Check that early items are evicted
    assert await manager.get("stress_key_0") is None
    assert await manager.get("stress_key_1999") is None
    # Check that recent items exist
    assert await manager.get("stress_key_2000") is not None
    assert await manager.get("stress_key_2999") is not None


@pytest.mark.asyncio
async def test_cache_strict_lru_eviction_order_access_protection():
    """Accessing an item via get() moves it to MRU, protecting it from upcoming evictions."""
    manager = CacheManager(max_items=4)

    # Fill cache: oldest -> newest: K1, K2, K3, K4
    await manager.set("K1", {"val": 1}, ttl_seconds=120)
    await manager.set("K2", {"val": 2}, ttl_seconds=120)
    await manager.set("K3", {"val": 3}, ttl_seconds=120)
    await manager.set("K4", {"val": 4}, ttl_seconds=120)
    assert list(manager._memory_cache.keys()) == ["K1", "K2", "K3", "K4"]

    # Access K1 and K2: order becomes K3 (oldest), K4, K1, K2 (MRU)
    await manager.get("K1")
    await manager.get("K2")
    assert list(manager._memory_cache.keys()) == ["K3", "K4", "K1", "K2"]

    # Insert K5 -> evicts K3 (oldest unaccessed). K1 and K2 are protected!
    await manager.set("K5", {"val": 5}, ttl_seconds=120)
    assert "K3" not in manager._memory_cache
    assert list(manager._memory_cache.keys()) == ["K4", "K1", "K2", "K5"]

    # Insert K6 -> evicts K4 (now oldest unaccessed).
    await manager.set("K6", {"val": 6}, ttl_seconds=120)
    assert "K4" not in manager._memory_cache
    assert list(manager._memory_cache.keys()) == ["K1", "K2", "K5", "K6"]

    # Access K1 again: order becomes K2 (oldest), K5, K6, K1 (MRU)
    await manager.get("K1")
    assert list(manager._memory_cache.keys()) == ["K2", "K5", "K6", "K1"]

    # Insert K7 -> evicts K2 (oldest unaccessed)
    await manager.set("K7", {"val": 7}, ttl_seconds=120)
    assert "K2" not in manager._memory_cache
    assert list(manager._memory_cache.keys()) == ["K5", "K6", "K1", "K7"]

    # Verify evicted keys return None via get()
    assert await manager.get("K3") is None
    assert await manager.get("K4") is None
    assert await manager.get("K2") is None

    # Verify remaining keys return valid data
    for k, v in [("K5", 5), ("K6", 6), ("K1", 1), ("K7", 7)]:
        res = await manager.get(k)
        assert res is not None
        assert res["val"] == v


@pytest.mark.asyncio
async def test_cache_update_existing_key_lru_protection():
    """Updating an existing key in CacheManager moves it to MRU position and prevents eviction."""
    manager = CacheManager(max_items=3)

    await manager.set("A", {"v": "a1"}, ttl_seconds=60)
    await manager.set("B", {"v": "b1"}, ttl_seconds=60)
    await manager.set("C", {"v": "c1"}, ttl_seconds=60)

    # Overwrite A with new value: order becomes B (oldest), C, A (MRU)
    await manager.set("A", {"v": "a2"}, ttl_seconds=60)
    assert len(manager._memory_cache) == 3

    # Insert D -> B must be evicted, NOT A
    await manager.set("D", {"v": "d1"}, ttl_seconds=60)
    assert await manager.get("B") is None
    assert (await manager.get("A"))["v"] == "a2"
    assert (await manager.get("C"))["v"] == "c1"
    assert (await manager.get("D"))["v"] == "d1"


@pytest.mark.asyncio
async def test_cache_ttl_expiration_passive_and_active_pruning():
    """Tests passive cleanup on get() and active batch cleanup via prune_expired()."""
    manager = CacheManager(max_items=100)

    # Insert 60 short-lived keys (0.04s) and 40 long-lived keys (60s)
    for i in range(60):
        await manager.set(f"short_{i}", {"val": i}, ttl_seconds=0.04)
    for i in range(40):
        await manager.set(f"long_{i}", {"val": i}, ttl_seconds=60.0)

    await asyncio.sleep(0.06)

    # 1. Passive expiration on get(): accessing short_0 should return None and delete key
    assert "short_0" in manager._memory_cache
    res = await manager.get("short_0")
    assert res is None
    assert "short_0" not in manager._memory_cache

    # 2. Active batch pruning: remaining 59 short keys should be pruned
    purged_count = manager.prune_expired()
    assert purged_count == 59

    # All 40 long keys must still be intact
    assert len(manager._memory_cache) == 40
    for i in range(40):
        val = await manager.get(f"long_{i}")
        assert val is not None
        assert val["val"] == i

    # Calling prune_expired() again when nothing is expired returns 0
    assert manager.prune_expired() == 0


@pytest.mark.asyncio
async def test_cache_boundary_capacity_one():
    """Cache with max_items=1 retains strictly the single most recent item."""
    manager = CacheManager(max_items=1)

    await manager.set("first", {"step": 1}, ttl_seconds=60)
    assert len(manager._memory_cache) == 1
    assert await manager.get("first") == {"step": 1}

    await manager.set("second", {"step": 2}, ttl_seconds=60)
    assert len(manager._memory_cache) == 1
    assert await manager.get("first") is None
    assert await manager.get("second") == {"step": 2}

    await manager.set("third", {"step": 3}, ttl_seconds=60)
    assert len(manager._memory_cache) == 1
    assert await manager.get("second") is None
    assert await manager.get("third") == {"step": 3}


@pytest.mark.asyncio
async def test_cache_clear_resets_storage_and_stats():
    """clear() completely empties cache and resets hits, misses, and hit_rate."""
    manager = CacheManager(max_items=10)
    await manager.set("k1", {"data": 1}, ttl_seconds=60)
    await manager.get("k1")  # Hit
    await manager.get("k_miss")  # Miss

    assert manager.stats == {"hits": 1, "misses": 1}
    assert manager.hit_rate == 50.0

    manager.clear()
    assert len(manager._memory_cache) == 0
    assert manager.stats == {"hits": 0, "misses": 0}
    assert manager.hit_rate == 0.0


@pytest.mark.asyncio
async def test_cache_concurrent_async_access():
    """Concurrently executing sets and gets preserves capacity invariant."""
    manager = CacheManager(max_items=20)

    async def worker(worker_id: int):
        for step in range(30):
            key = f"w_{worker_id}_step_{step}"
            await manager.set(key, {"w": worker_id, "s": step}, ttl_seconds=60)
            await manager.get(f"w_{worker_id}_step_{max(0, step - 1)}")

    # Run 10 workers concurrently
    await asyncio.gather(*[worker(i) for i in range(10)])

    assert len(manager._memory_cache) <= 20


# =====================================================================
# 2. RateLimiter Empirical Stress & Sliding Window Tests
# =====================================================================


def test_rate_limiter_flood_20k_identifiers_bounded_capacity():
    """
    Flooding rate limiter with 20,000 random token/IP identifiers
    strictly bounds requests dictionary length to max_tracked.
    """
    max_tracked = 300
    limiter = RateLimiter(limit_per_hour=50, max_tracked=max_tracked)

    for i in range(20000):
        token = f"tok_{i}_{uuid.uuid4().hex[:6]}"
        allowed, rem, retry = limiter.is_allowed(token)
        assert allowed is True
        assert rem == 49
        assert retry == 0
        # Invariant must hold continuously
        if i % 1000 == 0:
            assert len(limiter.requests) <= max_tracked

    assert len(limiter.requests) == max_tracked
    # Invariant: No empty timestamp lists exist in requests
    assert all(len(ts) > 0 for ts in limiter.requests.values())


def test_rate_limiter_flood_20k_under_large_capacity():
    """Flooding with 20,000 identifiers when max_tracked=20000 exactly captures 20,000 entries."""
    limiter = RateLimiter(limit_per_hour=100, max_tracked=20000)

    for i in range(20000):
        limiter.is_allowed(f"user_{i}")

    assert len(limiter.requests) == 20000
    assert "user_0" in limiter.requests
    assert "user_19999" in limiter.requests
    assert all(len(ts) == 1 for ts in limiter.requests.values())


def test_rate_limiter_default_max_tracked_boundary():
    """Verifies that exceeding default RATE_LIMIT_MAX_TRACKED bounds dictionary."""
    default_max = settings.RATE_LIMIT_MAX_TRACKED  # 10,000
    limiter = RateLimiter(limit_per_hour=100, max_tracked=default_max)

    # Insert exactly up to default_max
    for i in range(default_max):
        limiter.is_allowed(f"default_client_{i}")

    assert len(limiter.requests) == default_max

    # Insert 50 additional identifiers beyond capacity
    for i in range(default_max, default_max + 50):
        limiter.is_allowed(f"default_client_{i}")
        assert len(limiter.requests) <= default_max

    assert len(limiter.requests) == default_max


def test_rate_limiter_empty_timestamp_lists_completely_removed():
    """Tracking dictionary must delete keys when all timestamps expire, never keeping []."""
    limiter = RateLimiter(limit_per_hour=10, max_tracked=50)

    # Add 10 clients
    for i in range(10):
        limiter.is_allowed(f"client_{i}")
    assert len(limiter.requests) == 10

    # Age 6 clients past 3600 seconds
    now = time.time()
    for i in range(6):
        limiter.requests[f"client_{i}"] = [now - 3700]

    # Active purge
    purged = limiter.purge_expired()
    assert purged == 6
    assert len(limiter.requests) == 4

    # Verify none of the 6 exist as empty lists
    for i in range(6):
        assert f"client_{i}" not in limiter.requests

    # Verify remaining 4 have active timestamps
    for i in range(6, 10):
        assert f"client_{i}" in limiter.requests
        assert len(limiter.requests[f"client_{i}"]) == 1

    # Global invariant check
    assert all(len(ts) > 0 for ts in limiter.requests.values())


def test_rate_limiter_passive_expiration_on_request():
    """An identifier with expired timestamps has them removed on its next request."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=20)

    # Client makes initial requests
    limiter.is_allowed("returning_client")
    limiter.is_allowed("returning_client")
    assert len(limiter.requests["returning_client"]) == 2

    # Artificially age timestamps past 1 hour
    limiter.requests["returning_client"] = [time.time() - 3650, time.time() - 3610]

    # Next request: expired timestamps must be discarded and replaced with new request
    allowed, rem, retry = limiter.is_allowed("returning_client")
    assert allowed is True
    assert rem == 4  # 5 - 1 = 4 (previous expired requests do not count)
    assert retry == 0
    assert len(limiter.requests["returning_client"]) == 1


def test_rate_limiter_sliding_window_strict_accuracy():
    """Strictly validates sliding-window boundary calculation and retry_after."""
    limiter = RateLimiter(limit_per_hour=3, max_tracked=10)
    client_id = "test_strict_window"

    now = time.time()
    limiter.requests[client_id] = [now - 3500, now - 1800, now - 100]

    # Quota exhausted: 4th request must be rejected
    allowed, rem, retry = limiter.is_allowed(client_id)
    assert allowed is False
    assert rem == 0
    # Oldest timestamp is now - 3500. It expires in 3600 - 3500 = 100 seconds.
    assert 95 <= retry <= 105

    # Simulate time advancing 105 seconds: now - 3500 becomes now - 3605 (expired)
    limiter.requests[client_id] = [now - 1800, now - 100]
    allowed, rem, retry = limiter.is_allowed(client_id)
    assert allowed is True
    assert rem == 0  # 2 existing + 1 new = 3 used, remaining 0
    assert retry == 0


def test_rate_limiter_multi_burst_rolling_window():
    """Validates staggered request bursts expiring independently in sliding window."""
    limiter = RateLimiter(limit_per_hour=6, max_tracked=10)
    ident = "burst_client"

    t0 = time.time()
    # 2 requests at t0 - 3500 (will expire in 100s)
    # 2 requests at t0 - 2000 (will expire in 1600s)
    # 2 requests at t0 - 500  (will expire in 3100s)
    limiter.requests[ident] = [t0 - 3500, t0 - 3500, t0 - 2000, t0 - 2000, t0 - 500, t0 - 500]

    # 7th request: rejected (all 6 are active)
    allowed, rem, retry = limiter.is_allowed(ident)
    assert allowed is False
    assert rem == 0

    # Advance time past 100s so first 2 requests expire
    t1 = t0 + 105
    # Remove older than t1 - 3600:
    limiter.requests[ident] = [ts for ts in limiter.requests[ident] if ts > t1 - 3600]
    assert len(limiter.requests[ident]) == 4

    # 2 new requests should now be permitted
    allowed1, rem1, _ = limiter.is_allowed(ident)
    assert allowed1 is True
    assert rem1 == 1

    allowed2, rem2, _ = limiter.is_allowed(ident)
    assert allowed2 is True
    assert rem2 == 0

    # 3rd request rejected
    allowed3, rem3, _ = limiter.is_allowed(ident)
    assert allowed3 is False


def test_rate_limiter_lru_eviction_access_protection():
    """Re-requesting an identifier protects it from eviction when capacity is reached."""
    limiter = RateLimiter(limit_per_hour=10, max_tracked=3)

    limiter.is_allowed("client_a")
    limiter.is_allowed("client_b")
    limiter.is_allowed("client_c")
    assert len(limiter.requests) == 3

    # client_a makes another request, moving it to MRU: order is B, C, A
    limiter.is_allowed("client_a")

    # client_d arrives: B must be evicted (oldest unaccessed)
    limiter.is_allowed("client_d")
    assert len(limiter.requests) == 3
    assert "client_b" not in limiter.requests
    assert "client_a" in limiter.requests
    assert "client_c" in limiter.requests
    assert "client_d" in limiter.requests


def test_rate_limiter_boundary_max_tracked_one():
    """RateLimiter with max_tracked=1 evicts previous identifier on every new client."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=1)

    limiter.is_allowed("single_1")
    assert len(limiter.requests) == 1
    assert "single_1" in limiter.requests

    limiter.is_allowed("single_2")
    assert len(limiter.requests) == 1
    assert "single_1" not in limiter.requests
    assert "single_2" in limiter.requests

    limiter.is_allowed("single_3")
    assert len(limiter.requests) == 1
    assert "single_2" not in limiter.requests
    assert "single_3" in limiter.requests


def test_rate_limiter_global_invariants_under_mixed_traffic():
    """
    Stress-tests RateLimiter under pseudo-random interleaved traffic
    and asserts global invariants: len <= max_tracked and no empty lists.
    """
    import random

    rng = random.Random(42)
    max_tracked = 50
    limiter = RateLimiter(limit_per_hour=5, max_tracked=max_tracked)

    clients = [f"mixed_client_{i}" for i in range(150)]

    for step in range(500):
        client = rng.choice(clients)
        limiter.is_allowed(client)

        # Invariant checks
        assert len(limiter.requests) <= max_tracked
        for key, ts_list in limiter.requests.items():
            assert len(ts_list) > 0, f"Empty list found for key {key}"
            assert len(ts_list) <= limiter.limit
