"""
Tests for Synchronous Database Persistence & Multi-Tenant Fallback Consistency.
Verifies:
1. Immediate memory eviction: review submission is immediately retrievable from DB fallback.
2. Cross-worker retrieval: independent simulated worker retrieves review from DB with tenant isolation.
3. Database failure fail-closed: if DB persistence fails after retries, review submission returns 500 without durable ID.
4. Database retry resilience: transient DB failures recover with backoff and succeed.
5. Multi-tenant boundary preservation across eviction and fallback queries.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app
from cerberus.api.v1.review import _review_owners, reviews_store
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import hash_api_key
from cerberus.models.database import ApiKeyRecord, CodeReviewRecord


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    reviews_store.clear()
    _review_owners.clear()
    async with AsyncSessionLocal() as session:
        # Tenant A key
        res_a = await session.get(ApiKeyRecord, "test-tenant-a-id")
        if not res_a:
            session.add(
                ApiKeyRecord(
                    id="test-tenant-a-id",
                    key_hash=hash_api_key("cvai_tenant_alpha_consistent_key_111"),
                    name="tenant-alpha",
                    prefix="cvai_ten",
                    tenant_id="tenant_alpha",
                    scopes="review:read,review:write,admin",
                    is_active=True,
                )
            )
        # Tenant B key
        res_b = await session.get(ApiKeyRecord, "test-tenant-b-id")
        if not res_b:
            session.add(
                ApiKeyRecord(
                    id="test-tenant-b-id",
                    key_hash=hash_api_key("cvai_tenant_beta_consistent_key_222"),
                    name="tenant-beta",
                    prefix="cvai_ten",
                    tenant_id="tenant_beta",
                    scopes="review:read,review:write,admin",
                    is_active=True,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_immediate_memory_eviction_retrieval_consistency():
    """Review submitted is synchronously committed to DB and retrievable instantly upon total memory eviction."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_alpha_consistent_key_111"}

        # Submit review
        post_resp = await client.post(
            "/api/v1/review",
            headers=headers_a,
            json={"code": "def process_alpha(): return 100", "filename": "alpha.py", "language": "python"},
        )
        assert post_resp.status_code == 200
        review_id = post_resp.json()["review_id"]

        # Evict completely from in-memory stores immediately (simulating immediate LRU purge or worker crash)
        reviews_store.clear()
        _review_owners.clear()

        # Database record must already exist synchronously (no race condition, no sleep needed!)
        async with AsyncSessionLocal() as session:
            record = await session.get(CodeReviewRecord, review_id)
            assert record is not None
            assert record.id == review_id
            assert record.owner_id == "tenant_alpha"
            assert record.status in ("completed", "approved", "failed")

        # GET review status must successfully pull from DB, repopulate memory, and return 200
        get_resp = await client.get(f"/api/v1/review/{review_id}", headers=headers_a)
        assert get_resp.status_code == 200
        assert get_resp.json()["review_id"] == review_id
        assert review_id in reviews_store
        assert _review_owners.get(review_id) == "tenant_alpha"


@pytest.mark.asyncio
async def test_cross_worker_retrieval_and_tenant_boundary():
    """Simulated separate worker with empty memory correctly enforces tenant boundaries via DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_alpha_consistent_key_111"}
        headers_b = {"Authorization": "Bearer cvai_tenant_beta_consistent_key_222"}

        # Tenant Alpha submits review
        post_resp = await client.post(
            "/api/v1/review",
            headers=headers_a,
            json={"code": "def confidential(): return 'alpha_secret'", "filename": "alpha.py", "language": "python"},
        )
        assert post_resp.status_code == 200
        review_id = post_resp.json()["review_id"]

        # Wipe memory stores on simulated worker
        reviews_store.clear()
        _review_owners.clear()

        # Tenant Beta attempts to access Tenant Alpha's review -> Must query DB, verify owner, return 404
        get_b = await client.get(f"/api/v1/review/{review_id}", headers=headers_b)
        assert get_b.status_code == 404

        # Tenant Alpha accesses -> Successfully loads and returns 200
        get_a = await client.get(f"/api/v1/review/{review_id}", headers=headers_a)
        assert get_a.status_code == 200
        assert get_a.json()["review_id"] == review_id


@pytest.mark.asyncio
async def test_database_persistence_fail_closed_prevents_orphan_review_ids():
    """If database persistence fails after retries, review submission returns 500 without orphan ID and leaves no memory/durable trace."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_alpha_consistent_key_111"}
        reviews_store.clear()
        _review_owners.clear()

        with patch("cerberus.api.v1.review.AsyncSessionLocal", side_effect=RuntimeError("Database write fatal down")):
            resp = await client.post(
                "/api/v1/review",
                headers=headers,
                json={
                    "code": "def fail_test_persistence(): return 'must_fail'",
                    "filename": "fail.py",
                    "language": "python",
                },
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert detail["error"] == "persistence_failure"
            # Response body must never leak a usable review ID on failure
            assert "review_id" not in detail
            assert "id" not in detail

        # Guarantee no in-memory store or ownership trace remains
        assert len(reviews_store) == 0
        assert len(_review_owners) == 0

        # Guarantee no record exists in durable storage
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            q = select(CodeReviewRecord).where(CodeReviewRecord.code_snippet.contains("fail_test_persistence"))
            res = (await session.execute(q)).scalars().all()
            assert len(res) == 0

        # Attempting to fetch any arbitrary review returns 404
        get_orphan = await client.get("/api/v1/review/rev_failed_nonexistent", headers=headers)
        assert get_orphan.status_code == 404


@pytest.mark.asyncio
async def test_database_retry_resilience():
    """Transient database operational failures are retried and succeed on recovery."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_alpha_consistent_key_111"}

        attempts = 0
        real_session = AsyncSessionLocal

        def flaky_session():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("Transient connection reset by peer")
            return real_session()

        with patch("cerberus.api.v1.review.AsyncSessionLocal", side_effect=flaky_session):
            resp = await client.post(
                "/api/v1/review",
                headers=headers,
                json={"code": "def retry_success(): return 42", "filename": "retry.py", "language": "python"},
            )
            assert resp.status_code == 200
            assert attempts >= 2


@pytest.mark.asyncio
async def test_batch_database_persistence_fail_closed_and_retry():
    """Verify batch synchronous persistence fails closed on fatal error and retries on transient error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_alpha_consistent_key_111"}
        reviews_store.clear()
        _review_owners.clear()

        # 1. Fatal persistence failure returns 500 and leaves zero in-memory or durable artifacts
        with patch("cerberus.api.v1.review.AsyncSessionLocal", side_effect=RuntimeError("Fatal batch DB down")):
            resp = await client.post(
                "/api/v1/review/batch",
                headers=headers,
                json={"files": [{"code": "def batch_fail(): pass", "language": "python"}]},
            )
            assert resp.status_code == 500
            assert resp.json()["detail"]["error"] == "persistence_failure"
            assert "reviews" not in resp.json()
            assert len(reviews_store) == 0
            assert len(_review_owners) == 0

        # Verify no batch records persisted
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            q = select(CodeReviewRecord).where(CodeReviewRecord.code_snippet.contains("batch_fail"))
            res = (await session.execute(q)).scalars().all()
            assert len(res) == 0

        # 2. Transient error retries and succeeds
        attempts = 0
        real_session = AsyncSessionLocal

        def flaky_batch_session():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("Transient lock contention")
            return real_session()

        with patch("cerberus.api.v1.review.AsyncSessionLocal", side_effect=flaky_batch_session):
            resp = await client.post(
                "/api/v1/review/batch",
                headers=headers,
                json={
                    "files": [
                        {"code": "def b1(): return 1", "language": "python"},
                        {"code": "def b2(): return 2" + "#" * 12000, "language": "python"},
                    ]
                },
            )
            assert resp.status_code == 200
            assert attempts >= 2
            data = resp.json()
            assert data["total_files"] == 2
            rev_id = data["reviews"][0]["review_id"]

        # Verify records exist in DB
        async with AsyncSessionLocal() as session:
            rec = await session.get(CodeReviewRecord, rev_id)
            assert rec is not None
            assert rec.owner_id == "tenant_alpha"


@pytest.mark.asyncio
async def test_database_warm_pool_failure_branch():
    """Verify warm_connection_pool safely handles connection failure without crashing."""
    from unittest.mock import MagicMock

    from cerberus.core.database import warm_connection_pool

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = RuntimeError("Simulated pool warm failure")
    with patch("cerberus.core.database.engine", mock_engine):
        res = await warm_connection_pool()
        assert res is False
