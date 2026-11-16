"""
Data Retention and Privacy Purge Lifecycle Management.
Provides Distributed-Locked Retention Enforcement, Prometheus Metrics, and Audit Logging.
Can be executed as an automated background scheduler or as an external Kubernetes CronJob.
"""

import asyncio
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import delete, select

from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.telemetry import (
    RETENTION_LAST_RUN_TIMESTAMP_SECONDS,
    RETENTION_PURGED_RECORDS_TOTAL,
    RETENTION_RUNS_TOTAL,
)
from cerberus.models.database import CodeReviewRecord, FindingRecord, ReviewFeedbackRecord

logger = logging.getLogger("cerberus.retention")

_local_retention_lock = asyncio.Lock()
RETENTION_DISTRIBUTED_LOCK_KEY = "cvai:retention:lock"
RETENTION_LOCK_TTL_SECONDS = 300


async def run_retention_purge(retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Executes a data retention purge across database records older than retention_days.
    Uses distributed Redis locking (with in-memory fallback) to prevent concurrent runs across workers.
    Updates Prometheus retention metrics and emits structured audit logs.
    """
    days = retention_days if retention_days is not None else settings.DATA_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=days)
    lock_acquired = False
    redis_conn = cache_manager.redis_client

    # 1. Distributed lock acquisition
    if redis_conn:
        try:
            lock_acquired = bool(
                await redis_conn.set(
                    RETENTION_DISTRIBUTED_LOCK_KEY,
                    "locked",
                    ex=RETENTION_LOCK_TTL_SECONDS,
                    nx=True,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to acquire Redis retention lock: {e}; falling back to local lock.")
            lock_acquired = False

    if not lock_acquired:
        if _local_retention_lock.locked():
            logger.info("Retention purge already in progress on this instance. Skipping run.")
            return {
                "status": "skipped",
                "reason": "lock_held",
                "message": "Retention purge already in progress.",
            }
        await _local_retention_lock.acquire()
        lock_held_locally = True
    else:
        lock_held_locally = False

    start_ts = time.time()
    logger.info(f"Starting data retention purge for records older than {days} days (cutoff: {cutoff.isoformat()}).")

    try:
        async with AsyncSessionLocal() as session:
            # Query IDs of reviews to purge
            stmt_ids = select(CodeReviewRecord.id).where(CodeReviewRecord.created_at < cutoff)
            result_ids = await session.execute(stmt_ids)
            review_ids = [r[0] for r in result_ids.all()]

            findings_count = 0
            feedback_count = 0
            reviews_count = 0

            if review_ids:
                # 2. Delete child review feedback
                stmt_feedback = delete(ReviewFeedbackRecord).where(ReviewFeedbackRecord.review_id.in_(review_ids))
                res_feedback = await session.execute(stmt_feedback)
                feedback_count = getattr(res_feedback, "rowcount", 0) or 0

                # 3. Delete child review findings
                stmt_findings = delete(FindingRecord).where(FindingRecord.review_id.in_(review_ids))
                res_findings = await session.execute(stmt_findings)
                findings_count = getattr(res_findings, "rowcount", 0) or 0

                # 4. Delete parent code review records
                stmt_reviews = delete(CodeReviewRecord).where(CodeReviewRecord.id.in_(review_ids))
                res_reviews = await session.execute(stmt_reviews)
                reviews_count = getattr(res_reviews, "rowcount", 0) or 0

                await session.commit()

        duration = time.time() - start_ts
        RETENTION_RUNS_TOTAL.labels(status="success").inc()
        RETENTION_PURGED_RECORDS_TOTAL.labels(entity="reviews").inc(reviews_count)
        RETENTION_PURGED_RECORDS_TOTAL.labels(entity="findings").inc(findings_count)
        RETENTION_PURGED_RECORDS_TOTAL.labels(entity="feedback").inc(feedback_count)
        RETENTION_LAST_RUN_TIMESTAMP_SECONDS.set(time.time())

        logger.info(
            f"Retention purge completed in {duration:.2f}s. "
            f"Purged: {reviews_count} reviews, {findings_count} findings, {feedback_count} feedback."
        )

        return {
            "status": "success",
            "retention_days": days,
            "cutoff": cutoff.isoformat(),
            "reviews_purged": reviews_count,
            "findings_purged": findings_count,
            "feedback_purged": feedback_count,
            "duration_seconds": round(duration, 3),
        }

    except Exception as e:
        RETENTION_RUNS_TOTAL.labels(status="failure").inc()
        logger.error(f"Retention purge failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "retention_days": days,
        }
    finally:
        if redis_conn and lock_acquired:
            try:
                await redis_conn.delete(RETENTION_DISTRIBUTED_LOCK_KEY)
            except Exception:
                pass
        if lock_held_locally:
            _local_retention_lock.release()


async def retention_lifecycle_worker(interval_seconds: int = 86400) -> None:
    """Continuous background worker executing retention purge periodically."""
    logger.info(f"Retention lifecycle background worker started (interval: {interval_seconds}s).")
    while True:
        try:
            await run_retention_purge()
        except Exception as e:
            logger.warning(f"Unhandled error in retention background worker: {e}")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # Allows invoking directly: python -m cerberus.core.retention
    import asyncio

    res = asyncio.run(run_retention_purge())
    print(res)
    if res.get("status") == "failed":
        sys.exit(1)
    sys.exit(0)
