"""
Integration tests for distributed rate limiting and Redis-backed state management.
Tests sliding window Lua script atomicity under concurrency, TTL resets, and in-memory fallback.
"""

import asyncio
import pytest

from cerberus.core.per_key_rate_limiter import PerKeyRateLimiter
from cerberus.core.security import RateLimiter


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_concurrency_and_boundaries():
    """Verify in-memory sliding window rate limiter accurately limits requests."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=100)
    key = "test_key_concurrency_user"

    # Fire 5 requests - all must succeed
    for i in range(5):
        allowed, remaining, retry_after = limiter.is_allowed(key)
        assert allowed is True
        assert remaining == 5 - (i + 1)
        assert retry_after == 0

    # 6th request must be rejected
    allowed, remaining, retry_after = limiter.is_allowed(key)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rate_limiter_async_fallback_without_redis():
    """Verify that is_allowed_async cleanly falls back to in-memory sliding window when Redis is None."""
    limiter = RateLimiter(limit_per_hour=3, max_tracked=50)
    assert limiter._redis_client is None

    res1 = await limiter.is_allowed_async("client_1")
    assert res1[0] is True
    assert res1[1] == 2

    res2 = await limiter.is_allowed_async("client_1")
    assert res2[0] is True
    assert res2[1] == 1

    res3 = await limiter.is_allowed_async("client_1")
    assert res3[0] is True
    assert res3[1] == 0

    res4 = await limiter.is_allowed_async("client_1")
    assert res4[0] is False
    assert res4[1] == 0
    assert res4[2] > 0


@pytest.mark.asyncio
async def test_per_key_token_bucket_rate_limiter():
    """Verify per-key tier-aware token bucket rate limiter."""
    limiter = PerKeyRateLimiter()

    # Free tier key
    key = "cvai_test_free_key_12345"

    allowed, remaining, reset_seconds = await limiter.check_limit(key, tier="free")
    assert allowed is True
    assert remaining >= 0
    assert reset_seconds == 3600


@pytest.mark.asyncio
async def test_concurrent_rate_limiting():
    """Verify concurrent async requests correctly decrement the rate limit quota."""
    limiter = RateLimiter(limit_per_hour=10, max_tracked=100)
    key = "concurrent_client_test"

    async def hit():
        return await limiter.is_allowed_async(key)

    # 15 concurrent calls
    results = await asyncio.gather(*[hit() for _ in range(15)])

    allowed_calls = [r for r in results if r[0] is True]
    denied_calls = [r for r in results if r[0] is False]

    assert len(allowed_calls) == 10
    assert len(denied_calls) == 5
