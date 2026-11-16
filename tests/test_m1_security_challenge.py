"""
Empirical Challenge & Stress Test Suite for Milestone 1: Authentication & Security Hardening.
Tests negative authentication cases, token lifecycles, injection vectors, and CORS boundaries.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app, create_app
from cerberus.api.dependencies import verify_api_key
from cerberus.config import Settings, settings
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import generate_api_key, rate_limiter
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database schema and dev seed exist before challenge tests."""
    asyncio.run(init_db())


# ============================================================================
# Category 1: Negative Authentication Cases
# ============================================================================


class TestAuthenticationNegativeCases:
    """Stress-test authentication rejection against forged, malformed, and missing credentials."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        """Request without Authorization header must be rejected with 401 missing_authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents")
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "missing_authentication"

    @pytest.mark.asyncio
    async def test_empty_authorization_header(self):
        """Empty string Authorization header must be rejected with 401 missing_authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": ""})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "missing_authentication"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "header_value",
        [
            " ",
            "   ",
            "Bearer",
            "Bearer ",
            "Bearer   ",
            "Token some_random_token",
            "Basic dXNlcjpwYXNz",
            "Digest username=admin",
            "bearer_without_space",
            "Bearer token1 token2",
            "Bearer token1 token2 token3",
            "Bearer    extra_leading_space",
        ],
    )
    async def test_malformed_authorization_headers(self, header_value: str):
        """Malformed Authorization headers must be rejected with 401 invalid_token_format."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": header_value})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "invalid_token_format"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "arbitrary_token",
        [
            "cvai_",
            "cvai_attacker",
            "cvai_fabricated_token_999",
            "cvai_00000000000000000000000000000000",
            "cvai_admin",
            "cvai_root",
            "cvai_dev_key_1234",
            "cvai_dev_key_12",
            "cvai_dev_key_123_extra",
            "cvai_null",
            "cvai_undefined",
        ],
    )
    async def test_arbitrary_cvai_tokens_rejected(self, arbitrary_token: str):
        """Tokens starting with cvai_ that are unregistered must be rejected with 401 invalid_api_key."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {arbitrary_token}"})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_inactive_api_key_rejected(self):
        """An API key with is_active=False must be rejected with 401 invalid_api_key."""
        raw_key, key_hash, prefix = generate_api_key(name="inactive-key-test")
        async with AsyncSessionLocal() as session:
            record = ApiKeyRecord(
                key_hash=key_hash,
                name="inactive-key-test",
                prefix=prefix,
                scopes="review:read",
                is_active=False,
            )
            session.add(record)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {raw_key}"})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "invalid_api_key"
            assert "inactive" in data["detail"]["message"].lower() or "revoked" in data["detail"]["message"].lower()

    @pytest.mark.asyncio
    async def test_expired_api_key_with_utc_timezone_rejected(self):
        """An API key with expired UTC expires_at must be rejected with 401 invalid_api_key."""
        raw_key, key_hash, prefix = generate_api_key(name="expired-utc-test")
        async with AsyncSessionLocal() as session:
            record = ApiKeyRecord(
                key_hash=key_hash,
                name="expired-utc-test",
                prefix=prefix,
                scopes="review:read",
                is_active=True,
                expires_at=datetime.now(UTC) - timedelta(hours=2),
            )
            session.add(record)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {raw_key}"})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "invalid_api_key"
            assert "expired" in data["detail"]["message"].lower()

    @pytest.mark.asyncio
    async def test_expired_api_key_with_naive_datetime_rejected(self):
        """An API key with naive datetime in the past must be treated safely as UTC and rejected."""
        raw_key, key_hash, prefix = generate_api_key(name="expired-naive-test")
        naive_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)
        async with AsyncSessionLocal() as session:
            record = ApiKeyRecord(
                key_hash=key_hash,
                name="expired-naive-test",
                prefix=prefix,
                scopes="review:read",
                is_active=True,
                expires_at=naive_past,
            )
            session.add(record)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {raw_key}"})
            assert res.status_code == 401
            data = res.json()
            assert data["detail"]["error"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_valid_active_unexpired_key_accepted(self):
        """A valid active key with future expiration must be accepted with 200 OK."""
        raw_key, key_hash, prefix = generate_api_key(name="valid-active-key")
        async with AsyncSessionLocal() as session:
            record = ApiKeyRecord(
                key_hash=key_hash,
                name="valid-active-key",
                prefix=prefix,
                scopes="review:read",
                is_active=True,
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
            session.add(record)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {raw_key}"})
            assert res.status_code == 200
            assert isinstance(res.json(), list)

    @pytest.mark.asyncio
    async def test_bearer_case_insensitivity(self):
        """HTTP authorization scheme should be case-insensitive for 'bearer'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": "BEARER cvai_dev_key_123"})
            assert res.status_code == 200


# ============================================================================
# Category 2: Boundary Tokens, SQL Injection, and Pathological Inputs
# ============================================================================


class TestBoundaryAndAdversarialTokens:
    """Stress-test system resilience against injection strings, giant tokens, and edge cases."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "injection_payload",
        [
            "' OR '1'='1",
            "cvai_' OR '1'='1' --",
            "'; DROP TABLE api_keys; --",
            "' UNION SELECT 1, 'admin', 'hash', 'cvai_', 'all', 1, datetime('now'), NULL --",
            '" OR ""="',
            "admin'--",
            "cvai_'OR'1'='1'--",
        ],
    )
    async def test_sql_injection_in_token(self, injection_payload: str):
        """SQL injection payloads in Bearer token must be rejected with 401 without DB errors."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {injection_payload}"})
            assert res.status_code == 401
            assert res.json()["detail"]["error"] in ("invalid_api_key", "invalid_token_format")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("size", [1000, 10000, 50000])
    async def test_extreme_length_tokens(self, size: int):
        """Extremely large tokens must not crash the server or cause unhandled exceptions."""
        huge_token = "cvai_" + ("A" * size)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {huge_token}"})
            assert res.status_code == 401
            assert res.json()["detail"]["error"] == "invalid_api_key"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "special_token",
        [
            "cvai_<script>alert(1)</script>",
            "cvai_${7*7}",
            "cvai_{{constructor.constructor('return_this')()}}",
            "cvai_../../../../etc/passwd",
        ],
    )
    async def test_special_characters_and_script_payloads(self, special_token: str):
        """Special characters and injection strings must be safely handled and rejected with 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {special_token}"})
            assert res.status_code == 401
            assert res.json()["detail"]["error"] in ("invalid_api_key", "invalid_token_format")

    @pytest.mark.asyncio
    async def test_unicode_and_emoji_tokens_rejected_in_auth_verifier(self):
        """Unicode characters and emojis in API tokens must be rejected safely with 401."""
        req = Mock()
        for uni_token in ["cvai_🔥🔑🚀🛡️", "cvai_日本語トークン"]:
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(req, authorization=f"Bearer {uni_token}")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_unauthenticated_requests_do_not_pollute_rate_limiter(self):
        """Rejected authentication attempts should not register in rate_limiter.requests."""
        initial_tracked = len(rate_limiter.requests)
        fake_token = "cvai_adversarial_polluter_token_123"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {fake_token}"})
            assert res.status_code == 401

        # The fake token should NOT have been tracked by the rate limiter
        assert fake_token not in rate_limiter.requests
        assert len(rate_limiter.requests) == initial_tracked

    @pytest.mark.asyncio
    async def test_production_environment_rejects_dev_fallback_if_not_in_db(self, monkeypatch):
        """In production mode, settings.DEFAULT_DEV_API_KEY must NOT be permitted via fallback."""
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")

        # Query with an arbitrary token or unregistered dev key in prod mode
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/agents", headers={"Authorization": "Bearer cvai_unregistered_prod_token"})
            assert res.status_code == 401
            assert res.json()["detail"]["error"] == "invalid_api_key"


# ============================================================================
# Category 3: CORS Behavior & Stress Tests
# ============================================================================


class TestCORSBehaviorAndSecurity:
    """Stress-test CORS headers across whitelisted, non-whitelisted, and malicious origins."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "whitelisted_origin",
        [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:3000",
        ],
    )
    async def test_cors_whitelisted_origins_simple_request(self, whitelisted_origin: str):
        """Whitelisted origins must receive matching Access-Control-Allow-Origin and credentials true."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/health", headers={"Origin": whitelisted_origin})
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == whitelisted_origin
            assert res.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "whitelisted_origin",
        [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:3000",
        ],
    )
    async def test_cors_whitelisted_origins_preflight(self, whitelisted_origin: str):
        """Preflight OPTIONS request from whitelisted origin must be approved with credentials."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.options(
                "/api/v1/review",
                headers={
                    "Origin": whitelisted_origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization, content-type",
                },
            )
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == whitelisted_origin
            assert res.headers.get("access-control-allow-credentials") == "true"
            assert "POST" in res.headers.get("access-control-allow-methods", "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "untrusted_origin",
        [
            "http://example.com",
            "https://google.com",
            "http://evil.com",
            "https://attacker.org",
        ],
    )
    async def test_cors_non_whitelisted_origins_rejected(self, untrusted_origin: str):
        """Non-whitelisted origins must not receive Access-Control-Allow-Origin header."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/health", headers={"Origin": untrusted_origin})
            # Crucial security check: the untrusted origin is NEVER allowed
            assert res.headers.get("access-control-allow-origin") != untrusted_origin
            assert res.headers.get("access-control-allow-origin") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malicious_origin",
        [
            "http://localhost:3000.evil.com",
            "http://evil-localhost:3000",
            "http://localhost:3000@attacker.com",
            "http://localhost:3001",
            "http://localhost:8080",
            "http://localhost",
            "https://localhost:3000",
            "http://127.0.0.1",
            "http://127.0.0.1:8001",
            "null",
        ],
    )
    async def test_cors_adversarial_origins_rejected(self, malicious_origin: str):
        """Subdomain, port alteration, and protocol mismatch attacks must not receive CORS permissions."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Simple GET
            res = await client.get("/api/v1/health", headers={"Origin": malicious_origin})
            assert res.headers.get("access-control-allow-origin") != malicious_origin
            assert res.headers.get("access-control-allow-origin") is None

            # Preflight OPTIONS
            preflight = await client.options(
                "/api/v1/agents",
                headers={
                    "Origin": malicious_origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            # Preflight must be rejected with 400 Bad Request by CORSMiddleware
            assert preflight.status_code == 400
            assert preflight.headers.get("access-control-allow-origin") is None

    def test_cors_wildcard_origin_disallows_credentials(self, monkeypatch):
        """When CORS_ORIGINS includes '*', allow_credentials must be explicitly False."""
        monkeypatch.setattr(settings, "CORS_ORIGINS", "*")
        wildcard_app = create_app()

        # Find CORSMiddleware in middleware stack
        from fastapi.middleware.cors import CORSMiddleware

        cors_middleware = None
        for m in wildcard_app.user_middleware:
            if m.cls == CORSMiddleware:
                cors_middleware = m
                break

        assert cors_middleware is not None
        assert cors_middleware.kwargs.get("allow_origins") == ["*"]
        assert cors_middleware.kwargs.get("allow_credentials") is False

    @pytest.mark.asyncio
    async def test_cors_wildcard_runtime_behavior(self, monkeypatch):
        """Test runtime CORS response when wildcard is configured: origin=* and NO credentials header."""
        monkeypatch.setattr(settings, "CORS_ORIGINS", "*")
        wildcard_app = create_app()

        async with AsyncClient(transport=ASGITransport(app=wildcard_app), base_url="http://test") as client:
            res = await client.get("/api/v1/health", headers={"Origin": "http://arbitrary-site.com"})
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "*"
            # Under wildcard without allow_credentials, credentials header must NOT be true
            assert res.headers.get("access-control-allow-credentials") != "true"


# ============================================================================
# Category 4: Production Configuration Security
# ============================================================================


class TestProductionSecurityValidation:
    """Stress-test production settings validation against weak or default secrets."""

    def test_production_rejects_insecure_defaults(self):
        """Production environment must raise ValueError when default secrets are used."""
        insecure_keys = [
            "cerberus_dev_secret_key_change_in_production_32chars",
            "cerberus_production_secret_key_change_me_now_1234",
            "change_me_in_production",
            "secret",
            "changeme",
            "password",
            "admin",
        ]
        for weak in insecure_keys:
            with pytest.raises(ValueError, match="Insecure default SECRET_KEY is not permitted in production"):
                Settings(ENVIRONMENT="production", SECRET_KEY=weak)

    def test_production_rejects_short_secrets(self):
        """Production environment must raise ValueError when SECRET_KEY is < 32 chars."""
        short_keys = [
            "a" * 16,
            "a" * 31,
            "short_secret",
            "",
        ]
        for short in short_keys:
            with pytest.raises(ValueError):
                Settings(ENVIRONMENT="production", SECRET_KEY=short)

    def test_production_accepts_strong_secret(self):
        """Production environment accepts secrets >= 32 chars that are not in insecure list."""
        valid_secret = "k" * 32
        s = Settings(ENVIRONMENT="production", SECRET_KEY=valid_secret)
        assert s.SECRET_KEY == valid_secret

    def test_prod_alias_triggers_same_validation(self):
        """ENVIRONMENT='prod' alias triggers the same validation rules."""
        with pytest.raises(ValueError, match="Insecure default SECRET_KEY"):
            Settings(ENVIRONMENT="prod", SECRET_KEY="password")
