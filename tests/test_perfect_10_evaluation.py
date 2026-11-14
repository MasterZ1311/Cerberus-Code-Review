"""
Test Suite for 10/10 Capabilities:
- Multi-Language SyntaxVerifier (Python AST, JSON, YAML, JS/TS/Go delimiter verification)
- Cryptographic Timing-Safe Comparisons and Webhook HMAC Signatures
- Granular Role-Based Access Control (RBAC) Scoped Dependencies
- OASIS SARIF v2.1.0 Serializer & GitHub Code Scanning Export
- Native GitHub Webhook Receiver with X-Hub-Signature-256
- Automated In-Place Code Repair CLI ('apply-fix')
- Multi-Agent Domain Trade-off Arbitration Matrix & GitHub Review Comments
"""

import json
import os
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from typer.testing import CliRunner
from cerberus.api.app import app
from cerberus.cli.main import app as cli_app
from cerberus.config import settings
from cerberus.core.sarif import review_response_to_sarif, zip_review_response_to_sarif
from cerberus.core.security import generate_webhook_signature, timing_safe_compare, verify_github_signature
from cerberus.core.syntax_verifier import SyntaxVerifier
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse, Finding, SeverityEnum


runner = CliRunner()


def test_syntax_verifier_python():
    """Verify SyntaxVerifier parses valid Python and detects syntax errors."""
    valid, err = SyntaxVerifier.verify("def hello(): return 42", "python")
    assert valid is True
    assert err is None

    invalid, err = SyntaxVerifier.verify("def invalid(: return", "python")
    assert invalid is False
    assert "SyntaxError" in err


def test_syntax_verifier_json_and_yaml():
    """Verify SyntaxVerifier handles JSON and YAML payloads."""
    valid_json, _ = SyntaxVerifier.verify('{"status": "ok", "count": 10}', "json")
    assert valid_json is True

    invalid_json, _ = SyntaxVerifier.verify('{"status": "ok",', "json")
    assert invalid_json is False

    valid_yaml, _ = SyntaxVerifier.verify("version: '3.8'\nservices:\n  web:\n    image: nginx", "yaml")
    assert valid_yaml is True


def test_syntax_verifier_c_family_delimiters():
    """Verify balanced delimiter checks for JavaScript, TypeScript, Go, Java, and C++."""
    valid_js = """
    function compute(a, b) {
        if (a > b) {
            return [a, b];
        }
        return `Value: ${a}`;
    }
    """
    valid, err = SyntaxVerifier.verify(valid_js, "javascript")
    assert valid is True
    assert err is None

    invalid_js = "function broken(a, b) { if (a > b) { return [a, b]; } "  # Unclosed brace
    invalid_delim, err_delim = SyntaxVerifier.verify_balanced_delimiters(invalid_js)
    assert invalid_delim is False
    assert "Unclosed opening delimiter" in err_delim

    invalid_ts, err_ts = SyntaxVerifier.verify(invalid_js, "typescript")
    assert invalid_ts is False
    assert "SyntaxError" in err_ts or "delimiter" in err_ts.lower()


def test_timing_safe_compare():
    """Verify timing-safe comparison helper."""
    assert timing_safe_compare("secret_token_123", "secret_token_123") is True
    assert timing_safe_compare("secret_token_123", "secret_token_999") is False
    assert timing_safe_compare(None, "secret") is False


def test_github_webhook_hmac_signatures():
    """Verify GitHub webhook HMAC SHA-256 signature generation and verification."""
    secret = "cerberus_webhook_shared_secret_994821"
    payload = b'{"action": "opened", "pull_request": {"title": "Test PR"}}'

    sig = generate_webhook_signature(payload, secret)
    assert sig.startswith("sha256=")

    assert verify_github_signature(payload, sig, secret) is True
    assert verify_github_signature(payload, "sha256=invalidhash", secret) is False
    assert verify_github_signature(payload, None, secret) is False


def test_sarif_v2_1_0_generation():
    """Verify OASIS SARIF v2.1.0 output complies with schema."""
    findings = [
        Finding(
            id="SEC-SQLI-01",
            severity=SeverityEnum.CRITICAL,
            category="injection",
            title="SQL Injection Vulnerability",
            message="Unescaped SQL query string concatenation detected.",
            line=4,
            code_snippet='db.execute("SELECT * FROM users WHERE id = " + user_id)',
            recommendation="Use parameterized query.",
            suggestion='db.execute("SELECT * FROM users WHERE id = :id", {"id": user_id})',
            cwe_id="CWE-89",
            cvss_score=9.8
        )
    ]
    resp = CodeReviewResponse(
        review_id="rev_test_sarif_123",
        status="completed",
        created_at="2026-11-14T21:00:00Z",
        overall_score=60.0,
        critical_issues=findings
    )

    sarif = review_response_to_sarif(resp, filename="database.py")
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].startswith("https://raw.githubusercontent.com/oasis-tcs/sarif-spec")
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "cerberus</>"
    assert len(run["results"]) == 1
    assert run["results"][0]["ruleId"] == "CWE-89"
    assert run["results"][0]["level"] == "error"
    assert run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "database.py"


@pytest.mark.asyncio
async def test_sarif_endpoint():
    """Verify GET /api/v1/review/{review_id}/sarif endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # First submit review
        headers = {"Authorization": "Bearer cvai_dev_key_123"}
        review_res = await client.post(
            "/api/v1/review",
            headers=headers,
            json={"code": "import os; os.system('echo hi')", "language": "python"}
        )
        assert review_res.status_code == 200
        rev_id = review_res.json()["review_id"]

        # Fetch SARIF report
        sarif_res = await client.get(f"/api/v1/review/{rev_id}/sarif", headers=headers)
        assert sarif_res.status_code == 200
        data = sarif_res.json()
        assert data["version"] == "2.1.0"
        assert len(data["runs"]) > 0


@pytest.mark.asyncio
async def test_github_webhook_endpoint():
    """Verify POST /api/v1/review/webhooks/github endpoint with signature."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "action": "opened",
            "pull_request": {
                "title": "Fix security vulnerability",
                "body": "import os; os.system('ping 8.8.8.8')"
            },
            "number": 42
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        secret = settings.SECRET_KEY
        sig = generate_webhook_signature(body_bytes, secret)

        headers = {
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }

        res = await client.post("/api/v1/review/webhooks/github", headers=headers, content=body_bytes)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["event"] == "pull_request"
        assert "review_id" in data
        assert "github_review_comments" in data


def test_cli_apply_fix(tmp_path):
    """Verify CLI 'apply-fix' command safely repairs files and creates backups."""
    test_file = tmp_path / "vulnerable_script.py"
    test_file.write_text("import os; os.system('ping ' + host)\n", encoding="utf-8")

    result = runner.invoke(cli_app, ["apply-fix", "--file", str(test_file), "--backup"])
    assert result.exit_code == 0
    assert "Repairs successfully applied" in result.stdout
    # Verify backup exists
    backup_file = test_file.with_suffix(test_file.suffix + ".bak")
    assert backup_file.exists()


def test_cli_export_sarif(tmp_path):
    """Verify CLI 'export-sarif' command."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def multiply(a, b): return a * b\n", encoding="utf-8")
    output_sarif = tmp_path / "output.sarif"

    result = runner.invoke(cli_app, ["export-sarif", "--file", str(test_file), "--output", str(output_sarif)])
    assert result.exit_code == 0
    assert output_sarif.exists()
    sarif_data = json.loads(output_sarif.read_text(encoding="utf-8"))
    assert sarif_data["version"] == "2.1.0"
