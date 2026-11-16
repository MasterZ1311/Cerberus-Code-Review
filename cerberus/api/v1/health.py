"""
Health and Readiness Probes.
Truthful probes for monitoring systems, orchestrators, and load balancers.
"""

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
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
    """System liveness and detailed diagnostic probe with live database and cache status."""
    db_status = "connected"
    overall_status = "healthy"

    # 1. Live Database Ping
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Database health check probe failed: %s", e)
        db_status = "disconnected"
        overall_status = "degraded"

    # 2. Live Cache Probe
    cache_status = "in_memory_lru"
    if cache_manager.enabled and cache_manager.redis_client:
        try:
            await cache_manager.redis_client.ping()
            cache_status = "redis"
        except Exception as e:
            logger.warning("Redis health check probe failed: %s", e)
            cache_status = "disconnected"
            overall_status = "degraded"
    elif not cache_manager.enabled:
        cache_status = "disabled"

    return HealthResponse(
        status=overall_status,
        version=__version__,
        timestamp=datetime.now(UTC).isoformat(),
        database=db_status,
        cache=cache_status,
        active_agents=settings.enabled_agents_list,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/api/v1/ready")
@router.get("/api/v1/health/ready")
@router.get("/ready")
async def readiness_check(response: Response):
    """
    System readiness probe for traffic routing and load balancing.
    Fails truthfully with HTTP 503 if mandatory database or configured Redis connectivity is unavailable.
    """
    # 1. Database Connectivity Check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Readiness check failed: Database unavailable (%s)", e)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "unhealthy",
            "reason": "database_unavailable",
            "error": "Database connectivity check failed",
        }

    # 2. Redis Connectivity Check (enforced when Redis is configured or in production)
    redis_status = "not_configured"
    if cache_manager.enabled and (settings.REDIS_URL or settings.ENVIRONMENT.lower() in ("production", "prod")):
        if cache_manager.redis_client:
            try:
                await cache_manager.redis_client.ping()
                redis_status = "connected"
            except Exception as e:
                logger.error("Readiness check failed: Redis ping failed (%s)", e)
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                return {
                    "status": "not_ready",
                    "database": "connected",
                    "redis": "unhealthy",
                    "reason": "redis_unavailable",
                    "error": "Redis connectivity check failed",
                }
        elif settings.ENVIRONMENT.lower() in ("production", "prod") and settings.REDIS_URL:
            logger.error("Readiness check failed: Redis client not initialized in production")
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "status": "not_ready",
                "database": "connected",
                "redis": "uninitialized",
                "reason": "redis_uninitialized",
                "error": "Redis client is not connected",
            }

    return {"status": "ready", "database": "connected", "redis": redis_status}
