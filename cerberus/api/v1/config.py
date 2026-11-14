"""
Configuration Management Endpoints.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from cerberus.api.dependencies import verify_api_key
from cerberus.config import settings

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])


class ConfigUpdateModel(BaseModel):
    enabled_agents: Optional[str] = None
    severity_threshold: Optional[str] = None
    blocking_mode: Optional[bool] = None


@router.get("")
async def get_configuration(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Retrieve active system configuration parameters with redacted secrets."""
    return {
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "enabled_agents": settings.enabled_agents_list,
        "cache_enabled": settings.CACHE_ENABLED,
        "cache_ttl_seconds": settings.CACHE_TTL_SECONDS,
        "severity_threshold": settings.SEVERITY_THRESHOLD,
        "blocking_mode": settings.BLOCKING_MODE,
        "rate_limit_per_hour": settings.RATE_LIMIT_PER_HOUR,
    }


@router.put("", status_code=status.HTTP_200_OK)
async def update_configuration(
    update: ConfigUpdateModel,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, str]:
    """Update runtime configuration settings."""
    if update.enabled_agents is not None:
        settings.ENABLED_AGENTS = update.enabled_agents
    if update.severity_threshold is not None:
        settings.SEVERITY_THRESHOLD = update.severity_threshold
    if update.blocking_mode is not None:
        settings.BLOCKING_MODE = update.blocking_mode

    return {"status": "success", "message": "Configuration updated successfully"}
