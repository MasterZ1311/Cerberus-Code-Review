"""
Empirical Challenge & Stress Test Suite for Milestone 1 - Challenger 2.
Focus areas:
1. Production Secrets Validation: Settings initialization across environments and secret keys.
2. CLI Key Lifecycle: 'cerberus create-api-key' invocation, SQLite persistence, and API authentication.
"""

import asyncio
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from typer.testing import CliRunner

from cerberus.api.app import app
from cerberus.cli.main import app as cli_app
from cerberus.config import INSECURE_DEFAULT_SECRETS, Settings, settings
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.security import hash_api_key
from cerberus.models.database import ApiKeyRecord


@pytest.fixture(scope="session", autouse=True)
def ensure_db():
    """Ensure database schema is created."""
    asyncio.run(init_db())


# ============================================================================
# Category 1: Production Secrets Validation Stress Tests
# ============================================================================


class TestProductionSecretsValidation:
    """Stress tests for Settings initialization and production security validator."""

    # 1.1 Insecure Default Secrets in Production / Prod
    @pytest.mark.parametrize("env", ["production", "prod", "PRODUCTION", "PROD", "Production", "Prod"])
    @pytest.mark.parametrize("bad_secret", list(INSECURE_DEFAULT_SECRETS))
    def test_production_rejects_all_insecure_defaults(self, env: str, bad_secret: str):
        """Production environments must reject every known insecure default secret."""
        with pytest.raises(ValueError, match="Production configuration error: Insecure default SECRET_KEY"):
            Settings(ENVIRONMENT=env, SECRET_KEY=bad_secret)

    # 1.2 Empty or None Secrets in Production / Prod
    @pytest.mark.parametrize("env", ["production", "prod"])
    @pytest.mark.parametrize("empty_secret", ["", "   ", None])
    def test_production_rejects_empty_secrets(self, env: str, empty_secret: Optional[str]):
        """Production environments must reject empty, blank, or None secrets."""
        with pytest.raises(ValueError):
            Settings(ENVIRONMENT=env, SECRET_KEY=empty_secret)

    # 1.3 Secret Length Boundary Tests (< 32 chars) in Production
    @pytest.mark.parametrize("env", ["production", "prod"])
    @pytest.mark.parametrize("length", [1, 2, 8, 16, 24, 30, 31])
    def test_production_rejects_secrets_under_32_chars(self, env: str, length: int):
        """Production environments must strictly reject secrets with length < 32 chars."""
        short_secret = "x" * length
        with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters long in production"):
            Settings(ENVIRONMENT=env, SECRET_KEY=short_secret)

    # 1.4 Valid Secrets (>= 32 chars) in Production / Prod
    @pytest.mark.parametrize("env", ["production", "prod", "PRODUCTION", "PROD"])
    @pytest.mark.parametrize(
        "valid_secret",
        [
            "a" * 32,  # Exact boundary: 32 chars
            "12345678901234567890123456789012",  # 32 numeric chars
            "f4c6e7a8b9d0e1f2a3b4c5d6e7f8a9b0",  # 32 hex chars
            "x" * 64,  # 64 chars
            "super_secret_production_key_with_high_entropy_123",  # Descriptive high entropy
            secrets.token_urlsafe(32),  # 43 chars urlsafe
            secrets.token_hex(32),  # 64 hex chars
            "🔒" * 32,  # 32 unicode chars
        ],
    )
    def test_production_accepts_valid_high_entropy_secrets(self, env: str, valid_secret: str):
        """Production environments must accept secrets with length >= 32 that are not default."""
        s = Settings(ENVIRONMENT=env, SECRET_KEY=valid_secret)
        assert s.ENVIRONMENT == env
        assert s.SECRET_KEY == valid_secret

    # 1.5 Non-Production Environments (development, test, staging, etc.)
    @pytest.mark.parametrize(
        "env",
        [
            "development",
            "dev",
            "DEVELOPMENT",
            "test",
            "testing",
            "TEST",
            "staging",
            "local",
            "ci",
        ],
    )
    @pytest.mark.parametrize(
        "dev_secret",
        [
            "cerberus_dev_secret_key_change_in_production_32chars",  # Default dev key
            "short",  # Short key < 32 chars
            "secret",  # Known weak secret
            "123",  # Very short
            "a" * 32,  # 32 chars
        ],
    )
    def test_non_production_allows_defaults_and_short_keys(self, env: str, dev_secret: str):
        """Non-production environments (development, test, staging) must not be blocked by prod validator."""
        s = Settings(ENVIRONMENT=env, SECRET_KEY=dev_secret)
        assert s.ENVIRONMENT == env
        assert s.SECRET_KEY == dev_secret

    # 1.6 Environment Variable Override Behavior
    def test_env_var_override_production_validation(self, monkeypatch):
        """Environment variables via os.environ must trigger production validator properly."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "insecure_short")
        with pytest.raises(ValueError):
            Settings()

        # Valid override
        strong_key = "a" * 40
        monkeypatch.setenv("SECRET_KEY", strong_key)
        s = Settings()
        assert s.SECRET_KEY == strong_key


# ============================================================================
# Category 2: CLI Key Generation & Lifecycle Stress Tests
# ============================================================================


class TestCLIKeyLifecycle:
    """Stress tests for CLI key creation, SQLite persistence, and API authentication."""

    @pytest.fixture(autouse=True)
    def runner(self):
        return CliRunner()

    def _extract_key(self, output: str) -> str:
        """Helper to extract generated raw API key from CLI output."""
        match = re.search(r"(cvai_[0-9a-fA-F]+)", output)
        assert match, f"Could not extract API key from output: {output}"
        return match.group(1)

    # 2.1 Basic CLI Key Creation (Sync runner test)
    def test_cli_create_api_key_default(self, runner):
        """Running 'cerberus create-api-key' with default args produces a valid key."""
        res = runner.invoke(cli_app, ["create-api-key"])
        assert res.exit_code == 0
        raw_key = self._extract_key(res.stdout)
        assert raw_key.startswith("cvai_")
        assert len(raw_key) == 5 + 48  # prefix (5) + 24 bytes hex (48) = 53 chars

    # 2.2 CLI Key Creation with Custom Names
    @pytest.mark.parametrize(
        "key_name",
        [
            "ci-pipeline-runner",
            "github-actions-bot",
            "qa-tester-key",
            "key with spaces",
            "special_chars-123.456@test",
        ],
    )
    def test_cli_create_api_key_custom_name(self, runner, key_name: str):
        """Creating keys with various names succeeds and includes name in output."""
        res = runner.invoke(cli_app, ["create-api-key", "--name", key_name])
        assert res.exit_code == 0
        assert key_name in res.stdout
        raw_key = self._extract_key(res.stdout)
        assert raw_key.startswith("cvai_")

    # 2.3 Verify Database Persistence in SQLite `api_keys` Table
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key_name",
        [
            "db-verify-test-1",
            "db-verify-test-2",
            "security-scanner-prod",
        ],
    )
    async def test_cli_key_stored_in_sqlite(self, key_name: str):
        """CLI generated keys must exist in the SQLite database with correct schema fields."""
        runner = CliRunner()
        res = await asyncio.to_thread(runner.invoke, cli_app, ["create-api-key", "-n", key_name])
        assert res.exit_code == 0

        raw_key = re.search(r"(cvai_[0-9a-fA-F]+)", res.stdout).group(1)
        computed_hash = hash_api_key(raw_key)

        async with AsyncSessionLocal() as session:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == computed_hash)
            result = await session.execute(stmt)
            record = result.scalars().first()

            assert record is not None, f"Record for key {raw_key} not found in database!"
            assert record.name == key_name
            assert record.prefix == "cvai_"
            assert record.is_active is True
            assert record.scopes == "review:read,review:write"
            assert record.created_at is not None
            assert record.expires_at is None
            assert record.id is not None
            assert len(record.id) > 10

    # 2.4 End-to-End Authentication Against Protected API Endpoints
    @pytest.mark.asyncio
    async def test_cli_key_authenticates_against_api_endpoints(self):
        """Newly created CLI key must immediately authenticate against all protected API endpoints."""
        runner = CliRunner()
        res = await asyncio.to_thread(runner.invoke, cli_app, ["create-api-key", "--name", "e2e-api-auth-key"])
        assert res.exit_code == 0
        raw_key = re.search(r"(cvai_[0-9a-fA-F]+)", res.stdout).group(1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {raw_key}"}

            # 1. GET /api/v1/agents (protected)
            agents_res = await client.get("/api/v1/agents", headers=headers)
            assert agents_res.status_code == 200
            assert isinstance(agents_res.json(), list)
            assert len(agents_res.json()) > 0

            # 2. GET /api/v1/config (protected)
            config_res = await client.get("/api/v1/config", headers=headers)
            assert config_res.status_code == 200
            assert "environment" in config_res.json()

            # 3. GET /api/v1/analytics/repositories/test-owner/test-repo (protected)
            analytics_res = await client.get("/api/v1/analytics/repositories/test-owner/test-repo", headers=headers)
            assert analytics_res.status_code == 200
            assert "metrics" in analytics_res.json()

            # 4. POST /api/v1/review (protected)
            review_payload = {
                "code": "def add(a, b):\n    return a + b\n",
                "language": "python",
                "filename": "test_add.py",
            }
            review_res = await client.post("/api/v1/review", headers=headers, json=review_payload)
            assert review_res.status_code == 200
            assert "review_id" in review_res.json()

    # 2.5 Key Lifecycle: Revocation / Deactivation
    @pytest.mark.asyncio
    async def test_cli_key_deactivation_revocation(self):
        """If a CLI-generated key is marked is_active=False in DB, API access is immediately revoked."""
        runner = CliRunner()
        res = await asyncio.to_thread(runner.invoke, cli_app, ["create-api-key", "--name", "revocation-target"])
        raw_key = re.search(r"(cvai_[0-9a-fA-F]+)", res.stdout).group(1)
        computed_hash = hash_api_key(raw_key)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {raw_key}"}

            # First verify it works
            ok_res = await client.get("/api/v1/agents", headers=headers)
            assert ok_res.status_code == 200

            # Deactivate in database
            async with AsyncSessionLocal() as session:
                stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == computed_hash)
                record = (await session.execute(stmt)).scalars().first()
                record.is_active = False
                await session.commit()

            # Now verify it is rejected with 401
            revoked_res = await client.get("/api/v1/agents", headers=headers)
            assert revoked_res.status_code == 401
            assert revoked_res.json()["detail"]["error"] == "invalid_api_key"
            assert "inactive" in revoked_res.json()["detail"]["message"].lower()

    # 2.6 Key Lifecycle: Expiration
    @pytest.mark.asyncio
    async def test_cli_key_expiration(self):
        """If a CLI-generated key has an expires_at in the past, API access is rejected with 401."""
        runner = CliRunner()
        res = await asyncio.to_thread(runner.invoke, cli_app, ["create-api-key", "--name", "expiration-target"])
        raw_key = re.search(r"(cvai_[0-9a-fA-F]+)", res.stdout).group(1)
        computed_hash = hash_api_key(raw_key)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {raw_key}"}

            # Set expires_at in the past
            async with AsyncSessionLocal() as session:
                stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == computed_hash)
                record = (await session.execute(stmt)).scalars().first()
                record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
                await session.commit()

            # Now verify it is rejected with 401
            exp_res = await client.get("/api/v1/agents", headers=headers)
            assert exp_res.status_code == 401
            assert exp_res.json()["detail"]["error"] == "invalid_api_key"
            assert "expired" in exp_res.json()["detail"]["message"].lower()

    # 2.7 Multiple Unique CLI Keys Independence
    @pytest.mark.asyncio
    async def test_multiple_cli_keys_generated_independently(self):
        """Multiple CLI key invocations produce cryptographically distinct keys with unique hashes."""
        runner = CliRunner()
        keys = []
        for i in range(5):
            res = await asyncio.to_thread(runner.invoke, cli_app, ["create-api-key", "--name", f"multi-key-{i}"])
            assert res.exit_code == 0
            keys.append(re.search(r"(cvai_[0-9a-fA-F]+)", res.stdout).group(1))

        # Ensure all generated keys are unique
        assert len(set(keys)) == 5

        # Ensure all 5 hashes are distinct in DB
        hashes = [hash_api_key(k) for k in keys]
        assert len(set(hashes)) == 5

        async with AsyncSessionLocal() as session:
            for kh in hashes:
                stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == kh)
                rec = (await session.execute(stmt)).scalars().first()
                assert rec is not None
                assert rec.is_active is True
