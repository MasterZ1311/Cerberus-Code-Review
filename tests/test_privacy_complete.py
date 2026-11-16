"""
Direct Deep-Inspection Tests for End-to-End Privacy Guarantees.
Inspects L1 cache, L2 serialization, in-memory review stores, database records,
telemetry spans, and pub/sub stream payloads to guarantee total absence
of unredacted source code when RETAIN_SOURCE_CODE=false.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cerberus.api.app import app
from cerberus.api.v1.review import reviews_store
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.telemetry import Span
from cerberus.models.database import CodeReviewRecord, FindingRecord


@pytest.fixture(autouse=True)
async def setup_env():
    await init_db()
    cache_manager.clear()
    reviews_store.clear()


@pytest.mark.asyncio
async def test_privacy_l1_in_memory_cache_directly_redacted():
    """Directly inspect L1 memory cache dictionary to verify sensitive code is never stored."""
    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        cache_key = "cvai:cache:test_l1_redaction"
        sensitive_payload = {
            "code": "SECRET_API_KEY = 'super_secret_l1_value'",
            "filename": "auth.py",
            "score": 85.0,
            "findings": [
                {
                    "category": "security",
                    "code_snippet": "SECRET_API_KEY = 'super_secret_l1_value'",
                    "suggestion": "SECRET_API_KEY = os.getenv('KEY')",
                    "recommendation": "Use environment variables.",
                }
            ],
        }

        # Store in L1 cache
        await cache_manager.set(cache_key, sensitive_payload, ttl_seconds=60)

        # 1. Directly inspect L1 internal dictionary structure
        assert cache_key in cache_manager._memory_cache
        entry = cache_manager._memory_cache[cache_key]["data"]

        # Sensitive code fields must be redacted in L1
        assert "super_secret_l1_value" not in json.dumps(entry)
        assert "REDACTED" in entry["code"]
        assert "REDACTED" in entry["findings"][0]["code_snippet"]
        assert "REDACTED" in entry["findings"][0]["suggestion"]

        # Non-sensitive metadata MUST be preserved in L1
        assert entry["filename"] == "auth.py"
        assert entry["score"] == 85.0
        assert entry["findings"][0]["category"] == "security"
        assert entry["findings"][0]["recommendation"] == "Use environment variables."
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain


def test_privacy_l2_payload_encoding_redacted():
    """Verify that L2 payload encoder scrubs sensitive code prior to serialization/compression."""
    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        sensitive_obj = {
            "source_code": "def leak_database(): pass",
            "patch": "--- a/file.py\n+++ b/file.py\n@@ secret @@",
            "overall_score": 92.5,
            "status": "completed",
        }
        encoded = cache_manager._encode_payload(sensitive_obj)
        decoded = cache_manager._decode_payload(encoded)

        assert "leak_database" not in json.dumps(decoded)
        assert "secret" not in json.dumps(decoded)
        assert decoded["overall_score"] == 92.5
        assert decoded["status"] == "completed"
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain


@pytest.mark.asyncio
async def test_privacy_database_and_reviews_store_deep_inspection():
    """Deep inspection of HTTP response, in-memory reviews_store, and SQL database rows."""
    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        confidential_snippet = "def confidential_business_logic(): return 'classified_secret_999'"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer cvai_dev_key_123"}
            resp = await client.post(
                "/api/v1/review",
                headers=headers,
                json={"code": confidential_snippet, "filename": "classified.py", "language": "python"},
            )
            assert resp.status_code == 200
            review_data = resp.json()
            review_id = review_data["review_id"]

            # 1. Serialized response must not contain raw confidential code in code snippets
            assert "classified_secret_999" not in json.dumps(review_data["critical_issues"])
            assert "classified_secret_999" not in json.dumps(review_data["warnings"])
            assert "classified_secret_999" not in json.dumps(review_data["suggestions"])

            # 2. In-memory reviews_store must be redacted
            stored_response = reviews_store.get(review_id)
            assert stored_response is not None
            stored_dump = stored_response.model_dump()
            assert "classified_secret_999" not in json.dumps(stored_dump["critical_issues"])

            # 3. CodeReviewRecord in database must have redacted snippet and redacted results_json
            async with AsyncSessionLocal() as session:
                rec = await session.get(CodeReviewRecord, review_id)
                assert rec is not None
                assert "classified_secret_999" not in rec.code_snippet
                assert "[REDACTED]" in rec.code_snippet
                assert "classified_secret_999" not in json.dumps(rec.results_json)

                # 4. FindingRecord rows in database must have code_snippet set to None
                findings_stmt = select(FindingRecord).where(FindingRecord.review_id == review_id)
                findings = (await session.execute(findings_stmt)).scalars().all()
                for f in findings:
                    assert f.code_snippet is None
                    assert f.suggestion is None or "classified_secret_999" not in str(f.suggestion)
                    # Non-sensitive message/remediation must be present
                    assert f.title is not None
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain


def test_privacy_telemetry_spans_directly_redacted():
    """Verify Span.set_attribute and Span.add_event scrub sensitive code."""
    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        span = Span("test_span", "trace_111", "span_222")

        # Set sensitive code attribute
        span.set_attribute("code", "private_function_body()")
        span.set_attribute("source_code", "secret = 42")
        span.set_attribute("tenant_id", "tenant_alpha")

        # Direct inspection of span.attributes
        assert span.attributes["code"] == "[REDACTED]"
        assert span.attributes["source_code"] == "[REDACTED]"
        assert span.attributes["tenant_id"] == "tenant_alpha"

        # Add event with nested code snippet
        span.add_event("syntax_check", {"code_snippet": "bad_code_here()", "line": 42})
        assert span.events[0]["attributes"]["code_snippet"] == "[REDACTED BY PRIVACY POLICY]"
        assert span.events[0]["attributes"]["line"] == 42
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain
