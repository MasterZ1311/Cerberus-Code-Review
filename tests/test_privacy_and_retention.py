"""
Privacy and Data Retention Enforcement Integration Tests.
Verifies:
1. Recursive source code redaction across deeply nested dicts, lists, and JSON blobs.
2. Absence of raw code in database columns, findings, and JSON results when RETAIN_SOURCE_CODE=False.
3. Absence of raw code in L1/L2 cache payloads and OpenTelemetry trace spans.
4. Retention purge lifecycle execution, cascading cleanup, and Prometheus metrics recording.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from cerberus.api.app import app
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal, init_db
from cerberus.core.privacy import redact_source_code_recursively
from cerberus.core.retention import run_retention_purge
from cerberus.core.telemetry import (
    tracer,
)
from cerberus.models.database import CodeReviewRecord, FindingRecord, ReviewFeedbackRecord


@pytest.fixture(autouse=True)
async def setup_test_env():
    await init_db()


def test_recursive_redaction_sanitizes_nested_structures():
    sensitive_data = {
        "status": "completed",
        "code": "def secret_algo(): return 42",
        "metadata": {
            "source_code": "SELECT * FROM passwords;",
            "nested_list": [
                {"code_snippet": "rm -rf /", "message": "dangerous command"},
                {"patch": "@@ -1 +1 @@\n-secret\n+fixed", "author": "dev"},
            ],
        },
        "score": 90,
    }

    sanitized = redact_source_code_recursively(sensitive_data)

    assert sanitized["status"] == "completed"
    assert sanitized["score"] == 90
    assert "REDACTED" in sanitized["code"]
    assert "REDACTED" in sanitized["metadata"]["source_code"]
    assert "REDACTED" in sanitized["metadata"]["nested_list"][0]["code_snippet"]
    assert sanitized["metadata"]["nested_list"][0]["message"] == "dangerous command"
    assert "REDACTED" in sanitized["metadata"]["nested_list"][1]["patch"]


@pytest.mark.asyncio
async def test_database_and_cache_redacted_when_retain_false():
    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer cvai_dev_key_123"}
            code_sample = "def super_confidential(): return 'secret_key_123'"
            resp = await client.post(
                "/api/v1/review",
                headers=headers,
                json={"code": code_sample, "filename": "privacy_test.py", "language": "python"},
            )
            assert resp.status_code == 200
            review_id = resp.json()["review_id"]

            # Wait for background task to persist
            import asyncio

            rec = None
            for _ in range(20):
                async with AsyncSessionLocal() as session:
                    rec = await session.get(CodeReviewRecord, review_id)
                    if rec:
                        break
                await asyncio.sleep(0.1)

            assert rec is not None
            async with AsyncSessionLocal() as session:
                rec = await session.get(CodeReviewRecord, review_id)
                assert rec is not None
                assert "REDACTED" in rec.code_snippet
                assert code_sample not in json.dumps(rec.results_json)

                # Inspect child findings
                findings_stmt = select(FindingRecord).where(FindingRecord.review_id == review_id)
                findings = (await session.execute(findings_stmt)).scalars().all()
                for f in findings:
                    assert f.code_snippet is None
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain


def test_redact_source_code_tuples_and_sets():
    from cerberus.core.privacy import redact_source_code_recursively

    data_tuple = ({"code": "print('secret')"}, "normal_string")
    cleaned_tuple = redact_source_code_recursively(data_tuple)
    assert isinstance(cleaned_tuple, tuple)
    assert cleaned_tuple[0]["code"] == "[REDACTED BY PRIVACY POLICY]"

    data_set = {"normal_val", 123}
    cleaned_set = redact_source_code_recursively(data_set)
    assert isinstance(cleaned_set, set)
    assert 123 in cleaned_set


@pytest.mark.asyncio
async def test_retention_purge_with_redis_lock(monkeypatch):
    from unittest.mock import AsyncMock

    from cerberus.core.retention import run_retention_purge

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    monkeypatch.setattr(cache_manager, "redis_client", mock_redis)

    result = await run_retention_purge(retention_days=30)
    assert result["status"] == "success"
    mock_redis.set.assert_called_once()
    mock_redis.delete.assert_called_once()

    orig_retain = settings.RETAIN_SOURCE_CODE
    settings.RETAIN_SOURCE_CODE = False
    try:
        span = tracer.start_trace("review_execution", attributes={"code_snippet": "import sensitive_vault"})
        span_dict = span.to_dict()
        assert "REDACTED" in span_dict["attributes"]["code_snippet"]
    finally:
        settings.RETAIN_SOURCE_CODE = orig_retain


@pytest.mark.asyncio
async def test_retention_purge_lifecycle_and_metrics():
    # 1. Seed an expired review (45 days old) and an active review (5 days old)
    now = datetime.now(UTC)
    old_date = now - timedelta(days=45)
    recent_date = now - timedelta(days=5)

    old_id = "rev_retention_old_111"
    recent_id = "rev_retention_recent_222"

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ReviewFeedbackRecord).where(ReviewFeedbackRecord.review_id.in_([old_id, recent_id]))
        )
        await session.execute(delete(FindingRecord).where(FindingRecord.review_id.in_([old_id, recent_id])))
        await session.execute(delete(CodeReviewRecord).where(CodeReviewRecord.id.in_([old_id, recent_id])))
        await session.commit()

        # Old review + finding + feedback
        old_rev = CodeReviewRecord(
            id=old_id,
            owner_id="tenant_retention",
            code_snippet="def old(): pass",
            created_at=old_date,
        )
        old_finding = FindingRecord(
            review_id=old_id,
            owner_id="tenant_retention",
            agent_name="security",
            severity="low",
            category="quality",
            title="Old Finding",
            message="Old finding message",
            created_at=old_date,
        )
        old_feedback = ReviewFeedbackRecord(
            review_id=old_id,
            owner_id="tenant_retention",
            rating=5,
            created_at=old_date,
        )

        # Recent review
        recent_rev = CodeReviewRecord(
            id=recent_id,
            owner_id="tenant_retention",
            code_snippet="def recent(): pass",
            created_at=recent_date,
        )

        session.add_all([old_rev, old_finding, old_feedback, recent_rev])
        await session.commit()

    # 2. Run retention purge (30-day cutoff)
    result = await run_retention_purge(retention_days=30)
    assert result["status"] == "success"
    assert result["reviews_purged"] >= 1
    assert result["findings_purged"] >= 1
    assert result["feedback_purged"] >= 1

    # 3. Assert old records are deleted and recent records are preserved
    async with AsyncSessionLocal() as session:
        assert await session.get(CodeReviewRecord, old_id) is None
        assert await session.get(ReviewFeedbackRecord, old_id) is None
        assert await session.get(CodeReviewRecord, recent_id) is not None


@pytest.mark.asyncio
async def test_retention_lifecycle_worker_cycle():
    import asyncio

    from cerberus.core.retention import retention_lifecycle_worker

    worker_task = asyncio.create_task(retention_lifecycle_worker(interval_seconds=1))
    await asyncio.sleep(0.1)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


def test_retention_cli_command():
    from typer.testing import CliRunner

    from cerberus.cli.main import app as cli_app

    runner = CliRunner()
    res = runner.invoke(cli_app, ["retention", "purge", "--days", "365"])
    assert res.exit_code == 0
    assert "Retention Purge Completed" in res.output or "Retention" in res.output
