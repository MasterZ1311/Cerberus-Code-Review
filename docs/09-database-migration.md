# Database Architecture & Production PostgreSQL Migration Guide

Cerberus features dual-mode persistence architecture:
1. **Local Development / Embedded Mode:** High-concurrency asynchronous SQLite via `aiosqlite` with WAL mode and busy timeout.
2. **Production Multi-Replica Mode:** Enterprise PostgreSQL (14+) via `asyncpg` with connection pooling, multi-region read replicas, and zero-downtime migrations.

---

## 1. Engine Configuration & Dialect Routing

Cerberus automatically detects database connection strings and applies dialect-specific optimizations:

```python
# SQLite (Development)
DATABASE_URL="sqlite+aiosqlite:///./cerberus.db"

# PostgreSQL (Production)
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres-cluster.db.internal:5432/cerberus"
```

### PostgreSQL Enterprise Connection Pool Tuning
When `postgresql` is detected in `DATABASE_URL`, Cerberus initializes `SQLAlchemy` with:
- **`pool_size`**: 20 persistent worker connections per replica.
- **`max_overflow`**: 10 burst connections during high load.
- **`pool_recycle`**: 3600 seconds to prevent stale connection leaks through stateful firewalls.
- **`pool_pre_ping`**: True (validates connection liveness before checking out from pool).
- **`pool_timeout`**: 30 seconds wait queue before fail-closed error.

---

## 2. Step-by-Step Migration: SQLite to PostgreSQL

### Step 1: Provision Target PostgreSQL Instance
Ensure PostgreSQL 14, 15, or 16 is provisioned with UTF-8 encoding:
```sql
CREATE DATABASE cerberus ENCODING 'UTF8';
CREATE USER cerberus_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE cerberus TO cerberus_user;
```

### Step 2: Automated Forward Schema Provisioning
Run the Cerberus migration CLI or start the service with `DATABASE_URL` pointing to PostgreSQL:
```bash
export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/cerberus"
python -m cerberus.cli migrate
```
This executes all versioned migrations (`001_initial_schema`, `002_review_approval_columns`, `003_multitenancy_and_config`, `004_tenant_identity_enforcement`) transactionally.

### Step 3: Data Transfer (Optional)
If migrating historical reviews from an existing SQLite file:
```bash
# Using pgloader for fast zero-error streaming conversion
pgloader sqlite://cerberus.db postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/cerberus
```

### Step 4: Kubernetes Secret Configuration
Update your Kubernetes deployment secret:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cerberus-secrets
  namespace: cerberus-system
type: Opaque
stringData:
  DATABASE_URL: "postgresql+asyncpg://cerberus:$(DB_PASS)@postgres.database.svc.cluster.local:5432/cerberus?ssl=require"
```

---

## 3. High Availability & Backup Strategy
- **Continuous Archiving:** Enable WAL archiving to cloud storage (e.g. AWS S3 / Google GCS).
- **Daily Automated Snapshots:** Scheduled pg_dump via Kubernetes CronJob.
- **Multi-AZ Replication:** Synchronous standby replicas in secondary availability zones with automatic failover via Patroni or AWS RDS Multi-AZ.
