"""
Failure Mode and Resilience Integration Tests.
Validates:
1. Redis disconnection with graceful fallback to L1 cache, local locks, and local pub/sub.
2. PostgreSQL transient deadlock and operational error retry logic (execute_with_db_retry).
3. Migration fail-closed behavior on schema corruption or invalid statements.
4. Retention job distributed lock contention handling and error reporting.
5. Concurrent sliding-window rate limiting exhaustion under load.
6. GitHub webhook replay attack prevention via X-GitHub-Delivery deduplication.
7. Stream token invalid and expired single-use consumption resilience.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app
from cerberus.config import settings
from cerberus.core.cache import CacheManager
from cerberus.core.database import AsyncSessionLocal, execute_with_db_retry, init_db
from cerberus.core.migrations import run_migrations
from cerberus.core.retention import _local_retention_lock, run_retention_purge
from cerberus.core.security import RateLimiter, generate_webhook_signature


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_redis_failure_and_seamless_in_memory_fallback():
    """Verify that when Redis is unavailable, cache, locks, and events degrade gracefully."""
    mgr = CacheManager()
    mgr.redis_client = None  # Force Redis unavailable

    # 1. Set and Get in L1 in-memory cache
    await mgr.set("resilience_key", {"data": "secure_val"}, ttl_seconds=60)
    val = await mgr.get("resilience_key")
    assert val == {"data": "secure_val"}

    # 2. Invalidate / delete fallback
    await mgr.delete("resilience_key")
    assert await mgr.get("resilience_key") is None

    # 3. Pub/Sub fallback
    # Should not raise exception
    await mgr.publish_review_event("rev_resilience_test", {"event": "completed"})

    # 4. Stream token fallback
    token = await mgr.create_stream_token("rev_resilience_test", "tenant_test", ttl_seconds=30)
    consumed = await mgr.consume_stream_token(token)
    assert consumed is not None
    assert consumed["review_id"] == "rev_resilience_test"
    assert consumed["tenant_id"] == "tenant_test"

    # Second consumption must return None
    consumed_again = await mgr.consume_stream_token(token)
    assert consumed_again is None


@pytest.mark.asyncio
async def test_database_retry_on_transient_failures():
    """Verify execute_with_db_retry retries transient errors with exponential backoff."""
    attempt_count = 0

    async def flaky_db_op():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise RuntimeError(f"Transient deadlock error on attempt {attempt_count}")
        return "transaction_committed"

    result = await execute_with_db_retry(flaky_db_op, max_retries=3, delay=0.01)
    assert result == "transaction_committed"
    assert attempt_count == 3

    # Assert permanent failure raises after max_retries
    async def doomed_db_op():
        raise ValueError("Fatal syntax error in SQL")

    with pytest.raises(ValueError, match="Fatal syntax error"):
        await execute_with_db_retry(doomed_db_op, max_retries=3, delay=0.01)


@pytest.mark.asyncio
async def test_migration_fail_closed_on_error():
    """Verify schema migrations fail closed and abort transaction on bad SQL."""
    # Create mock engine whose begin() raises an operational error during migration
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = RuntimeError("Fatal DB disk I/O failure")

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn
    mock_ctx.__aexit__.return_value = None
    mock_engine.begin.return_value = mock_ctx

    with pytest.raises(RuntimeError, match="Fatal DB disk I/O failure"):
        await run_migrations(mock_engine)


@pytest.mark.asyncio
async def test_retention_purge_lock_contention_and_failure():
    """Verify retention purge handles active lock contention and reports errors safely."""
    # 1. Lock contention: manually acquire local lock
    await _local_retention_lock.acquire()
    try:
        res = await run_retention_purge(retention_days=30)
        assert res["status"] == "skipped"
        assert res["reason"] == "lock_held"
    finally:
        _local_retention_lock.release()

    # 2. Database exception handling during purge
    with patch("cerberus.core.retention.AsyncSessionLocal") as mock_session_cls:
        mock_session_cls.side_effect = RuntimeError("Database unreachable")
        res_err = await run_retention_purge(retention_days=30)
        assert res_err["status"] == "failed"
        assert "Database unreachable" in res_err["error"]


@pytest.mark.asyncio
async def test_concurrent_sliding_window_rate_limiter_exhaustion():
    """Verify sliding-window rate limiter enforces hard boundary under concurrent load."""
    limiter = RateLimiter(limit_per_hour=5, max_tracked=100)
    client_id = "tenant_concurrency_tester"

    async def make_request():
        return limiter.is_allowed(client_id)

    # Concurrently execute 10 rate check attempts
    results = await asyncio.gather(*(asyncio.to_thread(limiter.is_allowed, client_id) for _ in range(10)))

    allowed_count = sum(1 for r in results if r[0] is True)
    denied_count = sum(1 for r in results if r[0] is False)

    assert allowed_count == 5
    assert denied_count == 5

    # Denied requests must have positive retry_after
    for allowed, remaining, retry_after in results:
        if not allowed:
            assert remaining == 0
            assert retry_after > 0


@pytest.mark.asyncio
async def test_webhook_replay_prevention_deduplication():
    """Verify identical X-GitHub-Delivery requests are recognized as replays and rejected/ignored."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        delivery_id = "deliv_unique_resilience_test_888"
        payload = {
            "action": "labeled",
            "repository": {"name": "cerberus", "owner": {"login": "owner"}, "full_name": "owner/cerberus"},
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY
        signature = generate_webhook_signature(payload_bytes, secret)

        headers = {
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        }

        # First request: processed normally
        resp1 = await client.post("/api/v1/review/webhooks/github", headers=headers, content=payload_bytes)
        assert resp1.status_code == 200
        assert resp1.json().get("reason") != "duplicate_event"

        # Second request (Replay attack): duplicate delivery ID detected and ignored
        resp2 = await client.post("/api/v1/review/webhooks/github", headers=headers, content=payload_bytes)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert resp2.json().get("reason") == "duplicate_event"
        assert resp2.json()["delivery_id"] == delivery_id


@pytest.mark.asyncio
async def test_stream_token_invalid_or_expired_handling():
    """Verify consuming a missing, invalid, or expired stream token returns None cleanly."""
    mgr = CacheManager()
    mgr.redis_client = None

    result = await mgr.consume_stream_token("st_completely_fake_nonexistent_token")
    assert result is None


@pytest.mark.asyncio
async def test_readiness_probe_production_redis_failure():
    """Verify readiness probe returns HTTP 503 when Redis is unhealthy in production."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(settings, "ENVIRONMENT", "production"):
            with patch.object(settings, "REDIS_URL", "redis://fake-redis-host:6379"):
                with patch("cerberus.api.v1.health.cache_manager") as mock_cache:
                    mock_cache.enabled = True
                    mock_redis = AsyncMock()
                    mock_redis.ping.side_effect = RuntimeError("Connection refused")
                    mock_cache.redis_client = mock_redis

                    resp = await client.get("/api/v1/ready")
                    assert resp.status_code == 503
                    data = resp.json()
                    assert data["status"] == "not_ready"
                    assert data["redis"] == "unhealthy"


@pytest.mark.asyncio
async def test_stream_cross_worker_db_fallback():
    """Verify SSE streaming resolves completed status from DB when local in-memory store is empty."""
    import uuid

    from cerberus.api.v1.review import reviews_store
    from cerberus.models.database import CodeReviewRecord

    review_id = f"rev_cross_{uuid.uuid4().hex[:12]}"
    tenant_id = "tenant_stream_worker"

    # Seed record directly in DB as if another worker completed it
    async with AsyncSessionLocal() as session:
        record = CodeReviewRecord(
            id=review_id,
            owner_id=tenant_id,
            code_snippet="def worker_code(): pass",
            status="completed",
            results_json=json.dumps(
                {
                    "review_id": review_id,
                    "status": "completed",
                    "overall_score": 9.5,
                    "created_at": "2026-11-16T00:00:00Z",
                    "summary": "Completed on Worker A",
                    "findings": [],
                }
            ),
        )
        session.add(record)
        await session.commit()

    # Ensure local in-memory store does not have it (simulating Worker B)
    reviews_store.pop(review_id, None)

    mgr = CacheManager()
    mgr.redis_client = None
    token = await mgr.create_stream_token(review_id=review_id, tenant_id=tenant_id, ttl_seconds=30)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("cerberus.api.v1.review.cache_manager.consume_stream_token") as mock_consume:
            mock_consume.return_value = {"review_id": review_id, "tenant_id": tenant_id}
            resp = await client.get(f"/api/v1/review/{review_id}/stream?stream_token={token}")
            assert resp.status_code == 200
            assert "event: completed" in resp.text
            assert review_id in resp.text
