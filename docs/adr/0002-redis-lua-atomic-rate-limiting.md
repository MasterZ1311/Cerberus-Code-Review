# ADR-0002: Redis Lua Scripting for Atomic Rate Limiting

## Status
**Accepted** (2026-02-01)

## Context
Standard API rate limit implementations often suffer from race conditions:
- **Check-then-act race conditions:** In distributed environments, two concurrent requests check their quota, see 1 slot remaining, and both proceed, exceeding the quota.
- **Fixed-window boundary attacks:** Users send 100 requests at 11:59 and another 100 at 12:00, bursting 200 requests within seconds.

## Decision
We implemented a sliding-window rate limiter powered by an atomic Redis Lua script (`LUA_SLIDING_WINDOW_RATE_LIMIT` in `cerberus/core/security.py`).
- Timestamps are stored in a Redis Sorted Set (`ZSET`).
- The Lua script executes atomically on the Redis server:
  1. Purges entries older than 3600s (`ZREMRANGEBYSCORE`).
  2. Counts active requests (`ZCARD`).
  3. Rejects if count >= limit, returning calculated `retry_after`.
  4. Appends current request (`ZADD`) and resets TTL (`EXPIRE`).
- If Redis is unavailable or disconnected, the system automatically falls back to an in-memory sliding window queue.

## Consequences
### Positive
- Zero race conditions across multiple Kubernetes pods.
- Smooth rate limiting without burst vulnerabilities.
- Safe token hashing (`SHA-256`) prevents leaking API keys in Redis key names.

### Negative
- Higher Redis memory consumption compared to a simple integer counter. Mitigated by setting a 1-hour TTL and running automated key cleanup.
