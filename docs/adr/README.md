# Architecture Decision Records (ADRs)

This directory documents key architectural decisions made throughout the lifecycle of the Cerberus Multi-Agent Code Review platform.

Each record outlines the context, considered alternatives, architectural decision, and subsequent consequences.

---

## Index of Architectural Decisions

| ADR | Title | Date | Status |
|---|---|---|---|
| [ADR-0001](0001-python-asyncio-architecture.md) | Python AsyncIO & Event Loop Concurrency | 2026-01-15 | **Accepted** |
| [ADR-0002](0002-redis-lua-atomic-rate-limiting.md) | Redis Lua Scripting for Atomic Rate Limiting | 2026-02-01 | **Accepted** |
| [ADR-0003](0003-zero-config-heuristic-engine.md) | Offline Zero-Config AST Heuristic Engine as Default | 2026-02-15 | **Accepted** |
| [ADR-0004](0004-distributed-singleflight-deduplication.md) | Distributed SingleFlight for Cluster-Wide Coalescing | 2026-03-01 | **Accepted** |
| [ADR-0005](0005-dual-database-sqlite-postgres.md) | Dual-Mode Persistence: SQLite Local & PostgreSQL Production | 2026-03-15 | **Accepted** |
| [ADR-0006](0006-cosign-keyless-supply-chain.md) | Sigstore Cosign Keyless Signing & Digest Pinning | 2026-04-01 | **Accepted** |
