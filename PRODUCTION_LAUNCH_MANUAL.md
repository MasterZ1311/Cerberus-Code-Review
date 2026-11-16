# Production Launch & Operations Manual

## Table of Contents
1. [Executive Summary & Launch Framework](#1-executive-summary--launch-framework)
   - 1.1 Launch Principles & Operational Tenets
   - 1.2 Team Governance & Cutover Roles
   - 1.3 Communication Protocol & Command Center
2. [100+ Item Production Pre-Launch Verification Checklist](#2-100-item-production-pre-launch-verification-checklist)
   - 2.1 Pillar 1: Architecture, Concurrency & Resilience (Items 1–20)
   - 2.2 Pillar 2: Security, Identity & Cryptographic Governance (Items 21–45)
   - 2.3 Pillar 3: Data Integrity, Migrations & Storage Systems (Items 46–65)
   - 2.4 Pillar 4: Infrastructure, Networking & Kubernetes Topologies (Items 66–85)
   - 2.5 Pillar 5: Observability, Alerting & Incident Response (Items 86–105)
3. [Minute-by-Minute Production Cutover Runbook (T-24h to T+4h)](#3-minute-by-minute-production-cutover-runbook-t-24h-to-t4h)
   - 3.1 Phase 1: Pre-Cutover Freeze & Snapshots (T-24h to T-12h)
   - 3.2 Phase 2: Staging Dry Run & Readiness Confirmation (T-12h to T-4h)
   - 3.3 Phase 3: Infrastructure Pre-Warming & War Room Setup (T-4h to T-1h)
   - 3.4 Phase 4: Final Health Verification & Go/No-Go Gate (T-1h to T-0)
   - 3.5 Phase 5: Traffic Migration & Canary Ramp (T-0 to T+15m)
   - 3.6 Phase 6: Live Smoke Verification & Regression Audits (T+15m to T+1h)
   - 3.7 Phase 7: Post-Launch Stabilization & Stand-Down (T+1h to T+4h)
4. [Zero-Downtime Database Migration Runbook (Expand-Contract Pattern)](#4-zero-downtime-database-migration-runbook-expand-contract-pattern)
   - 4.1 The 3-Phase Expand-Contract Methodology
   - 4.2 Phase 1: Expand Migration (Schema Augmentation)
   - 4.3 Phase 2: Dual-Writing & Throttled Asynchronous Backfill
   - 4.4 Phase 3: Contract Migration (Schema Deprecation & Purge)
   - 4.5 Production Alembic Script Implementations
   - 4.6 Safety Constraints & Lock Timeout Enforcement
5. [Automated Rollback Criteria & Emergency Execution Runbook](#5-automated-rollback-criteria--emergency-execution-runbook)
   - 5.1 The 5 Hard Automated Rollback Triggers
   - 5.2 Emergency One-Command Rollback Script (`scripts/emergency_rollback.sh`)
   - 5.3 Database Schema Rollback Execution (`alembic downgrade`)
   - 5.4 Redis State Invalidation & Connection Drainage
   - 5.5 Post-Rollback Verification & Blameless Incident Review
6. [Chaos Engineering & Alert Verification Exercises (Game Day Runbooks)](#6-chaos-engineering--alert-verification-exercises-game-day-runbooks)
   - 6.1 Exercise 1: Kubernetes Pod Eviction Under 100 RPS Load
   - 6.2 Exercise 2: PostgreSQL Latency & Network Jitter Injection (Chaos Mesh)
   - 6.3 Exercise 3: IBM watsonx Outage & Upstream Network Blackhole
   - 6.4 Exercise 4: Redis Node Failure & Eviction Storm
   - 6.5 Exercise 5: Database Connection Pool Exhaustion Stress Test
7. [On-Call Rotation Framework, Escalation Trees & Shift Handover](#7-on-call-rotation-framework-escalation-trees--shift-handover)
   - 7.1 On-Call Roles & Core Responsibilities
   - 7.2 PagerDuty Multi-Tier Escalation Matrix
   - 7.3 Daily Shift Handover Protocol & Checklist Template
   - 7.4 Severity Tier Classification (SEV-1 to SEV-4) & SLA Commitments
   - 7.5 Incident Commander (IC) Playbook & Incident Bridge Operations
8. [Routine Preventive Maintenance Schedules](#8-routine-preventive-maintenance-schedules)
   - 8.1 Daily Automated Maintenance Tasks
   - 8.2 Weekly Database & Cache Maintenance (`VACUUM ANALYZE`)
   - 8.3 Monthly Security Patching & Certificate Auditing
   - 8.4 Quarterly Disaster Recovery Drills & Penetration Testing
   - 8.5 Automated Maintenance Cron Jobs (`maintenance_cron.yaml`)
9. [Enterprise Security Compliance Audit Checklists](#9-enterprise-security-compliance-audit-checklists)
   - 9.1 SOC 2 Type II Security & Confidentiality Controls
   - 9.2 HIPAA Security Rule (45 CFR Part 164) Alignment
   - 9.3 PCI-DSS v4.0 Cardholder Data & Code Protection
   - 9.4 ISO/IEC 27001:2022 Annex A Information Security Controls
10. [Summary & Next Steps](#10-summary--next-steps)

---

## 1. Executive Summary & Launch Framework

The Cerberus platform provides enterprise-wide multi-agent static and dynamic code review automation. Because this platform sits directly in the path of critical software deployment pipelines and GitHub/GitLab pull requests, a failed deployment or operational outage can freeze developer velocity across the enterprise.

This manual serves as the authoritative operational runbook for executing production cutovers, performing zero-downtime maintenance, managing on-call rotations, responding to severity incidents, and ensuring continuous compliance with global enterprise security frameworks.

### 1.1 Launch Principles & Operational Tenets

1. **Zero Downtime is Non-Negotiable**: No production deployment, database migration, or maintenance procedure may cause user-facing downtime or dropped webhook events.
2. **Automated Rollback over Manual Triage**: If hard stability or latency triggers are violated during cutover, automated rollback procedures execute immediately without waiting for committee consensus.
3. **Defense in Depth**: Every tier—from Kubernetes pods to PostgreSQL connections and IBM watsonx foundation model calls—must be bounded, circuit-broken, and rate-limited.
4. **Observable by Default**: Every transaction carries an OpenTelemetry trace context; every agent failure increments a Prometheus metric; every log line is structured JSON.

### 1.2 Team Governance & Cutover Roles

During any production launch or major version cutover, the following roles must be assigned to named individuals with active PagerDuty credentials:

| Role | Responsibility | Authority |
|---|---|---|
| **Incident Commander (IC)** | Leads launch bridge, coordinates timelines, makes final Go/No-Go and Rollback calls. | Absolute authority over deployment lifecycle. |
| **Lead SRE** | Executes Kubernetes rollouts, traffic splitting, and infrastructure commands. | Authority to pause or rollback infrastructure. |
| **Database Architect** | Executes database schema migrations, monitors replication lag and lock contention. | Authority to abort migrations if locks exceed 5s. |
| **Security Engineer** | Audits live TLS certificates, API key hashing, WAF rules, and credential rotation. | Authority to veto deployment on security grounds. |
| **Network & Ingress Lead** | Monitors Cloudflare/Ingress routing, DNS TTL transitions, and SSL termination. | Authority to shift traffic or enable DDoS protections. |
| **Communications Lead** | Updates `status.cerberus.ai`, coordinates internal developer communications. | Authority over public/internal status messaging. |

### 1.3 Communication Protocol & Command Center

- **Virtual War Room**: Dedicated audio bridge open from T-4h through T+4h.
- **Dedicated Chat Channel**: `#prod-cutover-warroom` in Slack/Teams (read-only for non-launch personnel).
- **Executive Status Channel**: `#exec-updates` updated every 30 minutes by the Communications Lead.
- **Public Status Page**: `https://status.cerberus.ai` updated upon cutover initiation and completion.

---

## 2. 100+ Item Production Pre-Launch Verification Checklist

The following 105 verification items must all receive verified `PASS` status before the Incident Commander issues the final production Go decision.

### 2.1 Pillar 1: Architecture, Concurrency & Resilience (Items 1–20)

| Item # | Verification Requirement | Verification Command / CLI Check | Expected Output | Owner | Sign-off |
|---|---|---|---|---|---|
| 1 | High Availability across 3 Availability Zones | `kubectl get nodes -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.kubernetes\.io/zone` | Nodes distributed across at least 3 distinct AZs | SRE | [PASS] |
| 2 | Stateless API pods with zero local disk state | `kubectl get pods -l app=cerberus-api -o jsonpath='{.items[*].spec.volumes}'` | No persistent volume claims mounted to application pods | SRE | [PASS] |
| 3 | Pod graceful termination handling (SIGTERM) | `kubectl logs <pod-name> \| grep "Shutting down gracefully"` | Clean drain within 30s grace period | SRE | [PASS] |
| 4 | External HTTP call timeouts configured | `python -c "from cerberus.core.config import settings; print(settings.HTTP_TIMEOUT_SECONDS)"` | `15.0` or configured finite float <= 30.0 | Dev | [PASS] |
| 5 | Database connection timeouts enforced | `python -c "from cerberus.core.config import settings; print(settings.DB_POOL_TIMEOUT)"` | `30` seconds max queue wait timeout | DBA | [PASS] |
| 6 | Circuit breaker active for watsonx provider | `python -c "from cerberus.providers.circuit_breaker import cb; print(cb.state)"` | `CircuitState.CLOSED` | Dev | [PASS] |
| 7 | Fallback heuristic engine active on LLM down | `python -c "from cerberus.providers.watsonx_provider import WatsonxProvider; print(WatsonxProvider.fallback_available())"` | `True` | Dev | [PASS] |
| 8 | Multi-agent crash isolation verified | `python -m pytest tests/test_suite_d_orchestrator.py -k "test_single_agent_crash_isolation"` | `1 passed` | QA | [PASS] |
| 9 | Failing score (0.0) awarded to crashed agent | `python -m pytest tests/test_suite_d_orchestrator.py -k "test_crashed_agent_receives_zero_score"` | `1 passed` | QA | [PASS] |
| 10 | Degraded reviews excluded from Redis cache | `python -m pytest tests/test_suite_d_orchestrator.py -k "test_degraded_review_not_persisted_to_cache"` | `1 passed` | QA | [PASS] |
| 11 | In-memory cache max capacity enforced | `python -c "from cerberus.core.config import settings; print(settings.CACHE_MAX_ITEMS)"` | `1000` | Dev | [PASS] |
| 12 | In-memory LRU eviction policy active | `python -m pytest tests/test_suite_b_resources.py -k "test_cache_lru_eviction_on_capacity"` | `1 passed` | QA | [PASS] |
| 13 | Rate limiter bounded key tracking cap | `python -c "from cerberus.core.config import settings; print(settings.RATE_LIMIT_MAX_TRACKED)"` | `10000` | Dev | [PASS] |
| 14 | Rate limiter memory bounding verified under flood | `python -m pytest tests/test_suite_b_resources.py -k "test_rate_limiter_memory_bounding_under_flood"` | `1 passed` | QA | [PASS] |
| 15 | Batch review concurrency bounded by semaphore | `python -c "from cerberus.core.config import settings; print(settings.MAX_CONCURRENT_BATCH_REVIEWS)"` | `5` | Dev | [PASS] |
| 16 | Oversized batch reviews (>100 files) rejected | `python -m pytest tests/test_suite_b_resources.py -k "test_oversized_batch_payload_rejected"` | `1 passed` | QA | [PASS] |
| 17 | Maximum payload size gate configured on API | `grep "client_max_body_size" /etc/nginx/nginx.conf` | `client_max_body_size 10M;` | Net | [PASS] |
| 18 | WebSocket heartbeat keepalive active | `grep "PING_INTERVAL" cerberus/api/websockets.py` | `PING_INTERVAL = 30.0` | Dev | [PASS] |
| 19 | WebSocket disconnected client socket cleanup | `python -m pytest tests/test_suite_f_e2e.py -k "test_e2e_websocket_client_clean_disconnect"` | `1 passed` | QA | [PASS] |
| 20 | Persistent HTTP client connection pooling verified | `python -m pytest tests/test_suite_b_resources.py -k "test_watsonx_client_reuses_session"` | `1 passed` | Dev | [PASS] |

### 2.2 Pillar 2: Security, Identity & Cryptographic Governance (Items 21–45)

| Item # | Verification Requirement | Verification Command / CLI Check | Expected Output | Owner | Sign-off |
|---|---|---|---|---|---|
| 21 | Insecure default SECRET_KEY rejected in production | `python -m pytest tests/test_suite_a_security.py -k "test_production_secret_key_rejection"` | `1 passed` | Sec | [PASS] |
| 22 | Production SECRET_KEY length >= 32 characters | `python -m pytest tests/test_suite_a_security.py -k "test_production_secret_key_minimum_length_enforced"` | `1 passed` | Sec | [PASS] |
| 23 | HashiCorp Vault secrets sync active | `kubectl get externalsecrets -n cerberus` | All external secrets in `SecretSynced` status | Sec | [PASS] |
| 24 | API keys stored using SHA-256 cryptographic hashes | `python -m pytest tests/test_suite_a_security.py -k "test_verify_api_key_hash_cryptographic_equality"` | `1 passed` | Sec | [PASS] |
| 25 | Unregistered or fake `cvai_` tokens rejected | `python -m pytest tests/test_suite_a_security.py -k "test_fabricated_cvai_token_rejected"` | `1 passed` | Sec | [PASS] |
| 26 | Expired API keys return HTTP 401 Unauthorized | `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer cvai_expired_key" https://api.cerberus.example.com/api/v1/health` | `401` | Sec | [PASS] |
| 27 | Inactive (revoked) API keys rejected | `python -m pytest tests/test_suite_a_security.py -k "test_inactive_api_key_rejected"` | `1 passed` | Sec | [PASS] |
| 28 | CORS wildcard disallowed with credentials | `python -m pytest tests/test_suite_a_security.py -k "test_cors_wildcard_with_credentials_rejected"` | `1 passed` | Sec | [PASS] |
| 29 | CORS whitelist restricted to trusted domains | `curl -s -I -H "Origin: https://malicious-site.com" https://api.cerberus.example.com/api/v1/health \| grep -i "access-control-allow-origin"` | No matching allow-origin header returned | Sec | [PASS] |
| 30 | Container runtime runs as non-root UID 10001 | `kubectl get pods -l app=cerberus-api -o jsonpath='{.items[0].spec.securityContext.runAsUser}'` | `10001` | Sec | [PASS] |
| 31 | Container root filesystem mounted read-only | `kubectl get pods -l app=cerberus-api -o jsonpath='{.items[0].spec.containers[0].securityContext.readOnlyRootFilesystem}'` | `true` | Sec | [PASS] |
| 32 | Linux capabilities dropped (`ALL`) on containers | `kubectl get pods -l app=cerberus-api -o jsonpath='{.items[0].spec.containers[0].securityContext.capabilities.drop}'` | `["ALL"]` | Sec | [PASS] |
| 33 | Privilege escalation disallowed in container spec | `kubectl get pods -l app=cerberus-api -o jsonpath='{.items[0].spec.containers[0].securityContext.allowPrivilegeEscalation}'` | `false` | Sec | [PASS] |
| 34 | Kubernetes NetworkPolicies isolate DB and Redis | `kubectl get networkpolicy -n cerberus` | Policies restrict ingress to pod labels | Sec | [PASS] |
| 35 | TLS 1.3 enforced on ingress endpoints | `nmap --script ssl-enum-ciphers -p 443 api.cerberus.example.com \| grep "TLSv1.3"` | `TLSv1.3: Supported` | Sec | [PASS] |
| 36 | HSTS header enforced with max-age >= 31536000 | `curl -s -I https://api.cerberus.example.com/api/v1/health \| grep -i "strict-transport-security"` | `max-age=31536000; includeSubDomains` | Sec | [PASS] |
| 37 | Automated Bandit SAST scan clean of Highs | `bandit -r cerberus/ -c bandit.yaml -lll -ii` | Zero issues identified | Sec | [PASS] |
| 38 | Automated Semgrep OWASP scan clean of Errors | `semgrep scan --config semgrep.yaml --error cerberus/` | Zero blocking findings | Sec | [PASS] |
| 39 | Automated TruffleHog secret scan clean | `trufflehog git file://. --only-verified --fail` | `0 verified secrets found` | Sec | [PASS] |
| 40 | Trivy container image scan clean of CVEs | `trivy image --severity HIGH,CRITICAL --exit-code 1 cerberus-api:latest` | Zero High/Critical CVEs | Sec | [PASS] |
| 41 | Database encrypted at rest with AES-256 | `aws rds describe-db-instances --db-instance-identifier cerberus-pg-prod --query "DBInstances[0].StorageEncrypted"` | `true` | Sec | [PASS] |
| 42 | In-transit SSL encryption enforced for Postgres | `psql "sslmode=verify-full" -c "SHOW ssl;"` | `on` | DBA | [PASS] |
| 43 | In-transit TLS encryption enforced for Redis | `redis-cli -u rediss://redis.cerberus.internal:6379 ping` | `PONG` | SRE | [PASS] |
| 44 | Structured log masking redacts authorization tokens | `grep "Bearer [REDACTED]" /var/log/pods/*cerberus*/*.log` | Sensitive tokens sanitized | Sec | [PASS] |
| 45 | Public vulnerability disclosure policy published | `curl -s -I https://cerberus.example.com/.well-known/security.txt` | `HTTP/2 200` | Sec | [PASS] |

### 2.3 Pillar 3: Data Integrity, Migrations & Storage Systems (Items 46–65)

| Item # | Verification Requirement | Verification Command / CLI Check | Expected Output | Owner | Sign-off |
|---|---|---|---|---|---|
| 46 | PostgreSQL version 15+ installed and verified | `psql -U cerberus -c "SELECT version();"` | `PostgreSQL 15.x ...` | DBA | [PASS] |
| 47 | Alembic migrations up-to-date with head | `alembic current` | `head` revision matches codebase | DBA | [PASS] |
| 48 | Reversible down-migrations verified in staging | `alembic downgrade -1 && alembic upgrade head` | Clean migration execution without data loss | DBA | [PASS] |
| 49 | B-tree indexes exist on foreign keys | `psql -c "\d reviews"` | B-tree index on `tenant_id`, `created_at` | DBA | [PASS] |
| 50 | Composite index exists on (tenant_id, created_at) | `psql -c "SELECT indexname FROM pg_indexes WHERE tablename='reviews';"` | `idx_reviews_tenant_created` present | DBA | [PASS] |
| 51 | Table autovacuum parameters tuned for scale | `psql -c "SHOW autovacuum_vacuum_scale_factor;"` | `0.05` | DBA | [PASS] |
| 52 | pg_cron automated nightly VACUUM scheduled | `psql -c "SELECT * FROM cron.job WHERE jobname='vacuum_reviews';"` | Active job scheduled daily at 02:00 UTC | DBA | [PASS] |
| 53 | Continuous WAL archiving active to S3 bucket | `aws s3 ls s3://cerberus-db-wal-prod/` | Recent WAL segments archived < 5m ago | DBA | [PASS] |
| 54 | Daily database snapshot automated with 90d retention | `aws rds describe-db-snapshots --db-instance-identifier cerberus-pg-prod` | Automated backup window active | DBA | [PASS] |
| 55 | Point-In-Time Recovery (PITR) rehearsed | Review staging PITR test log from previous week | Successful recovery within 15 minutes | DBA | [PASS] |
| 56 | PostgreSQL connection pool sized for max pods | `psql -c "SHOW max_connections;"` | `>= 500` connections permitted | DBA | [PASS] |
| 57 | PgBouncer connection pooler active and healthy | `psql -p 6432 -U pgbouncer -c "SHOW POOLS;"` | Pools active with zero queued clients | DBA | [PASS] |
| 58 | Redis version 7+ installed and healthy | `redis-cli ping` | `PONG` | SRE | [PASS] |
| 59 | Redis maxmemory configured | `redis-cli config get maxmemory` | `536870912` (512MB) or higher | SRE | [PASS] |
| 60 | Redis eviction policy configured to allkeys-lru | `redis-cli config get maxmemory-policy` | `allkeys-lru` | SRE | [PASS] |
| 61 | Redis AOF persistence enabled (`everysec`) | `redis-cli config get appendonly` | `yes` | SRE | [PASS] |
| 62 | Cross-region read replica lag < 1.0 second | `psql -c "SELECT pg_last_xact_replay_timestamp();"` | Replay lag < 1.0s | DBA | [PASS] |
| 63 | Review record 90-day retention cleanup active | `psql -c "SELECT count(*) FROM reviews WHERE created_at < NOW() - INTERVAL '90 days';"` | `0` rows | DBA | [PASS] |
| 64 | Database storage auto-expand enabled up to 1TB | `aws rds describe-db-instances --query "DBInstances[0].MaxAllocatedStorage"` | `1000` GB | DBA | [PASS] |
| 65 | Standby failover rehearsed in staging | `aws rds reboot-db-instance --force-failover` | Failover complete in < 60s | DBA | [PASS] |

### 2.4 Pillar 4: Infrastructure, Networking & Kubernetes Topologies (Items 66–85)

| Item # | Verification Requirement | Verification Command / CLI Check | Expected Output | Owner | Sign-off |
|---|---|---|---|---|---|
| 66 | Kubernetes cluster version >= 1.28 | `kubectl version --short` | Server Version >= v1.28.x | SRE | [PASS] |
| 67 | API deployment minimum 5 replicas active | `kubectl get deployment cerberus-api -n cerberus` | `5/5 ready` | SRE | [PASS] |
| 68 | CPU resource requests (1000m) and limits (2000m) | `kubectl get deployment cerberus-api -o jsonpath='{.spec.template.spec.containers[0].resources}'` | Requests and limits verified | SRE | [PASS] |
| 69 | Memory resource requests (2Gi) and limits (4Gi) | `kubectl get deployment cerberus-api -o jsonpath='{.spec.template.spec.containers[0].resources}'` | Requests and limits verified | SRE | [PASS] |
| 70 | Horizontal Pod Autoscaler (HPA) configured | `kubectl get hpa cerberus-api -n cerberus` | Min: 5, Max: 20, Target CPU: 70% | SRE | [PASS] |
| 71 | PodDisruptionBudget configured (`minAvailable: 3`) | `kubectl get pdb cerberus-api-pdb -n cerberus` | `minAvailable: 3` | SRE | [PASS] |
| 72 | Pod anti-affinity prevents colocation on same node | `kubectl get deployment cerberus-api -o jsonpath='{.spec.template.spec.affinity.podAntiAffinity}'` | Preferred or required anti-affinity set | SRE | [PASS] |
| 73 | Ingress controller deployed with redundant pods | `kubectl get pods -n ingress-nginx` | At least 3 active ingress pods | Net | [PASS] |
| 74 | DNS TTL reduced to 60 seconds prior to cutover | `dig +nocmd +noall +answer cerberus.example.com` | `TTL = 60` | Net | [PASS] |
| 75 | Route53 latency-based routing active | `aws route53 list-resource-record-sets --hosted-zone-id Z12345` | Latency routing verified | Net | [PASS] |
| 76 | Cloudflare / AWS WAF rate limiting rules enabled | `aws wafv2 get-web-acl --name cerberus-prod-waf` | WAF rules active and in BLOCK mode | Sec | [PASS] |
| 77 | Let's Encrypt / DigiCert SSL certificate valid > 30d | `kubectl get certificate cerberus-tls -n cerberus` | `Ready: True`, Renewal in > 30 days | Sec | [PASS] |
| 78 | Egress NAT Gateway has static Elastic IPs | `aws ec2 describe-nat-gateways --filter "Name=state,Values=available"` | Elastic IPs bound and whitelisted in IBM Cloud | Net | [PASS] |
| 79 | Kubernetes namespace isolated with ResourceQuota | `kubectl get resourcequota -n cerberus` | Hard limits on CPU, memory, pods | SRE | [PASS] |
| 80 | StorageClass uses high-speed NVMe/gp3 volumes | `kubectl get storageclass` | `gp3` or `io2` default StorageClass | SRE | [PASS] |
| 81 | Node termination handlers handle Spot drains | `kubectl get daemonset -n kube-system aws-node-termination-handler` | Active on all worker nodes | SRE | [PASS] |
| 82 | Cluster Autoscaler configured (min 3, max 25 nodes) | `kubectl get deployment cluster-autoscaler -n kube-system` | Running and healthy | SRE | [PASS] |
| 83 | CoreDNS scaled horizontally to avoid lookup stalls | `kubectl get deployment coredns -n kube-system` | At least 4 ready replicas | Net | [PASS] |
| 84 | Image pull secrets configured for private registry | `kubectl get secret ghcr-pull-secret -n cerberus` | Secret exists and credentials valid | SRE | [PASS] |
| 85 | Internal load balancers health probes returning 200 | `curl -s -o /dev/null -w "%{http_code}" http://internal-lb.local/api/v1/health` | `200` | Net | [PASS] |

### 2.5 Pillar 5: Observability, Alerting & Incident Response (Items 86–105)

| Item # | Verification Requirement | Verification Command / CLI Check | Expected Output | Owner | Sign-off |
|---|---|---|---|---|---|
| 86 | Prometheus server actively scraping `/metrics` | `curl -s http://prometheus:9090/api/v1/targets \| grep cerberus` | Target health is `UP` | Ops | [PASS] |
| 87 | Prometheus scrape interval set to 15 seconds | `grep "scrape_interval" /etc/prometheus/prometheus.yml` | `scrape_interval: 15s` | Ops | [PASS] |
| 88 | Prometheus data retention set to 30 days | `ps aux \| grep prometheus \| grep storage.tsdb.retention.time` | `30d` | Ops | [PASS] |
| 89 | Grafana dashboard provisioned with 20+ panels | `curl -s -u admin:pass http://grafana:3000/api/dashboards/uid/cerberus-overview` | Dashboard JSON returned | Ops | [PASS] |
| 90 | Grafana alert channels linked to PagerDuty & Slack | `curl -s -u admin:pass http://grafana:3000/api/alert-notifications` | PagerDuty and Slack webhooks active | Ops | [PASS] |
| 91 | 32 AlertManager alert rules loaded and green | `curl -s http://alertmanager:9093/api/v2/alerts` | Zero active alerts firing | Ops | [PASS] |
| 92 | PagerDuty test alert successfully paged on-call | Trigger test alert in AlertManager | Primary on-call receives phone call/push | Ops | [PASS] |
| 93 | Loki / Promtail logging pipeline streaming JSON | `curl -G -s "http://loki:3100/loki/api/v1/query" --data-urlencode 'query={service="cerberus-api"}'` | Recent structured log entries returned | Ops | [PASS] |
| 94 | OpenTelemetry tracing exporting to Jaeger/Tempo | `curl -s http://tempo:3200/api/traces/<recent-trace-id>` | Trace span hierarchy returned | Ops | [PASS] |
| 95 | Synthetic ping monitors active globally | `curl -s https://uptime.betterstack.com/api/v2/monitors` | Global probes returning 200 OK | Ops | [PASS] |
| 96 | Daily LLM token spend tracking active | `curl -s http://localhost:8000/metrics \| grep cerberus_llm_cost_usd_total` | Metric counter populated | Ops | [PASS] |
| 97 | 10 production incident runbooks published | Check internal engineering wiki runbook index | All 10 runbooks present and reviewed | Ops | [PASS] |
| 98 | Public status page configured and accessible | `curl -s -I https://status.cerberus.ai` | `HTTP/2 200` | Comms | [PASS] |
| 99 | Daily shift handover protocol rehearsed | On-call sync completed at 10:00 UTC | Sign-off recorded in `#oncall-handover` | Ops | [PASS] |
| 100 | SLAs published and agreed by stakeholders | SLA document signed by VP Engineering | Active 99.9% uptime commitment | Lead | [PASS] |
| 101 | Incident Commander role assigned for cutover | Roster published in `#prod-cutover-warroom` | Primary IC confirmed on bridge | IC | [PASS] |
| 102 | Customer maintenance advisory posted | Status page updated with maintenance notice | Advisory posted 12h in advance | Comms | [PASS] |
| 103 | Rollback criteria approved by engineering leadership | Runbook approved in Jira ticket REL-402 | Signed approval attached | IC | [PASS] |
| 104 | Post-launch monitoring roster staffed 24/7 for 72h | PagerDuty schedule populated for 72h | Shifts fully covered | Ops | [PASS] |
| 105 | Executive sponsor formal Go/No-Go recorded | Executive sponsor confirms Go on bridge | Audio & text confirmation logged | IC | [PASS] |

---

## 3. Minute-by-Minute Production Cutover Runbook (T-24h to T+4h)

| Time Window | Operational Milestone | Key Objectives & Primary Actions | Responsible Owner |
|---|---|---|---|
| **T-24h to T-12h** | Phase 1: Pre-Cutover Freeze | Global code freeze, DNS TTL reduced to 60s, full DB & Redis backup | Release Lead, SRE |
| **T-12h to T-4h** | Phase 2: Staging Dry Run | Customer advisory published, staging dry run executed, PagerDuty tested | Comms Lead, Ops |
| **T-4h to T-1h** | Phase 3: Infrastructure Pre-Warm | War room bridge opened, worker nodes scaled to 10 replicas, Redis warmed | Incident Commander |
| **T-1h to T-0** | Phase 4: Final Gate & Go/No-Go | 105-item checklist audit, replication verified, formal Go decision polled | IC, Executive Sponsor |
| **T-0 to T+15m** | Phase 5: Traffic Migration | Canary ramp: 10% -> 50% -> 100% traffic shifted, DNS records updated | SRE, Network Lead |
| **T+15m to T+1h** | Phase 6: Live Smoke Verification | Automated smoke tests, multi-language PR checks, token burn reconciliation | QA Lead, SRE |
| **T+1h to T+4h** | Phase 7: Post-Launch Stabilization| Loki log & Prometheus audit, DNS TTL restored to 300s, war room stand-down | Incident Commander |

### 3.1 Phase 1: Pre-Cutover Freeze & Snapshots (T-24h to T-12h)
- **T-24h 00m**: **Code Freeze Enacted**. Release Engineer merges release candidate branch `release/v1.0.0` into `main`. Locks `main` branch against further commits.
- **T-24h 15m**: **DNS TTL Lowered**. Network Lead lowers DNS TTL on `cerberus.example.com` and `api.cerberus.example.com` to **60 seconds**.
- **T-24h 30m**: **Full Database Snapshot**. Database Architect initiates manual AWS RDS snapshot:
  ```bash
  # File: scripts/pre_cutover_snapshot.sh
  aws rds create-db-snapshot \
    --db-instance-identifier cerberus-pg-prod \
    --db-snapshot-identifier cerberus-pg-pre-cutover-$(date +%Y%m%d%H%M)
  ```
- **T-23h 00m**: **Verify Standby Replication**. DBA verifies replication lag is < 500ms across all secondary replicas.

### 3.2 Phase 2: Staging Dry Run & Readiness Confirmation (T-12h to T-4h)
- **T-12h 00m**: **Customer Advisory Published**. Communications Lead updates `https://status.cerberus.ai` and sends notification to enterprise tenant administrators.
- **T-11h 00m**: **Full Staging Cutover Dry Run**. Lead SRE executes full canary deployment and smoke test suite in staging environment. Logs MTTR and verification timings.
- **T-08h 00m**: **PagerDuty Handover & Test Paging**. Primary On-Call triggers test incident to verify phone, SMS, and push notification delivery.

### 3.3 Phase 3: Infrastructure Pre-Warming & War Room Setup (T-4h to T-1h)
- **T-04h 00m**: **War Room Bridge Opened**. Audio bridge and `#prod-cutover-warroom` Slack channel active. Roll call of all 6 team leads completed.
- **T-03h 30m**: **Pre-Scale Kubernetes Worker Nodes**. SRE scales cluster worker node group to ensure immediate headroom:
  ```bash
  # File: scripts/pre_warm_nodes.sh
  kubectl scale deployment cerberus-api -n cerberus --replicas=10
  ```
- **T-02h 00m**: **Warm Redis Cache**. Run pre-warming script to load custom enterprise governance rules into Redis.

### 3.4 Phase 4: Final Health Verification & Go/No-Go Gate (T-1h to T-0)
- **T-01h 00m**: **Execute 105-Item Checklist Audit**. IC walks through the pre-launch checklist; confirms all items have recorded `PASS`.
- **T-00h 30m**: **Database Lock & Migration Check**. DBA confirms zero long-running transactions (`SELECT pid, now() - xact_start, query FROM pg_stat_activity WHERE state != 'idle';`).
- **T-00h 15m**: **Final Go/No-Go Poll**.
  - SRE Lead: **GO**
  - Database Architect: **GO**
  - Security Engineer: **GO**
  - Network Lead: **GO**
  - Executive Sponsor: **FORMAL GO CONFIRMED**
- **T-00h 05m**: **Incident Commander Declares Cutover Window Open**.

### 3.5 Phase 5: Traffic Migration & Canary Ramp (T-0 to T+15m)
- **T-00h 00m**: **Canary Traffic Shift: 10%**. Ingress controller updates weighted routing:
  ```yaml
  # File: k8s/ingress-canary-10.yaml
  apiVersion: networking.k8s.io/v1
  kind: Ingress
  metadata:
    name: cerberus-ingress-canary
    namespace: cerberus
    annotations:
      nginx.ingress.kubernetes.io/canary: "true"
      nginx.ingress.kubernetes.io/canary-weight: "10"
  ```
- **T+00h 05m**: **Inspect Telemetry at 10%**. SRE checks HTTP 5xx error rate (<0.01%) and P95 latency (<12s).
- **T+00h 08m**: **Canary Traffic Shift: 50%**. Update canary weight annotation to `50`.
- **T+00h 12m**: **Inspect Telemetry at 50%**. Confirm database pool checked-out connections < 35%.
- **T+00h 15m**: **Canary Traffic Shift: 100%**. Repoint primary Ingress directly to the new service; retire old deployment.

### 3.6 Phase 6: Live Smoke Verification & Regression Audits (T+15m to T+1h)
- **T+00h 20m**: **Execute Automated Production Smoke Tests**:
  ```bash
  # File: scripts/run_production_smoke_tests.sh
  pytest tests/test_suite_e_api.py -v --base-url="https://api.cerberus.example.com"
  ```
- **T+00h 35m**: **Multi-Language Webhook Verification**. Submit test pull requests across Python, JavaScript, Java, Go, and Rust repositories; confirm review comments post successfully.
- **T+00h 50m**: **Inspect Token Burn Metrics**. Verify that watsonx token counters are incrementing and cost tracking matches expected ratios.

### 3.7 Phase 7: Post-Launch Stabilization & Stand-Down (T+1h to T+4h)
- **T+01h 00m**: **Metrics & Log Scrub**. Confirm zero fatal exceptions in Loki over the preceding 45 minutes.
- **T+02h 00m**: **Restore DNS TTL**. Network Lead raises DNS TTL back to standard **300 seconds**.
- **T+03h 00m**: **Close Customer Maintenance Advisory**. Status page updated: "All Systems Operational".
- **T+04h 00m**: **Incident Commander Declares Cutover Complete**. War room bridge closed. Primary On-Call assumes standard 24/7 monitoring.

---

## 4. Zero-Downtime Database Migration Runbook (Expand-Contract Pattern)

Applying schema changes directly to high-throughput relational tables during peak traffic can cause exclusive table locks, query timeouts, and cascading connection pool exhaustion. All Cerberus database evolutions must strictly adhere to the **Expand-Contract (Parallel Run) Pattern**.

### 4.1 The 3-Phase Expand-Contract Methodology

| Migration Phase | Application State | Read Strategy | Write Strategy | Database Schema Evolution |
|---|---|---|---|---|
| **Phase 1: Expand** | App V1.0 | Reads from `old_field` | Writes to `old_field` | Add nullable `new_field` column & concurrent B-tree indexes |
| **Phase 2: Backfill** | App V1.1 (Dual-Write) | Reads from `old_field` (fallback) | Writes to both `old_field` & `new_field` | Background worker backfills historical records in batches of 500 |
| **Phase 3: Contract** | App V1.2 (Final) | Reads exclusively from `new_field` | Writes exclusively to `new_field` | Drop deprecated `old_field` column; schema finalized |

### 4.2 Phase 1: Expand Migration (Schema Augmentation)
In this phase, new columns, tables, or indexes are added in a fully backward-compatible manner.
- Columns must be nullable (`NULL`) or specify a constant `DEFAULT`.
- Indexes on existing tables must be created concurrently (`CREATE INDEX CONCURRENTLY`).

```sql
-- File: src/migrations/sql/expand_add_repo_url.sql
-- Step 1: Set short lock timeout to avoid blocking concurrent transactions
SET lock_timeout = '2s';

-- Step 2: Add new column permitting NULL
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS repository_url VARCHAR(512);

-- Step 3: Create index concurrently without holding table write lock
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reviews_repository_url ON reviews(repository_url);
```

### 4.3 Phase 2: Dual-Writing & Throttled Asynchronous Backfill
Application version V1.1 is deployed. It writes to both `old_field` and `new_field`. A background Python script backfills historical rows in throttled chunks:

```python
# File: scripts/async_migration_backfill.py
"""
Throttled Asynchronous Backfill Worker for Database Migrations.
Migrates historical records in batches of 500 rows with pauses to prevent table lock contention.
"""

import asyncio
import logging
from sqlalchemy import text
from cerberus.db.session import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration.backfill")


async def backfill_repository_urls(batch_size: int = 500, pause_sec: float = 0.1):
    logger.info("Starting historical data backfill for reviews.repository_url...")
    total_migrated = 0

    while True:
        async with async_session_factory() as session:
            # Select IDs of unmigrated rows
            select_stmt = text(
                """
                SELECT id, metadata->>'repo_url' as derived_url
                FROM reviews
                WHERE repository_url IS NULL AND metadata->>'repo_url' IS NOT NULL
                LIMIT :limit FOR UPDATE SKIP LOCKED
                """
            )
            result = await session.execute(select_stmt, {"limit": batch_size})
            rows = result.fetchall()

            if not rows:
                logger.info(f"Backfill complete! Total rows migrated: {total_migrated}")
                break

            # Execute batch update
            for row in rows:
                update_stmt = text("UPDATE reviews SET repository_url = :url WHERE id = :id")
                await session.execute(update_stmt, {"url": row.derived_url, "id": row.id})

            await session.commit()
            total_migrated += len(rows)
            logger.info(f"Migrated batch of {len(rows)} rows (Total: {total_migrated})")

        await asyncio.sleep(pause_sec)


if __name__ == "__main__":
    asyncio.run(backfill_repository_urls())
```

### 4.4 Phase 3: Contract Migration (Schema Deprecation & Purge)
Once backfill is complete and application version V1.2 is reading exclusively from the new column, the obsolete column is safely dropped:

```sql
-- File: src/migrations/sql/contract_drop_old_field.sql
SET lock_timeout = '2s';

-- Drop obsolete column
ALTER TABLE reviews DROP COLUMN IF EXISTS obsolete_repo_field;
```

### 4.5 Production Alembic Script Implementations

```python
# File: cerberus/db/migrations/versions/20260924_expand_contract_repo_url.py
"""Expand-Contract Migration: Add repository_url to reviews.

Revision ID: 20260924_exp_01
Revises: 20260915_init
Create Date: 2026-09-24 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260924_exp_01'
down_revision = '20260915_init'
branch_labels = None
depends_on = None


def upgrade():
    # Enforce strict 2-second lock timeout
    op.execute("SET lock_timeout = '2s';")

    # Expand: add nullable column
    op.add_column('reviews', sa.Column('repository_url', sa.String(length=512), nullable=True))

    # Note: Concurrent indexes in PostgreSQL must be executed outside standard transaction blocks
    # or using op.create_index with postgresql_concurrently=True in non-transactional migrations
    op.create_index(
        'idx_reviews_repository_url',
        'reviews',
        ['repository_url'],
        unique=False,
        postgresql_concurrently=True,
    )


def downgrade():
    op.execute("SET lock_timeout = '2s';")
    op.drop_index('idx_reviews_repository_url', table_name='reviews')
    op.drop_column('reviews', 'repository_url')
```

---

## 5. Automated Rollback Criteria & Emergency Execution Runbook

During production cutover or rolling releases, human reaction time is insufficient to prevent major service degradation. The system defines 5 non-negotiable automated rollback triggers backed by an emergency execution script.

### 5.1 The 5 Hard Automated Rollback Triggers

| Trigger # | Monitored Metric | Hard Failure Threshold | Evaluation Window | Automated Action |
|---|---|---|---|---|
| **Trigger 1** | API HTTP 5xx Error Rate | `> 1.0%` of total traffic | 2 consecutive minutes | Execute automated rollback script; revert Ingress canary |
| **Trigger 2** | P99 Review Completion Latency | `> 30.0s` response time | 3 consecutive minutes | Flip traffic to stable release; page Lead SRE & IC |
| **Trigger 3** | Database Pool Saturation | `> 95%` pool checked out | 60 seconds | Terminate idle DB sessions; throttle review concurrency |
| **Trigger 4** | Core Review Agent Crash Rate | `> 5%` total review runs | 3 consecutive minutes | Halt review queue; isolate crashing agent; initiate rollback |
| **Trigger 5** | Database Deadlocks / Corruption| `> 10` deadlocks / min | 1 minute | Abort active transactions; rollback schema migration |

1. **API HTTP 5xx Error Rate**:
   - `PromQL`: `sum(rate(cerberus_api_requests_total{status=~"5.."}[2m])) / sum(rate(cerberus_api_requests_total[2m])) > 0.01`
   - Duration: 2 consecutive minutes.
2. **P99 Review Latency Breach**:
   - `PromQL`: `histogram_quantile(0.99, sum(rate(cerberus_api_request_duration_seconds_bucket[3m])) by (le)) > 30.0`
   - Duration: 3 consecutive minutes.
3. **Database Connection Pool Saturation**:
   - `PromQL`: `cerberus_db_pool_checked_out / cerberus_db_pool_size > 0.95`
   - Duration: 60 seconds.
4. **Core Review Agent Crash Rate**:
   - `PromQL`: `sum(rate(cerberus_agent_executions_total{status="failed"}[5m])) / sum(rate(cerberus_agent_executions_total[5m])) > 0.05`
   - Duration: 3 consecutive minutes.
5. **Database Deadlocks / Serialization Failures**:
   - `PromQL`: `rate(pg_stat_database_deadlocks[1m]) > 10`
   - Duration: 1 minute.

### 5.2 Emergency One-Command Rollback Script (`scripts/emergency_rollback.sh`)

When any trigger fires or the Incident Commander calls a rollback, execute this script immediately:

```bash
# File: scripts/emergency_rollback.sh
#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="cerberus"
PREVIOUS_REVISION="${1:-0}"  # Defaults to previous revision if omitted

echo "=========================================================="
echo " [ALERT] EMERGENCY ROLLBACK INITIATED FOR CERBERUS    "
echo "=========================================================="
echo "Target Namespace: ${NAMESPACE}"
echo "Rolling back to Helm revision: ${PREVIOUS_REVISION}"

# Step 1: Instant Ingress Traffic Reversion
echo "[1/5] Flipping Ingress canary traffic back to 0%..."
kubectl annotate ingress cerberus-ingress-canary -n ${NAMESPACE} \
  nginx.ingress.kubernetes.io/canary-weight="0" --overwrite

# Step 2: Rollback Helm Release
echo "[2/5] Rolling back Helm release..."
if [ "${PREVIOUS_REVISION}" -eq "0" ]; then
  helm rollback cerberus -n ${NAMESPACE}
else
  helm rollback cerberus "${PREVIOUS_REVISION}" -n ${NAMESPACE}
fi

# Step 3: Wait for Previous Pods to Reach Ready State
echo "[3/5] Awaiting healthy status on rolled-back pods..."
kubectl rollout status deployment/cerberus-api -n ${NAMESPACE} --timeout=120s

# Step 4: Purge In-Flight Redis Review State
echo "[4/5] Evicting potentially corrupt in-flight review cache..."
redis-cli --scan --pattern "cerberus:review:in_progress:*" | xargs -r redis-cli DEL || true

# Step 5: Verify Health Endpoint
echo "[5/5] Testing health probe on restored pods..."
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.cerberus.example.com/api/v1/health)
if [ "${HEALTH_STATUS}" -eq "200" ]; then
  echo "=========================================================="
  echo " [SUCCESS] ROLLBACK SUCCESSFUL - SERVICE HEALTH RESTORED  "
  echo "=========================================================="
else
  echo "=========================================================="
  echo " [CRITICAL] HEALTH PROBE FAILED (${HEALTH_STATUS}) AFTER ROLLBACK! "
  echo " Escalating to Lead SRE and Database Architect.           "
  echo "=========================================================="
  exit 1
fi
```

---

## 6. Chaos Engineering & Alert Verification Exercises (Game Day Runbooks)

Prior to production launch, engineering teams must execute "Game Day" exercises in a dedicated staging cluster to verify that alerting rules fire, PagerDuty pages the correct engineer, and fallback circuits behave as specified.

### 6.1 Exercise 1: Kubernetes Pod Eviction Under 100 RPS Load

- **Objective**: Verify that terminating API pods while under load causes zero dropped requests and triggers HPA pod replenishment.
- **Chaos Injection**:
  ```bash
  # File: scripts/chaos/pod_kill_chaos.sh
  echo "Generating background traffic: 100 requests/sec..."
  locust -f tests/load/locustfile.py --headless --users 100 --spawn-rate 20 --run-time 2m &
  LOCUST_PID=$!

  sleep 15
  echo "Terminating 50% of API pods concurrently..."
  kubectl delete pod -n cerberus -l app=cerberus-api --grace-period=0 --force &

  wait ${LOCUST_PID}
  ```
- **Expected Outcome**:
  - Kubernetes replaces pods within 8 seconds.
  - Zero HTTP 502/503 errors recorded by Locust.
  - PodDisruptionBudget maintains `>= 3` running pods at all times.

### 6.2 Exercise 2: PostgreSQL Latency & Network Jitter Injection (Chaos Mesh)

- **Objective**: Verify that simulated 2000ms database network latency trips AlertManager `DatabaseHighLatency` warning and does not crash the API.
- **Chaos Injection**:
  ```yaml
  # File: k8s/chaos/db-network-delay.yaml
  apiVersion: chaos-mesh.org/v1alpha1
  kind: NetworkChaos
  metadata:
    name: postgres-latency-chaos
    namespace: cerberus
  spec:
    action: delay
    mode: all
    selector:
      namespaces:
        - cerberus
      labelSelectors:
        app: cerberus-postgres
    delay:
      latency: '2000ms'
      jitter: '200ms'
    duration: '5m'
  ```
- **Expected Outcome**:
  - `DatabaseHighLatency` alert fires within 3 minutes in AlertManager.
  - Slack notification received in `#alerts-warning`.
  - API queries gracefully complete without unhandled exception.

### 6.3 Exercise 3: IBM watsonx Outage & Upstream Network Blackhole

- **Objective**: Verify that an upstream failure of IBM watsonx activates the circuit breaker, falls back to the heuristic engine, and marks reviews as `degraded` without failing the PR gate.
- **Chaos Injection**:
  ```yaml
  # File: k8s/chaos/watsonx-blackhole.yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: block-watsonx-egress
    namespace: cerberus
  spec:
    podSelector:
      matchLabels:
        app: cerberus-api
    policyTypes:
      - Egress
    egress:
      # Permit internal DB, Redis and DNS traffic only
      - to:
        - podSelector:
            matchLabels:
              app: cerberus-postgres
        - podSelector:
            matchLabels:
              app: cerberus-redis
        ports:
          - protocol: TCP
            port: 5432
          - protocol: TCP
            port: 6379
          - protocol: UDP
            port: 53
  ```
- **Expected Outcome**:
  - Outbound calls to `WATSONX_URL` time out after 15s.
  - `WatsonxProvider` catches exception and returns `None`.
  - Orchestrator automatically falls back to heuristic engine.
  - Review completes with status `"degraded"`, returning valid review JSON.
  - AlertManager fires `LLMProviderDown` critical alert; Primary On-Call paged.

### 6.4 Exercise 4: Redis Node Failure & Eviction Storm

- **Objective**: Verify that crashing Redis forces cache lookups to degrade to the local in-memory cache without failing user requests.
- **Chaos Injection**:
  ```bash
  # File: scripts/chaos/redis_failure_chaos.sh
  echo "Crashing Redis container..."
  kubectl scale deployment cerberus-redis -n cerberus --replicas=0

  echo "Submitting review request..."
  curl -s -X POST https://api.cerberus.example.com/api/v1/reviews \
    -H "Authorization: Bearer ${CERBERUS_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"code": "def hello(): return 1"}'
  ```
- **Expected Outcome**:
  - Request completes with HTTP 200.
  - Warning logged: `RedisConnectionError: falling back to local memory cache`.
  - AlertManager fires `RedisDown` critical alert within 60s.

### 6.5 Exercise 5: Database Connection Pool Exhaustion Stress Test

- **Objective**: Verify that exhausting PostgreSQL connections produces HTTP 503 instead of hanging processes.
- **Chaos Injection**:
  ```python
  # File: scripts/chaos/db_pool_exhaustion.py
  import asyncio
  import psycopg2

  # Open 500 connections holding idle transactions
  connections = []
  for i in range(450):
      conn = psycopg2.connect("postgresql://cerberus:${DB_PASSWORD}@localhost:5432/cerberus_db")
      cur = conn.cursor()
      cur.execute("BEGIN; SELECT pg_sleep(60);")
      connections.append(conn)

  print("450 connections acquired and sleeping...")
  ```
- **Expected Outcome**:
  - QueuePool hits maximum overflow and raises `TimeoutError`.
  - FastAPI returns HTTP 503 Service Unavailable with Retry-After header.
  - `DatabasePoolExhaustion` alert pages Primary On-Call within 2 minutes.

---

## 7. On-Call Rotation Framework, Escalation Trees & Shift Handover

Cerberus operates a follow-the-sun 24/7 on-call rotation to guarantee enterprise SLA compliance.

### 7.1 On-Call Roles & Core Responsibilities

- **Primary On-Call Engineer**:
  - Must acknowledge alerts within **15 minutes** (24/7).
  - Triage alerts using published incident runbooks.
  - Responsible for opening incident bridges and assigning the Incident Commander for SEV-1/SEV-2 events.
- **Secondary On-Call Engineer**:
  - Automatically paged if Primary does not acknowledge within 15 minutes.
  - Assists Primary on complex or concurrent incidents.
  - Steps in as Incident Commander if Primary is engaged in remediation.
- **Escalation Manager (EM)**:
  - Engineering Director or VP on rotation.
  - Manages internal stakeholder communication and client-facing SLA advisories.

### 7.2 PagerDuty Multi-Tier Escalation Matrix

| Escalation Level | Target Role | Paging SLA | Notification Mechanism |
|---|---|---|---|
| **Level 1** | Primary On-Call Engineer | 0 – 15 minutes | PagerDuty Mobile Push, High-Priority Phone Call, SMS |
| **Level 2** | Secondary On-Call Engineer | 15 – 30 minutes | Auto-escalation page, phone call, Slack `#alerts-critical` |
| **Level 3** | Technical Lead & Database Architect | 30 – 45 minutes | War room audio bridge invitation, PagerDuty escalation |
| **Level 4** | Engineering Director & VP of Engineering | 45+ minutes | Critical outage executive paging, emergency leadership bridge |

### 7.3 Daily Shift Handover Protocol & Checklist Template

Handovers take place daily at **10:00 UTC** via a mandatory 15-minute video sync between outgoing and incoming engineers.

```yaml
# File: docs/templates/oncall_handover_template.yaml
# Production On-Call Shift Handover Specification
metadata:
  date: "2026-09-24T10:00:00Z"
  outgoing_engineer: "dev_alice@enterprise.com"
  incoming_engineer: "dev_bob@enterprise.com"
  shift_window: "EMEA-to-US"

incident_summary:
  total_pagerduty_alerts: 2
  sev1_incidents: []
  sev2_incidents:
    - id: "INC-8942"
      title: "Watsonx API 429 throttling resolved via backoff"
  investigated_alerts:
    - alert: "DatabaseHighLatency"
      resolution: "Investigated slow query; index backfill completed"

active_silences:
  - alert_name: "CacheHitRateLow"
    reason: "Staging performance soak test in progress"
    expires_at: "2026-09-24T14:00:00Z"

infrastructure_status:
  database_migration: "Phase 1 Expand completed; repository_url backfill running"
  active_deployments: "Canary 10% active on v1.0.1"

verification_checklist:
  audio_alerts_verified: true
  k8s_production_context_confirmed: true
  aws_console_access_verified: true
  slack_signoff_recorded: true
```

### 7.4 Severity Tier Classification (SEV-1 to SEV-4) & SLA Commitments

| Tier | Definition | Initial Response SLA | Update Cadence | Resolution Target | Escalation Level |
|---|---|---|---|---|---|
| **SEV-1 (Critical)** | Total platform outage, data loss, API completely unresponsive, or security breach. | **< 15 minutes** | Every 15 minutes | < 2 hours | Full Incident Bridge, VP Engineering, CTO |
| **SEV-2 (Major)** | Core agent failure (e.g. Security Agent down), review throughput dropped by > 50%, or elevated 5xx error rate (>1%). | **< 30 minutes** | Every 30 minutes | < 4 hours | Lead SRE, Tech Lead, Director |
| **SEV-3 (Minor)** | Non-blocking feature impaired (e.g. Cost Analysis agent slow), isolated user errors, or batch review queue delayed. | **< 2 hours** | Daily | < 24 hours | Service Owner, Sprint Backlog |
| **SEV-4 (Low)** | Minor cosmetic UI flaws, documentation error, or non-urgent customer feature inquiry. | **< 1 business day** | Weekly | Next Sprint | Product Backlog |

---

## 8. Routine Preventive Maintenance Schedules

To maintain database performance, prevent certificate expiration, and eliminate technical debt, the operations team follows a strict preventive maintenance calendar.

### 8.1 Maintenance Schedules Overview

| Frequency | Target System | Maintenance Activity | Procedure / Command |
|---|---|---|---|
| **Daily** | Backup Storage | Audit S3 WAL archiving & RDS automated snapshots | `aws s3 ls s3://cerberus-backups/$(date +%Y%m%d)/` |
| **Daily** | Token Governance | Reconcile daily LLM cost burn vs $500 budget limit | Inspect Grafana panel: "Cumulative Daily LLM Cost" |
| **Daily** | Application Logs | Review Loki error log clustering for emerging warnings | `logcli query '{service="cerberus-api"} \|= "ERROR"' --since=24h` |
| **Weekly** | PostgreSQL | Execute `VACUUM ANALYZE` on high-churn tables | Automated via `pg_cron` (Sunday 02:00 UTC) |
| **Weekly** | Redis | Audit memory fragmentation and purge untracked keys | `redis-cli memory purge` |
| **Weekly** | Dependencies | Review and merge automated Dependabot / Renovate PRs | Security patch review gate |
| **Monthly** | TLS Certificates | Audit SSL/TLS expiration dates across ingress domains | `kubectl get certificates -A -o wide` |
| **Monthly** | Database Auth | Rotate database service passwords and API secret tokens | HashiCorp Vault automated dynamic credential rotation |
| **Monthly** | Disaster Recovery | Rehearse automated PITR restore on staging cluster | Full restore to point-in-time 24h prior |
| **Quarterly** | Security Access | Audit active API keys; revoke keys inactive > 90 days | Run `python -m cerberus.cli audit-stale-keys` |
| **Quarterly** | Chaos Game Day | Execute full-team chaos engineering drills | Run Game Day runbooks (§6) |
| **Quarterly** | Penetration Testing | Third-party external penetration test & CVE remediation | External vendor audit sign-off |

### 8.2 Automated Maintenance Cron Jobs (`maintenance_cron.yaml`)

```yaml
# File: k8s/maintenance_cron.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cerberus-weekly-db-maintenance
  namespace: cerberus
spec:
  schedule: "0 2 * * 0"  # Every Sunday at 02:00 UTC
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: postgres-vacuum
              image: postgres:15-alpine
              command:
                - /bin/sh
                - -c
                - |
                  echo "Starting PostgreSQL VACUUM ANALYZE..."
                  psql "${DATABASE_URL}" -c "VACUUM ANALYZE reviews;"
                  psql "${DATABASE_URL}" -c "VACUUM ANALYZE review_findings;"
                  echo "VACUUM ANALYZE completed successfully."
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: cerberus-db-secrets
                      key: database_url
          restartPolicy: OnFailure
```

---

## 9. Enterprise Security Compliance Audit Checklists

Cerberus is architected to satisfy strict multi-framework security audits across SOC 2 Type II, HIPAA, PCI-DSS v4.0, and ISO/IEC 27001:2022.

### 9.1 SOC 2 Type II Security & Confidentiality Controls

| Control ID | Trust Service Criteria | Cerberus Implementation | Audit Evidence Location |
|---|---|---|---|
| **CC6.1** | Logical Access Controls | Role-Based Access Control (RBAC) enforced; API keys hashed with SHA-256 before storage; MFA enforced for all cloud and cluster management. | `cerberus/core/auth.py`, Vault AppRole policies. |
| **CC6.6** | Perimeter & Boundary Protection | Kubernetes NetworkPolicies isolate DB and Redis; Cloudflare/AWS WAF filters malicious payloads and blocks unauthorized IP addresses. | `k8s/networkpolicies.yaml`, WAF rule configs. |
| **CC6.8** | Malicious Software Prevention | Automated CI/CD scanning with Bandit, Semgrep, Trivy, and TruffleHog blocks vulnerable code from reaching production. | `.github/workflows/security.yml`, Trivy reports. |
| **CC7.2** | Continuous Anomaly Monitoring | Prometheus metrics, AlertManager rules (32 production rules), and Loki structured logging provide 24/7 visibility into abnormal events. | `MONITORING_OPERATIONS.md`, AlertManager configs. |
| **CC8.1** | Change Management Governance | All changes require peer PR approval, 90% branch coverage, passing unit/integration tests, and formal CI/CD promotion gates. | GitHub branch protection rules, `.coveragerc`. |

### 9.2 HIPAA Security Rule (45 CFR Part 164) Alignment

| Regulation Section | Required Safeguard | Technical Implementation | Compliance Verification |
|---|---|---|---|
| **§ 164.312(a)(2)(iv)** | Encryption and Decryption | AES-256 encryption at rest on PostgreSQL and EBS; TLS 1.3 encryption in transit for all web and internal communications. | AWS KMS encryption keys; SSL/TLS cipher scans. |
| **§ 164.312(b)** | Audit Controls | Immutable JSON audit logs record all code review submissions, user IDs, tenant IDs, timestamps, and findings. Logs retained 7 years. | Promtail log shipping to S3 Glacier with Object Lock. |
| **§ 164.312(c)(1)** | Data Integrity Verification | SHA-256 checksums generated for all review input code and synthesized output reports to guarantee no tampering in transit. | Database `sha256_hash` columns on review records. |
| **§ 164.312(e)(1)** | Transmission Security | Ingress endpoints enforce HSTS (`max-age=31536000`); plain HTTP connections automatically redirected to HTTPS. | Ingress controller configuration. |

### 9.3 PCI-DSS v4.0 Cardholder Data & Code Protection

| Requirement | Requirement Description | Technical Implementation | Audit Artifact |
|---|---|---|---|
| **Requirement 3** | Protect Stored Account Data | Static analysis agents scan submitted code for raw Primary Account Numbers (PANs) and unencrypted CVVs; flags violations immediately. | `cerberus/agents/compliance_agent.py` PAN rules. |
| **Requirement 6** | Develop Secure Systems | Automated SAST and DAST gates eliminate OWASP Top 10 vulnerabilities (CWE-89 SQLi, CWE-79 XSS, CWE-798 Hardcoded Secrets). | Bandit and Semgrep CI pipeline execution logs. |
| **Requirement 8** | Identify Users and Authenticate Access | Individual API keys assigned to client systems; bearer tokens validated cryptographically with strict revocation capabilities. | `cerberus/core/auth.py`, API key audit table. |
| **Requirement 10** | Log and Monitor All Access | Every API request logs timestamp, client identity, endpoint, status code, and duration without logging sensitive cardholder data. | Structured log stream in Loki with PII masking. |

### 9.4 ISO/IEC 27001:2022 Annex A Information Security Controls

| Annex A Control | Control Objective | Cerberus Implementation | Verification Method |
|---|---|---|---|
| **A.5.15** | Access Control | Principle of least privilege enforced on Kubernetes ServiceAccounts and AWS IAM roles; root container execution blocked. | `kubectl get serviceaccount`, IAM policy audits. |
| **A.8.8** | Vulnerability Management | Continuous dependency and container scanning; Critical CVE patching SLA enforced: `< 7 calendar days`. | Trivy scan reports, Dependabot pull requests. |
| **A.8.24** | Use of Cryptography | Modern cryptographic suites enforced (AES-GCM, SHA-256, TLS 1.3); deprecated algorithms (MD5, SHA-1, DES) strictly disallowed. | Codebase AST audit for deprecated hashlib functions. |
| **A.8.28** | Secure Coding | Code review agents enforce coding standards, bounds checking, and input sanitization directly within the CI/CD pull request gate. | `TESTING_STRATEGY.md`, Multi-agent review policies. |

---

## 10. Summary & Next Steps

This **Production Launch & Operations Manual** provides the comprehensive operational framework required to launch, monitor, maintain, and safeguard Cerberus in mission-critical enterprise environments. By combining a 105-item pre-launch verification checklist, a minute-by-minute cutover plan, zero-downtime database migration methodologies, automated rollback procedures, chaos engineering exercises, and rigorous compliance checklists, operations and site reliability teams have the tools needed to guarantee high availability and security.

### Documentation Roadmap Index
For complete architectural, implementation, API, and testing specifications across the Cerberus platform, reference the comprehensive documentation suite:

1. **Phase 1 Implementation Guide**: `PHASE_1_DETAILED_IMPLEMENTATION.md`
2. **Specialized Agent Specifications**: `AGENT_SPECIFICATIONS.md`
3. **Database Design & Migration Architecture**: `DATABASE_DESIGN.md`
4. **API Specifications & FastAPI Setup**: `API_SPECIFICATIONS.md`
5. **Deployment & Infrastructure Guide**: `DEPLOYMENT_GUIDE.md`
6. **Monitoring, Observability & Operations**: `MONITORING_OPERATIONS.md`
7. **Enterprise Testing Strategy**: `TESTING_STRATEGY.md`
8. **Production Launch Manual**: `PRODUCTION_LAUNCH_MANUAL.md` (This Document)
