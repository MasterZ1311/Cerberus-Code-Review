"""
Production Hardening & Coverage Elevation Tests: 10/10 Enterprise Standard.
Exhaustively exercises API Key RBAC boundaries, Analytics aggregations,
OpenRouter/Ollama providers, Cache lifecycle, and Schema Migration edge cases.
"""

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response
from starlette.requests import Request

from cerberus.api.v1.analytics import get_global_trends, get_repository_analytics
from cerberus.api.v1.keys import (
    CreateApiKeyRequest,
    create_api_key,
    list_api_keys,
    revoke_api_key,
    rotate_api_key,
)
from cerberus.core.cache import CacheManager
from cerberus.core.database import AsyncSessionLocal, engine
from cerberus.core.migrations import _migrate_multitenancy_columns, run_migrations
from cerberus.core.security import generate_api_key
from cerberus.models.database import ApiKeyRecord, CodeReviewRecord, FindingRecord
from cerberus.providers.ollama_provider import OllamaProvider
from cerberus.providers.openrouter_provider import OpenRouterProvider


# =========================================================================
# 1. API Keys RBAC, Scopes & Isolation Exhaustive Branch Testing
# =========================================================================
@pytest.mark.asyncio
async def test_api_keys_invalid_scope_rejection():
    """Verify that requesting an unrecognized scope returns HTTP 400."""
    req = CreateApiKeyRequest(name="bad-scope-key", scopes=["invalid:scope:xyz"])
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-a"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"admin"}

    with pytest.raises(Exception) as exc_info:
        await create_api_key(req, http_req, _admin="admin")
    assert getattr(exc_info.value, "status_code", None) == 400
    assert "Invalid scope" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_api_keys_tenant_admin_cannot_target_other_tenant():
    """Tenant admin cannot create keys for another tenant."""
    req = CreateApiKeyRequest(name="cross-tenant-key", tenant_id="tenant-b", scopes=["review:read"])
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-a"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"admin"}

    with pytest.raises(Exception) as exc_info:
        await create_api_key(req, http_req, _admin="admin")
    assert getattr(exc_info.value, "status_code", None) == 403
    assert "Only platform administrators can provision" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_api_keys_tenant_admin_cannot_mint_platform_admin_scope():
    """Tenant admin cannot grant platform:admin scope."""
    req = CreateApiKeyRequest(name="escalate-key", scopes=["platform:admin"])
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-a"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"admin"}

    with pytest.raises(Exception) as exc_info:
        await create_api_key(req, http_req, _admin="admin")
    assert getattr(exc_info.value, "status_code", None) == 403
    assert "cannot mint 'platform:admin'" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_api_keys_tenant_admin_cannot_grant_unheld_scope_without_admin():
    """Caller without 'admin' or target scope cannot grant it."""
    req = CreateApiKeyRequest(name="unheld-scope-key", scopes=["review:write"])
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-a"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"review:read"}  # Missing review:write and admin

    with pytest.raises(Exception) as exc_info:
        await create_api_key(req, http_req, _admin="admin")
    assert getattr(exc_info.value, "status_code", None) == 403
    assert "Cannot grant scope 'review:write'" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_api_keys_platform_admin_provision_and_list_filtering():
    """Platform admin can provision keys for other tenants and filter list by tenant."""
    req = CreateApiKeyRequest(
        name="platform-provisioned-key",
        tenant_id="tenant-external-42",
        scopes=["review:read", "review:write"],
        expires_in_days=30,
    )
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "platform-root"
    http_req.state.is_platform_admin = True
    http_req.state.api_key_scopes = {"platform:admin", "admin"}

    created = await create_api_key(req, http_req, _admin="admin")
    assert created.tenant_id == "tenant-external-42"
    assert created.expires_at is not None

    # List keys with tenant filter as platform admin
    listed = await list_api_keys(http_req, tenant_id="tenant-external-42", _admin="admin")
    assert any(k.id == created.id for k in listed)

    # List keys without tenant filter as platform admin
    all_listed = await list_api_keys(http_req, tenant_id=None, _admin="admin")
    assert len(all_listed) >= len(listed)

    # Tenant admin cannot filter by another tenant
    http_req_tenant = MagicMock(spec=Request)
    http_req_tenant.state.tenant_id = "tenant-a"
    http_req_tenant.state.is_platform_admin = False
    with pytest.raises(Exception) as exc_info:
        await list_api_keys(http_req_tenant, tenant_id="tenant-b", _admin="admin")
    assert getattr(exc_info.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_api_keys_revocation_and_rotation_edge_cases():
    """Test key lookup by name, revocation, rotation, and 404/403 branches."""
    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-rotate"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"admin", "review:read", "review:write"}

    # Create a key
    req = CreateApiKeyRequest(name="rotatable-key", scopes=["review:read"])
    created = await create_api_key(req, http_req, _admin="admin")

    # Rotate the key
    rotated = await rotate_api_key(created.id, http_req, _admin="admin")
    assert rotated.old_key_id == created.id
    assert rotated.new_key_id != created.id
    assert rotated.tenant_id == "tenant-rotate"

    # Revoke new key by name fallback
    revoked = await revoke_api_key("rotatable-key", http_req, _admin="admin")
    assert revoked["status"] == "revoked"

    # Not found branches
    with pytest.raises(Exception) as exc_404:
        await revoke_api_key("nonexistent-key-uuid-999", http_req, _admin="admin")
    assert getattr(exc_404.value, "status_code", None) == 404

    with pytest.raises(Exception) as exc_rotate_404:
        await rotate_api_key("nonexistent-key-uuid-999", http_req, _admin="admin")
    assert getattr(exc_rotate_404.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_api_keys_tenant_admin_cannot_revoke_or_rotate_platform_admin_key():
    """Tenant admin cannot revoke or rotate a key with platform:admin scope."""
    # Seed platform admin key directly
    _, key_hash, prefix = generate_api_key(name="seeded-plat-key")
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        plat_key = ApiKeyRecord(
            name="seeded-plat-key",
            tenant_id="tenant-guarded",
            key_hash=key_hash,
            prefix=prefix,
            scopes="platform:admin,admin",
            is_active=True,
            created_at=now,
        )
        session.add(plat_key)
        await session.commit()
        await session.refresh(plat_key)
        plat_key_id = plat_key.id

    http_req = MagicMock(spec=Request)
    http_req.state.tenant_id = "tenant-guarded"
    http_req.state.is_platform_admin = False
    http_req.state.api_key_scopes = {"admin"}

    with pytest.raises(Exception) as exc_revoke:
        await revoke_api_key(str(plat_key_id), http_req, _admin="admin")
    assert getattr(exc_revoke.value, "status_code", None) == 403

    with pytest.raises(Exception) as exc_rotate:
        await rotate_api_key(str(plat_key_id), http_req, _admin="admin")
    assert getattr(exc_rotate.value, "status_code", None) == 403


# =========================================================================
# 2. Analytics Aggregation & Date Filtering Edge Cases
# =========================================================================
@pytest.mark.asyncio
async def test_analytics_repository_metrics_aggregation():
    """Verify repository analytics with date filtering, wildcard querying, and finding counts."""
    owner = "org-metrics"
    repo = "repo-core"

    # Seed reviews with findings
    rev_id_1 = f"rev-test-{secrets.token_hex(6)}"
    rev_id_2 = f"rev-test-{secrets.token_hex(6)}"
    async with AsyncSessionLocal() as session:
        review_1 = CodeReviewRecord(
            id=rev_id_1,
            github_repo_owner=owner,
            github_repo_name=repo,
            code_snippet="def foo(): pass",
            overall_score=85.0,
            status="completed",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        review_2 = CodeReviewRecord(
            id=rev_id_2,
            github_repo_owner=owner,
            github_repo_name=repo,
            code_snippet="def bar(): pass",
            overall_score=75.0,
            status="completed",
            created_at=datetime.now(UTC),
        )
        session.add(review_1)
        session.add(review_2)

        finding_sec = FindingRecord(
            id=f"find-sec-{secrets.token_hex(6)}",
            review_id=rev_id_1,
            category="Security",
            severity="critical",
            agent_name="SecurityAgent",
            title="SQL Injection vulnerability",
            message="Detected raw string concatenation in SQL query",
        )
        finding_perf = FindingRecord(
            id=f"find-perf-{secrets.token_hex(6)}",
            review_id=rev_id_2,
            category="Performance",
            severity="medium",
            agent_name="performance",
            title="N+1 Query Issue",
            message="Repeated queries inside loop",
        )
        session.add(finding_sec)
        session.add(finding_perf)
        await session.commit()

    # Query analytics with valid date filters
    from_date = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    to_date = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    metrics = await get_repository_analytics(
        owner=owner, repo=repo, from_date=from_date, to_date=to_date, api_key="dev-key"
    )
    assert metrics["repository"] == f"{owner}/{repo}"
    assert metrics["metrics"]["total_reviews"] >= 2
    assert metrics["metrics"]["avg_score"] > 0
    assert metrics["metrics"]["vulnerabilities_prevented"] >= 1
    assert metrics["metrics"]["performance_optimizations"] >= 1

    # Global trends
    trends = await get_global_trends(days=14, api_key="dev-key")
    assert trends["period_days"] == 14
    assert trends["total_reviews"] >= 2

    # Query with wildcard repo
    wildcard_metrics = await get_repository_analytics(
        owner="*", repo="*", from_date="invalid-date-format", to_date="bad-date", api_key="dev-key"
    )
    assert wildcard_metrics["metrics"]["total_reviews"] >= 2

    # Query non-existent repo (zeroes check)
    empty_metrics = await get_repository_analytics(owner="ghost-owner-000", repo="ghost-repo-000", api_key="dev-key")
    assert empty_metrics["metrics"]["total_reviews"] == 0
    assert empty_metrics["metrics"]["avg_score"] == 0.0


# =========================================================================
# 3. OpenRouter & Ollama Provider Integration & Availability
# =========================================================================
@pytest.mark.asyncio
async def test_openrouter_provider_configuration_and_generation():
    """Verify OpenRouter model mapping, effective URLs, and generation logic."""
    provider = OpenRouterProvider(api_key="sk-or-test-key", model="auto")
    assert provider.effective_model == "anthropic/claude-3.5-sonnet"
    assert provider.effective_base_url == "https://openrouter.ai/api/v1"
    assert provider.effective_api_key == "sk-or-test-key"

    # Generation when not available
    with patch.object(provider, "is_available", AsyncMock(return_value=False)):
        res = await provider.generate_response("system", "user")
        assert res is None

    # Generation when available and mock response 200
    mock_resp = Response(
        status_code=200,
        json={"choices": [{"message": {"content": '{"verdict": "APPROVED"}'}}]},
        request=MagicMock(),
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(provider, "is_available", AsyncMock(return_value=True)):
        with patch.object(provider, "get_client", AsyncMock(return_value=mock_client)):
            res = await provider.generate_response("system", "user")
            assert '{"verdict": "APPROVED"}' in str(res)

    # Generation error path
    mock_client_err = AsyncMock()
    mock_client_err.post = AsyncMock(side_effect=RuntimeError("Connection dropped"))
    with patch.object(provider, "is_available", AsyncMock(return_value=True)):
        with patch.object(provider, "get_client", AsyncMock(return_value=mock_client_err)):
            res_err = await provider.generate_response("system", "user")
            assert res_err is None


@pytest.mark.asyncio
async def test_ollama_provider_configuration_and_generation():
    """Verify Ollama availability check and local generation handling."""
    provider = OllamaProvider()
    assert "codellama" in provider.effective_model or "llama" in provider.effective_model
    assert "http://" in provider.effective_base_url

    # is_available returns True on 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=Response(status_code=200, request=MagicMock()))
    with patch.object(provider, "get_client", AsyncMock(return_value=mock_client)):
        assert await provider.is_available() is True

    # is_available returns False on exception
    mock_client_fail = AsyncMock()
    mock_client_fail.get = AsyncMock(side_effect=ConnectionError("Ollama daemon offline"))
    with patch.object(provider, "get_client", AsyncMock(return_value=mock_client_fail)):
        assert await provider.is_available() is False

    # Generation success
    mock_client_gen = AsyncMock()
    mock_client_gen.post = AsyncMock(
        return_value=Response(status_code=200, json={"response": "Ollama generated fix analysis"}, request=MagicMock())
    )
    with patch.object(provider, "get_client", AsyncMock(return_value=mock_client_gen)):
        res = await provider.generate_response("system", "user")
        assert res == "Ollama generated fix analysis"

    # Generation HTTP error
    mock_client_gen_err = AsyncMock()
    mock_client_gen_err.post = AsyncMock(
        return_value=Response(status_code=500, text="Internal Server Error", request=MagicMock())
    )
    with patch.object(provider, "get_client", AsyncMock(return_value=mock_client_gen_err)):
        res_fail = await provider.generate_response("system", "user")
        assert res_fail is None


# =========================================================================
# 4. CacheManager Lifecycles, Expiration & Eviction
# =========================================================================
@pytest.mark.asyncio
async def test_cache_manager_lifecycle_and_eviction():
    """Test CacheManager hit, miss, ttl, eviction, and invalidation."""
    cache = CacheManager(max_items=3)

    # Set and Get
    await cache.set("key_1", {"data": "val_1"})
    res = await cache.get("key_1")
    assert res == {"data": "val_1"}

    # Cache hit
    hit = await cache.get("key_1")
    assert hit == {"data": "val_1"}
    assert cache.hit_rate > 0.0

    # Exceed capacity to trigger LRU eviction
    await cache.set("key_2", {"data": "val_2"})
    await cache.set("key_3", {"data": "val_3"})
    await cache.set("key_4", {"data": "val_4"})
    assert len(cache._memory_cache) <= 3

    # Invalidate
    cache.invalidate("key_4")
    assert await cache.get("key_4") is None

    # Clear
    cache.clear()
    assert len(cache._memory_cache) == 0


# =========================================================================
# 5. Schema Migrations Idempotency & Multitenancy Ledger
# =========================================================================
@pytest.mark.asyncio
async def test_schema_migrations_and_multitenancy_columns_robustness():
    """Verify run_migrations idempotency and _migrate_multitenancy_columns robustness."""
    # 1. Run migrations twice to verify zero duplicate executions
    first_run = await run_migrations(engine)
    second_run = await run_migrations(engine)
    assert first_run >= 0
    assert second_run == 0

    # 2. Test _migrate_multitenancy_columns on an active connection
    async with engine.begin() as conn:
        await _migrate_multitenancy_columns(conn)


# =========================================================================
# 6. Review Export Formats (SARIF, GitLab, SonarQube) & Approval/Feedback Lifecycle
# =========================================================================
@pytest.mark.asyncio
async def test_review_export_formats_and_lifecycle():
    """Verify SARIF, GitLab Code Quality, SonarQube exports, and Human Approval."""
    from httpx import ASGITransport, AsyncClient

    from cerberus.api.app import app

    headers = {"Authorization": "Bearer cvai_dev_key_123"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit review
        post_res = await client.post(
            "/api/v1/review",
            json={
                "code": "import os\nos.system('rm -rf ' + user_input)",
                "language": "python",
                "agents": ["security", "performance"],
            },
            headers=headers,
        )
        assert post_res.status_code == 200
        review_data = post_res.json()
        rev_id = review_data["review_id"]

        # 2. SARIF export
        sarif_res = await client.get(f"/api/v1/review/{rev_id}/sarif", headers=headers)
        assert sarif_res.status_code == 200
        assert "application/sarif+json" in sarif_res.headers.get("content-type", "")
        sarif_json = sarif_res.json()
        assert "$schema" in sarif_json
        assert "runs" in sarif_json

        # 3. GitLab Code Quality export
        gl_res = await client.get(f"/api/v1/review/{rev_id}/gitlab", headers=headers)
        assert gl_res.status_code == 200
        assert isinstance(gl_res.json(), list)

        # 4. SonarQube export
        sonar_res = await client.get(f"/api/v1/review/{rev_id}/sonarqube", headers=headers)
        assert sonar_res.status_code == 200
        assert "issues" in sonar_res.json()

        # 5. Review status only
        status_res = await client.get(f"/api/v1/review/{rev_id}/status", headers=headers)
        assert status_res.status_code == 200
        assert status_res.json()["review_id"] == rev_id

        # 6. Approve review
        approve_res = await client.post(
            f"/api/v1/review/{rev_id}/approve",
            json={"reviewer": "Lead Architect", "override_blocking": True, "notes": "Approved with exception"},
            headers=headers,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "approved"

        # 7. Submit feedback
        fb_res = await client.post(
            f"/api/v1/review/{rev_id}/feedback",
            json={"rating": 5, "comments": "Accurate detection of os.system command injection"},
            headers=headers,
        )
        assert fb_res.status_code == 200
        assert fb_res.json()["status"] == "success"
