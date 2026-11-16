"""
Two-Tier Caching System: Redis with Automatic In-Memory Fallback.
Features SingleFlight Stampede (Thundering Herd) Protection,
Transparent Payload Compression, and SHA-256 Request Fingerprinting.
Includes Short-Lived Scoped One-Time Stream Token Management.
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
import zlib
from collections import OrderedDict
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional, Set, TypeVar

from cerberus.config import settings
from cerberus.core.privacy import redact_source_code_recursively

logger = logging.getLogger("cerberus.cache")

T = TypeVar("T")

LUA_ATOMIC_GETDEL = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
end
return val
"""


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
        self.redis_client: Optional[Any] = None
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._stream_tokens: Dict[str, Dict[str, Any]] = {}
        self._token_lock = asyncio.Lock()
        self._local_subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._subscribers_lock = asyncio.Lock()
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

            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1.5)
            # Ping to verify
            await client.ping()
            self.redis_client = client
            logger.info("Connected to Redis cache successfully.")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}). Using robust In-Memory LRU Cache.")
            self.redis_client = None

    async def close(self) -> None:
        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception:
                pass
            self.redis_client = None

    def compute_cache_key(
        self,
        code: Optional[str],
        language: Optional[str] = "python",
        agents: Optional[List[str]] = None,
        filename: Optional[str] = None,
        context: Optional[Any] = None,
        config: Optional[Any] = None,
        ruleset_version: Optional[str] = None,
    ) -> str:
        """Generate deterministic SHA-256 fingerprint for code and execution parameters."""
        normalized_code = (code or "").strip().replace("\r\n", "\n")
        safe_lang = (language or "python").lower()
        agents_str = ",".join(sorted(agents or []))

        ctx_dict = (
            context.model_dump()
            if (context is not None and hasattr(context, "model_dump"))
            else (context if isinstance(context, dict) else {})
        )
        cfg_dict = (
            config.model_dump()
            if (config is not None and hasattr(config, "model_dump"))
            else (config if isinstance(config, dict) else {})
        )
        ctx_str = json.dumps(ctx_dict, sort_keys=True) if ctx_dict else ""
        cfg_str = json.dumps(cfg_dict, sort_keys=True) if cfg_dict else ""
        fn_str = (filename or "").strip()
        ver_str = (ruleset_version or "").strip()

        payload = f"{safe_lang}:{agents_str}:{fn_str}:{ctx_str}:{cfg_str}:{ver_str}:{normalized_code}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"cvai:cache:{digest}"

    def _encode_payload(self, value: Dict[str, Any]) -> str:
        """Serializes payload with automatic zlib compression for large objects and recursive privacy redaction."""
        # Source code retention enforcement: recursively scrub raw source code
        val_copy = dict(value)
        if not getattr(settings, "RETAIN_SOURCE_CODE", False):
            val_copy = redact_source_code_recursively(val_copy)

        raw_json = json.dumps(val_copy)
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

        self._memory_cache[key] = {"data": value, "expires_at": time.time() + ttl}

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

    def invalidate(self, key: str) -> bool:
        """Synchronously evict an item from L1 in-memory cache."""
        if key in self._memory_cache:
            del self._memory_cache[key]
            return True
        return False

    async def invalidate_async(self, key: str) -> bool:
        """Evict an item from both L1 in-memory cache and L2 Redis."""
        removed = self.invalidate(key)
        if self.redis_client:
            try:
                res = await self.redis_client.delete(key)
                if res > 0:
                    removed = True
            except Exception as e:
                logger.warning(f"Redis DELETE failed for key {key}: {e}")
        return removed

    # Async alias for standard cache delete API
    delete = invalidate_async

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
        self._stream_tokens.clear()
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

    async def create_stream_token(self, review_id: str, tenant_id: str, ttl_seconds: int = 60) -> str:
        """Generates a short-lived, scoped one-time token for SSE/WebSocket streaming."""
        token = f"st_{secrets.token_urlsafe(32)}"
        token_payload = {"review_id": review_id, "tenant_id": tenant_id, "expires_at": time.time() + ttl_seconds}
        if self.redis_client:
            try:
                await self.redis_client.set(f"cvai:stream_token:{token}", json.dumps(token_payload), ex=ttl_seconds)
                return token
            except Exception as e:
                logger.warning(f"Redis stream token write failed ({e}); fallback to memory.")

        self._stream_tokens[token] = token_payload
        return token

    async def consume_stream_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validates and atomically consumes a single-use stream token via Redis GETDEL/Lua.
        Guarantees that a token can NEVER be consumed twice under concurrency.
        """
        if not token or not token.strip():
            return None

        # 1. Try atomic Redis consumption first
        if self.redis_client:
            try:
                r_key = f"cvai:stream_token:{token}"
                val = None
                try:
                    # Redis 6.2+ native GETDEL
                    val = await self.redis_client.getdel(r_key)
                except Exception:
                    # Fallback to atomic Lua script evaluation
                    val = await self.redis_client.eval(LUA_ATOMIC_GETDEL, 1, r_key)

                if val:
                    data = json.loads(val)
                    if data.get("expires_at", 0) >= time.time():
                        return data
                    return None
            except Exception as e:
                logger.warning(f"Redis atomic stream token read failed: {e}")

        # 2. Concurrency-safe in-memory consumption protected by asyncio.Lock
        async with self._token_lock:
            now = time.time()
            if token in self._stream_tokens:
                entry = self._stream_tokens.pop(token)
                if entry.get("expires_at", 0) >= now:
                    return entry

        return None

    async def publish_review_event(self, review_id: str, event_data: Dict[str, Any]) -> None:
        """
        Publishes a review lifecycle event across application workers via Redis pub/sub.
        Also persists latest event in Redis and in-memory subscriber queues for late joiners.
        """
        payload_str = json.dumps(event_data)
        if self.redis_client:
            try:
                channel = f"cvai:review_events:{review_id}"
                await self.redis_client.publish(channel, payload_str)
                await self.redis_client.set(f"cvai:review_latest:{review_id}", payload_str, ex=300)
            except Exception as e:
                logger.warning(f"Redis pub/sub publish failed: {e}")

        # Dispatch to local in-memory subscribers
        async with self._subscribers_lock:
            queues = list(self._local_subscribers.get(review_id, set()))
        for q in queues:
            try:
                q.put_nowait(event_data)
            except Exception:
                pass

    async def subscribe_review_events(
        self, review_id: str, timeout_seconds: float = 30.0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribes to live review events across workers via Redis pub/sub with in-memory fallback.
        Ensures multi-worker horizontal scalability for SSE and WebSockets.
        """
        q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        async with self._subscribers_lock:
            if review_id not in self._local_subscribers:
                self._local_subscribers[review_id] = set()
            self._local_subscribers[review_id].add(q)

        pubsub = None
        listener_task = None
        if self.redis_client:
            try:
                pubsub = self.redis_client.pubsub()
                await pubsub.subscribe(f"cvai:review_events:{review_id}")

                async def _redis_listener():
                    try:
                        async for message in pubsub.listen():
                            if message and message.get("type") == "message":
                                raw_data = message.get("data")
                                if isinstance(raw_data, str):
                                    parsed = json.loads(raw_data)
                                    await q.put(parsed)
                    except (asyncio.CancelledError, Exception):
                        pass

                listener_task = asyncio.create_task(_redis_listener())
            except Exception as e:
                logger.warning(f"Redis pub/sub subscribe notice: {e}")

        try:
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                remaining = max(0.1, timeout_seconds - (time.time() - start_time))
                try:
                    event = await asyncio.wait_for(q.get(), timeout=min(remaining, 1.0))
                    yield event
                    if event.get("event") in ("review_completed", "completed", "error"):
                        break
                except TimeoutError:
                    continue
        finally:
            if listener_task:
                listener_task.cancel()
            if pubsub:
                try:
                    await pubsub.unsubscribe(f"cvai:review_events:{review_id}")
                    await pubsub.close()
                except Exception:
                    pass
            async with self._subscribers_lock:
                if review_id in self._local_subscribers:
                    self._local_subscribers[review_id].discard(q)
                    if not self._local_subscribers[review_id]:
                        del self._local_subscribers[review_id]


# Singleton cache instance
cache_manager = CacheManager()
