"""
Comprehensive Unit and Integration Tests for Milestone 2:
Memory Safety & Resource Management.

Verifies:
1. CacheManager: bounded OrderedDict LRU eviction, access reordering, TTL expiration, prune_expired(), and clear().
2. RateLimiter: bounded memory under identifier floods, empty key cleanup, sweep of expired timestamps, and purge_expired().
3. LLM Providers: persistent httpx.AsyncClient connection pooling, connection limits, and graceful close() lifecycle.
4. Review API: bounded reviews_store, database fallback for evicted reviews, batch size limits, and concurrency throttling.
"""

import asyncio
import time
import uuid
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from cerberus.api.app import app
from cerberus.api.v1.review import (
    REVIEWS_STORE_MAX_ITEMS,
    _store_review,
    reviews_store,
)
from cerberus.config import settings
from cerberus.core.cache import CacheManager
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.security import RateLimiter
from cerberus.models.database import CodeReviewRecord
from cerberus.models.schemas import CodeReviewResponse
from cerberus.providers.base import BaseLLMProvider
from cerberus.providers.ollama_provider import OllamaProvider
from cerberus.providers.openai_provider import OpenAIProvider
from cerberus.providers.watsonx_provider import WatsonxProvider


# =====================================================================
# 1. CacheManager Bounded LRU & Lifecycle Tests
# =====================================================================


@pytest.mark.asyncio
async def test_cache_bounded_capacity_and_lru_eviction():
    """CacheManager must evict the least-recently used entry when capacity is exceeded."""
    manager = CacheManager(max_items=3)

    await manager.set("key1", {"val": 1}, ttl_seconds=60)
    await manager.set("key2", {"val": 2}, ttl_seconds=60)
    await manager.set("key3", {"val": 3}, ttl_seconds=60)

    assert len(manager._memory_cache) == 3

    # Access key1 so key2 becomes the oldest / least recently used
    val1 = await manager.get("key1")
    assert val1 == {"val": 1}

    # Inserting key4 should evict key2 (not key1)
    await manager.set("key4", {"val": 4}, ttl_seconds=60)
    assert len(manager._memory_cache) == 3

    assert await manager.get("key2") is None  # key2 evicted
    assert await manager.get("key1") == {"val": 1}
    assert await manager.get("key3") == {"val": 3}
    assert await manager.get("key4") == {"val": 4}


@pytest.mark.asyncio
async def test_cache_expired_entry_deletion_on_get():
    """Accessing an expired entry via get() must delete it and return None."""
    manager = CacheManager(max_items=5)

    await manager.set("expiring_key", {"val": "temp"}, ttl_seconds=0.01)
    await asyncio.sleep(0.03)

    # get() must detect expiration, delete key, and return None
    result = await manager.get("expiring_key")
    assert result is None
    assert "expiring_key" not in manager._memory_cache


@pytest.mark.asyncio
async def test_cache_prune_expired_and_clear():
    """prune_expired() removes stale entries; clear() resets storage and stats."""
    manager = CacheManager(max_items=10)

    await manager.set("stale1", {"val": 1}, ttl_seconds=0.01)
    await manager.set("stale2", {"val": 2}, ttl_seconds=0.01)
    await manager.set("fresh", {"val": 3}, ttl_seconds=60)

    await asyncio.sleep(0.03)

    purged = manager.prune_expired()
    assert purged == 2
    assert "stale1" not in manager._memory_cache
    assert "stale2" not in manager._memory_cache
    assert "fresh" in manager._memory_cache

    manager.clear()
    assert len(manager._memory_cache) == 0
    assert manager.stats == {"hits": 0, "misses": 0}


# =====================================================================
# 2. RateLimiter Bounded Storage & Cleanup Tests
# =====================================================================


def test_rate_limiter_prunes_empty_identifier_keys():
    """When all timestamps for an identifier expire, the identifier key is deleted."""
    limiter = RateLimiter(limit_per_hour=10, max_tracked=100)

    allowed, remaining, retry = limiter.is_allowed("test_client")
    assert allowed is True
    assert "test_client" in limiter.requests

    # Artificially age the timestamp beyond 1 hour
    limiter.requests["test_client"] = [time.time() - 3601]

    # Calling purge_expired removes the key
    purged = limiter.purge_expired()
    assert purged == 1
    assert "test_client" not in limiter.requests


def test_rate_limiter_memory_bounding_under_random_identifiers():
    """RateLimiter memory must never exceed max_tracked under randomized identifier attacks."""
    max_capacity = 25
    limiter = RateLimiter(limit_per_hour=10, max_tracked=max_capacity)

    # Flood with 100 unique random identifiers
    for i in range(100):
        token = f"random_user_{i}_{uuid.uuid4().hex[:8]}"
        limiter.is_allowed(token)

    assert len(limiter.requests) <= max_capacity


def test_rate_limiter_sweep_and_oldest_eviction_at_capacity():
    """When capacity is reached, expired identifiers are purged; if still full, oldest key is evicted."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=3)

    limiter.is_allowed("user_a")
    limiter.is_allowed("user_b")
    limiter.is_allowed("user_c")
    assert len(limiter.requests) == 3

    # Age user_b beyond 1 hour
    limiter.requests["user_b"] = [time.time() - 3700]

    # user_d should trigger sweep, removing user_b, leaving user_a, user_c, user_d
    limiter.is_allowed("user_d")
    assert len(limiter.requests) == 3
    assert "user_b" not in limiter.requests
    assert "user_d" in limiter.requests

    # Now all 3 (a, c, d) are active. Adding user_e must evict the oldest (user_a)
    limiter.is_allowed("user_e")
    assert len(limiter.requests) == 3
    assert "user_a" not in limiter.requests
    assert "user_e" in limiter.requests


def test_rate_limiter_sliding_window_enforcement():
    """Rate limiter allows requests within limit and throttles with retry_after when exceeded."""
    limiter = RateLimiter(limit_per_hour=2, max_tracked=10)

    allowed1, rem1, retry1 = limiter.is_allowed("client_x")
    assert allowed1 is True
    assert rem1 == 1
    assert retry1 == 0

    allowed2, rem2, retry2 = limiter.is_allowed("client_x")
    assert allowed2 is True
    assert rem2 == 0
    assert retry2 == 0

    allowed3, rem3, retry3 = limiter.is_allowed("client_x")
    assert allowed3 is False
    assert rem3 == 0
    assert retry3 > 0


# =====================================================================
# 3. LLM Providers Client Pooling & Lifecycle Tests
# =====================================================================


class ConcreteProvider(BaseLLMProvider):
    async def is_available(self) -> bool:
        return True

    async def generate_response(self, system_prompt: str, user_prompt: str):
        return "response"


@pytest.mark.asyncio
async def test_base_provider_persistent_client_and_pooling():
    """BaseLLMProvider lazily instantiates and reuses a single httpx.AsyncClient with connection limits."""
    provider = ConcreteProvider()
    assert provider._client is None

    client1 = await provider.get_client()
    assert isinstance(client1, httpx.AsyncClient)
    assert not client1.is_closed
    transport = client1._transport
    assert getattr(transport, "_pool", None) is not None
    assert transport._pool._max_keepalive_connections == 20
    assert transport._pool._max_connections == 100

    # Second call returns identical client instance
    client2 = await provider.get_client()
    assert client1 is client2

    # Close gracefully shuts down the persistent client
    await provider.close()
    assert client1.is_closed
    assert provider._client is None


@pytest.mark.asyncio
async def test_provider_subclasses_client_lifecycle():
    """Ollama, OpenAI, and Watsonx providers support persistent connection reuse and close()."""
    for ProviderCls in (OllamaProvider, OpenAIProvider, WatsonxProvider):
        provider = ProviderCls()
        client = await provider.get_client()
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed

        # Verify client instance is reused
        client_again = await provider.get_client()
        assert client is client_again

        await provider.close()
        assert client.is_closed
        assert provider._client is None


# =====================================================================
# 4. Review API Bounded Store, DB Fallback & Batch Throttling Tests
# =====================================================================


def test_reviews_store_bounded_eviction(monkeypatch):
    """_store_review must bound memory and evict the oldest review when capacity is reached."""
    import cerberus.api.v1.review as review_module

    monkeypatch.setattr(review_module, "REVIEWS_STORE_MAX_ITEMS", 3)

    for i in range(4):
        rid = f"rev_bound_test_{i}_{uuid.uuid4().hex[:4]}"
        resp = CodeReviewResponse(
            review_id=rid,
            status="completed",
            created_at="2026-09-22T00:00:00Z",
            overall_score=90.0,
            processing_time_ms=100,
            language="python",
            agents_executed=["security"],
            summary=f"Review {i}",
            critical_issues=[],
            warnings=[],
            suggestions=[],
        )
        review_module._store_review(rid, resp)

    assert len(review_module.reviews_store) <= 3


@pytest.mark.asyncio
async def test_get_review_status_fallback_to_database():
    """When a review is evicted from reviews_store, get_review_status retrieves it from database."""
    evicted_review_id = f"rev_evicted_{uuid.uuid4().hex[:12]}"
    record_data = {
        "review_id": evicted_review_id,
        "status": "completed",
        "created_at": "2026-09-22T00:00:00Z",
        "overall_score": 88.5,
        "processing_time_ms": 150,
        "language": "python",
        "agents_executed": ["security", "quality"],
        "summary": "DB fallback test review",
        "critical_issues": [],
        "warnings": [],
        "suggestions": [],
    }

    # Persist record in SQLite DB
    async with AsyncSessionLocal() as session:
        rec = CodeReviewRecord(
            id=evicted_review_id,
            code_snippet="def foo(): pass",
            language="python",
            status="completed",
            overall_score=88.5,
            processing_time_ms=150,
            results_json=record_data,
        )
        session.add(rec)
        await session.commit()

    # Ensure it is NOT in in-memory reviews_store
    if evicted_review_id in reviews_store:
        del reviews_store[evicted_review_id]

    # Query API endpoint: should fall back to DB and succeed with 200
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/review/{evicted_review_id}", headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["review_id"] == evicted_review_id
        assert data["overall_score"] == 88.5

        # Verify it was re-cached in in-memory reviews_store
        assert evicted_review_id in reviews_store


@pytest.mark.asyncio
async def test_batch_review_exceeds_max_batch_size_rejected():
    """Submitting a batch review with more files than MAX_BATCH_SIZE returns HTTP 400."""
    from cerberus.models.schemas import CodeReviewRequest

    oversized_files = [
        CodeReviewRequest(code=f"def f_{i}(): pass", language="python") for i in range(settings.MAX_BATCH_SIZE + 5)
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in oversized_files]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res.status_code == 400
        assert f"exceeds maximum allowed of {settings.MAX_BATCH_SIZE}" in res.json()["detail"]


@pytest.mark.asyncio
async def test_batch_review_concurrency_bounded_by_semaphore(monkeypatch):
    """Batch review execution must throttle concurrent agent executions using semaphore."""
    from cerberus.agents.orchestrator import orchestrator
    from cerberus.models.schemas import CodeReviewRequest

    max_concurrent_observed = 0
    currently_active = 0
    lock = asyncio.Lock()

    original_execute_review = orchestrator.execute_review

    async def tracking_execute_review(req):
        nonlocal max_concurrent_observed, currently_active
        async with lock:
            currently_active += 1
            if currently_active > max_concurrent_observed:
                max_concurrent_observed = currently_active
        try:
            # Brief sleep to allow concurrent tasks to overlap up to semaphore limit
            await asyncio.sleep(0.05)
            return await original_execute_review(req)
        finally:
            async with lock:
                currently_active -= 1

    monkeypatch.setattr(orchestrator, "execute_review", tracking_execute_review)

    batch_files = [CodeReviewRequest(code=f"def file_{i}(): return {i}", language="python") for i in range(12)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in batch_files]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_files"] == 12
        assert len(data["reviews"]) == 12

    # Active concurrency must never have exceeded MAX_CONCURRENT_BATCH_REVIEWS
    assert max_concurrent_observed <= settings.MAX_CONCURRENT_BATCH_REVIEWS
    assert max_concurrent_observed > 1  # Confirms parallel processing occurred


@pytest.mark.asyncio
async def test_cache_update_existing_key_moves_to_mru():
    """Updating an existing key in CacheManager updates data and keeps item MRU."""
    manager = CacheManager(max_items=2)
    await manager.set("k1", {"val": "original"}, ttl_seconds=60)
    await manager.set("k2", {"val": "k2_val"}, ttl_seconds=60)

    # Overwrite k1
    await manager.set("k1", {"val": "updated"}, ttl_seconds=60)
    assert len(manager._memory_cache) == 2

    # Adding k3 should evict k2, not k1
    await manager.set("k3", {"val": "k3_val"}, ttl_seconds=60)
    assert await manager.get("k2") is None
    assert (await manager.get("k1"))["val"] == "updated"
    assert (await manager.get("k3"))["val"] == "k3_val"


def test_rate_limiter_partial_expired_timestamps():
    """RateLimiter correctly removes only timestamps older than 1 hour, keeping recent ones."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=10)
    now = time.time()
    limiter.requests["user_partial"] = [now - 4000, now - 3700, now - 1800, now - 600]

    allowed, rem, retry = limiter.is_allowed("user_partial")
    assert allowed is True
    # Initial timestamps inside 1-hour window: 2 (now - 1800, now - 600).
    # Plus new timestamp = 3. Remaining = 5 - 3 = 2.
    assert rem == 2
    assert len(limiter.requests["user_partial"]) == 3


@pytest.mark.asyncio
async def test_batch_review_exact_max_boundary(monkeypatch):
    """Batch review with exactly MAX_BATCH_SIZE is permitted and not rejected."""
    from cerberus.agents.orchestrator import orchestrator
    from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse

    dummy_resp = CodeReviewResponse(
        review_id="batch_boundary_rev",
        status="completed",
        created_at="2026-09-22T00:00:00Z",
        overall_score=95.0,
        processing_time_ms=10,
        language="python",
        agents_executed=["security"],
        summary="Boundary test",
        critical_issues=[],
        warnings=[],
        suggestions=[],
    )

    async def fast_mock_review(req):
        return dummy_resp

    monkeypatch.setattr(orchestrator, "execute_review", fast_mock_review)

    batch_files = [CodeReviewRequest(code="def f(): pass", language="python") for _ in range(settings.MAX_BATCH_SIZE)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in batch_files]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_files"] == settings.MAX_BATCH_SIZE


@pytest.mark.asyncio
async def test_provider_client_reuse_during_invocations(monkeypatch):
    """Provider generate_response reuses the persistent client and passes timeout."""
    provider = OllamaProvider()

    calls = []
    fake_client = await provider.get_client()

    async def mock_post(url, json=None, timeout=None, headers=None):
        calls.append({"url": url, "timeout": timeout})
        return httpx.Response(200, json={"response": "Mocked LLM generation"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(fake_client, "post", mock_post)

    resp1 = await provider.generate_response("System", "User 1")
    resp2 = await provider.generate_response("System", "User 2")

    assert resp1 == "Mocked LLM generation"
    assert resp2 == "Mocked LLM generation"
    assert len(calls) == 2
    assert calls[0]["timeout"] == 30.0
    assert calls[1]["timeout"] == 30.0

    await provider.close()
