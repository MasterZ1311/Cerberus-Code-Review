"""
Distributed SingleFlight Deduplication with Redis & Local Fallback.
Prevents thundering-herd problem across multi-replica Kubernetes pods by electing a single
leader pod to compute expensive LLM/Agent reviews and broadcasting results to followers.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger("cerberus.distributed_flight")


class DistributedSingleFlight:
    """
    Coordinates distributed request deduplication across process boundaries.
    """

    def __init__(self, redis_client: Optional[Any] = None, ttl_seconds: int = 45):
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._local_in_flight: Dict[str, asyncio.Future] = {}
        self._local_lock = asyncio.Lock()
        self._node_id = str(uuid.uuid4())[:8]

    def set_redis(self, redis_client: Any) -> None:
        """Update or inject Redis client after initialization."""
        self._redis = redis_client

    async def execute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        timeout_seconds: float = 30.0,
    ) -> Any:
        """
        Execute compute_fn once across all replicas for the given key.
        If another request with the same key is already running, wait for its result.
        """
        # Normalize key hash for consistency
        norm_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        local_future: Optional[asyncio.Future] = None

        # 1. Check local in-process deduplication first
        async with self._local_lock:
            if norm_key in self._local_in_flight:
                logger.debug("Local SingleFlight coalescing request for key %s", norm_key[:12])
                local_future = self._local_in_flight[norm_key]
            else:
                loop = asyncio.get_running_loop()
                local_future = loop.create_future()
                self._local_in_flight[norm_key] = local_future

        # If we joined an already in-flight local request, await it
        if local_future.done():
            return local_future.result()

        # Check if we were NOT the creator of the future
        async with self._local_lock:
            is_leader_of_local = self._local_in_flight.get(norm_key) is local_future and not local_future.done()

        if not is_leader_of_local:
            try:
                return await asyncio.wait_for(local_future, timeout=timeout_seconds)
            except Exception as e:
                logger.warning("Follower waiting on local future encountered error: %s", e)
                raise

        # We are the local leader. Now coordinate with distributed Redis if available.
        redis_lock_key = f"dsflight:lock:{norm_key}"
        redis_res_key = f"dsflight:result:{norm_key}"

        if self._redis:
            try:
                # Attempt to acquire distributed lock (leader election among replicas)
                acquired = await self._redis.set(
                    redis_lock_key,
                    self._node_id,
                    nx=True,
                    ex=self._ttl,
                )

                if not acquired:
                    # Another pod is computing this. Wait and poll result key.
                    logger.info("Follower pod waiting for distributed result on %s", norm_key[:12])
                    poll_interval = 0.2
                    start_time = asyncio.get_running_loop().time()
                    while (asyncio.get_running_loop().time() - start_time) < timeout_seconds:
                        cached_res = await self._redis.get(redis_res_key)
                        if cached_res is not None:
                            try:
                                if isinstance(cached_res, bytes):
                                    cached_res = cached_res.decode("utf-8")
                                data = json.loads(cached_res)
                                if not local_future.done():
                                    local_future.set_result(data)
                                return data
                            except Exception as parse_err:
                                logger.warning("Failed to parse distributed result: %s", parse_err)
                                break
                        await asyncio.sleep(poll_interval)
                    logger.warning("Distributed wait timed out on %s; proceeding to compute locally", norm_key[:12])
            except Exception as redis_err:
                logger.debug("Redis distributed flight failed (%s); falling back to local computation", redis_err)

        # Execute the actual workload
        try:
            result = await compute_fn()

            # Store result in Redis for other pods to consume
            if self._redis:
                try:
                    payload = json.dumps(result) if not isinstance(result, str) else result
                    await self._redis.set(redis_res_key, payload, ex=self._ttl)
                    await self._redis.delete(redis_lock_key)
                except Exception as write_err:
                    logger.debug("Could not cache distributed flight result: %s", write_err)

            if not local_future.done():
                local_future.set_result(result)
            return result
        except Exception as exc:
            if not local_future.done():
                local_future.set_exception(exc)
            if self._redis:
                try:
                    await self._redis.delete(redis_lock_key)
                except Exception:
                    pass
            raise
        finally:
            async with self._local_lock:
                self._local_in_flight.pop(norm_key, None)
