# ADR-0005: Dual-Mode Persistence (SQLite Local & PostgreSQL Production)

## Status
**Accepted** (2026-03-15)

## Context
Developers working on individual laptops require zero-dependency setup (no local Docker or database installation required), whereas enterprise production Kubernetes deployments require high-availability, multi-replica concurrency, and connection pooling.

## Decision
We implemented a dialect-aware SQLAlchemy async engine abstraction (`cerberus/core/database.py`):
- Automatically switches between `aiosqlite` (for `sqlite:///`) and `asyncpg` (for `postgresql://`).
- SQLite uses WAL mode (`PRAGMA journal_mode=WAL`) and `PRAGMA busy_timeout=30000` to prevent database locks.
- PostgreSQL activates enterprise connection pooling (`pool_size=20`, `max_overflow=10`, `pool_recycle=3600`, `pool_pre_ping=True`).
- Schema migrations run through an integrated asynchronous versioned migration runner (`cerberus/core/migrations.py`).

## Consequences
### Positive
- Zero friction for local developers: works immediately with `cerberus.db`.
- Full enterprise scalability for production: point `DATABASE_URL` to an AWS RDS Aurora or Google Cloud SQL PostgreSQL instance.

### Negative
- Schema DDL must remain compatible across both dialects (e.g. avoiding proprietary vendor-specific SQL extensions).
