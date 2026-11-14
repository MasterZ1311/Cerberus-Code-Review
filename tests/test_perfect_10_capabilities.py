"""
Comprehensive Verification Test Suite for Perfect 10 Capabilities:
- Security Headers & Log Sanitization Middleware
- Heuristic AST Caching & New CWE Detection (CWE-94, CWE-295, CWE-330)
- Human-in-the-Loop PR Approval Gate (/approve)
- Status-Only Gating Endpoint (/status)
- Server-Sent Events (SSE) Stream (/stream)
- Database Zero-Downtime Schema Migrations
- CLI API Key Management (list & revoke)
- Configuration & Feedback Endpoints
"""

import base64
import io
import json
import logging
import zipfile
import pytest
from httpx import AsyncClient, ASGITransport
from typer.testing import CliRunner
from cerberus.api.app import app
from cerberus.cli.main import app as cli_app
from cerberus.core.database import engine
from cerberus.core.migrations import run_migrations
from cerberus.core.security import generate_api_key
from cerberus.core.security_headers import SensitiveDataMaskingFilter
from cerberus.providers.heuristic_engine import HeuristicEngine


@pytest.mark.asyncio
async def test_security_headers_middleware():
    """Verify that all enterprise security headers are present on HTTP responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")
        assert "default-src 'self'" in resp.headers.get("Content-Security-Policy", "")
        assert "camera=()" in resp.headers.get("Permissions-Policy", "")


def test_sensitive_data_log_masking():
    """Verify that log filter masks sensitive API keys, OpenAI keys, and Bearer tokens."""
    log_filter = SensitiveDataMaskingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Authenticated user with cvai_1234567890abcdef and token sk-1234567890abcdef123456 and Bearer secret_token_xyz",
        args=(),
        exc_info=None
    )
    result = log_filter.filter(record)
    assert result is True
    assert "cvai_1234567890abcdef" not in record.msg
    assert "cvai_***REDACTED***" in record.msg
    assert "sk-1234567890abcdef123456" not in record.msg
    assert "sk-***REDACTED***" in record.msg
    assert "secret_token_xyz" not in record.msg
    assert "Bearer ***REDACTED***" in record.msg


def test_heuristic_ast_cache_performance():
    """Verify that HeuristicEngine caches parsed AST and returns identical trees."""
    code = "def sample(x):\n    return x * 2\n"
    tree1 = HeuristicEngine.get_parsed_ast(code)
    tree2 = HeuristicEngine.get_parsed_ast(code)
    assert tree1 is not None
    assert tree1 is tree2  # Identical reference from cache


def test_heuristic_new_security_rules():
    """Verify detection of eval/exec code injection, verify=False, and weak PRNG for tokens."""
    code = """
import random
import requests

def run_user_code(user_input):
    eval(user_input)
    resp = requests.get("https://internal.service/api", verify=False)
    auth_token = random.random()
    return resp.text
"""
    findings, score = HeuristicEngine.analyze_security(code, language="python")
    categories = [f.category for f in findings]
    cwes = [f.cwe_id for f in findings]

    assert "CWE-94" in cwes  # Code injection
    assert "CWE-295" in cwes  # Disabled TLS
    assert "CWE-330" in cwes  # Weak PRNG
    assert score < 50.0


@pytest.mark.asyncio
async def test_review_status_endpoint():
    """Verify the lightweight /status endpoint returns quick gating metrics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Create a review
        sub_resp = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"code": "def hello():\n    return 'world'\n"}
        )
        assert sub_resp.status_code == 200
        review_id = sub_resp.json()["review_id"]

        # 2. Query status endpoint
        status_resp = await client.get(
            f"/api/v1/review/{review_id}/status",
            headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["review_id"] == review_id
        assert data["status"] == "completed"
        assert "should_block" in data
        assert "overall_score" in data


@pytest.mark.asyncio
async def test_review_approve_endpoint():
    """Verify human-in-the-loop approval gate overrides blocking and updates status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Create a review that blocks
        sub_resp = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={
                "code": "import os; os.system('rm -rf /')",
                "config": {"blocking_mode": True}
            }
        )
        assert sub_resp.status_code == 200
        review_id = sub_resp.json()["review_id"]
        assert sub_resp.json()["should_block"] is True

        # 2. Approve with human override
        appr_resp = await client.post(
            f"/api/v1/review/{review_id}/approve",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={
                "reviewer": "lead_security_architect",
                "reason": "False positive in deployment container setup",
                "override_blocking": True
            }
        )
        assert appr_resp.status_code == 200
        appr_data = appr_resp.json()
        assert appr_data["status"] == "approved"
        assert appr_data["approved_by"] == "lead_security_architect"
        assert appr_data["override_applied"] is True

        # 3. Check status is now approved and should_block is False
        check_resp = await client.get(
            f"/api/v1/review/{review_id}",
            headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert check_resp.status_code == 200
        assert check_resp.json()["status"] == "approved"
        assert check_resp.json()["should_block"] is False


@pytest.mark.asyncio
async def test_review_stream_sse_endpoint():
    """Verify Server-Sent Events stream establishes and emits completion event."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a review first
        sub_resp = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"code": "def square(n): return n * n\n"}
        )
        review_id = sub_resp.json()["review_id"]

        # Connect to SSE stream
        sse_resp = await client.get(f"/api/v1/review/{review_id}/stream?token=cvai_dev_key_123")
        assert sse_resp.status_code == 200
        assert "text/event-stream" in sse_resp.headers.get("content-type", "")
        body = sse_resp.text
        assert "event: connected" in body
        assert "event: completed" in body


@pytest.mark.asyncio
async def test_runtime_config_update_endpoint():
    """Verify runtime configuration PUT endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Get configuration
        get_resp = await client.get("/api/v1/config", headers={"Authorization": "Bearer cvai_dev_key_123"})
        assert get_resp.status_code == 200
        assert "enabled_agents" in get_resp.json()

        # Update configuration
        put_resp = await client.put(
            "/api/v1/config",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"severity_threshold": "high", "blocking_mode": True}
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_review_feedback_submission():
    """Verify review developer feedback persistence endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        sub_resp = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"code": "x = 42\n"}
        )
        review_id = sub_resp.json()["review_id"]

        fb_resp = await client.post(
            f"/api/v1/review/{review_id}/feedback",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={
                "rating": 5,
                "is_helpful": True,
                "comments": "Accurate findings and great diff!"
            }
        )
        assert fb_resp.status_code == 200
        assert fb_resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_database_migrations_idempotent():
    """Verify schema migrations run cleanly and are idempotent."""
    count = await run_migrations(engine)
    # Re-running immediately should apply 0 new migrations
    second_count = await run_migrations(engine)
    assert second_count == 0


def test_cli_keys_commands():
    """Verify CLI list-api-keys and revoke-api-key commands."""
    runner = CliRunner()
    
    # 1. Create a key to test
    create_res = runner.invoke(cli_app, ["create-api-key", "--name", "test-cli-key-10"])
    assert create_res.exit_code == 0
    assert "API Key created successfully" in create_res.stdout

    # 2. List keys
    list_res = runner.invoke(cli_app, ["list-api-keys"])
    assert list_res.exit_code == 0
    assert "test-cli-key-10" in list_res.stdout

    # 3. Revoke key
    revoke_res = runner.invoke(cli_app, ["revoke-api-key", "test-cli-key-10"])
    assert revoke_res.exit_code == 0
    assert "successfully revoked" in revoke_res.stdout


@pytest.mark.asyncio
async def test_review_zip_base64_endpoint():
    """Verify ZIP base64 review endpoint analyzes multi-file archives."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("calc.py", "def add(a, b):\n    return a + b\n")
        zf.writestr("helper.py", "def multiply(x, y):\n    return x * y\n")
    zip_bytes = buf.getvalue()
    b64_content = base64.b64encode(zip_bytes).decode("ascii")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/review/zip-base64",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={
                "zip_base64": b64_content,
                "project_name": "code_package",
                "blocking": False
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert data["total_files_discovered"] == 2
        assert len(data["file_reviews"]) == 2


@pytest.mark.asyncio
async def test_review_zip_multipart_endpoint():
    """Verify multipart ZIP upload review endpoint."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("module.py", "def test():\n    return 'verified'\n")
    zip_bytes = buf.getvalue()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        files = {"file": ("project.zip", zip_bytes, "application/zip")}
        resp = await client.post(
            "/api/v1/review/zip",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            files=files
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert data["total_files_discovered"] == 1
        assert len(data["file_reviews"]) == 1


@pytest.mark.asyncio
async def test_review_approve_404_and_headers():
    """Verify that 404 responses from approve endpoint still retain security headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/review/non_existent_id_9999/approve",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={
                "reviewer": "qa_lead",
                "reason": "testing 404"
            }
        )
        assert resp.status_code == 404
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_provider_factory_resolution():
    """Verify provider initialization and fallback logic in cerberus.providers."""
    from cerberus.providers import get_llm_provider, resolve_auto_provider
    from cerberus.providers.base import BaseLLMProvider
    
    # Resolves to heuristic when no API keys are present in CI/offline environment
    auto_prov = resolve_auto_provider()
    assert auto_prov in ("heuristic", "groq", "openai", "anthropic", "gemini", "deepseek", "watsonx")

    # Offline/heuristic provider returns None so agents route to HeuristicEngine
    prov = get_llm_provider("heuristic")
    assert prov is None

    # Unknown provider gracefully falls back to None (HeuristicEngine)
    unknown = get_llm_provider("unknown_provider_xyz")
    assert unknown is None


@pytest.mark.asyncio
async def test_web_dashboard_ui_ux_features():
    """Verify that the embedded web dashboard serves all modern UI/UX components."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        content = resp.text
        # Visual & Design System Tokens
        assert "data-theme=\"dark\"" in content
        assert "--vsc-bg" in content
        assert "--vsc-diff-add-bg" in content
        # Interactive Controls & Accessibility
        assert "role=\"tablist\"" in content
        assert "role=\"tab\"" in content
        assert "role=\"alert\"" in content
        # Progressive Loading & Feedback States
        assert "loading-stepper-card" in content
        assert "skeleton-card" in content
        assert "toast-container" in content
        # Human-in-the-Loop PR Approval & Modals
        assert "approval-modal" in content
        assert "agents-modal" in content
        assert "apikey-modal" in content
        # VS Code Code Framing & Syntax Highlighter
        assert "vscode-code-frame" in content
        assert "editor-gutter" in content
        assert "highlightVSCode" in content




