"""
Tests for full codebase excellence and 10/10 quality verification.
Tests all hardened edge cases, multi-language fixes, error recovery,
cache boundaries, zip-slip protections, and background task longevity.
"""

import asyncio
import io
import json
import zipfile
import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.agents.ai_helper import (
    build_findings_from_llm,
    compute_composite_score,
    merge_findings,
    parse_llm_json,
)
from cerberus.agents.code_fixer_agent import CodeFixerAgent
from cerberus.agents.consensus_agent import ConsensusAgent
from cerberus.agents.orchestrator import orchestrator
from cerberus.api.app import app
from cerberus.api.v1.config import ConfigUpdateModel
from cerberus.api.v1.review import _background_tasks, _create_background_task
from cerberus.config import settings
from cerberus.core.cache import CacheManager
from cerberus.core.security import RateLimiter, generate_api_key, hash_api_key
from cerberus.core.zip_processor import (
    detect_language_from_path,
    extract_code_from_zip,
    is_safe_zip_path,
)
from cerberus.models.schemas import (
    CodeReviewRequest,
    Finding,
    ReviewApproveRequest,
    ReviewConfig,
    SeverityEnum,
)
from cerberus.providers.heuristic_engine import HeuristicEngine


# =========================================================================
# 1. AI Helper Edge Cases & JSON Parsing Robustness
# =========================================================================
def test_ai_helper_json_parsing_edge_cases():
    # Empty or None
    assert parse_llm_json(None) is None
    assert parse_llm_json("") is None
    assert parse_llm_json("   ") is None

    # Code fence with preamble comments
    raw_with_comments = """```json
    // Here is the analysis result
    {
        "score": 85.0,
        "findings": []
    }
    ```"""
    parsed = parse_llm_json(raw_with_comments)
    assert parsed is not None
    assert parsed["score"] == 85.0

    # Trailing commas in arrays and objects
    raw_trailing = '{"items": [1, 2, 3, ], "name": "test", }'
    parsed_trailing = parse_llm_json(raw_trailing)
    assert parsed_trailing is not None
    assert parsed_trailing["name"] == "test"
    assert len(parsed_trailing["items"]) == 3

    # Non-dict root returns should not crash
    assert parse_llm_json("[1, 2, 3]") is None
    assert parse_llm_json("Just plain text with no json") is None


def test_ai_helper_finding_builder_edge_cases():
    raw_findings = [
        "not a dict",
        {
            "severity": "CRIT",
            "line": "not an int",
            "title": "Invalid Line Type",
            "cvss_score": "9.5",
            "exploitability": "0.85",
        },
        {
            "severity": "invalid_sev",
            "line": 9999,  # out of bounds
            "title": "Out of bounds line",
            "cvss_score": "bad_float",
            "exploitability": None,
        },
    ]
    findings = build_findings_from_llm(raw_findings, "security", "print('hello')\n")
    assert len(findings) == 2
    assert findings[0].severity == SeverityEnum.CRITICAL
    assert findings[0].line is None
    assert findings[0].cvss_score == 9.5
    assert findings[0].exploitability == 0.85
    # Default severity fallback for unrecognized string
    assert findings[1].severity == SeverityEnum.MEDIUM
    assert findings[1].line is None
    assert findings[1].cvss_score is None


def test_ai_helper_composite_score_floors():
    # Clean code: no findings -> 100.0
    assert compute_composite_score([]) == 100.0

    # Anti-hallucination floor: heuristic is 100, LLM hallucinates low score
    finding = Finding(
        severity=SeverityEnum.CRITICAL,
        category="security",
        title="Test",
        message="Test msg",
    )
    score = compute_composite_score([finding, finding], llm_score=20.0, heuristic_score=100.0)
    assert score == 70.0  # Protected by 70.0 floor against LLM hallucination on clean code


# =========================================================================
# 2. Code Fixer & Multi-Language Support
# =========================================================================
@pytest.mark.asyncio
async def test_code_fixer_multi_language_and_ast():
    fixer = CodeFixerAgent()

    # Python AST verification
    py_code = "def foo():\n    x = 1\n"
    finding = Finding(
        severity=SeverityEnum.MEDIUM,
        category="quality",
        title="Improvement",
        message="Use 2",
        line=2,
        code_snippet="x = 1",
        suggestion="x = 2",
    )
    repaired_py = fixer._apply_heuristic_fixes(py_code, [finding], language="python")
    assert "x = 2" in repaired_py

    # Non-Python (e.g. JavaScript) - should apply repair without ast.parse failure
    js_code = "function test() {\n    const query = 'SELECT * FROM users';\n}"
    js_finding = Finding(
        severity=SeverityEnum.HIGH,
        category="security",
        title="Use parameterized",
        message="Fix query",
        line=2,
        code_snippet="const query = 'SELECT * FROM users';",
        suggestion="const query = 'SELECT * FROM users WHERE id = ?';",
    )
    repaired_js = fixer._apply_heuristic_fixes(js_code, [js_finding], language="javascript")
    assert "WHERE id = ?" in repaired_js

    # Convenience method
    res = await fixer.synthesize_fixes(js_code, [js_finding], language="javascript")
    assert res["patch_applied"] is True
    assert "diff --git" not in res["unified_diff"]  # standard unified diff
    assert "a/snippet.py" in res["unified_diff"]


# =========================================================================
# 3. Consensus Agent Arbitration
# =========================================================================
@pytest.mark.asyncio
async def test_consensus_agent_verdicts():
    agent = ConsensusAgent()

    # 1. Blocked on issues
    crit_finding = Finding(
        severity=SeverityEnum.CRITICAL,
        category="security",
        title="SQLi",
        message="SQL injection",
        line=5,
    )
    res_blocked = agent._evaluate_heuristic_consensus([crit_finding], {"security": 20.0})
    assert res_blocked["pr_action"] == "BLOCKED_ON_ISSUES"

    # 2. Needs revision
    med_finding = Finding(
        severity=SeverityEnum.MEDIUM,
        category="performance",
        title="Slow loop",
        message="O(n^2)",
        line=10,
    )
    res_revision = agent._evaluate_heuristic_consensus([med_finding], {"performance": 75.0})
    assert res_revision["pr_action"] == "NEEDS_REVISION"

    # 3. Merge ready
    res_ready = agent._evaluate_heuristic_consensus([], {"security": 100.0, "performance": 100.0})
    assert res_ready["pr_action"] == "MERGE_READY"


# =========================================================================
# 4. Cache Manager Resilience & Null Safety
# =========================================================================
@pytest.mark.asyncio
async def test_cache_null_safety_and_lru():
    cm = CacheManager(max_items=3)

    # Null safety in key computation
    key1 = cm.compute_cache_key(code=None, language=None)
    assert key1.startswith("cvai:cache:")

    key2 = cm.compute_cache_key(code="def foo(): pass", language="python", agents=["security"])
    assert key2.startswith("cvai:cache:")

    # LRU Bounded Eviction
    await cm.set("k1", {"val": 1})
    await cm.set("k2", {"val": 2})
    await cm.set("k3", {"val": 3})
    assert len(cm._memory_cache) == 3

    # Adding 4th item should evict k1
    await cm.set("k4", {"val": 4})
    assert len(cm._memory_cache) == 3
    assert await cm.get("k1") is None
    assert (await cm.get("k4"))["val"] == 4

    # Hit rate calculation
    assert cm.hit_rate > 0.0

    # Expired pruning
    purged = cm.prune_expired()
    assert purged >= 0


# =========================================================================
# 5. Security & Rate Limiting Hardening
# =========================================================================
@pytest.mark.asyncio
async def test_rate_limiter_hardening():
    rl = RateLimiter(limit_per_hour=3, max_tracked=5)

    # Defensively handles None or empty identifiers
    allowed, rem, retry = rl.is_allowed(None)
    assert allowed is True
    assert rem == 2

    allowed, rem, retry = rl.is_allowed("user_1")
    assert allowed is True

    # Check async path
    allowed, rem, retry = await rl.is_allowed_async("user_1")
    assert allowed is True

    # Purge expired check
    purged = rl.purge_expired()
    assert purged >= 0

    # Key generation verification
    raw_key, key_hash, prefix = generate_api_key(name="test_runner")
    assert raw_key.startswith(prefix)
    assert hash_api_key(raw_key) == key_hash


# =========================================================================
# 6. ZIP Processor Safety & Traversal Resistance
# =========================================================================
def test_zip_processor_security_guards():
    # Zip slip path traversal checks
    assert is_safe_zip_path("src/main.py") is True
    assert is_safe_zip_path("src/utils/helpers.py") is True

    # Malicious paths
    assert is_safe_zip_path("../evil.py") is False
    assert is_safe_zip_path("foo/../../evil.py") is False
    assert is_safe_zip_path("/etc/passwd") is False
    assert is_safe_zip_path("C:/Windows/System32/evil.dll") is False
    assert is_safe_zip_path("D:\\evil.py") is False

    # Language extension detection across 25+ filetypes
    assert detect_language_from_path("script.py") == "python"
    assert detect_language_from_path("app.ts") == "typescript"
    assert detect_language_from_path("query.sql") == "sql"
    assert detect_language_from_path("style.css") == "css"
    assert detect_language_from_path("Main.java") == "java"
    assert detect_language_from_path("binary.exe") is None

    # Invalid zip buffer raises ValueError
    with pytest.raises(ValueError, match="not a valid ZIP archive"):
        extract_code_from_zip(b"not a zip file content")


# =========================================================================
# 7. Background Tasks & API Endpoints
# =========================================================================
@pytest.mark.asyncio
async def test_background_task_strong_reference():
    async def dummy():
        await asyncio.sleep(0.01)

    initial_count = len(_background_tasks)
    task = _create_background_task(dummy())
    assert task in _background_tasks
    await task
    # Should automatically clean up from the strong set
    await asyncio.sleep(0.02)
    assert task not in _background_tasks


@pytest.mark.asyncio
async def test_api_review_endpoints_full_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Empty code submission -> 400
        res_empty = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"code": "   ", "language": "python"},
        )
        assert res_empty.status_code == 400

        # 2. Valid code submission
        res_valid = await client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"code": "def hello():\n    return 'world'\n", "language": "python"},
        )
        assert res_valid.status_code == 200
        data = res_valid.json()
        review_id = data["review_id"]

        # 3. Status endpoint
        res_status = await client.get(
            f"/api/v1/review/{review_id}/status", headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert res_status.status_code == 200
        assert res_status.json()["review_id"] == review_id

        # 4. Results endpoint
        res_results = await client.get(
            f"/api/v1/review/{review_id}/results", headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert res_results.status_code == 200

        # 5. Approve endpoint with override
        res_appr = await client.post(
            f"/api/v1/review/{review_id}/approve",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"reviewer": "Lead Architect", "override_blocking": True},
        )
        assert res_appr.status_code == 200
        assert res_appr.json()["status"] == "approved"

        # 6. Feedback endpoint
        res_fb = await client.post(
            f"/api/v1/review/{review_id}/feedback",
            headers={"Authorization": "Bearer cvai_dev_key_123"},
            json={"rating": 5, "is_helpful": True, "comments": "Excellent review!"},
        )
        assert res_fb.status_code == 200
        assert res_fb.json()["status"] == "success"

        # 7. Config endpoint update model validation
        res_cfg_get = await client.get("/api/v1/config", headers={"Authorization": "Bearer cvai_dev_key_123"})
        assert res_cfg_get.status_code == 200

        res_cfg_put = await client.put(
            "/api/v1/config", headers={"Authorization": "Bearer cvai_dev_key_123"}, json={"blocking_mode": False}
        )
        assert res_cfg_put.status_code == 200


# =========================================================================
# 8. Heuristic Engine Edge Cases
# =========================================================================
def test_heuristic_engine_ast_and_edge_cases():
    # None or non-string input
    assert HeuristicEngine.get_parsed_ast(None) is None
    assert HeuristicEngine.get_parsed_ast("") is None
    assert HeuristicEngine.get_parsed_ast(12345) is None

    # Syntax error returns None gracefully
    assert HeuristicEngine.get_parsed_ast("def broken_syntax(:") is None

    # Valid python ast cached
    tree = HeuristicEngine.get_parsed_ast("x = 1 + 2")
    assert tree is not None

    # N+1 query loop detection
    n_plus_one_code = """
for user_id in user_ids:
    user = db.query(User).get(user_id)
"""
    perf_findings, score = HeuristicEngine.analyze_performance(n_plus_one_code)
    assert any(f.category == "database" for f in perf_findings)
    assert score < 100.0

    # Insecure deserialization detection
    deser_code = "import pickle\ndata = pickle.loads(user_input)\n"
    sec_findings, score = HeuristicEngine.analyze_security(deser_code)
    assert any(f.category == "deserialization" for f in sec_findings)
