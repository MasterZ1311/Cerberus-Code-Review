import asyncio
import time
import unittest.mock
from datetime import UTC, datetime
from typing import Optional

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app
from cerberus.config import settings
from cerberus.core.github_app import GitHubPullRequestInfo, post_check_run_to_github
from cerberus.core.syntax_verifier import SyntaxVerifier
from cerberus.providers.base import BaseLLMProvider, CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# 1. SSE Stream endpoint & Batch Limits Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_upload_sse_and_limits():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a fresh review to stream
        rev_create = await client.post(
            "/api/v1/review",
            json={"code": "x = 42\n", "language": "python"},
            headers=headers,
        )
        assert rev_create.status_code == 200
        rev_data = rev_create.json()
        target_rev_id = rev_data["review_id"]

        # Generate stream token
        tok_res = await client.post(f"/api/v1/review/{target_rev_id}/stream-token", headers=headers)
        assert tok_res.status_code == 200
        stream_tok = tok_res.json()["stream_token"]

        # Test SSE with stream_token
        sse_res = await client.get(f"/api/v1/review/{target_rev_id}/stream?stream_token={stream_tok}")
        assert sse_res.status_code == 200
        assert "text/event-stream" in sse_res.headers.get("content-type", "")

        # Test SSE with already consumed / invalid stream token -> 401
        sse_bad_tok = await client.get(f"/api/v1/review/{target_rev_id}/stream?stream_token={stream_tok}")
        assert sse_bad_tok.status_code == 401

        # Test SSE with Bearer auth header
        sse_bearer = await client.get(f"/api/v1/review/{target_rev_id}/stream", headers=headers)
        assert sse_bearer.status_code == 200

        # Test SSE with unauthenticated -> 401
        sse_no_auth = await client.get(f"/api/v1/review/{target_rev_id}/stream")
        assert sse_no_auth.status_code == 401

        # Batch review exceeding max batch size -> 400
        overflow_files = [
            {"code": f"x_{i} = {i}\n", "filename": f"f_{i}.py"} for i in range(settings.MAX_BATCH_SIZE + 2)
        ]
        batch_overflow = await client.post(
            "/api/v1/review/batch",
            json={"project_name": "overflow", "files": overflow_files},
            headers=headers,
        )
        assert batch_overflow.status_code == 400
        assert "exceeds maximum allowed" in batch_overflow.json()["detail"]

        # Upload ZIP with non-zip extension -> 400
        bad_ext_res = await client.post(
            "/api/v1/review/upload-zip",
            files={"file": ("project.tar.gz", b"binarycontent", "application/gzip")},
            headers=headers,
        )
        assert bad_ext_res.status_code == 400
        assert ".zip extension" in bad_ext_res.json()["detail"]


# ---------------------------------------------------------------------------
# 2. GitHub Checks API & Outbound Posting Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_github_checks_api_posting():
    pr_info = GitHubPullRequestInfo(
        repo_owner="test-org",
        repo_name="test-repo",
        full_name="test-org/test-repo",
        pr_number=101,
        head_sha="abcd1234efgh5678",
        branch="feature",
        title="Sample PR",
        action="opened",
    )
    payload = {"name": "cerberus", "head_sha": pr_info.head_sha, "status": "completed"}

    # 1. No token -> fails gracefully
    orig_token = settings.GITHUB_TOKEN
    try:
        settings.GITHUB_TOKEN = ""
        success, err = await post_check_run_to_github(pr_info, payload, token=None)
        assert success is False
        assert "not configured" in str(err)
    finally:
        settings.GITHUB_TOKEN = orig_token

    # 2. Mock 201 Created from GitHub Checks API
    with unittest.mock.patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 201
        mock_resp.text = '{"id": 12345}'
        mock_post.return_value = mock_resp

        success, err = await post_check_run_to_github(pr_info, payload, token="ghp_mock_token_123")
        assert success is True
        assert err is None

    # 3. Mock 500 Server Error from GitHub Checks API
    with unittest.mock.patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        success, err = await post_check_run_to_github(pr_info, payload, token="ghp_mock_token_123")
        assert success is False
        assert "GitHub Checks API error (500)" in str(err)

    # 4. Mock Network / Connection Exception
    with unittest.mock.patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        success, err = await post_check_run_to_github(pr_info, payload, token="ghp_mock_token_123")
        assert success is False
        assert "Failed to contact GitHub Checks API" in str(err)


# ---------------------------------------------------------------------------
# 3. LLM Provider Base, Circuit Breaker & Retry Resilience
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_circuit_breaker_and_provider_retry():
    # 1. CircuitBreaker state transitions
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Wait for recovery timeout
    time.sleep(0.25)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    # 2. BaseLLMProvider concrete mock
    class MockProvider(BaseLLMProvider):
        async def is_available(self) -> bool:
            return True

        async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
            return "mocked response"

    prov = MockProvider()
    client = await prov.get_client()
    assert isinstance(client, httpx.AsyncClient)
    await prov.close()
    assert prov._client is None

    # 3. execute_request_with_retry: Open breaker returns None
    prov.circuit_breaker.state = CircuitState.OPEN
    prov.circuit_breaker.last_failure_time = time.time()

    async def noop_coro():
        return None

    res = await prov.execute_request_with_retry(noop_coro)
    assert res is None
    prov.circuit_breaker.state = CircuitState.CLOSED

    # 4. execute_request_with_retry: Success with HTTP 200
    mock_resp_200 = unittest.mock.MagicMock(status_code=200)

    async def success_200_coro():
        return mock_resp_200

    res_200 = await prov.execute_request_with_retry(success_200_coro, max_retries=1, initial_backoff=0.01)
    assert res_200 == mock_resp_200

    # 5. execute_request_with_retry: Transient 429 then 200
    call_counts = 0

    async def transient_429_fn():
        nonlocal call_counts
        call_counts += 1
        if call_counts == 1:
            return unittest.mock.MagicMock(status_code=429)
        return unittest.mock.MagicMock(status_code=200)

    res_retry = await prov.execute_request_with_retry(transient_429_fn, max_retries=2, initial_backoff=0.01)
    assert res_retry.status_code == 200
    assert call_counts == 2

    # 6. execute_request_with_retry: Network Timeout
    async def timeout_fn():
        raise httpx.TimeoutException("Timeout")

    res_timeout = await prov.execute_request_with_retry(timeout_fn, max_retries=1, initial_backoff=0.01)
    assert res_timeout is None

    # 7. execute_request_with_retry: Unexpected Exception
    async def crash_fn():
        raise RuntimeError("Fatal provider panic")

    res_crash = await prov.execute_request_with_retry(crash_fn, max_retries=1, initial_backoff=0.01)
    assert res_crash is None


# ---------------------------------------------------------------------------
# 4. SyntaxVerifier Multi-Language and AST Edge Cases
# ---------------------------------------------------------------------------
def test_syntax_verifier_deep_branches():
    # 1. Delimiter balancing with comments and string literals
    valid_comments_code = (
        "// Single line comment\n"
        "/* Block comment */\n"
        "const greeting = 'Hello, world!';\n"
        "const num = 42;\n"
        "function run() { return [1, 2, 3]; }\n"
    )
    valid, err = SyntaxVerifier.verify(valid_comments_code, language="javascript")
    assert valid is True
    assert err is None

    # Delimiter mismatch
    mismatch_code = "function test() { return [1, 2, (3] };"
    inv, inv_err = SyntaxVerifier.verify(mismatch_code, language="javascript")
    assert inv is False
    assert inv_err is not None

    # 2. Native / Tree-sitter AST Extraction & Verification for Python
    py_valid = (
        "import os\nfrom sys import path\ndef worker(x: int) -> int:\n    return x * 2\nclass Engine:\n    pass\n"
    )
    meta = SyntaxVerifier.extract_ast_metadata(py_valid, language="python")
    assert meta["parser_type"] in ("tree_sitter", "python_ast")
    assert meta["node_count"] > 0
    assert meta["has_syntax_errors"] is False

    py_invalid = "def broken(:"
    meta_bad = SyntaxVerifier.extract_ast_metadata(py_invalid, language="python")
    assert meta_bad["has_syntax_errors"] is True

    # 3. Java / C++ / C# Regex extraction
    cpp_code = "class Controller {\n    void process() {}\n    int calculate(int a) {}\n};\n"
    meta_cpp = SyntaxVerifier.extract_ast_metadata(cpp_code, language="cpp")
    assert "Controller" in meta_cpp["classes_or_structs"]
    assert "process" in meta_cpp["functions"]

    # 4. JSON & YAML verification
    json_valid = '{"status": "ok", "items": [1, 2, 3]}'
    assert SyntaxVerifier.verify(json_valid, language="json")[0] is True
    assert SyntaxVerifier.verify('{"bad_json":', language="json")[0] is False

    yaml_valid = "name: Cerberus\nversion: 1.0\nagents:\n  - security\n  - performance\n"
    assert SyntaxVerifier.verify(yaml_valid, language="yaml")[0] is True

    # 5. Empty or unknown language
    assert SyntaxVerifier.verify("", language="python") == (True, None)
    assert SyntaxVerifier.verify("echo hello", language="unknown")[0] is True


# ---------------------------------------------------------------------------
# 5. Database Operations, Session Rollback & Purge Retention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_database_operations_and_retries():
    from cerberus.core.database import execute_with_db_retry, get_db_session, purge_expired_reviews

    # 1. execute_with_db_retry with transient failure
    attempt_count = 0

    async def flaky_db_op():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise RuntimeError("Transient deadlock")
        return "success_val"

    result = await execute_with_db_retry(flaky_db_op, max_retries=3, delay=0.01)
    assert result == "success_val"
    assert attempt_count == 2

    # execute_with_db_retry exhausting retries
    async def doomed_db_op():
        raise ValueError("Permanent DB violation")

    with pytest.raises(ValueError):
        await execute_with_db_retry(doomed_db_op, max_retries=2, delay=0.01)

    # 2. purge_expired_reviews
    purged = await purge_expired_reviews(retention_days=365)
    assert isinstance(purged, int)

    # 3. get_db_session rollback on error
    with pytest.raises(RuntimeError):
        async for _session in get_db_session():
            raise RuntimeError("Forced session error for rollback test")


# ---------------------------------------------------------------------------
# 6. Zip Processor Edge Cases, Symlinks & Malformed Archives
# ---------------------------------------------------------------------------
def test_zip_processor_security_and_edge_cases(tmp_path):
    import zipfile

    from cerberus.core.zip_processor import extract_code_from_zip

    # 1. Non-existent path -> ValueError
    with pytest.raises(ValueError, match="ZIP file not found"):
        extract_code_from_zip(tmp_path / "does_not_exist.zip")

    # 2. Non-zip file -> ValueError
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_text("not a real zip content", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid ZIP"):
        extract_code_from_zip(fake_zip)

    # 3. Valid zip via Path object with Latin-1 fallback content & ignored files
    real_zip_path = tmp_path / "valid.zip"
    with zipfile.ZipFile(real_zip_path, "w") as zf:
        zf.writestr("clean.py", "def add(a, b):\n    return a + b\n")
        zf.writestr("ignored.pyc", b"bytecode")
        zf.writestr(".git/config", "secret=true")
        zf.writestr("node_modules/pkg/index.js", "console.log(1);")
        # non-utf8 bytes that trigger latin-1 fallback
        zf.writestr("latin1.py", b"# comment with invalid utf8: \xe9\nvar_x = 1\n")

    res = extract_code_from_zip(real_zip_path, project_name="path_project")
    assert res.project_name == "path_project"
    assert len(res.code_files) >= 2
    assert any("ignored.pyc" in s for s in res.skipped_files)
    assert any(".git/config" in s for s in res.skipped_files)
    assert any("node_modules" in s for s in res.skipped_files)


# ---------------------------------------------------------------------------
# 7. Cloud LLM Providers Mock Unit Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cloud_providers_unit_coverage():
    from cerberus.providers.anthropic_provider import AnthropicProvider
    from cerberus.providers.deepseek_provider import DeepSeekProvider
    from cerberus.providers.gemini_provider import GeminiProvider
    from cerberus.providers.groq_provider import GroqProvider
    from cerberus.providers.ollama_provider import OllamaProvider
    from cerberus.providers.openai_provider import OpenAIProvider
    from cerberus.providers.watsonx_provider import WatsonxProvider

    # 1. WatsonxProvider
    wx = WatsonxProvider()
    wx.api_key = "wx_test_key"
    wx.project_id = "proj_123"
    assert await wx.is_available() is True
    assert "granite" in wx.effective_model_id.lower()

    # WatsonX token cached
    wx._iam_token = "cached_iam_token"
    wx._token_expires_at = time.time() + 3600
    assert await wx._get_iam_token() == "cached_iam_token"

    # WatsonX token exchange mock 200
    wx._iam_token = None
    with unittest.mock.patch("httpx.AsyncClient.post") as mock_wx_post:
        resp_mock = unittest.mock.MagicMock(status_code=200)
        resp_mock.json.return_value = {"access_token": "fresh_iam_token", "expires_in": 3600}
        mock_wx_post.return_value = resp_mock

        token = await wx._get_iam_token()
        assert token == "fresh_iam_token"

    # WatsonX generate_response mock 200
    with unittest.mock.patch("httpx.AsyncClient.post") as mock_wx_gen:
        gen_mock = unittest.mock.MagicMock(status_code=200)
        gen_mock.json.return_value = {"results": [{"generated_text": "watsonx answer"}]}
        mock_wx_gen.return_value = gen_mock

        res = await wx.generate_response("system", "user")
        assert res == "watsonx answer"

    # 2. OpenAIProvider
    oai = OpenAIProvider(api_key="sk-mocked-key-for-testing-12345")
    assert await oai.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_oai:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"choices": [{"message": {"content": "openai response"}}]}
        mock_oai.return_value = resp

        ans = await oai.generate_response("sys", "user")
        assert ans == "openai response"

    # 3. AnthropicProvider
    anth = AnthropicProvider(api_key="sk-ant-mocked-key-for-testing-12345")
    assert await anth.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_anth:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"content": [{"text": "anthropic response"}]}
        mock_anth.return_value = resp

        ans = await anth.generate_response("sys", "user")
        assert ans == "anthropic response"

    # 4. GeminiProvider
    gem = GeminiProvider(api_key="gemini_mock_key_123456789")
    assert await gem.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_gem:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "gemini response"}]}}]}
        mock_gem.return_value = resp

        ans = await gem.generate_response("sys", "user")
        assert ans == "gemini response"

    # 5. DeepSeekProvider
    ds = DeepSeekProvider(api_key="sk-deepseek-mock-key-123456789")
    assert await ds.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_ds:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"choices": [{"message": {"content": "deepseek response"}}]}
        mock_ds.return_value = resp

        ans = await ds.generate_response("sys", "user")
        assert ans == "deepseek response"

    # 6. GroqProvider
    groq = GroqProvider(api_key="gsk_mock_groq_key_123456789")
    assert await groq.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_groq:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"choices": [{"message": {"content": "groq response"}}]}
        mock_groq.return_value = resp

        ans = await groq.generate_response("sys", "user")
        assert ans == "groq response"

    # 7. OllamaProvider
    ollama = OllamaProvider()
    with unittest.mock.patch("httpx.AsyncClient.get") as mock_ol_get:
        mock_ol_get.return_value = unittest.mock.MagicMock(status_code=200)
        assert await ollama.is_available() is True

    with unittest.mock.patch("httpx.AsyncClient.post") as mock_ol_post:
        resp = unittest.mock.MagicMock(status_code=200)
        resp.json.return_value = {"response": "ollama response"}
        mock_ol_post.return_value = resp

        ans = await ollama.generate_response("sys", "user")
        assert ans == "ollama response"


# ---------------------------------------------------------------------------
# 8. Telemetry Tracer Deep Coverage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telemetry_tracer_deep_coverage():
    from cerberus.core.telemetry import Tracer

    t = Tracer(max_stored_traces=10)

    # 1. sync_span without exception
    with t.sync_span("sync_operation", attributes={"user": "admin"}) as s:
        assert s.name == "sync_operation"
        assert s.status == "OK"
    assert s.status == "OK"

    # 2. sync_span with exception
    with pytest.raises(ValueError):
        with t.sync_span("failing_sync") as s_fail:
            raise ValueError("Deliberate sync error")
    assert s_fail.status == "ERROR"
    assert len(s_fail.events) == 1
    assert s_fail.events[0]["name"] == "exception"

    # 3. async_span with exception
    with pytest.raises(RuntimeError):
        async with t.async_span("failing_async") as s_async_fail:
            raise RuntimeError("Deliberate async error")
    assert s_async_fail.status == "ERROR"

    # 4. Spans retrieval and eviction
    spans = t.get_trace_spans(s.trace_id)
    assert len(spans) == 1

    # Add enough traces to trigger LRU eviction
    for i in range(15):
        t.start_span(f"span_{i}")
    assert len(t._traces) <= 10

    # 5. Clear
    t.clear()
    assert len(t._traces) == 0


# ---------------------------------------------------------------------------
# 9. Cache Manager Invalidation, Pruning and Aliases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cache_manager_invalidation_and_pruning():
    from cerberus.core.cache import CacheManager

    cm = CacheManager()
    cm.enabled = True
    await cm.set("item_1", {"v": 1}, ttl_seconds=3600)
    await cm.set("item_expired", {"v": 2}, ttl_seconds=-10)

    # Invalidate memory item
    assert cm.invalidate("item_1") is True
    assert cm.invalidate("non_existent") is False

    # Prune expired
    pruned = cm.prune_expired()
    assert pruned >= 1

    # Invalidate async with mock redis client
    mock_redis = unittest.mock.AsyncMock()
    mock_redis.delete.return_value = 1
    cm.redis_client = mock_redis

    await cm.set("redis_key", {"v": "val"}, ttl_seconds=60)
    res = await cm.invalidate_async("redis_key")
    assert res is True

    # Invalidate async with redis error
    mock_redis.delete.side_effect = RuntimeError("Redis down")
    res_err = await cm.delete("redis_key")
    assert res_err is False


# ---------------------------------------------------------------------------
# 10. API Key Rotation and Revocation Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_keys_rotation_and_revocation_branches():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a new key
        create_res = await client.post(
            "/api/v1/keys",
            json={"name": "key_to_rotate", "scopes": ["review:read", "review:write"]},
            headers=headers,
        )
        assert create_res.status_code == 201
        key_id = create_res.json()["id"]

        # Rotate key by ID
        rot_res = await client.post(f"/api/v1/keys/{key_id}/rotate", headers=headers)
        assert rot_res.status_code == 200
        new_key_data = rot_res.json()
        assert "raw_key" in new_key_data
        assert "new_key_id" in new_key_data

        # Rotate key by name fallback
        rot_name_res = await client.post("/api/v1/keys/key_to_rotate/rotate", headers=headers)
        assert rot_name_res.status_code == 200

        # Rotate non-existent key -> 404
        rot_nf = await client.post("/api/v1/keys/non_existent_key_xyz/rotate", headers=headers)
        assert rot_nf.status_code == 404

        # Revoke non-existent key -> 404
        rev_nf = await client.delete("/api/v1/keys/non_existent_key_xyz", headers=headers)
        assert rev_nf.status_code == 404


# ---------------------------------------------------------------------------
# 11. Webhook Ingestion Advanced Payload Branches
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_advanced_payload_branches():
    import json

    from cerberus.core.security import generate_webhook_signature

    transport = ASGITransport(app=app)
    secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Malformed JSON -> 400
        bad_json = b"{not: a: json"
        sig_bad = generate_webhook_signature(bad_json, secret)
        res_bad = await client.post(
            "/api/v1/review/webhooks/github",
            content=bad_json,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig_bad,
                "Content-Type": "application/json",
            },
        )
        assert res_bad.status_code == 400

        # 2. Ignored action (e.g. closed)
        closed_event = {
            "action": "closed",
            "number": 12,
            "pull_request": {"number": 12, "head": {"sha": "123"}},
            "repository": {"name": "repo", "owner": {"login": "user"}},
        }
        closed_bytes = json.dumps(closed_event).encode("utf-8")
        sig_closed = generate_webhook_signature(closed_bytes, secret)
        res_closed = await client.post(
            "/api/v1/review/webhooks/github",
            content=closed_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig_closed,
                "Content-Type": "application/json",
            },
        )
        assert res_closed.status_code == 200
        assert res_closed.json()["status"] == "ignored"

        # 3. Pull request with markdown codeblock in PR body
        body_with_code = "Fixing issue:\n```python\ndef fixed_worker():\n    return 42\n```\n"
        body_event = {
            "action": "opened",
            "number": 13,
            "pull_request": {
                "number": 13,
                "head": {"sha": "headsha123"},
                "body": body_with_code,
                "title": "PR with code in body",
            },
            "repository": {"name": "repo", "owner": {"login": "user"}},
        }
        body_bytes = json.dumps(body_event).encode("utf-8")
        sig_body = generate_webhook_signature(body_bytes, secret)
        res_body = await client.post(
            "/api/v1/review/webhooks/github",
            content=body_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig_body,
                "Content-Type": "application/json",
            },
        )
        assert res_body.status_code == 200
        assert res_body.json()["status"] == "completed"

        # 4. Pull request with no code content at all -> ignored
        empty_code_event = {
            "action": "opened",
            "number": 14,
            "pull_request": {
                "number": 14,
                "head": {"sha": "headsha456"},
                "body": "",
                "title": "",
            },
            "repository": {"name": "repo", "owner": {"login": "user"}},
        }
        empty_bytes = json.dumps(empty_code_event).encode("utf-8")
        sig_empty = generate_webhook_signature(empty_bytes, secret)
        res_empty = await client.post(
            "/api/v1/review/webhooks/github",
            content=empty_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig_empty,
                "Content-Type": "application/json",
            },
        )
        assert res_empty.status_code == 200
        assert res_empty.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# 12. Zip Processor Security Guards
# ---------------------------------------------------------------------------
def test_zip_processor_security_guards():
    import zipfile

    from cerberus.core.zip_processor import is_safe_zip_path, is_symlink_entry

    # Path traversal and injection rejection
    assert is_safe_zip_path("valid/path/file.py") is True
    assert is_safe_zip_path("null\0byte.py") is False
    assert is_safe_zip_path("%2e%2e/etc/passwd") is False
    assert is_safe_zip_path("%2fetc/passwd") is False
    assert is_safe_zip_path("/absolute/path.py") is False
    assert is_safe_zip_path("\\windows\\abs.py") is False
    assert is_safe_zip_path("C:/Windows/System32.py") is False
    assert is_safe_zip_path("folder/../../escape.py") is False
    assert is_safe_zip_path("a/b/c/d/e/f/g/h/i/j/k/l/m.py", max_depth=5) is False

    # Symlink detection
    info_symlink = zipfile.ZipInfo("symlink_entry")
    info_symlink.external_attr = 0o120777 << 16
    assert is_symlink_entry(info_symlink) is True

    info_normal = zipfile.ZipInfo("normal_file.py")
    info_normal.external_attr = 0o100644 << 16
    assert is_symlink_entry(info_normal) is False


# ---------------------------------------------------------------------------
# 13. CodeFixerAgent LLM Patch Verification & Fallback Reversion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_code_fixer_llm_patch_and_reversion():
    from cerberus.agents.code_fixer_agent import CodeFixerAgent
    from cerberus.models.schemas import Finding, SeverityEnum

    fixer = CodeFixerAgent()

    # 1. LLM returning fenced markdown code
    mock_prov = unittest.mock.AsyncMock()
    mock_prov.generate_response.return_value = '{"repaired_code": "```python\\nx = 1\\ny = 2\\n```"}'
    fixer.provider = mock_prov

    finding = Finding(
        category="quality",
        severity=SeverityEnum.MEDIUM,
        title="Sample",
        message="Message",
        line=1,
    )
    res = await fixer.generate_patch("x = 1\n", [finding], filename="sample.py", language="python")
    assert "repaired_code" in res

    # 2. Patch verification failure causing safe fallback reversion
    mock_prov.generate_response.return_value = '{"repaired_code": "def corrupted_syntax(:"}'
    res_fallback = await fixer.generate_patch("x = 1\n", [finding], filename="sample.py", language="python")
    assert res_fallback["repaired_code"] == "x = 1\n"


# ---------------------------------------------------------------------------
# 14. Review API WebSocket Streams, Multi-Tenant and DB Fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_api_websocket_stream_and_db_fallback():
    from starlette.testclient import TestClient

    from cerberus.api.v1.review import (
        REVIEWS_STORE_MAX_ITEMS,
        _review_owners,
        _store_zip_review,
        reviews_store,
    )

    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a review
        rev_res = await client.post(
            "/api/v1/review",
            json={"code": "def calculate(a, b):\n    return a * b\n", "language": "python"},
            headers=headers,
        )
        assert rev_res.status_code == 200
        rev_data = rev_res.json()
        rev_id = rev_data["review_id"]

        # Wait a tiny bit for background DB persist task to complete
        await asyncio.sleep(0.1)

        # 2. Generate stream token
        st_res = await client.post(f"/api/v1/review/{rev_id}/stream-token", headers=headers)
        assert st_res.status_code == 200
        stream_tok = st_res.json()["stream_token"]

        # 3. Test WebSocket with stream_token
        with TestClient(app) as ws_client:
            with ws_client.websocket_connect(f"/api/v1/review/{rev_id}/ws?stream_token={stream_tok}") as ws:
                msg = ws.receive_json()
                assert msg["event"] == "connected"

            # 4. Test WebSocket with Bearer header
            with ws_client.websocket_connect(
                f"/api/v1/review/{rev_id}/ws",
                headers={"authorization": f"Bearer {dev_key}"},
            ) as ws2:
                msg2 = ws2.receive_json()
                assert msg2["event"] == "connected"

            # 5. Test WebSocket in production with forbidden query token
            orig_env = settings.ENVIRONMENT
            try:
                settings.ENVIRONMENT = "production"
                with pytest.raises((Exception,)):
                    with ws_client.websocket_connect(f"/api/v1/review/{rev_id}/ws?token={dev_key}"):
                        pass
            finally:
                settings.ENVIRONMENT = orig_env

        # 6. Test DB fallback for get_review_status when evicted from memory store
        if rev_id in reviews_store:
            del reviews_store[rev_id]
        if rev_id in _review_owners:
            del _review_owners[rev_id]

        status_res = await client.get(f"/api/v1/review/{rev_id}", headers=headers)
        assert status_res.status_code == 200
        assert status_res.json()["review_id"] == rev_id

        # 7. Test Base64 ZIP size overflow (413)
        huge_b64 = "A" * (settings.MAX_ZIP_UPLOAD_BYTES * 2)
        huge_res = await client.post("/api/v1/review/zip-base64", json={"zip_base64": huge_b64}, headers=headers)
        assert huge_res.status_code == 413

        # 8. Test _store_zip_review LRU eviction
        assert REVIEWS_STORE_MAX_ITEMS > 0
        assert rev_res.status_code == 200
        # Test storing existing ID moves to end
        from cerberus.models.schemas import ZipReviewResponse

        dummy_zip_res = ZipReviewResponse(
            project_name="lru_test",
            review_id="zip_lru_1",
            status="completed",
            created_at=datetime.now(UTC).isoformat(),
            total_files_discovered=1,
            reviewed_files_count=1,
            skipped_files_count=0,
            total_lines_of_code=10,
            overall_project_score=90.0,
            severity_summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            language_distribution={"python": 1},
            file_reviews=[],
            top_critical_findings=[],
            collaborative_consensus={"pr_action": "MERGE_READY"},
        )
        _store_zip_review("zip_lru_1", dummy_zip_res, owner_id="tenant_1")
        _store_zip_review("zip_lru_1", dummy_zip_res, owner_id="tenant_1")  # triggers move_to_end


# ---------------------------------------------------------------------------
# 15. Health & Readiness Probes Deep Branches
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_and_readiness_probes_all_branches():
    from cerberus.core.cache import cache_manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Healthy /health
        res_h = await client.get("/health")
        assert res_h.status_code == 200

        # 2. Redis probe healthy and failing
        mock_redis = unittest.mock.AsyncMock()
        mock_redis.ping.return_value = True
        cache_manager.redis_client = mock_redis

        res_redis_ok = await client.get("/health")
        assert res_redis_ok.status_code == 200
        assert res_redis_ok.json()["cache"] == "redis"

        # Redis probe failure
        mock_redis.ping.side_effect = RuntimeError("Redis timeout")
        res_redis_fail = await client.get("/health")
        assert res_redis_fail.status_code == 200
        assert res_redis_fail.json()["cache"] == "disconnected"

        # Cache disabled
        cache_manager.enabled = False
        res_cache_dis = await client.get("/health")
        assert res_cache_dis.status_code == 200
        assert res_cache_dis.json()["cache"] == "disabled"

        # Restore cache manager state
        cache_manager.enabled = True
        cache_manager.redis_client = None

        # 3. Database probe failure
        with unittest.mock.patch("cerberus.api.v1.health.AsyncSessionLocal") as mock_sess:
            mock_sess.side_effect = RuntimeError("DB down")
            res_db_fail = await client.get("/health")
            assert res_db_fail.status_code == 200
            assert res_db_fail.json()["database"] == "disconnected"


# ---------------------------------------------------------------------------
# 16. Cloud Provider Error Handling and Fallbacks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_error_handling_and_resilience():
    from cerberus.providers.anthropic_provider import AnthropicProvider
    from cerberus.providers.deepseek_provider import DeepSeekProvider
    from cerberus.providers.gemini_provider import GeminiProvider
    from cerberus.providers.groq_provider import GroqProvider
    from cerberus.providers.openai_provider import OpenAIProvider
    from cerberus.providers.watsonx_provider import WatsonxProvider

    # 1. OpenAI: HTTP 400 error and exception
    p_openai = OpenAIProvider(api_key="sk-test-openai")
    mock_resp_400 = unittest.mock.MagicMock()
    mock_resp_400.status_code = 400
    mock_resp_400.text = "Bad Request"
    with unittest.mock.patch.object(
        p_openai, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
    ):
        res = await p_openai.generate_response("sys", "user")
        assert res is None

    mock_resp_empty = unittest.mock.MagicMock()
    mock_resp_empty.status_code = 200
    mock_resp_empty.json.return_value = {"choices": []}
    with unittest.mock.patch.object(
        p_openai, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_empty)
    ):
        res = await p_openai.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(p_openai, "get_client", side_effect=RuntimeError("Client crash")):
        res = await p_openai.generate_response("sys", "user")
        assert res is None

    # 2. Anthropic: HTTP 400 error, empty content, and exception
    p_anthropic = AnthropicProvider(api_key="sk-test-anthropic")
    with unittest.mock.patch.object(
        p_anthropic, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
    ):
        res = await p_anthropic.generate_response("sys", "user")
        assert res is None

    mock_resp_anthropic_empty = unittest.mock.MagicMock()
    mock_resp_anthropic_empty.status_code = 200
    mock_resp_anthropic_empty.json.return_value = {"content": []}
    with unittest.mock.patch.object(
        p_anthropic, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_anthropic_empty)
    ):
        res = await p_anthropic.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(p_anthropic, "get_client", side_effect=RuntimeError("Client crash")):
        res = await p_anthropic.generate_response("sys", "user")
        assert res is None

    # 3. Gemini: HTTP 400 error, empty parts, and exception
    p_gemini = GeminiProvider(api_key="test-gemini-key")
    with unittest.mock.patch.object(
        p_gemini, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
    ):
        res = await p_gemini.generate_response("sys", "user")
        assert res is None

    mock_resp_gemini_empty = unittest.mock.MagicMock()
    mock_resp_gemini_empty.status_code = 200
    mock_resp_gemini_empty.json.return_value = {"candidates": [{"content": {"parts": []}}]}
    with unittest.mock.patch.object(
        p_gemini, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_gemini_empty)
    ):
        res = await p_gemini.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(p_gemini, "get_client", side_effect=RuntimeError("Client crash")):
        res = await p_gemini.generate_response("sys", "user")
        assert res is None

    # 4. DeepSeek: HTTP 400 error, empty choices, and exception
    p_deepseek = DeepSeekProvider(api_key="sk-test-deepseek")
    with unittest.mock.patch.object(
        p_deepseek, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
    ):
        res = await p_deepseek.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(
        p_deepseek, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_empty)
    ):
        res = await p_deepseek.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(p_deepseek, "get_client", side_effect=RuntimeError("Client crash")):
        res = await p_deepseek.generate_response("sys", "user")
        assert res is None

    # 5. Groq: HTTP 400 error, empty choices, and exception
    p_groq = GroqProvider(api_key="gsk-test-groq")
    with unittest.mock.patch.object(
        p_groq, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
    ):
        res = await p_groq.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(
        p_groq, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_empty)
    ):
        res = await p_groq.generate_response("sys", "user")
        assert res is None

    with unittest.mock.patch.object(p_groq, "get_client", side_effect=RuntimeError("Client crash")):
        res = await p_groq.generate_response("sys", "user")
        assert res is None

    # 6. Watsonx: token failures, generation errors, and exception
    p_watsonx = WatsonxProvider()
    p_watsonx.api_key = "test-ibm-key"
    p_watsonx.project_id = "test-ibm-proj"

    # Token fetch error (HTTP 400)
    mock_token_resp_400 = unittest.mock.MagicMock()
    mock_token_resp_400.status_code = 400
    mock_token_resp_400.text = "Unauthorized"
    mock_client = unittest.mock.AsyncMock()
    mock_client.post.return_value = mock_token_resp_400
    with unittest.mock.patch.object(p_watsonx, "get_client", unittest.mock.AsyncMock(return_value=mock_client)):
        tok = await p_watsonx._get_iam_token()
        assert tok is None

    # Token fetch exception
    mock_client.post.side_effect = RuntimeError("IAM failure")
    with unittest.mock.patch.object(p_watsonx, "get_client", unittest.mock.AsyncMock(return_value=mock_client)):
        tok = await p_watsonx._get_iam_token()
        assert tok is None

    # Watsonx generate_response with valid token but request returns HTTP 400
    with unittest.mock.patch.object(p_watsonx, "_get_iam_token", unittest.mock.AsyncMock(return_value="mock_token")):
        with unittest.mock.patch.object(
            p_watsonx, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_400)
        ):
            res = await p_watsonx.generate_response("sys", "user")
            assert res is None

        # Watsonx generate_response with empty results
        mock_resp_watsonx_empty = unittest.mock.MagicMock()
        mock_resp_watsonx_empty.status_code = 200
        mock_resp_watsonx_empty.json.return_value = {"results": []}
        with unittest.mock.patch.object(
            p_watsonx, "execute_request_with_retry", unittest.mock.AsyncMock(return_value=mock_resp_watsonx_empty)
        ):
            res = await p_watsonx.generate_response("sys", "user")
            assert res is None

        # Watsonx generate_response exception
        with unittest.mock.patch.object(p_watsonx, "get_client", side_effect=RuntimeError("Client crash")):
            res = await p_watsonx.generate_response("sys", "user")
            assert res is None


# ---------------------------------------------------------------------------
# 17. Config API Validation, Persistence and Retrieval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_config_api_validation_and_persistence():
    transport = ASGITransport(app=app)
    dev_key = settings.DEFAULT_DEV_API_KEY
    headers = {"Authorization": f"Bearer {dev_key}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET active configuration
        get_res = await client.get("/api/v1/config", headers=headers)
        assert get_res.status_code == 200
        conf_data = get_res.json()
        assert "environment" in conf_data
        assert "severity_threshold" in conf_data

        # 2. PUT with invalid severity_threshold -> 400
        bad_sev_res = await client.put(
            "/api/v1/config",
            json={"severity_threshold": "unacceptable_level"},
            headers=headers,
        )
        assert bad_sev_res.status_code == 400
        assert "Invalid severity_threshold" in bad_sev_res.json()["detail"]

        # 3. PUT with unknown agent -> 400
        bad_agent_res = await client.put(
            "/api/v1/config",
            json={"enabled_agents": ["security", "super_unknown_agent"]},
            headers=headers,
        )
        assert bad_agent_res.status_code == 400
        assert "Unknown agent" in bad_agent_res.json()["detail"]

        # 4. PUT with valid configuration
        valid_put_res = await client.put(
            "/api/v1/config",
            json={
                "severity_threshold": "high",
                "blocking_mode": True,
                "enabled_agents": ["security", "performance"],
            },
            headers=headers,
        )
        assert valid_put_res.status_code == 200
        assert valid_put_res.json()["status"] == "success"

        # Verify applied configuration
        get_after = await client.get("/api/v1/config", headers=headers)
        assert get_after.json()["severity_threshold"] == "high"
        assert get_after.json()["blocking_mode"] is True
        assert "security" in get_after.json()["enabled_agents"]

        # 5. PATCH with comma-separated string for enabled_agents
        patch_res = await client.patch(
            "/api/v1/config",
            json={"enabled_agents": "security, quality, architecture"},
            headers=headers,
        )
        assert patch_res.status_code == 200

        # Restore defaults
        await client.put(
            "/api/v1/config",
            json={
                "severity_threshold": "low",
                "blocking_mode": False,
                "enabled_agents": ["security", "quality", "performance", "architecture", "dependencies", "secrets"],
            },
            headers=headers,
        )


# ---------------------------------------------------------------------------
# 18. Database Purge Expired Reviews and Pool Warmup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_database_purge_expired_reviews_and_warmup():
    from cerberus.core.database import purge_expired_reviews, warm_connection_pool

    # Test warm_connection_pool
    warmed = await warm_connection_pool()
    assert warmed is True

    # Test purge_expired_reviews
    purged = await purge_expired_reviews(retention_days=30)
    assert isinstance(purged, int)
    assert purged >= 0
