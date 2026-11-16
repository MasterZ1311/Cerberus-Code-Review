"""
Multi-Tenant Usage & Billing Quota Management for cerberus</>.
Tracks, meters, and enforces monthly review consumption per tenant across tiers.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("cerberus.core.quota")

# Default tier quotas (monthly review allowances)
TIER_MONTHLY_LIMITS: Dict[str, int] = {
    "free": 100,
    "pro": 5_000,
    "team": 2_500,
    "enterprise": 100_000,
    "unlimited": 10_000_000,
}


class TenantQuotaManager:
    """Tracks and enforces monthly review usage quotas per tenant."""

    def __init__(self):
        # In-memory storage: { "tenant_id:YYYY-MM": count }
        self._usage: Dict[str, int] = {}
        # Tenant configured tiers: { "tenant_id": "pro" }
        self._tenant_tiers: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    def _get_period_key(self, tenant_id: str) -> str:
        """Constructs period key for the current UTC month: tenant:YYYY-MM."""
        now = datetime.now(UTC)
        period = now.strftime("%Y-%m")
        return f"{tenant_id}:{period}"

    def get_tier(self, tenant_id: str) -> str:
        """Returns the tier for the given tenant (defaults to 'free')."""
        return self._tenant_tiers.get(tenant_id, "free").lower()

    def set_tier(self, tenant_id: str, tier: str) -> None:
        """Sets or upgrades the tier for the given tenant."""
        normalized = tier.strip().lower()
        if normalized not in TIER_MONTHLY_LIMITS:
            normalized = "free"
        self._tenant_tiers[tenant_id] = normalized
        logger.info("Updated tenant '%s' tier to '%s'", tenant_id, normalized)

    def get_tier_limit(self, tier: str) -> int:
        """Returns the monthly limit for a tier."""
        return TIER_MONTHLY_LIMITS.get(tier.strip().lower(), TIER_MONTHLY_LIMITS["free"])

    async def check_quota(self, tenant_id: str, tier: Optional[str] = None) -> Tuple[bool, int, int]:
        """
        Checks whether the tenant has remaining quota for the current month.
        Returns (allowed, current_count, limit).
        """
        effective_tier = (tier or self.get_tier(tenant_id)).lower()
        limit = TIER_MONTHLY_LIMITS.get(effective_tier, TIER_MONTHLY_LIMITS["free"])
        key = self._get_period_key(tenant_id)

        async with self._lock:
            current = self._usage.get(key, 0)

        allowed = current < limit
        return allowed, current, limit

    async def record_review(self, tenant_id: str) -> int:
        """
        Increments the monthly usage counter for the tenant.
        Returns the new total usage count.
        """
        key = self._get_period_key(tenant_id)
        async with self._lock:
            new_count = self._usage.get(key, 0) + 1
            self._usage[key] = new_count
            return new_count

    async def get_quota_status(self, tenant_id: str) -> Dict[str, Any]:
        """Returns full quota status and analytics for the given tenant."""
        tier = self.get_tier(tenant_id)
        limit = TIER_MONTHLY_LIMITS.get(tier, TIER_MONTHLY_LIMITS["free"])
        key = self._get_period_key(tenant_id)

        async with self._lock:
            current = self._usage.get(key, 0)

        remaining = max(0, limit - current)
        pct_used = round((current / limit) * 100, 1) if limit > 0 else 0.0

        now = datetime.now(UTC)
        # Next month reset
        if now.month == 12:
            reset_date = datetime(now.year + 1, 1, 1, tzinfo=UTC)
        else:
            reset_date = datetime(now.year, now.month + 1, 1, tzinfo=UTC)

        return {
            "tenant_id": tenant_id,
            "tier": tier,
            "billing_period": now.strftime("%Y-%m"),
            "used": current,
            "limit": limit,
            "remaining": remaining,
            "percent_used": pct_used,
            "resets_at": reset_date.isoformat(),
            "status": "active" if remaining > 0 else "quota_exceeded",
        }

    async def reset_usage(self, tenant_id: str) -> None:
        """Resets current month's usage (e.g. for testing or plan rollover)."""
        key = self._get_period_key(tenant_id)
        async with self._lock:
            self._usage[key] = 0


# Global singleton instance
quota_manager = TenantQuotaManager()
tenant_quota_manager = quota_manager
