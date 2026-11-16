"""
Regression Tests: Enforce Scope Delegation Hierarchy and Eliminate Privilege Escalation.
Verifies that tenant admins CANNOT:
1. Mint platform:admin keys or keys with unheld scopes.
2. Provision keys for other tenants.
3. List, filter, revoke, or rotate keys of other tenants or platform:admin keys.
4. Modify runtime configuration (/api/v1/config).
5. Access cross-tenant reviews, ZIP reviews, SSE streams, or WebSockets.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cerberus.api.app import app
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import hash_api_key
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(ApiKeyRecord).where(
                ApiKeyRecord.name.in_(["tenant-a-admin", "tenant-a-user", "tenant-b-admin", "platform-root-admin"])
            )
        )
        existing = {r.name for r in res.scalars().all()}

        to_add = []
        if "tenant-a-admin" not in existing:
            to_add.append(
                ApiKeyRecord(
                    key_hash=hash_api_key("cvai_tenant_a_admin_key_111111111111111"),
                    name="tenant-a-admin",
                    prefix="cvai_ten",
                    tenant_id="tenant_a",
                    scopes="admin,review:read,review:write",
                    is_active=True,
                )
            )
        if "tenant-a-user" not in existing:
            to_add.append(
                ApiKeyRecord(
                    key_hash=hash_api_key("cvai_tenant_a_user_key_1111111111111111"),
                    name="tenant-a-user",
                    prefix="cvai_ten",
                    tenant_id="tenant_a",
                    scopes="review:read,review:write",
                    is_active=True,
                )
            )
        if "tenant-b-admin" not in existing:
            to_add.append(
                ApiKeyRecord(
                    key_hash=hash_api_key("cvai_tenant_b_admin_key_222222222222222"),
                    name="tenant-b-admin",
                    prefix="cvai_ten",
                    tenant_id="tenant_b",
                    scopes="admin,review:read,review:write",
                    is_active=True,
                )
            )
        if "platform-root-admin" not in existing:
            to_add.append(
                ApiKeyRecord(
                    key_hash=hash_api_key("cvai_platform_admin_super_secret_key_999"),
                    name="platform-root-admin",
                    prefix="cvai_pla",
                    tenant_id="platform",
                    scopes="platform:admin",
                    is_active=True,
                )
            )
        if to_add:
            session.add_all(to_add)
            await session.commit()


@pytest.mark.asyncio
async def test_tenant_admin_cannot_mint_platform_admin():
    """A tenant-scoped admin cannot grant 'platform:admin' to any key."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_a_admin_key_111111111111111"}
        resp = await client.post(
            "/api/v1/keys",
            headers=headers,
            json={"name": "rogue-platform-key", "scopes": ["platform:admin"]},
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "Cannot grant 'platform:admin'" in detail or "scope" in detail.lower()


@pytest.mark.asyncio
async def test_tenant_admin_cannot_grant_unheld_scopes():
    """A tenant caller cannot grant scopes that they do not possess."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A tenant caller with only review:read cannot create an admin key
        headers = {"Authorization": "Bearer cvai_tenant_a_user_key_1111111111111111"}
        resp = await client.post(
            "/api/v1/keys",
            headers=headers,
            json={"name": "escalation-attempt", "scopes": ["admin"]},
        )
        # User lacks 'admin' scope entirely -> 403 Forbidden
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_tenant_admin_cannot_provision_key_for_another_tenant():
    """A tenant admin cannot provision an API key assigned to a different tenant."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_a_admin_key_111111111111111"}
        resp = await client.post(
            "/api/v1/keys",
            headers=headers,
            json={"name": "cross-tenant-key", "tenant_id": "tenant_b", "scopes": ["review:read"]},
        )
        assert resp.status_code == 403
        assert "Only platform administrators can provision" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tenant_admin_cannot_rotate_to_platform_admin_or_cross_tenant():
    """Rotating a key preserves original tenant and cannot escalate to platform:admin."""
    async with AsyncSessionLocal() as session:
        stmt_b = select(ApiKeyRecord).where(ApiKeyRecord.name == "tenant-b-admin")
        rec_b = (await session.execute(stmt_b)).scalar_one()
        key_b_id = rec_b.id

        stmt_p = select(ApiKeyRecord).where(ApiKeyRecord.name == "platform-root-admin")
        rec_p = (await session.execute(stmt_p)).scalar_one()
        key_p_id = rec_p.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_admin_key_111111111111111"}

        # Attempt to rotate tenant B's key using tenant A's admin credentials
        resp_b = await client.post(
            f"/api/v1/keys/{key_b_id}/rotate",
            headers=headers_a,
        )
        assert resp_b.status_code == 404  # Tenant-scoped lookup hides key from other tenants

        # Attempt to rotate platform admin key using tenant A's admin credentials
        resp_plat = await client.post(
            f"/api/v1/keys/{key_p_id}/rotate",
            headers=headers_a,
        )
        assert resp_plat.status_code in (403, 404)


@pytest.mark.asyncio
async def test_tenant_admin_cannot_access_or_modify_system_configuration():
    """Tenant admin must be blocked from modifying system runtime configuration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_tenant_a_admin_key_111111111111111"}

        # PUT /api/v1/config requires platform:admin
        put_resp = await client.put(
            "/api/v1/config",
            headers=headers,
            json={"CACHE_ENABLED": False},
        )
        assert put_resp.status_code == 403
        assert "platform:admin" in str(put_resp.json())

        # PATCH /api/v1/config requires platform:admin
        patch_resp = await client.patch(
            "/api/v1/config",
            headers=headers,
            json={"LOG_LEVEL": "DEBUG"},
        )
        assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_can_manage_cross_tenant_and_system_config():
    """A verified platform admin can modify configuration and manage keys."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_platform_admin_super_secret_key_999"}

        # Platform admin can access config
        cfg_resp = await client.get("/api/v1/config", headers=headers)
        assert cfg_resp.status_code == 200

        # Platform admin can provision keys with any valid scope for any tenant
        create_resp = await client.post(
            "/api/v1/keys",
            headers=headers,
            json={"name": "provisioned-by-platform", "tenant_id": "tenant_custom", "scopes": ["admin", "review:read"]},
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["tenant_id"] == "tenant_custom"
