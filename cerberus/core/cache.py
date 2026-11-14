"""
Two-Tier Caching System: Redis with Automatic In-Memory Fallback.
Features SingleFlight Stampede (Thundering Herd) Protection,
Transparent Payload Compression, and SHA-256 Request Fingerprinting.
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
import zlib
from collections import OrderedDict
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar
from cerberus.config import settings

logger = logging.getLogger("cerberus.cache")

T = TypeVar("T")


class SingleFlight:
    """
    Coalesces identical concurrent asynchronous executions into a single shared invocation.
    Prevents cache stampedes and thundering herds under heavy concurrent load.
    """

    def __init__(self):
        self._in_flight: Dict[str, asyncio.Future] = {}
        self.coalesced_count = 0

    async def execute(self, key: str, coro_fn: Callable[[], Coroutine[Any, Any, T]]) -> T:
        if key in self._in_flight:
            self.coalesced_count += 1
            logger.debug(f"SingleFlight coalescing concurrent request for key: {key}")
            # Await identical in-flight task
            fut = self._in_flight[key]
            return await fut

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._in_flight[key] = fut

        try:
            res = await coro_fn()
            if not fut.done():
                fut.set_result(res)
            return res
        except BaseException as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            self._in_flight.pop(key, None)


class CacheManager:
    """
    High-performance two-tier cache with L1 in-memory LRU, L2 Redis,
    transparent zlib compression, and stampede protection.
    """

    COMPRESSION_THRESHOLD_BYTES = 8192  # 8 KB

    def __init__(self, max_items: Optional[int] = None):
        self.enabled = settings.CACHE_ENABLED
        self.ttl = settings.CACHE_TTL_SECONDS
        self.max_items = max_items if max_items is not None else settings.CACHE_MAX_ITEMS
        self.redis_client = None
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.singleflight = SingleFlight()
        self.stats = {
            "hits": 0,
            "misses": 0,
        }
        self.tier_stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "bytes_saved_by_compression": 0,
        }

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

    def _encode_payload(self, value: Dict[str, Any]) -> str:
        """Serializes payload with automatic zlib compression for large objects."""
        raw_json = json.dumps(value)
        if len(raw_json.encode("utf-8")) > self.COMPRESSION_THRESHOLD_BYTES:
            compressed = zlib.compress(raw_json.encode("utf-8"), level=6)
            b64_str = base64.b64encode(compressed).decode("ascii")
            self.tier_stats["bytes_saved_by_compression"] += max(0, len(raw_json) - len(b64_str))
            return f"__GZ__{b64_str}"
        return raw_json

    def _decode_payload(self, val: str) -> Dict[str, Any]:
        """Deserializes payload with transparent decompression if compressed."""
        if val.startswith("__GZ__"):
            b64_str = val[6:]
            compressed = base64.b64decode(b64_str.encode("ascii"))
            decompressed = zlib.decompress(compressed).decode("utf-8")
            return json.loads(decompressed)
        return json.loads(val)

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        # 1. Try In-Memory LRU (L1 Cache - Sub-millisecond)
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if entry["expires_at"] > time.time():
                self._memory_cache.move_to_end(key)
                self.tier_stats["l1_hits"] += 1
                self.stats["hits"] += 1
                return entry["data"]
            else:
                del self._memory_cache[key]

        # 2. Try Redis (L2 Cache)
        if self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val:
                    decoded = self._decode_payload(val)
                    self.tier_stats["l2_hits"] += 1
                    self.stats["hits"] += 1
                    # Populate L1 cache for subsequent instant access
                    self._set_memory(key, decoded, self.ttl)
                    return decoded
            except Exception as e:
                logger.warning(f"Redis GET failed: {e}")

        self.stats["misses"] += 1
        return None

    def _set_memory(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        """Internal L1 in-memory setter with LRU eviction."""
        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
        else:
            while len(self._memory_cache) >= self.max_items and self._memory_cache:
                self._memory_cache.popitem(last=False)

        self._memory_cache[key] = {
            "data": value,
            "expires_at": time.time() + ttl
        }

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        if not self.enabled:
            return

        ttl = ttl_seconds or self.ttl

        # 1. Set in Memory (L1)
        self._set_memory(key, value, ttl)

        # 2. Set in Redis (L2) with automatic compression
        if self.redis_client:
            try:
                payload_str = self._encode_payload(value)
                await self.redis_client.set(key, payload_str, ex=ttl)
            except Exception as e:
                logger.warning(f"Redis SET failed: {e}")

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
        self.stats = {
            "hits": 0,
            "misses": 0,
        }
        self.tier_stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "bytes_saved_by_compression": 0,
        }

    @property
    def hit_rate(self) -> float:
        total = self.stats["hits"] + self.stats["misses"]
        return (self.stats["hits"] / total * 100.0) if total > 0 else 0.0


# Singleton cache instance
cache_manager = CacheManager()
