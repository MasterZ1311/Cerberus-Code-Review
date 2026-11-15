"""
Configuration Management Endpoints with Multi-Worker Database Persistence & Validation.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from cerberus.api.dependencies import require_scopes, verify_api_key
from cerberus.config import settings
from cerberus.core.database import AsyncSessionLocal
from cerberus.models.database import RuntimeConfigRecord

logger = logging.getLogger("cerberus.api.config")
router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
KNOWN_AGENTS = {
    "security",
    "performance",
    "quality",
    "architecture",
    "compliance",
    "dependency",
    "secret",
    "consensus",
    "code_fixer",
}


class ConfigUpdateModel(BaseModel):
    enabled_agents: Optional[str | List[str]] = None
    severity_threshold: Optional[str] = None
    blocking_mode: Optional[bool] = None


async def _load_persisted_config() -> Dict[str, str]:
    """Load runtime config from database if present."""
    config_dict: Dict[str, str] = {}
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(RuntimeConfigRecord)
            res = await session.execute(stmt)
            for rec in res.scalars().all():
                config_dict[rec.key] = rec.value
    except Exception as e:
        logger.debug(f"Could not load runtime config from DB: {e}")
    return config_dict


async def _persist_config_key(key: str, value: str) -> None:
    """Persist a single runtime configuration key to database."""
    try:
        async with AsyncSessionLocal() as session:
            rec = await session.get(RuntimeConfigRecord, key)
            if rec:
                rec.value = value
            else:
                session.add(RuntimeConfigRecord(key=key, value=value))
            await session.commit()
    except Exception as e:
        logger.warning(f"Could not persist config key '{key}' to DB: {e}")


@router.get("")
async def get_configuration(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Retrieve active system configuration parameters with redacted secrets."""
    db_config = await _load_persisted_config()
    severity = db_config.get("SEVERITY_THRESHOLD", settings.SEVERITY_THRESHOLD)
    blocking = (
        db_config.get("BLOCKING_MODE", "").lower() in ("true", "1")
        if "BLOCKING_MODE" in db_config
        else settings.BLOCKING_MODE
    )
    agents_str = db_config.get("ENABLED_AGENTS", settings.ENABLED_AGENTS)
    agents_list = [a.strip() for a in agents_str.split(",") if a.strip()]

    return {
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "enabled_agents": agents_list,
        "cache_enabled": settings.CACHE_ENABLED,
        "cache_ttl_seconds": settings.CACHE_TTL_SECONDS,
        "severity_threshold": severity,
        "blocking_mode": blocking,
        "rate_limit_per_hour": settings.RATE_LIMIT_PER_HOUR,
    }


@router.put("", status_code=status.HTTP_200_OK)
@router.patch("", status_code=status.HTTP_200_OK)
async def update_configuration(
    update: ConfigUpdateModel, api_key: str = Depends(require_scopes("admin"))
) -> Dict[str, str]:
    """Update runtime configuration settings with strict validation and database persistence."""
    if update.severity_threshold is not None:
        sev = update.severity_threshold.strip().lower()
        if sev not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity_threshold '{update.severity_threshold}'. Must be one of: {sorted(VALID_SEVERITIES)}",
            )
        settings.SEVERITY_THRESHOLD = sev
        await _persist_config_key("SEVERITY_THRESHOLD", sev)

    if update.enabled_agents is not None:
        if isinstance(update.enabled_agents, list):
            agent_names = [a.strip().lower() for a in update.enabled_agents if a.strip()]
        else:
            agent_names = [a.strip().lower() for a in update.enabled_agents.split(",") if a.strip()]
        for a in agent_names:
            if a not in KNOWN_AGENTS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown agent '{a}'. Valid agents are: {sorted(KNOWN_AGENTS)}",
                )
        settings.ENABLED_AGENTS = ",".join(agent_names)
        await _persist_config_key("ENABLED_AGENTS", settings.ENABLED_AGENTS)

    if update.blocking_mode is not None:
        settings.BLOCKING_MODE = update.blocking_mode
        await _persist_config_key("BLOCKING_MODE", str(update.blocking_mode))

    return {"status": "success", "message": "Configuration updated and persisted successfully"}
