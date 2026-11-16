"""
Per-Key Rate Limiting with Tier-Based Quotas.
Provides granular rate limiting based on API key tier (free, pro, enterprise).
"""

import asyncio
import logging
import time
from typing import Dict, Tuple

from cerberus.config import settings

logger = logging.getLogger("cerberus.rate_limiter")


class TokenBucket:
    """Token bucket algorithm for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens refilled per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        async with self._lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            # Check if sufficient tokens available
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def get_remaining(self) -> int:
        """Get remaining tokens."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            current_tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            return int(current_tokens)


class PerKeyRateLimiter:
    """Rate limiter with per-key quotas based on tier."""

    def __init__(self):
        self.limiters: Dict[str, TokenBucket] = {}
        self.tier_limits: Dict[str, Tuple[int, int]] = {
            "free": (
                getattr(settings, "RATE_LIMIT_FREE_TIER", 100),
                3600,
            ),  # 100 requests/hour
            "pro": (getattr(settings, "RATE_LIMIT_PRO_TIER", 1000), 3600),  # 1000 requests/hour
            "enterprise": (
                getattr(settings, "RATE_LIMIT_ENTERPRISE_TIER", 10000),
                3600,
            ),  # 10k requests/hour
            "admin": (100000, 3600),  # Admins get very high limits
        }
        self._cleanup_interval = 3600  # Clean up old limiters every hour
        self._last_cleanup = time.time()

    async def check_limit(self, api_key: str, tier: str = "free") -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Args:
            api_key: API key identifier
            tier: Tier level (free, pro, enterprise, admin)

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        # Periodic cleanup of old limiters
        if time.time() - self._last_cleanup > self._cleanup_interval:
            await self._cleanup_old_limiters()

        # Get or create token bucket for this key
        if api_key not in self.limiters:
            quota, window = self.tier_limits.get(tier.lower(), self.tier_limits["free"])
            refill_rate = quota / window
            self.limiters[api_key] = TokenBucket(capacity=quota, refill_rate=refill_rate)

        # Attempt to consume token
        bucket = self.limiters[api_key]
        allowed = await bucket.consume(1)
        remaining = await bucket.get_remaining()

        # Calculate reset time (fixed 1 hour window)
        reset_seconds = 3600

        return allowed, remaining, reset_seconds

    async def _cleanup_old_limiters(self) -> None:
        """Remove limiters that haven't been used recently."""
        # Keep cleanup simple - remove limiters for keys that have full tokens (unused)
        keys_to_remove = []
        for key, bucket in self.limiters.items():
            if await bucket.get_remaining() >= bucket.capacity * 0.9:
                keys_to_remove.append(key)

        for key in keys_to_remove[:100]:  # Limit cleanup batch size
            del self.limiters[key]

        self._last_cleanup = time.time()
        if keys_to_remove:
            logger.debug("Cleaned up %s inactive rate limiters", len(keys_to_remove))


# Global instance
per_key_rate_limiter = PerKeyRateLimiter()
