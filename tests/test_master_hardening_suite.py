"""
Master Hardening & Verification Test Suite for Cerberus.
Validates the complete 10/10 transformation:
- GitHub Webhook Security & Idempotent Replay Defense
- RBAC Scope Enforcement & RESTful API Key Management
- Zip-Slip, Symlink, and Chunked Streaming Zip-Bomb Protection
- Multi-Stage In-Memory Patch Verification Pipeline
- Two-Tier Cache Fingerprinting & Cache Invalidation
- Genuine Database Health Check & Repository Analytics
"""

import hashlib
import hmac
import io
import json
import time
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import create_app
from cerberus.config import settings
from cerberus.core.cache import CacheManager
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.patch_verifier import PatchVerificationPipeline, PatchVerificationStage
from cerberus.core.security import generate_api_key
from cerberus.core.zip_processor import extract_code_from_zip, is_safe_zip_path, is_symlink_entry
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.mark.asyncio
async def test_webhook_replay_protection(app):
    """Ensure duplicate X-GitHub-Delivery requests within TTL are detected and ignored."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "action": "opened",
            "number": 101,
            "repository": {"full_name": "owner/repo"},
            "pull_request": {
                "number": 101,
                "title": "Fix security vulnerability",
                "body": "```python\ndef safe_code():\n    return True\n```",
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY
        sig = "sha256=" + hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        delivery_id = f"delivery-uuid-{time.time()}"

        headers = {
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
            "Content-Type": "application/json",
        }

        # First request: processed
        r1 = await client.post("/api/v1/review/webhooks/github", content=body_bytes, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["status"] == "completed"

        # Second request with identical delivery_id: ignored as duplicate
        r2 = await client.post("/api/v1/review/webhooks/github", content=body_bytes, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "ignored"
        assert r2.json()["reason"] == "duplicate_event"


@pytest.mark.asyncio
async def test_webhook_tamper_and_missing_signatures(app, monkeypatch):
    """Ensure tampered HMAC signatures and missing headers are strictly rejected."""
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "strict_test_webhook_secret_key_12345")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        body = b'{"action": "ping"}'

        # Missing signature header
        r_missing = await client.post(
            "/api/v1/review/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"},
        )
        assert r_missing.status_code == 401
        assert "Missing" in str(r_missing.json()["detail"])

        # Tampered signature
        r_tampered = await client.post(
            "/api/v1/review/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert r_tampered.status_code == 401
        assert "Invalid GitHub X-Hub-Signature-256" in str(r_tampered.json()["detail"])


@pytest.mark.asyncio
async def test_rbac_scope_enforcement_and_key_crud(app):
    """Verify admin-only RBAC protection, key creation, listing, rotation, and revocation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Generate an unprivileged key (review:read only)
        raw_ro, hash_ro, prefix_ro = generate_api_key(name="read-only-worker")
        async with AsyncSessionLocal() as session:
            ro_rec = ApiKeyRecord(
                name="read-only-worker", key_hash=hash_ro, prefix=prefix_ro, scopes="review:read", is_active=True
            )
            session.add(ro_rec)
            await session.commit()

        # 2. Attempt admin action with unprivileged key -> 403 Forbidden
        r_forbidden = await client.post(
            "/api/v1/keys", headers={"Authorization": f"Bearer {raw_ro}"}, json={"name": "sub-key"}
        )
        assert r_forbidden.status_code == 403
        assert r_forbidden.json()["detail"]["error"] == "insufficient_scope"

        # 3. Use default admin dev key to create a new managed key
        admin_headers = {"Authorization": f"Bearer {settings.DEFAULT_DEV_API_KEY}"}
        r_create = await client.post(
            "/api/v1/keys",
            headers=admin_headers,
            json={"name": "audited-service-key", "scopes": ["review:read", "review:write"], "expires_in_days": 30},
        )
        assert r_create.status_code == 201
        key_data = r_create.json()
        assert key_data["name"] == "audited-service-key"
        assert "raw_key" in key_data
        created_key_id = key_data["id"]

        # 4. List keys: ensure raw_key is not leaked
        r_list = await client.get("/api/v1/keys", headers=admin_headers)
        assert r_list.status_code == 200
        summaries = r_list.json()
        assert any(k["id"] == created_key_id for k in summaries)
        for s in summaries:
            assert "raw_key" not in s
            assert "key_hash" not in s

        # 5. Rotate key atomically
        r_rotate = await client.post(f"/api/v1/keys/{created_key_id}/rotate", headers=admin_headers)
        assert r_rotate.status_code == 200
        rot_data = r_rotate.json()
        assert rot_data["old_key_id"] == created_key_id
        assert rot_data["new_key_id"] != created_key_id
        assert rot_data["is_active"] is True

        # 6. Revoke rotated key
        r_del = await client.delete(f"/api/v1/keys/{rot_data['new_key_id']}", headers=admin_headers)
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_zip_security_streaming_and_symlinks():
    """Verify chunked streaming decompression aborts on zip-bombs and symlinks are rejected."""
    # 1. Symlink detection
    symlink_info = zipfile.ZipInfo("symlink.txt")
    symlink_info.create_system = 3  # Unix
    symlink_info.external_attr = 0o120777 << 16  # S_IFLNK
    assert is_symlink_entry(symlink_info) is True

    normal_info = zipfile.ZipInfo("normal.py")
    assert is_symlink_entry(normal_info) is False

    # 2. Path safety checks
    assert is_safe_zip_path("valid/path/file.py") is True
    assert is_safe_zip_path("../escape.py") is False
    assert is_safe_zip_path("/etc/passwd") is False
    assert is_safe_zip_path("deep/" + "/".join(["sub"] * 20) + "/file.py") is False  # Exceeds max depth

    # 3. Streaming decompression safely skips files exceeding single-file cap without memory explosion
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge_file.py", "A" * (12 * 1024 * 1024))  # 12 MB exceeds 10 MB per-file cap
        zf.writestr("clean_file.py", "def valid(): return 1\n")
    zip_bytes = buf.getvalue()

    result = extract_code_from_zip(zip_bytes)
    assert any("exceeds single file size limit" in s for s in result.skipped_files)
    assert any(cf.filename == "clean_file.py" for cf in result.code_files)

    # 4. Total archive size cap raises ValueError
    oversized_archive_bytes = b"PK\x03\x04" + b"\x00" * (26 * 1024 * 1024)
    with pytest.raises(ValueError, match="exceeds safety maximum"):
        extract_code_from_zip(oversized_archive_bytes)


def test_multi_stage_patch_verification_pipeline():
    """Verify the 5-stage patch verification pipeline catches syntax errors and security regressions."""
    original_code = "def add(a, b):\n    return a + b\n"

    # Stage 1: Clean valid patch
    repaired_code = 'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a + b\n'
    res_valid = PatchVerificationPipeline.verify_patch(
        original_code, repaired_code, language="python", filename="math_utils.py"
    )
    assert res_valid.is_valid is True
    assert res_valid.stage == PatchVerificationStage.REGRESSION_FREE
    assert res_valid.patch_diff is not None
    assert "--- a/math_utils.py" in res_valid.patch_diff

    # Stage 2: Patch introducing syntax error
    syntax_error_code = "def broken(:\n    return False\n"
    res_syn_err = PatchVerificationPipeline.verify_patch(
        original_code, syntax_error_code, language="python", filename="math_utils.py"
    )
    assert res_syn_err.is_valid is False
    assert res_syn_err.stage == PatchVerificationStage.REJECTED
    assert len(res_syn_err.syntax_errors) > 0

    # Stage 3: Patch introducing critical security vulnerability (eval)
    malicious_patch = "def add(a, b):\n    eval(str(a))\n    return a + b\n"
    res_sec_err = PatchVerificationPipeline.verify_patch(
        original_code, malicious_patch, language="python", filename="math_utils.py"
    )
    assert res_sec_err.is_valid is False
    assert res_sec_err.stage == PatchVerificationStage.REJECTED
    assert "security issues" in res_sec_err.explanation


def test_cache_fingerprint_divergence():
    """Verify cache keys diverge when code, language, filename, context, or config differ."""
    cm = CacheManager()
    code = "def calc(): return 42"

    key_base = cm.compute_cache_key(code, language="python")
    key_diff_filename = cm.compute_cache_key(code, language="python", filename="different.py")
    key_diff_context = cm.compute_cache_key(code, language="python", context={"repo": "owner/repo"})
    key_diff_config = cm.compute_cache_key(code, language="python", config={"blocking_mode": True})

    # All keys must be unique fingerprints
    assert key_base != key_diff_filename
    assert key_base != key_diff_context
    assert key_base != key_diff_config
    assert key_diff_filename != key_diff_context

    # Invalidate key
    cm._memory_cache[key_base] = {"data": {"val": 1}, "expires_at": time.time() + 100}
    assert cm.invalidate(key_base) is True
    assert key_base not in cm._memory_cache


@pytest.mark.asyncio
async def test_live_database_health_and_analytics(app):
    """Verify live database pings in health endpoint and genuine aggregated analytics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Health check verifies DB ping
        r_health = await client.get("/api/v1/health")
        assert r_health.status_code == 200
        health_data = r_health.json()
        assert health_data["database"] == "connected"
        assert health_data["status"] == "healthy"

        # Analytics endpoint computes genuine aggregate stats from DB
        auth_header = {"Authorization": f"Bearer {settings.DEFAULT_DEV_API_KEY}"}
        r_analytics = await client.get("/api/v1/analytics/repositories/owner-test/repo-test", headers=auth_header)
        assert r_analytics.status_code == 200
        analytics_data = r_analytics.json()
        assert "metrics" in analytics_data
        assert "total_reviews" in analytics_data["metrics"]
        assert "vulnerabilities_prevented" in analytics_data["metrics"]
        assert "findings_by_severity" in analytics_data["metrics"]
