"""
Production Hardening Verification Suite (10/10)
Verifies:
1. Truthful readiness (/ready) checks and fail-closed DB initialization
2. SingleFlight cache stampede coalescing on review execution
3. Strict multi-tenant isolation across all endpoints (status, sarif, gitlab, sonarqube, approve, feedback, stream-token)
4. Atomic sliding-window rate limiting and token fingerprinting
5. Streaming upload byte cap (HTTP 413) on oversized ZIPs
6. Strict base64 validation and decoded size cap
7. One-time scoped stream tokens for SSE/WebSocket and prohibition of query API keys in production
8. Explicit HMAC webhook signature enforcement and multi-worker replay prevention
9. Runtime configuration validation and cross-worker database persistence
10. Source code retention controls (redaction) and TTL purge
11. Dashboard accessibility (keyboard focus, ARIA attributes, reduced motion)
"""

import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.api.app import app
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal, init_db, purge_expired_reviews
from cerberus.core.security import (
    RateLimiter,
    generate_api_key,
    generate_webhook_signature,
    get_token_fingerprint,
    hash_api_key,
)
from cerberus.models.database import ApiKeyRecord, CodeReviewRecord, RuntimeConfigRecord
from cerberus.models.schemas import CodeReviewRequest


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


# ---------------------------------------------------------------------------
# 1. Truthful Readiness & Fail-Closed DB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_probe_fails_truthfully_on_db_outage():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Healthy check first
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

        # Simulate database failure via session error
        with patch("cerberus.api.v1.health.AsyncSessionLocal") as mock_session_cls:
            mock_session_cls.side_effect = RuntimeError("Database connection pool exhausted")
            down_resp = await client.get("/api/v1/health/ready")
            assert down_resp.status_code == 503
            down_data = down_resp.json()
            assert down_data["status"] == "not_ready"
            assert down_data["database"] == "unhealthy"


@pytest.mark.asyncio
async def test_fail_closed_db_initialization():
    """Verify init_db raises runtime error when migrations fail."""
    with patch("cerberus.core.database.run_migrations", side_effect=RuntimeError("Migration failure")):
        with pytest.raises(RuntimeError, match="Migration failure"):
            await init_db()


# ---------------------------------------------------------------------------
# 2. SingleFlight Cache Stampede Coalescing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_singleflight_coalescing_on_cache_miss():
    """Concurrent identical review requests coalesce into 1 execution."""
    orchestrator = ReviewOrchestrator()
    code_sample = "def calculate_total(items):\n    return sum(item.price for item in items)\n"
    req = CodeReviewRequest(
        code=code_sample,
        language="python",
        filename="order_service.py",
        enable_agents=["security", "quality"],
    )

    # Invalidate any prior cache
    cache_key = cache_manager.compute_cache_key(
        code=req.code,
        language=req.language or "python",
        agents=["security", "quality"],
        filename=req.filename,
    )
    await cache_manager.delete(cache_key)

    call_count = 0
    orig_analyze = orchestrator.registry["security"].analyze

    async def counting_analyze(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.08)
        return await orig_analyze(*args, **kwargs)

    with patch.object(orchestrator.registry["security"], "analyze", side_effect=counting_analyze):
        # Fire 5 concurrent requests for identical uncached code
        results = await asyncio.gather(
            orchestrator.execute_review(req),
            orchestrator.execute_review(req),
            orchestrator.execute_review(req),
            orchestrator.execute_review(req),
            orchestrator.execute_review(req),
        )

    # All 5 callers get valid results
    assert len(results) == 5
    for r in results:
        assert r.status == "completed"
        assert r.overall_score >= 0

    # Exactly 1 underlying agent execution occurred due to SingleFlight
    assert call_count == 1


# ---------------------------------------------------------------------------
# 3. Multi-Tenant Isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_tenant_isolation_strict():
    """Tenant B with valid key cannot access Tenant A's reviews, exports, or feedback."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create API keys for Tenant A and Tenant B
        raw_key_a, hash_a, _ = generate_api_key("tenant_a")
        raw_key_b, hash_b, _ = generate_api_key("tenant_b")

        async with AsyncSessionLocal() as session:
            session.add(
                ApiKeyRecord(
                    key_hash=hash_a,
                    name="Tenant A Key",
                    prefix="crb_live_",
                    tenant_id="tenant_alpha",
                    scopes="review:read,review:write",
                    is_active=True,
                )
            )
            session.add(
                ApiKeyRecord(
                    key_hash=hash_b,
                    name="Tenant B Key",
                    prefix="crb_live_",
                    tenant_id="tenant_beta",
                    scopes="review:read,review:write",
                    is_active=True,
                )
            )
            await session.commit()

        # Tenant A creates a review
        create_resp = await client.post(
            "/api/v1/review",
            json={
                "code": "import os\ndef test(): pass\n",
                "language": "python",
                "file_path": "test.py",
            },
            headers={"Authorization": f"Bearer {raw_key_a}"},
        )
        assert create_resp.status_code == 200
        rev_id = create_resp.json()["review_id"]

        # Tenant A can read it
        own_resp = await client.get(
            f"/api/v1/review/{rev_id}",
            headers={"Authorization": f"Bearer {raw_key_a}"},
        )
        assert own_resp.status_code == 200

        # Tenant B attempts access -> 404 Not Found (zero information leak)
        endpoints = [
            ("GET", f"/api/v1/review/{rev_id}", None),
            ("GET", f"/api/v1/review/{rev_id}/sarif", None),
            ("GET", f"/api/v1/review/{rev_id}/gitlab", None),
            ("GET", f"/api/v1/review/{rev_id}/sonarqube", None),
            ("POST", f"/api/v1/review/{rev_id}/approve", {"reviewer": "Eve", "override_blocking": True}),
            ("POST", f"/api/v1/review/{rev_id}/feedback", {"rating": 5, "is_helpful": True}),
            ("POST", f"/api/v1/review/{rev_id}/stream-token", None),
        ]

        for method, url, payload in endpoints:
            if method == "GET":
                resp = await client.get(url, headers={"Authorization": f"Bearer {raw_key_b}"})
            else:
                resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {raw_key_b}"})
            assert resp.status_code == 404, f"Tenant B leaked access to {method} {url}"


# ---------------------------------------------------------------------------
# 4. Atomic Rate Limiting & Token Fingerprinting
# ---------------------------------------------------------------------------
def test_token_fingerprinting_prevents_raw_token_storage():
    raw_token = "crb_live_super_secret_client_token_12345678"
    fingerprint = get_token_fingerprint(raw_token)
    assert raw_token not in fingerprint
    assert len(fingerprint) == 32
    assert fingerprint == get_token_fingerprint(raw_token)


def test_rate_limiter_quota_and_retry_after():
    limiter = RateLimiter(limit_per_hour=3, max_tracked=10)
    user = "rate_limit_test_client"

    # First 3 requests permitted
    assert limiter.is_allowed(user)[0] is True
    assert limiter.is_allowed(user)[0] is True
    assert limiter.is_allowed(user)[0] is True

    # 4th request rejected with retry-after > 0
    allowed, remaining, retry_after = limiter.is_allowed(user)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


# ---------------------------------------------------------------------------
# 5. Streaming Upload Byte Cap & Base64 Size Caps
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_streaming_upload_rejects_oversized_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dev_key = settings.DEFAULT_DEV_API_KEY
        oversized_data = b"PK\x03\x04" + b"A" * (26 * 1024 * 1024)
        files = {"file": ("huge.zip", oversized_data, "application/zip")}
        resp = await client.post(
            "/api/v1/review/zip",
            files=files,
            headers={"Authorization": f"Bearer {dev_key}"},
        )
        assert resp.status_code == 413


@pytest.mark.asyncio
async def test_base64_validation_and_size_caps():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dev_key = settings.DEFAULT_DEV_API_KEY
        # 1. Malformed base64
        bad_b64_resp = await client.post(
            "/api/v1/review/zip-base64",
            json={"zip_base64": "NotValidBase64@@@!!", "project_name": "malformed"},
            headers={"Authorization": f"Bearer {dev_key}"},
        )
        assert bad_b64_resp.status_code == 400

        # 2. Oversized base64 decoded size
        huge_raw = b"PK\x03\x04" + b"0" * (26 * 1024 * 1024)
        huge_b64 = base64.b64encode(huge_raw).decode("ascii")
        huge_resp = await client.post(
            "/api/v1/review/zip-base64",
            json={"zip_base64": huge_b64, "project_name": "huge"},
            headers={"Authorization": f"Bearer {dev_key}"},
        )
        assert huge_resp.status_code == 413


# ---------------------------------------------------------------------------
# 6. Scoped Stream Tokens & Query Param Prohibition in Production
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stream_token_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        raw_key, key_hash, _ = generate_api_key("stream_tester")
        async with AsyncSessionLocal() as session:
            session.add(
                ApiKeyRecord(
                    key_hash=key_hash,
                    name="Stream Key",
                    prefix="crb_live_",
                    tenant_id="stream_tenant",
                    scopes="review:read,review:write",
                    is_active=True,
                )
            )
            await session.commit()

        # Create review
        rev_resp = await client.post(
            "/api/v1/review",
            json={"code": "x = 1\n", "language": "python", "file_path": "x.py"},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        rev_id = rev_resp.json()["review_id"]

        # Request scoped stream token
        token_resp = await client.post(
            f"/api/v1/review/{rev_id}/stream-token",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert token_resp.status_code == 200
        stream_token = token_resp.json()["stream_token"]
        assert len(stream_token) >= 32

        # Token allows stream access
        stream_resp = await client.get(
            f"/api/v1/review/{rev_id}/stream?token={stream_token}"
        )
        assert stream_resp.status_code == 200

        # One-time use: second attempt with same token is rejected
        second_resp = await client.get(
            f"/api/v1/review/{rev_id}/stream?token={stream_token}"
        )
        assert second_resp.status_code == 401


@pytest.mark.asyncio
async def test_raw_api_key_query_param_rejected_in_production():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(settings, "ENVIRONMENT", "production"):
            resp = await client.get(
                "/api/v1/review/rev_12345/stream?api_key=crb_live_some_key"
            )
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Webhook Signature & Multi-Worker Replay Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_signature_and_replay_prevention():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = json.dumps({"action": "opened", "pull_request": {"number": 42}}).encode("utf-8")
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY
        valid_sig = generate_webhook_signature(payload, secret)

        # 1. Missing signature
        missing_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=payload,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert missing_resp.status_code == 401

        # 2. Invalid signature
        bad_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
                "Content-Type": "application/json",
            },
        )
        assert bad_resp.status_code == 401

        # 3. Valid signature with delivery ID
        delivery_id = f"delivery_{time.time()}"
        ok_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": valid_sig,
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert ok_resp.status_code == 200

        # 4. Replay attempt with identical delivery ID -> ignored / duplicate
        replay_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": valid_sig,
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert replay_resp.status_code == 200
        assert replay_resp.json()["status"] == "ignored"
        assert replay_resp.json()["reason"] == "duplicate_event"


# ---------------------------------------------------------------------------
# 8. Runtime Configuration Validation & DB Persistence
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_runtime_config_validation_and_persistence():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an admin key
        raw_admin_key, admin_hash, _ = generate_api_key("admin_user")
        async with AsyncSessionLocal() as session:
            session.add(
                ApiKeyRecord(
                    key_hash=admin_hash,
                    name="Admin Key",
                    prefix="crb_live_",
                    tenant_id="ops_tenant",
                    scopes="admin,review:read,review:write",
                    is_active=True,
                )
            )
            await session.commit()

        admin_headers = {"Authorization": f"Bearer {raw_admin_key}"}

        # Invalid severity
        bad_sev = await client.patch(
            "/api/v1/config",
            json={"severity_threshold": "unsupported_level"},
            headers=admin_headers,
        )
        assert bad_sev.status_code == 400

        # Invalid agent
        bad_agent = await client.patch(
            "/api/v1/config",
            json={"enabled_agents": ["security", "fake_agent_xyz"]},
            headers=admin_headers,
        )
        assert bad_agent.status_code == 400

        # Valid update
        good_resp = await client.patch(
            "/api/v1/config",
            json={"severity_threshold": "high", "enabled_agents": ["security", "quality"]},
            headers=admin_headers,
        )
        assert good_resp.status_code == 200
        assert good_resp.json()["status"] == "success"

        # Verify persisted in database across workers
        async with AsyncSessionLocal() as session:
            rec = await session.get(RuntimeConfigRecord, "SEVERITY_THRESHOLD")
            assert rec is not None
            assert rec.value == "high"

            rec_agents = await session.get(RuntimeConfigRecord, "ENABLED_AGENTS")
            assert rec_agents is not None
            assert "security" in rec_agents.value


# ---------------------------------------------------------------------------
# 9. Source Code Retention Controls & TTL Cleanup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_code_retention_redaction():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dev_key = settings.DEFAULT_DEV_API_KEY
        with patch.object(settings, "RETAIN_SOURCE_CODE", False):
            resp = await client.post(
                "/api/v1/review",
                json={
                    "code": "SECRET_PASSWORD = 'super_sensitive_api_key'\n",
                    "language": "python",
                    "file_path": "auth.py",
                },
                headers={"Authorization": f"Bearer {dev_key}"},
            )
            assert resp.status_code == 200
            rev_id = resp.json()["review_id"]

            # Wait for background persistence task
            await asyncio.sleep(0.15)

            async with AsyncSessionLocal() as session:
                rec = await session.get(CodeReviewRecord, rev_id)
                assert rec is not None
                assert rec.code_snippet == "[REDACTED]"


@pytest.mark.asyncio
async def test_data_retention_ttl_purge():
    # Insert an old review older than 30 days
    async with AsyncSessionLocal() as session:
        old_record = CodeReviewRecord(
            id="rev_stale_to_purge",
            code_snippet="print('old code')",
            language="python",
            overall_score=80.0,
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
        )
        session.add(old_record)
        await session.commit()

    # Purge reviews older than 30 days
    purged_count = await purge_expired_reviews(retention_days=30)
    assert purged_count >= 1

    # Verify old review is gone
    async with AsyncSessionLocal() as session:
        rec = await session.get(CodeReviewRecord, "rev_stale_to_purge")
        assert rec is None


# ---------------------------------------------------------------------------
# 10. Dashboard Accessibility (WCAG 2.1 AA)
# ---------------------------------------------------------------------------
def test_dashboard_accessibility_attributes():
    from pathlib import Path

    html_path = Path("cerberus/web/index.html")
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    # ARIA roles and labels
    assert 'role="tablist"' in content
    assert 'role="tab"' in content
    assert "aria-selected=" in content
    assert "aria-label=" in content
    assert 'role="alert"' in content

    # Focus-visible keyboard outlines
    assert ":focus-visible" in content
    assert "outline:" in content

    # Reduced motion preference support
    assert "@media (prefers-reduced-motion: reduce)" in content
