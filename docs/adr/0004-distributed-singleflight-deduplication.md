# ADR-0004: Distributed SingleFlight for Cluster-Wide Coalescing

## Status
**Accepted** (2026-03-01)

## Context
When webhooks arrive from GitHub or GitLab on large repositories, multiple CI matrix runners or duplicate webhook delivery events frequently send the exact same commit SHA for review simultaneously.
Without coalescing, N identical multi-agent reviews would execute in parallel across Kubernetes pods, consuming expensive LLM tokens, CPU, and database writes.

## Decision
We implemented `DistributedSingleFlight` in `cerberus/core/distributed_flight.py`:
- In-process deduplication via `asyncio.Future`.
- Distributed leader election via Redis `SET key pod_id NX EX ttl`.
- The elected leader executes the review pipeline and caches the result.
- Concurrent followers across all replica pods wait for the computed result or poll the result key.
- Graceful fallback to local in-memory SingleFlight if Redis is unreachable.

## Consequences
### Positive
- Up to 90% reduction in redundant LLM spend and database write load during webhook storms.
- Zero stampede or thundering-herd issues on cache misses.

### Negative
- Followers introduce small polling latency (~200ms) waiting for leader completion.
