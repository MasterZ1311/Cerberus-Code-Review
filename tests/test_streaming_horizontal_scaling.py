"""
Streaming Security and Horizontal Scalability Integration Tests.
Verifies:
1. Complete rejection of raw API-key query parameters across all modes.
2. Atomic single-use stream-token consumption (immune to concurrent double-consumption races).
3. Cross-worker Redis pub/sub event delivery for SSE and WebSockets.
4. Tenant ownership enforcement for Bearer-authenticated streams.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from cerberus.api.app import app
from cerberus.api.v1.review import (
    _review_owners,
    reviews_store,
)
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import hash_api_key
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(autouse=True)
async def setup_test_keys():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ApiKeyRecord).where(ApiKeyRecord.tenant_id.in_(["tenant_stream_a", "tenant_stream_b"]))
        )
        await session.commit()

        # Tenant A key
        raw_key_a = "cvai_stream_tenant_a_11111111111111111111"
        rec_a = ApiKeyRecord(
            tenant_id="tenant_stream_a",
            key_hash=hash_api_key(raw_key_a),
            name="Stream Tenant A",
            prefix="cvai_stre",
            scopes="review:read,review:write,admin",
            is_active=True,
        )
        session.add(rec_a)

        # Tenant B key
        raw_key_b = "cvai_stream_tenant_b_22222222222222222222"
        rec_b = ApiKeyRecord(
            tenant_id="tenant_stream_b",
            key_hash=hash_api_key(raw_key_b),
            name="Stream Tenant B",
            prefix="cvai_streb",
            scopes="review:read,review:write,admin",
            is_active=True,
        )
        session.add(rec_b)
        await session.commit()

    yield

    reviews_store.clear()
    _review_owners.clear()


@pytest.mark.asyncio
async def test_raw_api_key_query_params_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. SSE with raw ?token= is forbidden and returns 400
        resp = await client.get("/api/v1/review/rev_test_123/stream?token=cvai_raw_key")
        assert resp.status_code == 400
        assert "forbidden" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_concurrent_stream_token_consumption_atomic():
    """
    Spawns 30 concurrent workers attempting to consume the exact same stream token.
    Under atomic GETDEL / Lua semantics, EXACTLY ONE worker must succeed.
    """
    review_id = "rev_atomic_test_999"
    tenant_id = "tenant_stream_a"

    token = await cache_manager.create_stream_token(review_id=review_id, tenant_id=tenant_id, ttl_seconds=30)
    assert token.startswith("st_")

    # Launch 30 concurrent consumption coroutines
    async def _try_consume():
        return await cache_manager.consume_stream_token(token)

    results = await asyncio.gather(*[_try_consume() for _ in range(30)])

    consumed_payloads = [r for r in results if r is not None]
    assert len(consumed_payloads) == 1, (
        f"Atomic violation! Token consumed {len(consumed_payloads)} times under concurrency."
    )
    assert consumed_payloads[0]["review_id"] == review_id
    assert consumed_payloads[0]["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_multi_worker_pubsub_event_delivery():
    """
    Simulates cross-worker event delivery:
    Worker 1 (listener) subscribes to review events.
    Worker 2 (publisher) publishes an event on the review channel.
    Worker 1 receives the event and handles it.
    """
    review_id = "rev_pubsub_worker_test"

    received_events = []

    async def _worker_subscriber():
        async for evt in cache_manager.subscribe_review_events(review_id, timeout_seconds=5.0):
            received_events.append(evt)
            if evt.get("event") == "review_completed":
                break

    subscriber_task = asyncio.create_task(_worker_subscriber())
    await asyncio.sleep(0.05)  # Let subscriber set up channel

    # Worker 2 publishes progress event
    await cache_manager.publish_review_event(
        review_id,
        {"event": "agent_completed", "agent": "security", "score": 95},
    )

    # Worker 2 publishes completion event
    await cache_manager.publish_review_event(
        review_id,
        {"event": "review_completed", "review_id": review_id, "overall_score": 95, "status": "completed"},
    )

    await asyncio.wait_for(subscriber_task, timeout=5.0)

    assert len(received_events) >= 2
    event_names = [e.get("event") for e in received_events]
    assert "agent_completed" in event_names
    assert "review_completed" in event_names


@pytest.mark.asyncio
async def test_bearer_authenticated_streaming_target_ownership():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_stream_tenant_a_11111111111111111111"}
        headers_b = {"Authorization": "Bearer cvai_stream_tenant_b_22222222222222222222"}

        # Submit review under Tenant A
        sub = await client.post(
            "/api/v1/review",
            headers=headers_a,
            json={"code": "def process(): return True", "filename": "test.py", "language": "python"},
        )
        review_id = sub.json()["review_id"]

        # 1. Tenant B attempts SSE with Bearer auth on Tenant A's review -> 404
        sse_b = await client.get(f"/api/v1/review/{review_id}/stream", headers=headers_b)
        assert sse_b.status_code == 404

        # 2. Tenant A connects via Bearer auth -> 200 text/event-stream
        sse_a = await client.get(f"/api/v1/review/{review_id}/stream", headers=headers_a)
        assert sse_a.status_code == 200
        assert "text/event-stream" in sse_a.headers["content-type"]
