"""
Comprehensive Multi-Tenant Isolation Integration Test Suite.
Proves that Tenant B cannot access Tenant A data across:
REST endpoints (GET, results, status, sarif, gitlab, sonarqube, approve, feedback),
ZIP review reports, real-time SSE & WebSocket streams, key management lifecycle,
L1/L2 cache, and database fallback queries.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from cerberus.api.app import app
from cerberus.api.v1.review import (
    _review_owners,
    _zip_review_owners,
    reviews_store,
    zip_reviews_store,
)
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import hash_api_key
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    # Seed Tenant A and Tenant B API Keys
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ApiKeyRecord).where(ApiKeyRecord.tenant_id.in_(["tenant_alpha", "tenant_beta", "platform_corp", ""]))
        )
        await session.commit()

        # Key for Tenant A
        raw_key_a = "cvai_tenant_a_key_111111111111111111111111"
        rec_a = ApiKeyRecord(
            tenant_id="tenant_alpha",
            key_hash=hash_api_key(raw_key_a),
            name="Tenant Alpha Key",
            prefix="cvai_tena",
            scopes="review:read,review:write,admin",
            is_active=True,
        )
        session.add(rec_a)

        # Key for Tenant B
        raw_key_b = "cvai_tenant_b_key_222222222222222222222222"
        rec_b = ApiKeyRecord(
            tenant_id="tenant_beta",
            key_hash=hash_api_key(raw_key_b),
            name="Tenant Beta Key",
            prefix="cvai_tenb",
            scopes="review:read,review:write,admin",
            is_active=True,
        )
        session.add(rec_b)

        # Platform Admin Key
        raw_key_admin = "cvai_platform_admin_key_9999999999999999"
        rec_admin = ApiKeyRecord(
            tenant_id="platform_corp",
            key_hash=hash_api_key(raw_key_admin),
            name="Platform SuperAdmin",
            prefix="cvai_plat",
            scopes="review:read,review:write,admin,platform:admin",
            is_active=True,
        )
        session.add(rec_admin)
        await session.commit()

    yield

    reviews_store.clear()
    zip_reviews_store.clear()
    _review_owners.clear()
    _zip_review_owners.clear()


@pytest.mark.asyncio
async def test_key_management_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_key_111111111111111111111111"}
        headers_b = {"Authorization": "Bearer cvai_tenant_b_key_222222222222222222222222"}

        # 1. Tenant A creates a key
        create_resp = await client.post(
            "/api/v1/keys",
            headers=headers_a,
            json={"name": "Alpha Service Key", "scopes": ["review:read"]},
        )
        assert create_resp.status_code == 201
        key_data_a = create_resp.json()
        assert key_data_a["tenant_id"] == "tenant_alpha"
        created_key_id = key_data_a["id"]

        # 2. Tenant B lists keys - must NOT see Tenant A's key
        list_b = await client.get("/api/v1/keys", headers=headers_b)
        assert list_b.status_code == 200
        keys_b = list_b.json()
        for k in keys_b:
            assert k["tenant_id"] == "tenant_beta"
            assert k["id"] != created_key_id

        # 3. Tenant B attempts to revoke Tenant A's key - forbidden / 404
        revoke_resp = await client.delete(f"/api/v1/keys/{created_key_id}", headers=headers_b)
        assert revoke_resp.status_code == 404

        # 4. Tenant B attempts to rotate Tenant A's key - forbidden / 404
        rotate_resp = await client.post(f"/api/v1/keys/{created_key_id}/rotate", headers=headers_b)
        assert rotate_resp.status_code == 404

        # 5. Tenant A rotates their own key - tenant identity preserved
        rotate_ok = await client.post(f"/api/v1/keys/{created_key_id}/rotate", headers=headers_a)
        assert rotate_ok.status_code == 200
        rotated_info = rotate_ok.json()
        assert rotated_info["tenant_id"] == "tenant_alpha"


@pytest.mark.asyncio
async def test_review_endpoints_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_key_111111111111111111111111"}
        headers_b = {"Authorization": "Bearer cvai_tenant_b_key_222222222222222222222222"}
        headers_admin = {"Authorization": "Bearer cvai_platform_admin_key_9999999999999999"}

        # 1. Tenant A submits a review
        sub_resp = await client.post(
            "/api/v1/review",
            headers=headers_a,
            json={
                "code": "import os\ndef ping(ip):\n    os.system('ping ' + ip)",
                "filename": "vuln.py",
                "language": "python",
            },
        )
        assert sub_resp.status_code == 200
        rev_a = sub_resp.json()
        review_id = rev_a["review_id"]

        # 2. Tenant A can read their own review
        get_a = await client.get(f"/api/v1/review/{review_id}", headers=headers_a)
        assert get_a.status_code == 200

        # 3. Tenant B attempts cross-tenant access to all endpoints -> Must return 404
        endpoints_to_test = [
            f"/api/v1/review/{review_id}",
            f"/api/v1/review/{review_id}/results",
            f"/api/v1/review/{review_id}/status",
            f"/api/v1/review/{review_id}/sarif",
            f"/api/v1/review/{review_id}/gitlab",
            f"/api/v1/review/{review_id}/sonarqube",
        ]
        for ep in endpoints_to_test:
            resp_b = await client.get(ep, headers=headers_b)
            assert resp_b.status_code == 404, (
                f"Endpoint {ep} leaked Tenant A data to Tenant B! Status: {resp_b.status_code}"
            )

        # 4. Tenant B cannot approve Tenant A's review
        approve_b = await client.post(
            f"/api/v1/review/{review_id}/approve",
            headers=headers_b,
            json={"reviewer": "evil_tenant_b", "override_blocking": True},
        )
        assert approve_b.status_code == 404

        # 5. Tenant B cannot submit feedback on Tenant A's review
        feedback_b = await client.post(
            f"/api/v1/review/{review_id}/feedback",
            headers=headers_b,
            json={"rating": 1, "comments": "hijacked feedback"},
        )
        assert feedback_b.status_code == 404

        # 6. Tenant B cannot issue stream tokens for Tenant A's review
        st_resp = await client.post(f"/api/v1/review/{review_id}/stream-token", headers=headers_b)
        assert st_resp.status_code == 404

        # 7. Platform Admin CAN access Tenant A's review
        admin_resp = await client.get(f"/api/v1/review/{review_id}", headers=headers_admin)
        assert admin_resp.status_code == 200


@pytest.mark.asyncio
async def test_database_fallback_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_key_111111111111111111111111"}
        headers_b = {"Authorization": "Bearer cvai_tenant_b_key_222222222222222222222222"}

        # Submit review under Tenant A
        sub = await client.post(
            "/api/v1/review",
            headers=headers_a,
            json={"code": "def secret(): return 'alpha_secret'", "filename": "alpha.py", "language": "python"},
        )
        review_id = sub.json()["review_id"]

        # Evict completely from memory cache and ownership store
        reviews_store.clear()
        _review_owners.clear()

        # Tenant B queries review_id -> DB lookup executes -> Must verify owner and return 404
        get_b = await client.get(f"/api/v1/review/{review_id}", headers=headers_b)
        assert get_b.status_code == 404

        # Tenant A queries review_id -> DB lookup executes -> Restores to cache and returns 200
        get_a = await client.get(f"/api/v1/review/{review_id}", headers=headers_a)
        assert get_a.status_code == 200
        assert get_a.json()["review_id"] == review_id


@pytest.mark.asyncio
async def test_zip_review_tenant_isolation():
    import io
    import zipfile

    # Build an in-memory sample zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("module.py", "def compute(): return 123\n")
    zip_content = zip_buf.getvalue()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_key_111111111111111111111111"}
        headers_b = {"Authorization": "Bearer cvai_tenant_b_key_222222222222222222222222"}

        # Upload zip review as Tenant A
        upload_resp = await client.post(
            "/api/v1/review/zip",
            headers=headers_a,
            files={"file": ("project.zip", zip_content, "application/zip")},
            data={"project_name": "alpha_project"},
        )
        assert upload_resp.status_code == 200
        zip_review_id = upload_resp.json()["review_id"]

        # Tenant A can access
        get_zip_a = await client.get(f"/api/v1/review/zip/{zip_review_id}", headers=headers_a)
        assert get_zip_a.status_code == 200

        # Tenant B gets 404 across all zip review endpoints
        get_zip_b = await client.get(f"/api/v1/review/zip/{zip_review_id}", headers=headers_b)
        assert get_zip_b.status_code == 404

        sonar_b = await client.get(f"/api/v1/review/zip/{zip_review_id}/sonarqube", headers=headers_b)
        assert sonar_b.status_code == 404

        gl_b = await client.get(f"/api/v1/review/zip/{zip_review_id}/gitlab", headers=headers_b)
        assert gl_b.status_code == 404


@pytest.mark.asyncio
async def test_key_rotation_and_revocation_extended_cases():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"Authorization": "Bearer cvai_tenant_a_key_111111111111111111111111"}
        headers_admin = {"Authorization": "Bearer cvai_platform_admin_key_9999999999999999"}

        # 1. Create a named key for Tenant A
        create_resp = await client.post(
            "/api/v1/keys",
            headers=headers_a,
            json={"name": "Special-Named-Key", "scopes": ["review:read"]},
        )
        assert create_resp.status_code == 201
        created_id = create_resp.json()["id"]
        assert created_id is not None

        # 2. Rotate by key name
        rot_by_name = await client.post("/api/v1/keys/Special-Named-Key/rotate", headers=headers_a)
        assert rot_by_name.status_code == 200
        assert rot_by_name.json()["tenant_id"] == "tenant_alpha"

        # 3. Revoke by key name
        rev_by_name = await client.delete("/api/v1/keys/Special-Named-Key", headers=headers_a)
        assert rev_by_name.status_code == 200
        assert rev_by_name.json()["status"] == "revoked"

        # 4. Rotate non-existent key -> 404
        rot_404 = await client.post("/api/v1/keys/non-existent-key-12345/rotate", headers=headers_a)
        assert rot_404.status_code == 404

        # 5. Revoke non-existent key -> 404
        rev_404 = await client.delete("/api/v1/keys/non-existent-key-12345", headers=headers_a)
        assert rev_404.status_code == 404

        # 6. Platform admin can rotate and revoke Tenant A's key
        create_resp2 = await client.post(
            "/api/v1/keys",
            headers=headers_a,
            json={"name": "Admin-Managed-Key", "scopes": ["review:read"]},
        )
        assert create_resp2.status_code == 201
        key2_id = create_resp2.json()["id"]

        admin_rot = await client.post(f"/api/v1/keys/{key2_id}/rotate", headers=headers_admin)
        assert admin_rot.status_code == 200
        assert admin_rot.json()["tenant_id"] == "tenant_alpha"

        admin_rev = await client.delete(f"/api/v1/keys/{key2_id}", headers=headers_admin)
        assert admin_rev.status_code == 200
        assert admin_rev.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_inactive_expired_and_unowned_keys_rejected():
    import uuid
    from datetime import UTC, datetime, timedelta

    from cerberus.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed inactive key with random unique suffixes
        uid = uuid.uuid4().hex
        raw_inactive = f"cvai_inactive_{uid}"
        raw_expired = f"cvai_expired_{uid}"
        raw_unowned = f"cvai_unowned_{uid}"

        async with AsyncSessionLocal() as session:
            rec_inact = ApiKeyRecord(
                tenant_id="tenant_alpha",
                key_hash=hash_api_key(raw_inactive),
                name=f"Inactive Key {uid[:6]}",
                prefix="cvai_inac",
                scopes="review:read",
                is_active=False,
            )
            rec_exp = ApiKeyRecord(
                tenant_id="tenant_alpha",
                key_hash=hash_api_key(raw_expired),
                name=f"Expired Key {uid[:6]}",
                prefix="cvai_expi",
                scopes="review:read",
                is_active=True,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
            rec_unowned = ApiKeyRecord(
                tenant_id="",
                key_hash=hash_api_key(raw_unowned),
                name=f"Unowned Key {uid[:6]}",
                prefix="cvai_unow",
                scopes="review:read",
                is_active=True,
            )
            session.add_all([rec_inact, rec_exp, rec_unowned])
            await session.commit()

        # Inactive key -> 401
        inact_resp = await client.get("/api/v1/keys", headers={"Authorization": f"Bearer {raw_inactive}"})
        assert inact_resp.status_code == 401

        # Expired key -> 401
        exp_resp = await client.get("/api/v1/keys", headers={"Authorization": f"Bearer {raw_expired}"})
        assert exp_resp.status_code == 401

        # Unowned key in production environment -> 401
        orig_env = settings.ENVIRONMENT
        settings.ENVIRONMENT = "production"
        try:
            unowned_resp = await client.get("/api/v1/keys", headers={"Authorization": f"Bearer {raw_unowned}"})
            assert unowned_resp.status_code == 401
            assert unowned_resp.json()["detail"]["error"] == "unowned_api_key"
        finally:
            settings.ENVIRONMENT = orig_env
