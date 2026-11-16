# Cerberus Disaster Recovery (DR) & Business Continuity Runbook

This runbook defines exact Recovery Time Objectives (RTO), Recovery Point Objectives (RPO), backup protocols, and step-by-step restoration procedures for the Cerberus platform.

---

## 1. Disaster Recovery Targets

```
┌─────────────────────────────────────────────────────────────┐
│                   DISASTER RECOVERY TARGETS                 │
├───────────────────────────────┬─────────────────────────────┤
│ RTO (Recovery Time Objective) │ < 15 minutes to cold stand  │
│ RPO (Recovery Point Objective)│ < 1 hour of review history  │
│ Configuration Recovery        │ 0 minutes (GitOps driven)   │
│ Encryption at Rest            │ AES-256 (KMS Managed)       │
└───────────────────────────────┴─────────────────────────────┘
```

---

## 2. Backup Topology & Schedules

### A. Primary Relational Database (PostgreSQL)
- **Continuous Write-Ahead Log (WAL) Archiving:** Shipped to encrypted S3/GCS bucket continuously (`archive_timeout = 60s`).
- **Full Daily Backups:** Automated `pg_dump -Fc` snapshot taken daily at 02:00 UTC via dedicated Kubernetes CronJob:
  ```bash
  pg_dump -h $DB_HOST -U cerberus_user -d cerberus -Fc | gzip | aws s3 cp - s3://cerberus-backups/postgres/$(date +%Y%m%d_%H%M%S).dump.gz
  ```
- **Backup Retention:** 30 days rolling lifecycle policy with immutable object lock (WORM).

### B. Redis Cluster State
- **AOF (Append Only File):** Enabled with `appendfsync everysec`.
- **RDB Snapshots:** Captured every 15 minutes and copied to backup storage.

---

## 3. Incident Playbooks

### Playbook 1: Production Database Corrupted / Unreachable
1. **Identify Primary Failure:**
   ```bash
   kubectl logs -n cerberus-system -l app=cerberus --tail=100 | grep "DatabaseError"
   ```
2. **Promote Standby Read Replica (RTO < 3 mins):**
   ```bash
   # AWS RDS / Patroni trigger failover
   patronictl -c /etc/patroni/cerberus.yml failover
   ```
3. **If Full Restore from S3 Backup Required:**
   ```bash
   # Pull latest snapshot from S3
   aws s3 cp s3://cerberus-backups/postgres/latest.dump.gz ./restore.dump.gz
   gunzip -c restore.dump.gz | pg_restore -h $NEW_DB_HOST -U cerberus_user -d cerberus --clean --if-exists
   ```
4. **Update Kubernetes Connection Secret:**
   ```bash
   kubectl set env deployment/cerberus DATABASE_URL="postgresql+asyncpg://cerberus:$(DB_PASS)@$NEW_DB_HOST:5432/cerberus" -n cerberus-system
   kubectl rollout status deployment/cerberus -n cerberus-system
   ```

---

### Playbook 2: Immediate Rollback of Faulty Release
If a bad release or database migration causes crashes, immediately initiate automated rollback:
```bash
python scripts/rollback.py
```
Or via `kubectl`:
```bash
kubectl rollout undo deployment/cerberus -n cerberus-system
kubectl rollout status deployment/cerberus -n cerberus-system
```

---

### Playbook 3: Redis Failure / Cluster Loss
Cerberus features **fail-open in-memory fallback**:
- When Redis fails, rate limiting automatically degrades to in-process sliding window (`cerberus/core/security.py`).
- Cache degrades to local in-memory LRU (`cerberus/core/cache.py`).
- SingleFlight falls back to local futures (`cerberus/core/distributed_flight.py`).
- **No human intervention required to keep code review services alive.**

---

## 4. Quarterly Disaster Recovery Drill Checklist
Every quarter, engineering must execute a mock failure drill in staging:
- [ ] Simulate database instance termination.
- [ ] Restore latest automated backup into staging database.
- [ ] Run verification test suite: `pytest tests/ -v`.
- [ ] Verify timing: Total elapsed recovery must be < 15 minutes.
- [ ] Log test results in `docs/dr-drill-log.md`.
