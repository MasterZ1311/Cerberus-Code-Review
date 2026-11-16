"""
Multi-Tenant Organizations & Quota Management Router for cerberus</>.
Provides usage metrics, billing quota status, and tier provisioning.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from cerberus.api.dependencies import require_scopes, verify_api_key
from cerberus.core.quota import TIER_MONTHLY_LIMITS, quota_manager

router = APIRouter(prefix="/api/v1/tenants", tags=["Multi-Tenant & Quotas"])


class UpgradeTierRequest(BaseModel):
    """Payload to upgrade a tenant's billing tier."""

    tenant_id: Optional[str] = Field(default=None, description="Target tenant identifier (defaults to active tenant)")
    tier: str = Field(..., description="Target tier: 'free', 'team', 'pro', 'enterprise', 'unlimited'")


@router.get("/current", status_code=status.HTTP_200_OK)
async def get_current_tenant_quota(
    request: Request,
    token: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Returns the current tenant's usage metrics, active tier, and remaining monthly quota."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    return await quota_manager.get_quota_status(tenant_id)


@router.get("/tiers", status_code=status.HTTP_200_OK)
async def list_available_tiers(token: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Lists available subscription tiers and their monthly review limits."""
    return {
        "tiers": [
            {"tier": tier, "monthly_limit": limit, "description": f"{tier.title()} subscription plan"}
            for tier, limit in TIER_MONTHLY_LIMITS.items()
        ]
    }


@router.post("/upgrade", status_code=status.HTTP_200_OK)
async def upgrade_tenant_tier(
    payload: UpgradeTierRequest,
    request: Request,
    token: str = Depends(require_scopes("admin")),
) -> Dict[str, Any]:
    """Upgrades a tenant's plan tier (Requires 'admin' scope)."""
    target_tenant: str = str(payload.tenant_id or getattr(request.state, "tenant_id", "default") or "default")
    normalized_tier = payload.tier.lower().strip()
    if normalized_tier not in TIER_MONTHLY_LIMITS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_tier",
                "message": f"Tier '{payload.tier}' is invalid. Allowed: {list(TIER_MONTHLY_LIMITS.keys())}",
            },
        )

    quota_manager.set_tier(target_tenant, normalized_tier)
    status_info = await quota_manager.get_quota_status(target_tenant)
    return {
        "status": "success",
        "message": f"Tenant '{target_tenant}' upgraded to tier '{normalized_tier}'",
        "tenant_id": target_tenant,
        "tier": normalized_tier,
        "limit": status_info.get("limit", 100),
        "quota": status_info,
    }
