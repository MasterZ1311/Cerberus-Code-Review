"""
Empirical Challenge & Stress Test Suite for Milestone 2:
Provider Session Pooling & Batch Review Concurrency Throttling.

Challenger 2 Test Battery:
1. Provider Session Pooling:
   - OllamaProvider persistent client session reuse across is_available() and generate_response()
   - OpenAIProvider persistent client session reuse across multiple invocations
   - WatsonxProvider persistent client session reuse across multiple invocations
   - Provider session resilience under simulated connection errors / timeouts
   - Concurrent get_client() race condition verification
   - Provider close() lifecycle, socket closure, and reinitialization
   - HTTP transport connection pool limits (max_keepalive=20, max_connections=100)
2. Batch Review Concurrency & Throttling:
   - Active concurrent tasks strictly bounded by MAX_CONCURRENT_BATCH_REVIEWS under heavy load (25 files)
   - Dynamic semaphore sizing when MAX_CONCURRENT_BATCH_REVIEWS is altered
   - Rejection of oversized batches (> MAX_BATCH_SIZE) with HTTP 400
   - Acceptance of boundary batches (exactly MAX_BATCH_SIZE = 100 files)
   - Handling of empty batch requests ([] files)
   - Semaphore cleanup and deadlock prevention under agent exceptions
   - Batch reviews stored in bounded reviews_store
   - Authentication enforcement on batch endpoint
"""

import asyncio
import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.agents.orchestrator import orchestrator
from cerberus.api.app import app
from cerberus.api.v1.review import reviews_store
from cerberus.config import settings
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse
from cerberus.providers.ollama_provider import OllamaProvider
from cerberus.providers.openai_provider import OpenAIProvider
from cerberus.providers.watsonx_provider import WatsonxProvider


def _make_dummy_response(review_id: str = None) -> CodeReviewResponse:
    rid = review_id or f"rev_stress_{uuid.uuid4().hex[:8]}"
    return CodeReviewResponse(
        review_id=rid,
        status="completed",
        created_at="2026-09-22T00:00:00Z",
        overall_score=85.0,
        processing_time_ms=50,
        language="python",
        agents_executed=["security", "performance"],
        summary="Stress test review",
        critical_issues=[],
        warnings=[],
        suggestions=[],
    )


# =====================================================================
# PART 1: PROVIDER SESSION POOLING & LIFECYCLE
# =====================================================================


@pytest.mark.asyncio
async def test_ollama_provider_session_reuse_across_calls(monkeypatch):
    """Verify OllamaProvider reuses the exact same AsyncClient session across multiple calls."""
    provider = OllamaProvider()
    client = await provider.get_client()
    original_client_id = id(client)

    post_call_count = 0
    get_call_count = 0

    async def mock_get(url, timeout=None):
        nonlocal get_call_count
        get_call_count += 1
        return httpx.Response(200, json={"models": []}, request=httpx.Request("GET", url))

    async def mock_post(url, json=None, timeout=None):
        nonlocal post_call_count
        post_call_count += 1
        return httpx.Response(
            200, json={"response": f"Ollama answer {post_call_count}"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(client, "get", mock_get)
    monkeypatch.setattr(client, "post", mock_post)

    # 1. Check availability twice
    avail1 = await provider.is_available()
    avail2 = await provider.is_available()
    assert avail1 is True
    assert avail2 is True
    assert get_call_count == 2
    assert id(provider._client) == original_client_id

    # 2. Generate responses 5 times
    for i in range(1, 6):
        resp = await provider.generate_response("System Prompt", f"User question {i}")
        assert resp == f"Ollama answer {i}"
        assert id(provider._client) == original_client_id

    assert post_call_count == 5
    assert not client.is_closed

    # 3. Graceful close
    await provider.close()
    assert client.is_closed
    assert provider._client is None


@pytest.mark.asyncio
async def test_openai_provider_session_reuse_across_calls(monkeypatch):
    """Verify OpenAIProvider reuses the exact same AsyncClient session across multiple requests."""
    provider = OpenAIProvider()
    provider.api_key = "sk-test-challenger-key-for-pooling-verification"

    client = await provider.get_client()
    original_client_id = id(client)

    call_count = 0

    async def mock_post(url, json=None, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1
        payload = {"choices": [{"message": {"content": f"OpenAI answer {call_count}"}}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(client, "post", mock_post)

    for i in range(1, 6):
        resp = await provider.generate_response("System prompt", f"User prompt {i}")
        assert resp == f"OpenAI answer {i}"
        assert id(provider._client) == original_client_id

    assert call_count == 5
    assert not client.is_closed

    await provider.close()
    assert client.is_closed
    assert provider._client is None


@pytest.mark.asyncio
async def test_watsonx_provider_session_reuse_across_calls(monkeypatch):
    """Verify WatsonxProvider reuses the exact same AsyncClient session across multiple requests."""
    provider = WatsonxProvider()
    provider.api_key = "watsonx-test-credential"
    provider.project_id = "watsonx-project-1234"

    client = await provider.get_client()
    original_client_id = id(client)

    call_count = 0

    async def mock_post(url, *args, **kwargs):
        nonlocal call_count
        if "iam.cloud.ibm.com" in str(url):
            return httpx.Response(
                200, json={"access_token": "mock-iam-token", "expires_in": 3600}, request=httpx.Request("POST", url)
            )
        call_count += 1
        payload = {"results": [{"generated_text": f"watsonx granite result {call_count}"}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(client, "post", mock_post)

    for i in range(1, 6):
        resp = await provider.generate_response("System prompt", f"User prompt {i}")
        assert resp == f"watsonx granite result {i}"
        assert id(provider._client) == original_client_id

    assert call_count == 5
    assert not client.is_closed

    await provider.close()
    assert client.is_closed
    assert provider._client is None


@pytest.mark.asyncio
async def test_provider_session_resilience_under_network_errors(monkeypatch):
    """Verify that network errors during request execution do NOT close or invalidate the pooled client."""
    provider = OllamaProvider()
    client = await provider.get_client()
    client_id = id(client)

    # First call: simulate network timeout
    async def mock_post_timeout(url, json=None, timeout=None):
        raise httpx.ReadTimeout("Read timed out after 30.0s")

    monkeypatch.setattr(client, "post", mock_post_timeout)
    res1 = await provider.generate_response("Sys", "User")
    assert res1 is None
    # Client must remain alive and not None
    assert provider._client is not None
    assert not client.is_closed
    assert id(provider._client) == client_id

    # Second call: simulate connection error
    async def mock_post_conn_err(url, json=None, timeout=None):
        raise httpx.ConnectError("Connection refused by endpoint")

    monkeypatch.setattr(client, "post", mock_post_conn_err)
    res2 = await provider.generate_response("Sys", "User")
    assert res2 is None
    assert not client.is_closed
    assert id(provider._client) == client_id

    # Third call: recovers successfully using the same client
    async def mock_post_ok(url, json=None, timeout=None):
        return httpx.Response(200, json={"response": "Recovered!"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(client, "post", mock_post_ok)
    res3 = await provider.generate_response("Sys", "User")
    assert res3 == "Recovered!"
    assert id(provider._client) == client_id

    await provider.close()
    assert client.is_closed


@pytest.mark.asyncio
async def test_provider_concurrent_get_client_race_condition():
    """Verify 50 concurrent coroutines calling get_client() on uninitialized provider receive identical instance."""
    provider = OllamaProvider()
    assert provider._client is None

    # Spawn 50 simultaneous get_client requests
    tasks = [provider.get_client() for _ in range(50)]
    clients = await asyncio.gather(*tasks)

    # All 50 references must be the exact same object
    first_client = clients[0]
    assert all(c is first_client for c in clients)
    assert len(set(id(c) for c in clients)) == 1
    assert not first_client.is_closed

    await provider.close()
    assert first_client.is_closed
    assert provider._client is None


@pytest.mark.asyncio
async def test_provider_close_lifecycle_and_reinitialization():
    """Verify close() terminates the session and subsequent get_client() re-initializes cleanly."""
    for ProviderCls in (OllamaProvider, OpenAIProvider, WatsonxProvider):
        provider = ProviderCls()
        c1 = await provider.get_client()
        assert not c1.is_closed

        # Close
        await provider.close()
        assert c1.is_closed
        assert provider._client is None

        # Double close (idempotency check — must not raise exception)
        await provider.close()
        assert provider._client is None

        # Re-initialize on subsequent demand
        c2 = await provider.get_client()
        assert not c2.is_closed
        assert c2 is not c1
        assert id(c2) != id(c1)

        await provider.close()
        assert c2.is_closed


@pytest.mark.asyncio
async def test_provider_connection_pool_limits_configuration():
    """Verify connection pool limits are strictly configured with keepalive=20 and max=100."""
    for ProviderCls in (OllamaProvider, OpenAIProvider, WatsonxProvider):
        provider = ProviderCls()
        client = await provider.get_client()
        transport = client._transport

        assert hasattr(transport, "_pool"), "Transport should have connection pool"
        pool = transport._pool
        assert pool._max_keepalive_connections == 20
        assert pool._max_connections == 100

        await provider.close()


# =====================================================================
# PART 2: BATCH REVIEW CONCURRENCY & BOUNDARY TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_batch_review_concurrency_ceiling_under_heavy_load(monkeypatch):
    """Stress test: 25 files submitted; concurrent orchestrator executions must never exceed MAX_CONCURRENT_BATCH_REVIEWS."""
    concurrency_ceiling = settings.MAX_CONCURRENT_BATCH_REVIEWS
    active_tasks = 0
    max_active_observed = 0
    lock = asyncio.Lock()
    total_processed = 0

    async def instrumented_execute_review(req):
        nonlocal active_tasks, max_active_observed, total_processed
        async with lock:
            active_tasks += 1
            if active_tasks > max_active_observed:
                max_active_observed = active_tasks

        try:
            # Overlap window: simulate async execution time
            await asyncio.sleep(0.04)
            return _make_dummy_response()
        finally:
            async with lock:
                active_tasks -= 1
                total_processed += 1

    monkeypatch.setattr(orchestrator, "execute_review", instrumented_execute_review)

    batch_requests = [
        CodeReviewRequest(code=f"def worker_code_{i}(): return {i}", language="python") for i in range(25)
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in batch_requests]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["total_files"] == 25
        assert len(data["reviews"]) == 25

    # Concurrency verification:
    # 1. Active tasks must NEVER have exceeded the semaphore ceiling
    assert max_active_observed <= concurrency_ceiling, (
        f"Concurrency violation: observed {max_active_observed} concurrent tasks, limit is {concurrency_ceiling}"
    )
    # 2. Concurrency must have reached the ceiling under 25 overlapping tasks
    assert max_active_observed == concurrency_ceiling, (
        f"Expected ceiling {concurrency_ceiling} to be reached, but max observed was {max_active_observed}"
    )
    # 3. All 25 tasks must have completed
    assert total_processed == 25
    assert active_tasks == 0


@pytest.mark.asyncio
async def test_batch_review_concurrency_with_dynamic_semaphore(monkeypatch):
    """Verify batch concurrency adapts when MAX_CONCURRENT_BATCH_REVIEWS is configured to different values."""
    custom_ceiling = 3
    monkeypatch.setattr(settings, "MAX_CONCURRENT_BATCH_REVIEWS", custom_ceiling)

    active_tasks = 0
    max_active_observed = 0
    lock = asyncio.Lock()

    async def instrumented_execute_review(req):
        nonlocal active_tasks, max_active_observed
        async with lock:
            active_tasks += 1
            if active_tasks > max_active_observed:
                max_active_observed = active_tasks
        try:
            await asyncio.sleep(0.04)
            return _make_dummy_response()
        finally:
            async with lock:
                active_tasks -= 1

    monkeypatch.setattr(orchestrator, "execute_review", instrumented_execute_review)

    batch_requests = [CodeReviewRequest(code=f"def snippet_{i}(): pass", language="python") for i in range(12)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in batch_requests]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res.status_code == 200
        assert res.json()["total_files"] == 12

    assert max_active_observed == custom_ceiling


@pytest.mark.asyncio
async def test_batch_review_rejection_over_max_batch_size():
    """Verify batch sizes exceeding MAX_BATCH_SIZE (101, 110, 200) are rejected with HTTP 400."""
    limit = settings.MAX_BATCH_SIZE

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for excess in [1, 10, 100]:
            total_size = limit + excess
            oversized_files = [
                CodeReviewRequest(code=f"def f_{i}(): pass", language="python") for i in range(total_size)
            ]

            res = await client.post(
                "/api/v1/review/batch",
                json={"files": [f.model_dump() for f in oversized_files]},
                headers={"Authorization": "Bearer cvai_dev_key_123"},
            )

            assert res.status_code == 400
            err_detail = res.json()["detail"]
            assert f"Batch size {total_size} exceeds maximum allowed of {limit}" in err_detail


@pytest.mark.asyncio
async def test_batch_review_boundary_exact_max_batch_size(monkeypatch):
    """Verify exactly MAX_BATCH_SIZE (100 files) is permitted and successfully processed."""
    limit = settings.MAX_BATCH_SIZE

    async def fast_mock_review(req):
        return _make_dummy_response()

    monkeypatch.setattr(orchestrator, "execute_review", fast_mock_review)

    boundary_files = [CodeReviewRequest(code=f"def bound_{i}(): pass", language="python") for i in range(limit)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in boundary_files]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["total_files"] == limit
        assert len(data["reviews"]) == limit


@pytest.mark.asyncio
async def test_batch_review_boundary_zero_files():
    """Verify empty batch request (0 files) returns 200 OK with empty reviews list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch", json={"files": []}, headers={"Authorization": "Bearer cvai_dev_key_123"}
        )

        assert res.status_code == 200
        data = res.json()
        assert data["total_files"] == 0
        assert data["reviews"] == []


@pytest.mark.asyncio
async def test_batch_review_unauthenticated_request_rejected():
    """Verify batch review endpoint rejects missing and invalid API credentials."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Missing auth
        res1 = await client.post(
            "/api/v1/review/batch", json={"files": [{"code": "def f(): pass", "language": "python"}]}
        )
        assert res1.status_code == 401

        # Invalid token
        res2 = await client.post(
            "/api/v1/review/batch",
            json={"files": [{"code": "def f(): pass", "language": "python"}]},
            headers={"Authorization": "Bearer cvai_unregistered_key_999"},
        )
        assert res2.status_code == 401


@pytest.mark.asyncio
async def test_batch_review_semaphore_cleanup_on_file_exceptions(monkeypatch):
    """Verify that when an exception occurs inside a batch task, the semaphore is released and no deadlock occurs."""
    call_idx = 0

    async def failing_execute_review(req):
        nonlocal call_idx
        call_idx += 1
        if call_idx % 2 == 0:
            raise RuntimeError(f"Simulated agent failure on item {call_idx}")
        return _make_dummy_response()

    monkeypatch.setattr(orchestrator, "execute_review", failing_execute_review)

    batch_requests = [CodeReviewRequest(code=f"def code_{i}(): pass", language="python") for i in range(6)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Since asyncio.gather doesn't catch exceptions without return_exceptions=True,
        # an exception will be raised to FastAPI handler (or return 500)
        try:
            res = await client.post(
                "/api/v1/review/batch",
                json={"files": [f.model_dump() for f in batch_requests]},
                headers={"Authorization": "Bearer cvai_dev_key_123"},
            )
            # If FastAPI handles uncaught exceptions, it yields 500
            assert res.status_code in (500, 200)
        except RuntimeError:
            pass  # ASGI transport may re-raise directly in test

    # Now verify that subsequent batch requests succeed normally (semaphore was not leaked)
    async def normal_execute_review(req):
        return _make_dummy_response()

    monkeypatch.setattr(orchestrator, "execute_review", normal_execute_review)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_after = await client.post(
            "/api/v1/review/batch",
            json={"files": [{"code": "def recovery(): pass", "language": "python"}]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res_after.status_code == 200
        assert res_after.json()["total_files"] == 1


@pytest.mark.asyncio
async def test_batch_review_results_stored_in_reviews_store(monkeypatch):
    """Verify all successfully completed batch review responses are added to in-memory reviews_store."""
    generated_ids = []

    async def mock_review(req):
        resp = _make_dummy_response()
        generated_ids.append(resp.review_id)
        return resp

    monkeypatch.setattr(orchestrator, "execute_review", mock_review)

    batch_requests = [CodeReviewRequest(code=f"def stored_file_{i}(): pass", language="python") for i in range(5)]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/review/batch",
            json={"files": [f.model_dump() for f in batch_requests]},
            headers={"Authorization": "Bearer cvai_dev_key_123"},
        )
        assert res.status_code == 200

    assert len(generated_ids) == 5
    for rid in generated_ids:
        assert rid in reviews_store, f"Review {rid} not found in reviews_store"
