"""
Validation Test Suite for Cerberus Perfect 10 Capabilities:
- OpenRouter provider & Circuit Breaker resilience
- Multi-language code repair (Python, TypeScript, Go, Rust)
- Pre-review & Post-review Orchestrator lifecycle hooks
- GitLab Code Quality & GitHub Check Runs integration
- Shannon entropy key validation & ReDoS mitigation
- CLI Automated Git Hooks installation/uninstallation
"""

from datetime import UTC, datetime

import pytest
from httpx import Response

from cerberus.agents.base import BaseAgent
from cerberus.agents.code_fixer_agent import CodeFixerAgent
from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.core.github_app import GitHubPullRequestInfo, build_github_check_run_payload
from cerberus.core.sarif import (
    review_response_to_gitlab_code_quality,
    zip_review_response_to_gitlab_code_quality,
)
from cerberus.core.security import calculate_shannon_entropy, verify_key_entropy
from cerberus.models.schemas import (
    AgentResult,
    CodeReviewRequest,
    CodeReviewResponse,
    Finding,
    ReviewConfig,
    SeverityEnum,
    SeveritySummary,
    ZipFileReview,
    ZipReviewResponse,
)
from cerberus.providers import get_llm_provider
from cerberus.providers.base import CircuitBreaker, CircuitState
from cerberus.providers.heuristic_engine import HeuristicEngine
from cerberus.providers.openrouter_provider import OpenRouterProvider


@pytest.mark.asyncio
async def test_openrouter_provider_and_resolution(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-abcdef1234567890abcdef123456")
    provider = get_llm_provider("openrouter")
    assert isinstance(provider, OpenRouterProvider)
    assert provider.effective_base_url == "https://openrouter.ai/api/v1"
    assert provider.effective_model == "anthropic/claude-3.5-sonnet"
    assert await provider.is_available() is True


def test_circuit_breaker_lifecycle():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Wait for recovery timeout
    import time

    time.sleep(0.25)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_provider_execute_request_with_retry_and_circuit_breaker():
    provider = OpenRouterProvider(api_key="sk-or-v1-testkey1234567890")
    attempts = 0

    async def transient_fail():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return Response(status_code=503)
        return Response(status_code=200, json={"choices": [{"message": {"content": "Resolved"}}]})

    res = await provider.execute_request_with_retry(transient_fail, max_retries=2, initial_backoff=0.01)
    assert res is not None
    assert res.status_code == 200
    assert attempts == 2
    assert provider.circuit_breaker.state == CircuitState.CLOSED


def test_shannon_entropy_calculation():
    # Low entropy (repetitive)
    low = "aaaaaaaaaaaaaaaa"
    assert calculate_shannon_entropy(low) == 0.0
    assert verify_key_entropy(low) is False

    # High entropy (random hex token)
    high = "cvai_a9b8c7d6e5f41234567890abcdef1234567890ab"
    entropy = calculate_shannon_entropy(high)
    assert entropy >= 3.5
    assert verify_key_entropy(high) is True


def test_heuristic_redos_bounding():
    huge_line = "a = " + "1 + " * 50000 + "2"
    safe = HeuristicEngine._safe_scan_line(huge_line, max_chars=5000)
    assert len(safe) == 5000


@pytest.mark.asyncio
async def test_multi_language_code_repair():
    fixer = CodeFixerAgent()

    # 1. Python bare except repair
    py_code = "try:\n    x = 1\nexcept:\n    pass\n"
    findings = [
        Finding(
            id="Q-1",
            category="quality",
            severity=SeverityEnum.MEDIUM,
            title="Bare Exception Clause",
            message="Avoid bare except clauses.",
            line=3,
            code_snippet="except:",
            suggestion="except Exception:",
        )
    ]
    repaired_py = fixer._apply_heuristic_fixes(py_code, findings, language="python")
    assert "except Exception:" in repaired_py
    assert fixer._verify_syntax(repaired_py, language="python") is True

    # 2. TypeScript loose equality repair
    ts_code = "function check(a: any, b: any) {\n  return a == b;\n}"
    ts_findings = [
        Finding(
            id="TS-1",
            category="quality",
            severity=SeverityEnum.MEDIUM,
            title="Use strict equality (===)",
            message="Avoid loose equality operator ==",
            line=2,
            code_snippet="return a == b;",
            suggestion="return a === b;",
        )
    ]
    repaired_ts = fixer._apply_heuristic_fixes(ts_code, ts_findings, language="typescript")
    assert "===" in repaired_ts
    assert fixer._verify_syntax(repaired_ts, language="typescript") is True


@pytest.mark.asyncio
async def test_orchestrator_lifecycle_hooks():
    orch = ReviewOrchestrator()
    pre_called = False
    post_called = False

    async def custom_pre_hook(req: CodeReviewRequest) -> CodeReviewRequest:
        nonlocal pre_called
        pre_called = True
        return req

    async def custom_post_hook(resp: CodeReviewResponse) -> CodeReviewResponse:
        nonlocal post_called
        post_called = True
        resp.summary = (resp.summary or "") + " [Verified by Custom Hook]"
        return resp

    orch.register_pre_hook(custom_pre_hook)
    orch.register_post_hook(custom_post_hook)

    req = CodeReviewRequest(
        code="def add(a, b):\n    return a + b\n", language="python", config=ReviewConfig(blocking_mode=False)
    )
    res = await orch.execute_review(req)

    assert pre_called is True
    assert post_called is True
    assert "[Verified by Custom Hook]" in (res.summary or "")


def test_gitlab_code_quality_export():
    now_iso = datetime.now(UTC).isoformat()
    review = CodeReviewResponse(
        review_id="rev_gl_123",
        status="completed",
        created_at=now_iso,
        overall_score=85.0,
        critical_issues=[
            Finding(
                id="SEC-1",
                category="injection",
                severity=SeverityEnum.CRITICAL,
                title="SQL Injection",
                message="Untrusted SQL concatenation",
                line=12,
                cwe_id="CWE-89",
            )
        ],
    )
    gl_report = review_response_to_gitlab_code_quality(review, filename="app/db.py")
    assert isinstance(gl_report, list)
    assert len(gl_report) == 1
    item = gl_report[0]
    assert item["check_name"] == "CWE-89"
    assert item["severity"] == "critical"
    assert item["location"]["path"] == "app/db.py"
    assert item["location"]["lines"]["begin"] == 12
    assert "fingerprint" in item


def test_github_check_run_payload_generation():
    now_iso = datetime.now(UTC).isoformat()
    review = CodeReviewResponse(
        review_id="rev_gh_456",
        status="completed",
        created_at=now_iso,
        overall_score=92.0,
        should_block=False,
        suggestions=[
            Finding(
                id="Q-1",
                category="quality",
                severity=SeverityEnum.LOW,
                title="Missing Docstring",
                message="Add docstring to helper function",
                line=5,
            )
        ],
    )
    pr_info = GitHubPullRequestInfo(
        action="opened",
        pr_number=42,
        title="Test Pull Request",
        repo_name="demo-repo",
        repo_owner="test-owner",
        full_name="test-owner/demo-repo",
        head_sha="a1b2c3d4",
    )
    check_payload = build_github_check_run_payload(review, pr_info, filename="src/helper.py")
    assert check_payload["name"] == "cerberus</> Autonomous Multi-Agent QA"
    assert check_payload["head_sha"] == "a1b2c3d4"
    assert check_payload["status"] == "completed"
    assert check_payload["conclusion"] == "success"
    assert len(check_payload["output"]["annotations"]) == 1
    ann = check_payload["output"]["annotations"][0]
    assert ann["path"] == "src/helper.py"
    assert ann["start_line"] == 5
    assert ann["annotation_level"] == "notice"


def test_cli_git_hooks_installation_and_uninstallation(tmp_path):
    from typer.testing import CliRunner

    from cerberus.cli.main import app

    runner = CliRunner()
    fake_git = tmp_path / ".git"
    fake_git.mkdir(parents=True)

    # 1. Install hooks
    result = runner.invoke(app, ["hooks", "install", "--repo-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (fake_git / "hooks" / "pre-commit").exists()
    assert (fake_git / "hooks" / "pre-push").exists()

    # 2. Uninstall hooks
    un_result = runner.invoke(app, ["hooks", "uninstall", "--repo-dir", str(tmp_path)])
    assert un_result.exit_code == 0
    assert not (fake_git / "hooks" / "pre-commit").exists()
    assert not (fake_git / "hooks" / "pre-push").exists()


@pytest.mark.asyncio
async def test_gitlab_api_endpoint():
    from httpx import ASGITransport, AsyncClient

    from cerberus.api.app import app
    from cerberus.api.v1.review import _store_review

    now_iso = datetime.now(UTC).isoformat()
    fake_review = CodeReviewResponse(
        review_id="rev_test_gl_api",
        status="completed",
        created_at=now_iso,
        overall_score=95.0,
        suggestions=[
            Finding(
                id="Q-1",
                category="quality",
                severity=SeverityEnum.LOW,
                title="PEP 8 naming convention",
                message="Variable should be snake_case",
                line=4,
            )
        ],
    )
    _store_review(fake_review.review_id, fake_review)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(
            f"/api/v1/review/{fake_review.review_id}/gitlab", headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["check_name"] == "Q-1"
        assert data[0]["severity"] == "info"


@pytest.mark.asyncio
async def test_openrouter_provider_generate_response_mocked(monkeypatch):
    provider = OpenRouterProvider(api_key="sk-or-v1-testkey1234567890")

    class MockAsyncClient:
        is_closed = False

        async def post(self, url, json=None, headers=None, timeout=None):
            return Response(
                status_code=200, json={"choices": [{"message": {"content": "OpenRouter refactored code successfully"}}]}
            )

        async def aclose(self):
            pass

    provider._client = MockAsyncClient()
    result = await provider.generate_response("System prompt", "User code")
    assert result == "OpenRouter refactored code successfully"


@pytest.mark.asyncio
async def test_db_execute_with_retry():
    from cerberus.core.database import execute_with_db_retry

    call_count = 0

    async def flaky_op():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("Transient DB lock")
        return "success"

    res = await execute_with_db_retry(flaky_op, max_retries=3, delay=0.01)
    assert res == "success"
    assert call_count == 2

    # Test max retries exceeded
    async def always_fails():
        raise ValueError("Fatal error")

    with pytest.raises(ValueError):
        await execute_with_db_retry(always_fails, max_retries=2, delay=0.01)


def test_zip_gitlab_code_quality_export():
    now_iso = datetime.now(UTC).isoformat()
    rev = CodeReviewResponse(
        review_id="rev_sub_1",
        status="completed",
        created_at=now_iso,
        overall_score=80.0,
        warnings=[
            Finding(
                id="PERF-1",
                category="performance",
                severity=SeverityEnum.HIGH,
                title="Quadratic Complexity",
                message="Nested loops O(N^2)",
                line=25,
            )
        ],
    )
    zip_resp = ZipReviewResponse(
        review_id="zip_rev_123",
        project_name="my_project",
        status="completed",
        created_at=now_iso,
        skipped_files_count=0,
        total_lines_of_code=50,
        severity_summary=SeveritySummary(critical=0, high=1, medium=0, low=0, info=0),
        overall_project_score=80.0,
        total_files_discovered=1,
        reviewed_files_count=1,
        file_reviews=[
            ZipFileReview(
                review_id="rev_sub_1",
                filename="main.py",
                file_path="src/main.py",
                language="python",
                lines_of_code=50,
                score=80.0,
                review=rev,
            )
        ],
    )
    gl_issues = zip_review_response_to_gitlab_code_quality(zip_resp)
    assert len(gl_issues) == 1
    assert gl_issues[0]["severity"] == "major"
    assert gl_issues[0]["location"]["path"] == "src/main.py"
    assert gl_issues[0]["location"]["lines"]["begin"] == 25


def test_dynamic_agent_registration():
    orch = ReviewOrchestrator()

    class CustomAgent(BaseAgent):
        name = "custom"
        version = "1.0.0"
        purpose = "Custom test agent"

        def get_capabilities(self):
            return ["Custom AST verification"]

        async def analyze(self, code, language="python", context=None):
            return AgentResult(agent_name="custom", score=100.0, execution_time_ms=5.0, status="completed", findings=[])

    orch.register_agent("custom", CustomAgent())
    agents = orch.list_agents()
    custom_entry = next((a for a in agents if a["id"] == "custom"), None)
    assert custom_entry is not None
    assert custom_entry["purpose"] == "Custom test agent"
    assert "Custom AST verification" in custom_entry["capabilities"]


def test_cli_formats_gitlab_and_check_run(tmp_path):
    from typer.testing import CliRunner

    from cerberus.cli.main import app

    runner = CliRunner()
    test_file = tmp_path / "sample.py"
    test_file.write_text("x = 1\n", encoding="utf-8")

    # 1. Test GitLab format
    res_gl = runner.invoke(app, ["review", str(test_file), "--format", "gitlab"])
    assert res_gl.exit_code == 0
    assert "[" in res_gl.stdout

    # 2. Test Check Run format
    res_cr = runner.invoke(app, ["review", str(test_file), "--format", "check-run"])
    assert res_cr.exit_code == 0
    assert "cerberus</> Autonomous Multi-Agent QA" in res_cr.stdout
