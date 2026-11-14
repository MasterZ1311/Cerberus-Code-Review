"""
Security, API Key Generation, Authentication, and Rate Limiting.
"""

import hashlib
import hmac
import logging
import secrets
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple
from cerberus.config import settings

logger = logging.getLogger("cerberus.security")


def timing_safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing side-channel attacks."""
    if a is None or b is None:
        return False
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


def generate_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Computes standard sha256 HMAC signature for outgoing webhooks."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_github_signature(
    payload_bytes: bytes,
    signature_header: Optional[str],
    secret: Optional[str]
) -> bool:
    """
    Validates GitHub X-Hub-Signature-256 HMAC SHA-256 webhook signatures.
    Returns True if valid, False otherwise.
    """
    if not signature_header or not secret:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_sig = signature_header[len(prefix):].strip().lower()
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    computed_sig = mac.hexdigest().lower()

    return hmac.compare_digest(expected_sig.encode("utf-8"), computed_sig.encode("utf-8"))


def generate_api_key(name: str = "default") -> Tuple[str, str, str]:
    """
    Generates a secure API key.
    Returns: (raw_key, key_hash, prefix)
    """
    token = secrets.token_hex(24)
    prefix = settings.API_KEY_PREFIX
    raw_key = f"{prefix}{token}"
    key_hash = hash_api_key(raw_key)
    return raw_key, key_hash, prefix


def hash_api_key(key: str) -> str:
    """Computes SHA-256 hash of API key for safe database storage."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{key}".encode("utf-8")).hexdigest()


def calculate_shannon_entropy(data: str) -> float:
    """
    Computes Shannon entropy (bits per character) of a string to detect weak/predictable keys.
    Random hex tokens have entropy ~3.8-4.0.
    """
    if not data:
        return 0.0
    import math
    from collections import Counter
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def verify_key_entropy(key: str, min_entropy: float = 3.0) -> bool:
    """Verifies that an API key possesses sufficient cryptographic entropy."""
    if not key or len(key) < 16:
        return False
    return calculate_shannon_entropy(key) >= min_entropy


class RateLimiter:
    """
    Two-Tier Sliding-Window Rate Limiter.
    Supports atomic distributed sliding-window tracking via Redis Sorted Sets (ZADD, ZREMRANGEBYSCORE, ZCARD)
    with seamless local bounded in-memory sliding-window fallback.
    """
    def __init__(self, limit_per_hour: int = 100, max_tracked: Optional[int] = None, redis_url: Optional[str] = None):
        self.limit = limit_per_hour
        self.max_tracked = max_tracked if max_tracked is not None else settings.RATE_LIMIT_MAX_TRACKED
        self.requests: OrderedDict[str, List[float]] = OrderedDict()
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis_client = None

    async def connect(self, redis_client=None) -> None:
        """Connect to Redis for distributed multi-worker rate limiting."""
        if redis_client is not None:
            self._redis_client = redis_client
            return

        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=1.5
            )
            await client.ping()
            self._redis_client = client
            logger.info("Connected distributed Redis RateLimiter successfully.")
        except Exception as e:
            logger.debug(f"Distributed Redis rate limiting not available ({e}). Using robust in-memory sliding window.")
            self._redis_client = None

    async def close(self) -> None:
        """Close connection to distributed Redis rate limiter."""
        if self._redis_client:
            try:
                await self._redis_client.close()
            except Exception:
                pass
            self._redis_client = None

    def purge_expired(self) -> int:
        """Purge all tracking keys that have no timestamps or whose timestamps are all expired."""
        now = time.time()
        one_hour_ago = now - 3600
        purged = 0
        keys_to_remove = []
        for ident, timestamps in list(self.requests.items()):
            active = [ts for ts in timestamps if ts > one_hour_ago]
            if not active:
                keys_to_remove.append(ident)
            else:
                self.requests[ident] = active
        for ident in keys_to_remove:
            if ident in self.requests:
                del self.requests[ident]
                purged += 1
        return purged

    def is_allowed(self, identifier: Optional[str] = None) -> Tuple[bool, int, int]:
        """
        Check whether request is permitted in local bounded in-memory sliding window.
        Returns: (allowed, remaining, retry_after_seconds)
        """
        ident = str(identifier or "anonymous")
        now = time.time()
        one_hour_ago = now - 3600

        # Prune older timestamps
        if ident in self.requests:
            self.requests[ident] = [ts for ts in self.requests[ident] if ts > one_hour_ago]
            if len(self.requests[ident]) == 0:
                del self.requests[ident]

        # If identifier not tracked yet and at capacity, run sweep and evict if needed
        if ident not in self.requests:
            if len(self.requests) >= self.max_tracked:
                self.purge_expired()
                while len(self.requests) >= self.max_tracked and self.requests:
                    self.requests.popitem(last=False)

        current_timestamps = self.requests.get(ident, [])
        current_count = len(current_timestamps)
        if current_count >= self.limit:
            oldest_ts = current_timestamps[0]
            retry_after = int(oldest_ts + 3600 - now) + 1
            return False, 0, max(1, retry_after)

        if ident not in self.requests:
            self.requests[ident] = []
        self.requests[ident].append(now)
        self.requests.move_to_end(ident)
        remaining = self.limit - (current_count + 1)
        return True, remaining, 0

    async def is_allowed_async(self, identifier: Optional[str] = None) -> Tuple[bool, int, int]:
        """
        Check rate limit. If distributed Redis client is available, executes atomic
        sliding-window verification across all workers. Falls back gracefully to in-memory.
        """
        ident = str(identifier or "anonymous")
        if self._redis_client:
            try:
                now = time.time()
                one_hour_ago = now - 3600
                key = f"cvai:ratelimit:{ident}"

                pipe = self._redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, one_hour_ago)
                pipe.zcard(key)
                pipe.zrange(key, 0, 0, withscores=True)
                results = await pipe.execute()

                current_count = results[1]
                oldest_entries = results[2]

                if current_count >= self.limit:
                    oldest_ts = oldest_entries[0][1] if oldest_entries else now
                    retry_after = int(oldest_ts + 3600 - now) + 1
                    return False, 0, max(1, retry_after)

                # Add current request timestamp
                pipe2 = self._redis_client.pipeline()
                member_id = f"{now}:{secrets.token_hex(4)}"
                pipe2.zadd(key, {member_id: now})
                pipe2.expire(key, 3600)
                await pipe2.execute()

                remaining = self.limit - (current_count + 1)
                return True, max(0, remaining), 0
            except Exception as e:
                logger.warning(f"Redis rate limit check failed ({e}); falling back to local memory.")

        # Fallback to local in-memory sliding window
        return self.is_allowed(identifier)


# Singleton rate limiter
rate_limiter = RateLimiter(limit_per_hour=settings.RATE_LIMIT_PER_HOUR, max_tracked=settings.RATE_LIMIT_MAX_TRACKED)
