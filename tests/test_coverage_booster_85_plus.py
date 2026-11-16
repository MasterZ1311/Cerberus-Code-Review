"""
High-Density Branch Coverage Booster for Cerberus Code Review.
Systematically targets unexercised branches across:
- Review API (webhooks, replays, streaming tokens, SARIF/GitLab/SonarQube exports)
- Analytics API (/api/v1/analytics/repositories and /trends)
- API Key Lifecycle (/api/v1/keys CRUD, scopes, rotation, revoking)
- Cache Edge Cases (Redis L2 hit/miss, zlib compression, L1 eviction, prune, token consume)
- Schema Migrations Runner (fresh ledger, sequential execution, idempotency)
- GitHub App Event Handling & Payloads (parse_pull_request_event, build_pr_review_payload, build_github_check_run_payload, post_pr_review_to_github)
- Code Fixer Agent (TypeScript, Go, Rust, Python AST repairs, diff synthesis, comments)
- Typer CLI Subcommands (doctor, health, list-agents, key management, SARIF/SonarQube exports)
- Heuristic Engine Multi-Language Rules (TypeScript, Go, Rust, Python)
- App Lifespan (startup, connection warmup, shutdown)
"""

import asyncio
import base64
import io
import json
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from starlette.testclient import TestClient

from cerberus.agents.code_fixer_agent import CodeFixerAgent
from cerberus.api.app import app, lifespan
from cerberus.cli.main import (
    _render_zip_review_cli,
    apply_fix_command,
    create_api_key as cli_create_api_key,
    doctor as cli_doctor,
    export_gitlab_command,
    export_sarif_command,
    export_sonarqube_command,
    health as cli_health,
    list_agents as cli_list_agents,
    review as cli_review,
    revoke_api_key as cli_revoke_api_key,
)
from cerberus.config import settings
from cerberus.core.cache import CacheManager, cache_manager
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.github_app import (
    build_github_check_run_payload,
    build_pr_review_payload,
    parse_pull_request_event,
    post_pr_review_to_github,
)
from cerberus.core.migrations import (
    MIGRATIONS,
    _migrate_multitenancy_columns,
    run_migrations,
)
from cerberus.core.security import generate_webhook_signature
from cerberus.models.database import ApiKeyRecord, CodeReviewRecord, FindingRecord
from cerberus.models.schemas import (
    CodeReviewResponse,
    FeedbackRequest,
    Finding,
    GitHubPRReviewPayload,
    ReviewApproveRequest,
    SeverityEnum,
    SeveritySummary,
    ZipReviewResponse,
)
from cerberus.providers.heuristic_engine import HeuristicEngine


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


# ---------------------------------------------------------------------------
# 1. Analytics Endpoints Branch Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_analytics_repositories_empty_and_populated():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Empty repository metrics
        res_empty = await client.get("/api/v1/analytics/repositories/octocat/empty-repo", headers=headers)
        assert res_empty.status_code == 200
        data_empty = res_empty.json()
        assert data_empty["metrics"]["total_reviews"] == 0

        # 2. Populate records in DB for octocat/hello-world
        unique_rev_id = f"rev_analytics_{uuid.uuid4().hex[:8]}"
        async with AsyncSessionLocal() as session:
            rev1 = CodeReviewRecord(
                id=unique_rev_id,
                github_repo_owner="octocat",
                github_repo_name="hello-world",
                code_snippet="x = 1",
                language="python",
                overall_score=90.0,
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
            )
            session.add(rev1)

            f1 = FindingRecord(
                review_id=unique_rev_id,
                agent_name="security",
                severity="critical",
                category="security",
                title="SQLi Bug",
                message="SQL Injection detected",
                line_number=5,
                remediation="Use parameterized queries",
            )
            f2 = FindingRecord(
                review_id=unique_rev_id,
                agent_name="performance",
                severity="medium",
                category="performance",
                title="Slow loop",
                message="O(n^2) loop",
                line_number=12,
            )
            session.add_all([f1, f2])
            await session.commit()

        # 3. Query repository with date filtering (both valid and invalid to hit branches)
        from_d = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        to_d = datetime.now(timezone.utc).isoformat()
        res_pop = await client.get(
            f"/api/v1/analytics/repositories/octocat/hello-world?from_date={from_d}&to_date={to_d}",
            headers=headers,
        )
        assert res_pop.status_code == 200
        data_pop = res_pop.json()
        assert data_pop["metrics"]["total_reviews"] >= 1
        assert data_pop["metrics"]["vulnerabilities_prevented"] >= 1
        assert data_pop["metrics"]["performance_optimizations"] >= 1
        assert data_pop["metrics"]["findings_by_severity"]["critical"] >= 1

        # Date filter exception branches
        res_bad_dates = await client.get(
            "/api/v1/analytics/repositories/octocat/hello-world?from_date=invalid_date&to_date=invalid_date",
            headers=headers,
        )
        assert res_bad_dates.status_code == 200

        # 4. Global Trends
        res_trends = await client.get("/api/v1/analytics/trends?days=14", headers=headers)
        assert res_trends.status_code == 200
        trends_data = res_trends.json()
        assert trends_data["total_reviews"] >= 1
        assert trends_data["average_quality_score"] > 0


# ---------------------------------------------------------------------------
# 2. API Key Management Endpoints Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_keys_crud_lifecycle():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Key with expiration
        create_resp = await client.post(
            "/api/v1/keys",
            json={"name": "Integration Key", "scopes": ["review:read", "review:write"], "expires_in_days": 30},
            headers=headers,
        )
        assert create_resp.status_code == 201
        key_data = create_resp.json()
        key_id = key_data["id"]
        assert key_data["raw_key"].startswith("cvai_")
        assert key_data["prefix"] is not None

        # 2. List Keys
        list_resp = await client.get("/api/v1/keys", headers=headers)
        assert list_resp.status_code == 200
        keys_list = list_resp.json()
        assert any(k.get("id") == key_id for k in keys_list)

        # 3. Rotate Key
        rotate_resp = await client.post(f"/api/v1/keys/{key_id}/rotate", headers=headers)
        assert rotate_resp.status_code == 200
        rotated_data = rotate_resp.json()
        new_key_id = rotated_data["new_key_id"]
        assert new_key_id != key_id

        # 4. Revoke Key
        revoke_resp = await client.delete(f"/api/v1/keys/{new_key_id}", headers=headers)
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "revoked"

        # 5. Non-existent key error branches
        bad_revoke = await client.delete("/api/v1/keys/non_existent_id", headers=headers)
        assert bad_revoke.status_code == 404

        bad_rotate = await client.post("/api/v1/keys/non_existent_id/rotate", headers=headers)
        assert bad_rotate.status_code == 404


# ---------------------------------------------------------------------------
# 3. CacheManager Edge Cases & Redis Mock Integration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cache_manager_lru_and_error_handling():
    cm = CacheManager(max_items=3)

    # L1 In-Memory insertion & capacity eviction
    await cm.set("k1", {"val": 1}, ttl_seconds=3600)
    await cm.set("k2", {"val": 2}, ttl_seconds=3600)
    await cm.set("k3", {"val": 3}, ttl_seconds=3600)
    await cm.set("k4", {"val": 4}, ttl_seconds=3600)

    # k1 should have been evicted due to max_items=3
    assert await cm.get("k1") is None
    assert (await cm.get("k4"))["val"] == 4

    # Expired pruning
    cm._memory_cache["expired_key"] = {"data": {"val": 99}, "expires_at": 1000.0}
    pruned = cm.prune_expired()
    assert pruned >= 1
    assert "expired_key" not in cm._memory_cache

    # Invalidate
    assert cm.invalidate("k4") is True
    assert cm.invalidate("non_existent") is False

    # Invalidate async
    await cm.invalidate_async("k3")
    assert await cm.get("k3") is None

    # Clear
    cm.clear()
    assert len(cm._memory_cache) == 0

    # Stream token consume unknown
    consumed = await cm.consume_stream_token("st_unknown_token")
    assert consumed is None

    # Hit rate calculation
    assert cm.hit_rate == 0.0

    # Test with Mock Redis Client for L2 coverage
    mock_redis = AsyncMock()
    cm.redis_client = mock_redis

    # Redis SET & GET
    mock_redis.get.return_value = json.dumps({"redis_key": "redis_val"})
    val = await cm.get("test_redis_key")
    assert val == {"redis_key": "redis_val"}

    # Redis ZLIB compression test (>8192 bytes)
    large_payload = {"data": "x" * 10000}
    encoded = cm._encode_payload(large_payload)
    assert encoded.startswith("__GZ__")
    decoded = cm._decode_payload(encoded)
    assert decoded == large_payload

    # Redis stream token creation & consumption
    mock_redis.set.return_value = True
    token = await cm.create_stream_token("rev_123", "tenant_abc", ttl_seconds=60)
    assert token.startswith("st_")

    payload_json = json.dumps({"review_id": "rev_123", "tenant_id": "tenant_abc", "expires_at": time.time() + 60})
    mock_redis.get.return_value = payload_json
    mock_redis.getdel.return_value = payload_json
    mock_redis.eval.return_value = payload_json
    mock_redis.delete.return_value = 1
    consumed_data = await cm.consume_stream_token(token)
    assert consumed_data is not None
    assert consumed_data["review_id"] == "rev_123"

    # Close redis
    await cm.close()


# ---------------------------------------------------------------------------
# 4. Migrations Engine Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migrations_engine_execution():
    # 1. Run migrations on a fresh in-memory SQLite engine to verify ledger insertion
    fresh_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    applied_count = await run_migrations(fresh_engine)
    assert applied_count == len(MIGRATIONS)

    # 2. Second execution must be idempotent and apply 0
    applied_second = await run_migrations(fresh_engine)
    assert applied_second == 0

    # 3. Test multitenancy migration idempotency
    async with fresh_engine.begin() as conn:
        await _migrate_multitenancy_columns(conn)

    # 4. Test error rollback when a migration fails
    bad_migrations = list(MIGRATIONS) + [("999_broken", "Invalid SQL", "THIS IS AN INVALID SQL STATEMENT;")]
    with patch("cerberus.core.migrations.MIGRATIONS", bad_migrations):
        with pytest.raises(Exception):
            await run_migrations(fresh_engine)

    await fresh_engine.dispose()


# ---------------------------------------------------------------------------
# 5. GitHub App Event Parsing, Formatting & Outbound Post
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_github_app_parsing_and_formatting():
    # 1. Pull Request Event
    sample_pr_payload = {
        "action": "opened",
        "pull_request": {
            "number": 101,
            "title": "Fix memory leak in parser",
            "html_url": "https://github.com/org/repo/pull/101",
            "head": {"sha": "abc123def456"},
            "base": {"ref": "main"},
            "diff_url": "https://github.com/org/repo/pull/101.diff",
        },
        "repository": {
            "name": "repo",
            "owner": {"login": "org"},
            "full_name": "org/repo",
        },
    }

    pr_info = parse_pull_request_event(sample_pr_payload)
    assert pr_info is not None
    assert pr_info.pr_number == 101
    assert pr_info.head_sha == "abc123def456"

    # Non-PR event
    assert parse_pull_request_event({"action": "labeled"}) is None

    # 2. Format review markdown
    finding = Finding(
        category="security",
        severity=SeverityEnum.HIGH,
        title="Insecure Deserialization",
        message="pickle.loads on untrusted input",
        line=42,
        recommendation="Use json.loads instead",
    )
    resp = CodeReviewResponse(
        review_id="rev_gh_test",
        status="completed",
        created_at=datetime.now(timezone.utc).isoformat(),
        overall_score=72.0,
        summary="Security risks identified",
        critical_issues=[finding],
        warnings=[],
        suggestions=[],
        processing_time_ms=120,
    )

    # 3. Build Check Run Payload
    check_payload = build_github_check_run_payload(resp, pr_info=pr_info, filename="app.py")
    assert "cerberus" in check_payload["name"].lower()
    assert check_payload["conclusion"] in ("success", "failure", "neutral")
    assert "output" in check_payload

    # 4. PR Review comments payload
    payload = build_pr_review_payload(resp, pr_info=pr_info, filename="app.py")
    assert payload.event in ("REQUEST_CHANGES", "COMMENT", "APPROVE")
    assert len(payload.comments) >= 1
    assert payload.comments[0].path == "app.py"

    # 5. Outbound GitHub API Post with Mock
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock success
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        success, err = await post_pr_review_to_github(pr_info, payload, token="test_gh_token")
        assert success is True
        assert err is None

        # Mock failure
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable Entity"
        fail_ok, fail_err = await post_pr_review_to_github(pr_info, payload, token="test_gh_token")
        assert fail_ok is False
        assert "422" in str(fail_err)


# ---------------------------------------------------------------------------
# 6. Code Fixer Agent Multi-Language Repairs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_code_fixer_repairs():
    fixer = CodeFixerAgent()

    # 1. Python bare except
    code_py = "try:\n    x = 1\nexcept:\n    pass\n"
    f_py = Finding(
        category="quality",
        severity=SeverityEnum.MEDIUM,
        title="Bare Except",
        message="Bare except caught",
        line=3,
        suggestion="except Exception:",
    )
    repaired_py = fixer._apply_heuristic_fixes(code_py, [f_py], language="python")
    assert "except Exception:" in repaired_py

    # 2. TypeScript loose equality
    code_ts = "function compare(a: any, b: any) {\n    return a == b;\n}\n"
    f_ts = Finding(
        category="quality",
        severity=SeverityEnum.MEDIUM,
        title="Loose Equality",
        message="Use strict equality",
        line=2,
        suggestion="return a === b;",
    )
    repaired_ts = fixer._apply_language_specific_repairs(code_ts, language="typescript", findings=[f_ts])
    assert "===" in repaired_ts

    # 3. Go error check
    code_go = "package main\nfunc check() {\n    f, err := openFile()\n    if err != nil { panic(err) }\n}\n"
    f_go = Finding(
        category="quality",
        severity=SeverityEnum.HIGH,
        title="Error check",
        message="Return err instead of panic",
        line=4,
        suggestion="return err",
    )
    repaired_go = fixer._apply_language_specific_repairs(code_go, language="go", findings=[f_go])
    assert repaired_go is not None

    # 4. Rust panic / unwrap replacement
    code_rs = "fn main() {\n    let v = Some(1);\n    let x = v.unwrap();\n}\n"
    f_rs = Finding(
        category="quality",
        severity=SeverityEnum.HIGH,
        title="Unwrap safety",
        message="Use expect or match",
        line=3,
        suggestion='.expect("valid")',
    )
    repaired_rs = fixer._apply_language_specific_repairs(code_rs, language="rust", findings=[f_rs])
    assert ".expect" in repaired_rs

    # 5. Backward compatibility and edge cases
    assert fixer._verify_python_syntax("x = 1") is True
    assert fixer._verify_python_syntax("def incomplete(") is False
    assert fixer._generate_unified_diff("unchanged\n", "unchanged\n") == ""

    # 6. Synthesize fixes and generate patch
    synth = await fixer.synthesize_fixes(code_py, [f_py], filename="test.py", language="python")
    assert synth["syntax_valid"] is True

    patch_res = await fixer.generate_patch(code_py, [f_py], filename="test.py", language="python")
    assert "repaired_code" in patch_res

    # 7. Format review comments
    comments = fixer.generate_pr_review_comments([f_py], filename="test.py")
    assert len(comments) == 1
    assert comments[0]["path"] == "test.py"


# ---------------------------------------------------------------------------
# 7. Webhook Ingestion, Replay Protection, and Export Formats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_github_webhook_and_export_endpoints():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ping Event
        ping_payload = json.dumps({"zen": "Mind over matter", "hook_id": 42}).encode("utf-8")
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY
        ping_sig = generate_webhook_signature(ping_payload, secret)

        ping_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=ping_payload,
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": ping_sig,
                "Content-Type": "application/json",
            },
        )
        assert ping_resp.status_code == 200
        assert ping_resp.json()["status"] == "pong"

        # 2. Unsupported event
        bad_event = await client.post(
            "/api/v1/review/webhooks/github",
            content=ping_payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": ping_sig,
                "Content-Type": "application/json",
            },
        )
        assert bad_event.status_code == 400

        # 3. Missing Signature -> 401
        no_sig = await client.post(
            "/api/v1/review/webhooks/github",
            content=ping_payload,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert no_sig.status_code == 401

        # 4. Valid PR Webhook Review
        pr_event = {
            "action": "opened",
            "number": 55,
            "pull_request": {
                "number": 55,
                "title": "Add helper",
                "head": {"sha": "def789"},
                "base": {"ref": "main"},
            },
            "repository": {"name": "test-repo", "owner": {"login": "test-owner"}, "full_name": "test-owner/test-repo"},
            "code": "def calculate(a, b):\n    return a + b\n",
            "filename": "calc.py",
        }
        pr_bytes = json.dumps(pr_event).encode("utf-8")
        pr_sig = generate_webhook_signature(pr_bytes, secret)
        delivery_id = f"deliv_{uuid.uuid4().hex}"

        webhook_review_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=pr_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": pr_sig,
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert webhook_review_resp.status_code == 200
        wh_data = webhook_review_resp.json()
        assert wh_data["status"] == "completed"
        wh_review_id = wh_data["review_id"]

        # 5. Replay Protection: identical delivery id is detected and ignored
        replay_resp = await client.post(
            "/api/v1/review/webhooks/github",
            content=pr_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": pr_sig,
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert replay_resp.status_code == 200
        assert replay_resp.json()["reason"] == "duplicate_event"

        # 6. Export Review Formats (SARIF, GitLab, SonarQube)
        sarif_res = await client.get(f"/api/v1/review/{wh_review_id}/sarif", headers=headers)
        assert sarif_res.status_code == 200
        assert sarif_res.headers["content-type"].startswith("application/sarif+json")

        gitlab_res = await client.get(f"/api/v1/review/{wh_review_id}/gitlab", headers=headers)
        assert gitlab_res.status_code == 200

        sonar_res = await client.get(f"/api/v1/review/{wh_review_id}/sonarqube", headers=headers)
        assert sonar_res.status_code == 200

        # 7. Stream token generation
        st_res = await client.post(f"/api/v1/review/{wh_review_id}/stream-token", headers=headers)
        assert st_res.status_code == 200
        assert "stream_token" in st_res.json()


# ---------------------------------------------------------------------------
# 8. Feedback, Approval, Batch, and Zip Endpoints
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_feedback_and_approval():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a real review via POST /api/v1/review
        review_resp = await client.post(
            "/api/v1/review",
            json={"code": "def process_data(val):\n    return val * 2\n", "language": "python"},
            headers=headers,
        )
        assert review_resp.status_code == 200
        rev_id = review_resp.json()["review_id"]

        # 2. Submit Feedback
        fb_resp = await client.post(
            f"/api/v1/review/{rev_id}/feedback",
            json={"rating": 5, "is_helpful": True, "comments": "Accurate findings"},
            headers=headers,
        )
        assert fb_resp.status_code == 200
        assert fb_resp.json()["status"] == "success"

        # 3. Duplicate or updated feedback
        fb_resp2 = await client.post(
            f"/api/v1/review/{rev_id}/feedback",
            json={"rating": 4, "is_helpful": True, "comments": "Updated comment"},
            headers=headers,
        )
        assert fb_resp2.status_code == 200

        # 4. Approve Review
        appr_resp = await client.post(
            f"/api/v1/review/{rev_id}/approve",
            json={"reviewer": "lead_engineer", "reason": "Verified safe", "override_blocking": True},
            headers=headers,
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["status"] == "approved"

        # 5. Batch Review submission
        batch_resp = await client.post(
            "/api/v1/review/batch",
            json={
                "project_name": "microservices",
                "files": [
                    {"code": "x = 1\n", "filename": "a.py"},
                    {"code": "y = 2\n", "filename": "b.py"},
                ],
            },
            headers=headers,
        )
        assert batch_resp.status_code == 200
        batch_data = batch_resp.json()
        assert batch_data["total_files"] == 2
        assert len(batch_data["reviews"]) == 2

        # 6. ZIP Review Exports (SonarQube & GitLab for ZIP projects)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("module.py", "def add(a, b):\n    return a + b\n")
        b64_zip = base64.b64encode(buf.getvalue()).decode("utf-8")

        zip_review_res = await client.post(
            "/api/v1/review/zip-base64",
            json={"zip_base64": b64_zip, "project_name": "zip_test"},
            headers=headers,
        )
        assert zip_review_res.status_code == 200
        zip_id = zip_review_res.json()["review_id"]

        zip_sonar = await client.get(f"/api/v1/review/zip/{zip_id}/sonarqube", headers=headers)
        assert zip_sonar.status_code == 200

        zip_gl = await client.get(f"/api/v1/review/zip/{zip_id}/gitlab", headers=headers)
        assert zip_gl.status_code == 200

    # 7. WebSocket Live Streaming Connection
    with TestClient(app) as ws_client:
        with ws_client.websocket_connect(
            f"/api/v1/review/{rev_id}/ws",
            headers={"Authorization": f"Bearer {dev_key}"},
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "connected"
            assert msg["review_id"] == rev_id


# ---------------------------------------------------------------------------
# 9. CLI Typer Subcommands Coverage
# ---------------------------------------------------------------------------
def test_cli_subcommands(tmp_path: Path):
    # 1. System diagnostics and health
    cli_health()
    cli_doctor()
    cli_list_agents()

    # 2. Key creation and revocation
    cli_create_api_key(name="test_cli_runner_key")
    cli_revoke_api_key(name="test_cli_runner_key")

    # 3. Export subcommands
    code_file = tmp_path / "example.py"
    code_file.write_text("x = 1\ny = 2\n", encoding="utf-8")

    sarif_out = tmp_path / "out.sarif"
    export_sarif_command(file=code_file, output=sarif_out, language="python")

    sonar_out = tmp_path / "out_sonar.json"
    export_sonarqube_command(file=code_file, output=sonar_out, language="python")

    gl_out = tmp_path / "out_gl.json"
    export_gitlab_command(file=code_file, output=gl_out, language="python")

    # 4. Review CLI formats
    cli_review(snippet="x = 1", format="markdown", output=tmp_path / "rev.md")
    cli_review(snippet="x = 1", format="json", output=tmp_path / "rev.json")

    # 5. Display Zip Results rendering
    sample_zip_res = ZipReviewResponse(
        project_name="demo_proj",
        review_id="zip_rev_123",
        status="completed",
        created_at=datetime.now(timezone.utc).isoformat(),
        total_files_discovered=2,
        reviewed_files_count=2,
        skipped_files_count=0,
        total_lines_of_code=40,
        overall_project_score=85.0,
        severity_summary=SeveritySummary(critical=0, high=1, medium=2, low=1, info=0),
        language_distribution={"python": 2},
        file_reviews=[],
        top_critical_findings=[
            Finding(severity=SeverityEnum.HIGH, category="security", title="Secret", message="Hardcoded secret")
        ],
        collaborative_consensus={"pr_action": "MERGE_READY", "summary": "Ready to merge"},
    )
    _render_zip_review_cli(sample_zip_res, blocking=False)

    # 6. Apply Fix CLI command
    fix_file = tmp_path / "fixable.py"
    fix_file.write_text("try:\n    x = 1\nexcept:\n    pass\n", encoding="utf-8")
    apply_fix_command(file=fix_file, backup=True, language="python")
    assert (tmp_path / "fixable.py.bak").exists()


# ---------------------------------------------------------------------------
# 10. Multi-Language Heuristic Engine Analysis Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_heuristic_engine_multi_language_coverage():
    # TypeScript inspection
    ts_code = 'const data: any = eval("process.env");\nconsole.log(data == null);\n'
    findings_sec, _ = HeuristicEngine.analyze_security(ts_code, language="typescript", filename="service.ts")
    assert isinstance(findings_sec, list)

    findings_perf, _ = HeuristicEngine.analyze_performance(ts_code, language="typescript", filename="service.ts")
    assert isinstance(findings_perf, list)

    # Go inspection
    go_code = 'package main\nimport "fmt"\nfunc main() {\n    var x int\n    fmt.Println(x)\n}\n'
    findings_qual, _ = HeuristicEngine.analyze_quality(go_code, language="go", filename="main.go")
    assert isinstance(findings_qual, list)

    # Rust inspection
    rs_code = "fn compute(v: Option<i32>) -> i32 {\n    v.unwrap()\n}\n"
    findings_arch, _ = HeuristicEngine.analyze_architecture(rs_code, language="rust", filename="lib.rs")
    assert isinstance(findings_arch, list)


# ---------------------------------------------------------------------------
# 11. Review Upload, Validation, and Isolation Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_upload_and_validation_edge_cases():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload valid ZIP via multipart form
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("script.py", "def main():\n    print('ok')\n")
        zip_bytes = buf.getvalue()

        upload_res = await client.post(
            "/api/v1/review/upload-zip",
            files={"file": ("project.zip", zip_bytes, "application/zip")},
            data={"project_name": "multipart_test"},
            headers=headers,
        )
        assert upload_res.status_code == 200
        assert upload_res.json()["reviewed_files_count"] >= 1

        # 2. Base64 validation errors
        empty_b64 = await client.post("/api/v1/review/zip-base64", json={"zip_base64": ""}, headers=headers)
        assert empty_b64.status_code == 400

        bad_chars_b64 = await client.post(
            "/api/v1/review/zip-base64", json={"zip_base64": "!!!not_valid_b64!!!"}, headers=headers
        )
        assert bad_chars_b64.status_code == 400

        # 3. Not found errors for missing review IDs
        nf_zip = await client.get("/api/v1/review/zip/non_existent_zip_123", headers=headers)
        assert nf_zip.status_code == 404

        nf_rev = await client.get("/api/v1/review/non_existent_rev_123", headers=headers)
        assert nf_rev.status_code == 404

        nf_token = await client.post("/api/v1/review/non_existent_rev_123/stream-token", headers=headers)
        assert nf_token.status_code == 404
