"""
Two-Tier Caching System: Redis with Automatic In-Memory Fallback.
Computes SHA-256 fingerprints to eliminate redundant LLM reviews.
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from cerberus.config import settings

logger = logging.getLogger("cerberus.cache")


class CacheManager:
    def __init__(self, max_items: Optional[int] = None):
        self.enabled = settings.CACHE_ENABLED
        self.ttl = settings.CACHE_TTL_SECONDS
        self.max_items = max_items if max_items is not None else settings.CACHE_MAX_ITEMS
        self.redis_client = None
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.stats = {"hits": 0, "misses": 0}

    async def connect(self) -> None:
        """Attempt connection to Redis; seamlessly fallback to in-memory if unavailable."""
        if not self.enabled:
            return

        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1.5
            )
            # Ping to verify
            await client.ping()
            self.redis_client = client
            logger.info("Connected to Redis cache successfully.")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}). Using robust In-Memory LRU Cache.")
            self.redis_client = None

    async def close(self) -> None:
        if self.redis_client:
            await self.redis_client.close()

    def compute_cache_key(self, code: Optional[str], language: Optional[str] = "python", agents: Optional[List[str]] = None) -> str:
        """Generate deterministic SHA-256 fingerprint for code and execution parameters."""
        normalized_code = (code or "").strip().replace("\r\n", "\n")
        safe_lang = (language or "python").lower()
        agents_str = ",".join(sorted(agents or []))
        payload = f"{safe_lang}:{agents_str}:{normalized_code}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"cvai:cache:{digest}"

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        # 1. Try Redis
        if self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val:
                    self.stats["hits"] += 1
                    return json.loads(val)
            except Exception as e:
                logger.warning(f"Redis GET failed: {e}")

        # 2. Try In-Memory LRU
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if entry["expires_at"] > time.time():
                self._memory_cache.move_to_end(key)
                self.stats["hits"] += 1
                return entry["data"]
            else:
                del self._memory_cache[key]

        self.stats["misses"] += 1
        return None

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        if not self.enabled:
            return

        ttl = ttl_seconds or self.ttl

        # 1. Set in Redis
        if self.redis_client:
            try:
                await self.redis_client.set(key, json.dumps(value), ex=ttl)
            except Exception as e:
                logger.warning(f"Redis SET failed: {e}")

        # 2. Always set in Memory as well for local resilience with LRU eviction
        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
        else:
            while len(self._memory_cache) >= self.max_items and self._memory_cache:
                self._memory_cache.popitem(last=False)

        self._memory_cache[key] = {
            "data": value,
            "expires_at": time.time() + ttl
        }

    def prune_expired(self) -> int:
        """Remove all expired entries from in-memory cache. Returns count of purged items."""
        now = time.time()
        expired_keys = [k for k, v in self._memory_cache.items() if v["expires_at"] <= now]
        for k in expired_keys:
            del self._memory_cache[k]
        return len(expired_keys)

    def clear(self) -> None:
        """Clear in-memory cache and reset statistics."""
        self._memory_cache.clear()
        self.stats = {"hits": 0, "misses": 0}

    @property
    def hit_rate(self) -> float:
        total = self.stats["hits"] + self.stats["misses"]
        return (self.stats["hits"] / total * 100.0) if total > 0 else 0.0


# Singleton cache instance
cache_manager = CacheManager()
