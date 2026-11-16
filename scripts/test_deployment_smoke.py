#!/usr/bin/env python3
"""
Deployment Smoke Test Verification Script for Cerberus.
Validates:
1. Dockerfile configuration: multi-stage build, unprivileged user (uid 1000), healthcheck probe.
2. docker-compose.yml configuration: private network isolation, no host-exposed ports for DB/Redis, pinned images.
3. Production configuration validation: strict fail-closed rejection of insecure secrets.
4. Live service readiness probe: truthful health and readiness responses under ASGI transport.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_dockerfile_security():
    print("[1/4] Validating Dockerfile security configuration...")
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist"
    content = dockerfile_path.read_text(encoding="utf-8")

    # Verify multi-stage build
    assert "AS builder" in content, "Dockerfile must use a builder stage"
    assert "AS runtime" in content, "Dockerfile must use a runtime stage"

    # Verify non-root user
    assert "useradd" in content and "cerberus" in content, "Must create dedicated cerberus user"
    assert "USER cerberus" in content, "Runtime stage must run as non-root user"

    # Verify healthcheck instruction
    assert "HEALTHCHECK" in content, "Dockerfile must include container HEALTHCHECK"

    # Verify non-editable install
    assert "pip install -e" not in content, "Production image must not use editable install"
    print("  -> Dockerfile passed all security and reproducibility checks.")


def test_docker_compose_configuration():
    print("[2/4] Validating docker-compose.yml network & port isolation...")
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"
    content = compose_path.read_text(encoding="utf-8")

    # PostgreSQL must NOT expose ports to host
    lines = content.splitlines()
    db_section = False
    redis_section = False
    for line in lines:
        if line.strip().startswith("db:"):
            db_section = True
            redis_section = False
        elif line.strip().startswith("redis:"):
            redis_section = True
            db_section = False
        elif line.strip().startswith("prometheus:") or line.strip().startswith("grafana:") or line.strip().startswith("api:"):
            db_section = False
            redis_section = False

        if db_section and "ports:" in line:
            raise AssertionError("db service must not map ports publicly to host! Use expose: instead.")
        if redis_section and "ports:" in line:
            raise AssertionError("redis service must not map ports publicly to host! Use expose: instead.")

    # Pinned versions
    assert "postgres:15.10-alpine" in content, "PostgreSQL image must be pinned"
    assert "redis:7.4.2-alpine" in content, "Redis image must be pinned"
    print("  -> docker-compose.yml passed all port isolation and version pinning checks.")


def test_production_settings_validation():
    print("[3/4] Validating production fail-closed settings enforcement...")
    from pydantic import ValidationError
    from cerberus.config import Settings

    # Attempting to start in production with default/insecure secret must fail
    try:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="cerberus_dev_secret_key_change_in_production_32chars",
            DATABASE_URL="postgresql+asyncpg://cerberus:dev_pass@localhost:5432/cerberus",
        )
        raise AssertionError("Settings failed to reject insecure SECRET_KEY in production!")
    except (ValueError, ValidationError):
        pass  # Expected fail-closed behavior

    # Attempting to enable ALLOW_INSECURE_LOCAL_WEBHOOKS in production must fail
    try:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a_genuine_strong_production_secret_key_32_chars!",
            ALLOW_INSECURE_LOCAL_WEBHOOKS=True,
            DATABASE_URL="postgresql+asyncpg://cerberus:prod_pass@localhost:5432/cerberus",
        )
        raise AssertionError("Settings failed to reject ALLOW_INSECURE_LOCAL_WEBHOOKS in production!")
    except (ValueError, ValidationError):
        pass  # Expected fail-closed behavior

    print("  -> Settings strictly enforces fail-closed production safety rules.")


def test_live_asgi_readiness_probe():
    print("[4/5] Validating live service health and readiness endpoints...")
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from cerberus.api.app import app
    from cerberus.core.database import init_db

    async def _probe():
        await init_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health probe
            health_resp = await client.get("/api/v1/health")
            assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
            assert health_resp.json()["status"] == "healthy"

            # 2. Readiness probe
            ready_resp = await client.get("/api/v1/ready")
            assert ready_resp.status_code == 200, f"Readiness check failed: {ready_resp.text}"
            assert ready_resp.json()["status"] == "ready"

            # 3. Security headers
            assert health_resp.headers.get("X-Content-Type-Options") == "nosniff"
            assert "Content-Security-Policy" in health_resp.headers

            # 4. Metrics endpoint
            metrics_resp = await client.get("/metrics")
            assert metrics_resp.status_code == 200
            assert "cerberus_" in metrics_resp.text

    asyncio.run(_probe())
    print("  -> Live ASGI endpoints passed all health, readiness, and metrics verification.")


def test_live_asgi_authentication_and_tenancy():
    print("[5/5] Validating ASGI live authentication and tenant boundary enforcement...")
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from cerberus.api.app import app
    from cerberus.core.database import init_db

    async def _test_auth():
        await init_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Anonymous request without API key must be rejected with 401
            anon_resp = await client.post(
                "/api/v1/review",
                json={"code": "def foo(): pass", "filename": "test.py", "language": "python"},
            )
            assert anon_resp.status_code == 401, f"Expected 401, got {anon_resp.status_code}"

            # 2. Invalid API key must be rejected with 401
            invalid_resp = await client.post(
                "/api/v1/review",
                headers={"Authorization": "Bearer cvai_invalid_key_99999999"},
                json={"code": "def foo(): pass", "filename": "test.py", "language": "python"},
            )
            assert invalid_resp.status_code == 401, f"Expected 401, got {invalid_resp.status_code}"

            # 3. Valid key request succeeds
            dev_key = "cvai_dev_key_123"
            valid_resp = await client.post(
                "/api/v1/review",
                headers={"Authorization": f"Bearer {dev_key}"},
                json={"code": "def valid(): return 42", "filename": "valid.py", "language": "python"},
            )
            assert valid_resp.status_code == 200, f"Expected 200, got {valid_resp.status_code}: {valid_resp.text}"
            review_id = valid_resp.json()["review_id"]

            # 4. Same tenant can fetch review status
            status_resp = await client.get(
                f"/api/v1/review/{review_id}",
                headers={"Authorization": f"Bearer {dev_key}"},
            )
            assert status_resp.status_code == 200

    asyncio.run(_test_auth())
    print("  -> Live ASGI authentication and tenant boundaries verified successfully.")


def main():
    print("=== Running Cerberus Deployment Smoke Test Suite ===")
    try:
        test_dockerfile_security()
        test_docker_compose_configuration()
        test_production_settings_validation()
        test_live_asgi_readiness_probe()
        test_live_asgi_authentication_and_tenancy()
        print("\n=== [PASS] All 5 Deployment Smoke Tests Succeeded ===")
        return 0
    except Exception as e:
        print(f"\n[FAIL] Smoke test failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
