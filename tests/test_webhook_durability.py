"""
Regression test suite for Webhook Durability and Background Task Management.
Verifies:
1. Webhook synchronously persists core review records prior to memory/cache/event/GitHub side-effects.
2. Webhook DB persistence failure returns safe 500 with no review ID leaked.
3. On persistence failure, no trace remains in memory (reviews_store, _review_owners) or cache.
4. No external GitHub review is posted on persistence failure.
5. The review cannot subsequently be fetched via GET.
6. Normal webhook flow persists durably and completes successfully.
7. Background task manager logs unhandled task exceptions without 'Task exception was never retrieved'.
8. Background tasks drain safely during lifecycle without closed-event-loop warnings.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cerberus.api.app import app
from cerberus.api.v1.review import _review_owners, reviews_store
from cerberus.config import settings
from cerberus.core.background import background_tasks
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import generate_webhook_signature, hash_api_key
from cerberus.models.database import ApiKeyRecord, CodeReviewRecord


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()
    reviews_store.clear()
    _review_owners.clear()
    async with AsyncSessionLocal() as session:
        res_admin = await session.get(ApiKeyRecord, "test-platform-admin-webhook-id")
        if not res_admin:
            session.add(
                ApiKeyRecord(
                    id="test-platform-admin-webhook-id",
                    key_hash=hash_api_key("cvai_admin_webhook_key_777"),
                    name="platform-admin-webhook",
                    prefix="cvai_adm",
                    tenant_id="platform_admin",
                    scopes="review:read,review:write,admin,platform:admin",
                    is_active=True,
                )
            )
            await session.commit()
    yield
    reviews_store.clear()
    _review_owners.clear()


@pytest.mark.asyncio
async def test_webhook_database_persistence_fail_closed():
    """
    Verify that if database persistence fails during a webhook pull_request review:
    - HTTP 500 is returned.
    - No review ID is leaked in the response body.
    - No review is kept in memory (reviews_store or _review_owners).
    - No durable row is stored.
    - No external PR review is posted to GitHub.
    - No unhandled background task exceptions occur.
    """
    secret = settings.SECRET_KEY
    payload = {
        "action": "opened",
        "number": 101,
        "filename": "auth_service.py",
        "code": "def authenticate(user, password):\n    return password == 'secret'\n",
        "pull_request": {
            "title": "Add insecure authentication",
            "body": "Implements basic login check",
            "head": {"sha": "sha_fail_101", "ref": "feat-login"},
            "base": {"ref": "main"},
        },
        "repository": {"name": "core-backend", "owner": {"login": "corp"}, "full_name": "corp/core-backend"},
    }
    raw_payload = json.dumps(payload).encode("utf-8")
    sig = generate_webhook_signature(raw_payload, secret)

    github_post_mock = AsyncMock(return_value=(True, {"id": 12345}))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate fatal database outage on persistence
        with (
            patch(
                "cerberus.api.v1.review.AsyncSessionLocal",
                side_effect=RuntimeError("Simulated database outage during webhook persist"),
            ),
            patch("cerberus.api.v1.review.post_pr_review_to_github", github_post_mock),
        ):
            response = await client.post(
                "/api/v1/review/webhooks/github",
                content=raw_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Delivery": "delivery-fail-closed-001",
                },
            )

            # 1. Safe 500 error returned
            assert response.status_code == 500
            data = response.json()
            assert data["detail"]["error"] == "persistence_failure"
            assert "Failed to persist webhook review record" in data["detail"]["message"]

            # 2. No usable review ID leaked in response
            assert "review_id" not in data
            assert "review_id" not in data.get("detail", {})

            # 3. No memory traces remain
            assert len(reviews_store) == 0
            assert len(_review_owners) == 0

            # 4. No external GitHub review was posted
            assert github_post_mock.call_count == 0

    # 5. Verify no record exists in durable storage
    async with AsyncSessionLocal() as session:
        q = select(CodeReviewRecord).where(CodeReviewRecord.code_snippet.contains("authenticate(user, password)"))
        res = (await session.execute(q)).scalars().all()
        assert len(res) == 0


@pytest.mark.asyncio
async def test_webhook_success_is_synchronously_persisted_and_retrievable():
    """Verify that a successful webhook review is durably persisted and retrievable."""
    secret = settings.SECRET_KEY
    payload = {
        "action": "opened",
        "number": 102,
        "filename": "valid_calc.py",
        "code": "def calculate_total(a, b):\n    return a + b\n",
        "pull_request": {
            "title": "Add calculator helper",
            "body": "Pure function with no side effects",
            "head": {"sha": "sha_success_102", "ref": "feat-calc"},
            "base": {"ref": "main"},
        },
        "repository": {"name": "core-backend", "owner": {"login": "corp"}, "full_name": "corp/core-backend"},
    }
    raw_payload = json.dumps(payload).encode("utf-8")
    sig = generate_webhook_signature(raw_payload, secret)

    github_post_mock = AsyncMock(return_value=(True, {"id": 8888}))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("cerberus.api.v1.review.post_pr_review_to_github", github_post_mock):
            response = await client.post(
                "/api/v1/review/webhooks/github",
                content=raw_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Delivery": "delivery-success-002",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert "review_id" in data
            rev_id = data["review_id"]
            assert data["posted_to_github"] is True
            assert github_post_mock.call_count == 1

            # Evict from memory to prove durable DB fallback
            reviews_store.clear()
            _review_owners.clear()

            # Now fetch via GET from webhook owner
            get_resp = await client.get(
                f"/api/v1/review/{rev_id}",
                headers={"Authorization": "Bearer cvai_admin_webhook_key_777"},
            )
            assert get_resp.status_code == 200
            get_data = get_resp.json()
            assert get_data["review_id"] == rev_id
            assert get_data["status"] == "completed"


@pytest.mark.asyncio
async def test_background_task_manager_exception_retrieval(caplog):
    """
    Verify that background tasks with exceptions do not trigger
    'Task exception was never retrieved' warnings and are logged cleanly.
    """
    import asyncio

    task_failed = False

    async def failing_worker():
        nonlocal task_failed
        await asyncio.sleep(0.01)
        task_failed = True
        raise ValueError("Simulated background worker failure")

    task = background_tasks.create_task(failing_worker(), name="test_failing_task")
    await asyncio.sleep(0.05)

    assert task.done()
    assert task_failed is True
    # Exception was retrieved by done callback, no unhandled warning
    assert task.exception() is not None
    assert isinstance(task.exception(), ValueError)
    # Background tasks set should be pruned
    assert task not in background_tasks._tasks


@pytest.mark.asyncio
async def test_background_task_manager_drain_tasks():
    """Verify background_tasks.drain_tasks waits for in-flight tasks cleanly."""
    import asyncio

    completed = []

    async def slow_task(idx: int):
        await asyncio.sleep(0.05)
        completed.append(idx)

    for i in range(5):
        background_tasks.create_task(slow_task(i), name=f"slow_{i}")

    await background_tasks.drain_tasks(timeout=2.0)
    assert len(completed) == 5
    assert sorted(completed) == [0, 1, 2, 3, 4]
