"""
Health and Readiness Probes.
No authentication required to allow monitoring systems, k8s, and load balancers to poll.
"""

import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy import text
from cerberus import __version__
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal
from cerberus.models.schemas import HealthResponse

logger = logging.getLogger("cerberus.health")
router = APIRouter(tags=["Health"])
START_TIME = time.time()


@router.get("/api/v1/health", response_model=HealthResponse)
@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System liveness and readiness health check with live database and cache ping."""
    db_status = "connected"
    overall_status = "healthy"

    # 1. Live Database Ping
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Database health check probe failed: {e}")
        db_status = "disconnected"
        overall_status = "degraded"

    # 2. Live Cache Probe
    cache_status = "in_memory_lru"
    if cache_manager.enabled and cache_manager.redis_client:
        try:
            await cache_manager.redis_client.ping()
            cache_status = "redis"
        except Exception as e:
            logger.warning(f"Redis health check probe failed: {e}")
            cache_status = "disconnected"
            overall_status = "degraded"
    elif not cache_manager.enabled:
        cache_status = "disabled"

    return HealthResponse(
        status=overall_status,
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        database=db_status,
        cache=cache_status,
        active_agents=settings.enabled_agents_list,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/api/v1/ready")
@router.get("/ready")
async def readiness_check():
    """System readiness probe for traffic routing."""
    return {"status": "ready"}
