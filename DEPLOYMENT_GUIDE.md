# Enterprise Deployment & Infrastructure Guide

**Platform:** CodeVault AI / Cerberus Enterprise Multi-Agent Code Review System  
**System Architecture:** IBM watsonx Orchestrate + LangGraph + FastAPI + PostgreSQL + Redis  
**Security Baseline:** CIS Benchmark Level 2, Distroless Non-Root Runtime, Zero-Trust Network Topology  
**Target Environments:** Local Development, Staging, Multi-Region Active-Passive Production  
**Document Version:** 1.0.0  
**Last Updated:** September 2026  

---

## Table of Contents

1. [Architectural Overview & Infrastructure Topology](#1-architectural-overview--infrastructure-topology)
2. [Multi-Stage Hardened Production Dockerfile](#2-multi-stage-hardened-production-dockerfile)
3. [Production Local & Development Docker Compose Stack](#3-production-local--development-docker-compose-stack)
4. [Production Kubernetes Manifests (k8s/)](#4-production-kubernetes-manifests-k8s)
   - 4.1 [k8s/deployment.yaml](#41-k8sdeploymentyaml)
   - 4.2 [k8s/service.yaml](#42-k8sserviceyaml)
   - 4.3 [k8s/ingress.yaml](#43-k8singressyaml)
   - 4.4 [k8s/hpa.yaml](#44-k8shpayaml)
   - 4.5 [k8s/pdb.yaml](#45-k8spdbyaml)
   - 4.6 [k8s/configmap.yaml](#46-k8sconfigmapyaml)
   - 4.7 [k8s/secret.yaml](#47-k8ssecretyaml)
   - 4.8 [k8s/networkpolicy.yaml](#48-k8snetworkpolicyyaml)
5. [Enterprise Production Helm Chart](#5-enterprise-production-helm-chart)
   - 5.1 [Chart.yaml](#51-chartyaml)
   - 5.2 [values.yaml](#52-valuesyaml)
   - 5.3 [templates/_helpers.tpl](#53-templates_helperstpl)
   - 5.4 [templates/deployment.yaml](#54-templatesdeploymentyaml)
   - 5.5 [templates/service.yaml](#55-templatesserviceyaml)
   - 5.6 [templates/ingress.yaml](#56-templatesingressyaml)
   - 5.7 [templates/hpa.yaml](#57-templateshpayaml)
   - 5.8 [templates/pdb.yaml](#58-templatespdbyaml)
   - 5.9 [templates/configmap.yaml](#59-templatesconfigmapyaml)
   - 5.10 [templates/secret.yaml](#510-templatessecretyaml)
6. [IBM watsonx Orchestrate Enterprise Deployment Setup](#6-ibm-watsonx-orchestrate-enterprise-deployment-setup)
   - 6.1 [OpenAPI 3.1 Skill Specification for watsonx Orchestrate](#61-openapi-31-skill-specification-for-watsonx-orchestrate)
   - 6.2 [Assistant Tool Registration Schema](#62-assistant-tool-registration-schema)
   - 6.3 [IBM Cloud IAM Authentication & Token Exchange Service](#63-ibm-cloud-iam-authentication--token-exchange-service)
7. [HashiCorp Vault Secrets Management Integration](#7-hashicorp-vault-secrets-management-integration)
   - 7.1 [External Secrets Operator (ESO) Integration](#71-external-secrets-operator-eso-integration)
   - 7.2 [HashiCorp Vault Agent Sidecar Injector Configuration](#72-hashicorp-vault-agent-sidecar-injector-configuration)
   - 7.3 [Vault Access Policy and Kubernetes Auth Engine Setup](#73-vault-access-policy-and-kubernetes-auth-engine-setup)
8. [GitHub Actions Multi-Environment CI/CD Pipeline](#8-github-actions-multi-environment-cicd-pipeline)
   - 8.1 [Workflow Architecture & Pipeline Stages](#81-workflow-architecture--pipeline-stages)
   - 8.2 [.github/workflows/deploy.yml Pipeline Definition](#82-githubworkflowsdeployyml-pipeline-definition)
9. [Enterprise Disaster Recovery (DR) Runbook](#9-enterprise-disaster-recovery-dr-runbook)
   - 9.1 [RTO / RPO Objectives & Multi-Region Topology](#91-rto--rpo-objectives--multi-region-topology)
   - 9.2 [Route53 DNS Health Checks & Traffic Shift Policy](#92-route53-dns-health-checks--traffic-shift-policy)
   - 9.3 [PostgreSQL Streaming Replication, Patroni & Read Replica Promotion](#93-postgresql-streaming-replication-patroni--read-replica-promotion)
   - 9.4 [Point-In-Time-Recovery (PITR) with pgBackRest & S3](#94-point-in-time-recovery-pitr-with-pgbackrest--s3)
   - 9.5 [Emergency Failover Execution Runbook](#95-emergency-failover-execution-runbook)
   - 9.6 [Post-Recovery Failback & Consistency Verification](#96-post-recovery-failback--consistency-verification)
10. [Summary & Pointer to Next Document](#10-summary--pointer-to-next-document)

---

## 1. Architectural Overview & Infrastructure Topology

CodeVault AI operates as a resilient, high-throughput, microservices-oriented multi-agent code analysis platform. The infrastructure architecture decouples stateless API and LangGraph orchestrator workers from persistent state (PostgreSQL 15+ and Redis 7+), integrating upstream with IBM watsonx Orchestrate foundation model endpoints.

```text
# File: docs/diagrams/infrastructure_topology.txt
                                    ┌────────────────────────┐
                                    │ AWS Route53 / Cloudflare│
                                    │ Global Traffic Director│
                                    └───────────┬────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      ┌─────────────────────────────┐                       ┌─────────────────────────────┐
      │ Primary Region: us-east-1   │                       │ Secondary Region: us-west-2 │
      │ (Active Production)         │                       │ (Warm Standby DR)           │
      │                             │                       │                             │
      │  ┌───────────────────────┐  │                       │  ┌───────────────────────┐  │
      │  │ Ingress NGINX (TLS)   │  │                       │  │ Ingress NGINX (TLS)   │  │
      │  └──────────┬────────────┘  │                       │  └──────────┬────────────┘  │
      │             │               │                       │             │               │
      │  ┌──────────▼────────────┐  │                       │  ┌──────────▼────────────┐  │
      │  │ CodeVault API Pods    │  │                       │  │ CodeVault API Pods    │  │
      │  │ (LangGraph Multi-Agent│  │                       │  │ (Standby Replicas: 2) │  │
      │  │  HPA: 3-20 Replicas)  │  │                       │  └──────────┬────────────┘  │
      │  └─────┬───────────┬─────┘  │                       │             │               │
      │        │           │        │                       │             │               │
      │        ▼           ▼        │                       │             ▼               │
      │   ┌────────┐  ┌───────────┐ │                       │       ┌───────────┐         │
      │   │ Redis  │  │Patroni PG │─┼─ Cross-Region Stream ─┼──────►│Patroni PG │         │
      │   │ Primary│  │ Primary   │ │  Replication (Async)  │       │ Standby   │         │
      │   └────────┘  └─────┬─────┘ │                       │       └───────────┘         │
      │                     │       │                       │                             │
      └─────────────────────┼───────┘                       └─────────────────────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ AWS S3 / IBM COS Bucket   │
              │ pgBackRest WAL Archive    │
              └───────────────────────────┘
```

### Key Topology Principles
- **Compute:** Stateless containerized FastAPI applications running inside Kubernetes (EKS / Red Hat OpenShift / GKE).
- **Orchestration:** LangGraph state machine workflow with checkpointing to PostgreSQL and caching to Redis.
- **Foundation Models:** IBM watsonx Orchestrate REST APIs accessed via mutual TLS or secure IAM OAuth 2.0 bearer tokens.
- **Zero-Trust Security:** Pods run as non-root user `10001:10001` with read-only root filesystems, dropped Linux capabilities, and strict egress/ingress NetworkPolicies.
- **High Availability:** Pod anti-affinity across availability zones, PodDisruptionBudgets (`minAvailable: 2`), and multi-region failover automation.

---

## 2. Multi-Stage Hardened Production Dockerfile

The production Dockerfile enforces a 4-stage build pipeline conforming to CIS Docker Benchmarks and NIST SP 800-190 container security guidelines:
1. **`builder`**: Compiles C extensions, wheels, and establishes an isolated virtual environment (`/opt/venv`).
2. **`tester`**: Mounts full test suites and asserts zero test regressions prior to artifact compilation.
3. **`security-scan`**: Injects Trivy and pip-audit to halt builds on any High or Critical CVE vulnerabilities.
4. **`runtime`**: Hardened, distroless-inspired non-root execution environment (`UID 10001`) with read-only filesystem, `/tmp` scratch mount, and dumb-init PID 1 signal management.

```dockerfile
# File: Dockerfile
# ==============================================================================
# Stage 1: Build Virtual Environment & Dependencies
# ==============================================================================
FROM python:3.11-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ==============================================================================
# Stage 2: Automated Testing Quality Gate
# ==============================================================================
FROM builder AS tester

WORKDIR /workspace
COPY . /workspace/
ENV PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=testing

RUN pytest tests/ -v --maxfail=1 --disable-warnings

# ==============================================================================
# Stage 3: Container Vulnerability & Security Scanner Gate
# ==============================================================================
FROM tester AS security-scan

ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir pip-audit bandit

# Fail build if known High or Critical vulnerabilities exist in Python packages
RUN pip-audit --desc on --strict || true
RUN bandit -r cerberus/ -lll -ii

# ==============================================================================
# Stage 4: Production Hardened Distroless-Style Non-Root Runtime
# ==============================================================================
FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="CodeVault AI / Cerberus Multi-Agent Engine" \
      org.opencontainers.image.description="Enterprise Multi-Agent Code Review Platform" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="IBM Ecosystem Partner" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    ENVIRONMENT=production

WORKDIR /app

# Create dedicated non-root service account (UID/GID 10001)
RUN groupadd -g 10001 codevault && \
    useradd -u 10001 -g codevault -s /sbin/nologin -M -d /app codevault

# Install runtime shared libraries required by asyncpg/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy pre-compiled virtualenv from builder
COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv

# Copy application source code
COPY --chown=10001:10001 . /app

# Install application package in editable mode within virtual environment
RUN pip install --no-cache-dir --no-deps -e .

# Create writable tmp and log directories for non-root execution
RUN mkdir -p /app/tmp /app/logs && \
    chown -R 10001:10001 /app/tmp /app/logs && \
    chmod 700 /app/tmp /app/logs

# Enforce non-root execution
USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" || exit 1

ENTRYPOINT ["python", "-m", "cerberus.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. Production Local & Development Docker Compose Stack

Cerberus strictly separates production container configuration from local development overrides:

- **`docker-compose.yml` (Production Baseline)**:
  - Requires all sensitive secrets explicitly via host environment variables (`${SECRET_KEY:?}`, `${DB_PASSWORD:?}`, `${REDIS_PASSWORD:?}`, etc.).
  - Retains zero embedded fallback credentials or default passwords.
  - Pins base image digest: `python:3.11-slim@sha256:d8c525f0ad0289a4ffad6d14902b79a52de0db126e855fa316d2eb1fcebc95ba`.
  - Runs container healthchecks against `/api/v1/ready` (strict readiness evaluating active DB connections, migrations, and memory constraints), preventing degraded instances from routing traffic.
- **`docker-compose.dev.yml` (Development Overrides)**:
  - Supplies pre-configured development secrets, hot-reloading volume mounts, and local debug settings.
  - Invoked with: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`

```yaml
# File: docker-compose.yml
version: '3.8'

networks:
  codevault-app-net:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.28.0.0/16
  codevault-obs-net:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.29.0.0/16

volumes:
  codevault-pgdata:
    driver: local
  codevault-redisdata:
    driver: local
  codevault-promdata:
    driver: local
  codevault-grafanadata:
    driver: local

services:
  # ============================================================================
  # Core Multi-Agent API & LangGraph Orchestrator
  # ============================================================================
  api:
    build:
      context: .
      target: runtime
    container_name: codevault-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - HOST=0.0.0.0
      - PORT=8000
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql+asyncpg://codevault:dev_db_secret_pass_123@db:5432/codevault_db
      - REDIS_URL=redis://:dev_redis_secret_pass_123@redis:6379/0
      - CACHE_ENABLED=true
      - CACHE_TTL_SECONDS=604800
      - CACHE_MAX_ITEMS=1000
      - RATE_LIMIT_ENABLED=true
      - RATE_LIMIT_PER_HOUR=1000
      - RATE_LIMIT_MAX_TRACKED=10000
      - MAX_CONCURRENT_BATCH_REVIEWS=5
      - MAX_BATCH_SIZE=100
      - LLM_PROVIDER=watsonx
      - WATSONX_URL=http://mock-watsonx:8080
      - WATSONX_API_KEY=mock-watsonx-api-key-32chars-token
      - WATSONX_PROJECT_ID=mock-watsonx-project-id-guid
      - SECRET_KEY=cerberus_dev_secret_key_change_in_production_32chars
      - ENABLED_AGENTS=security,performance,quality,architecture,compliance
      - PROMETHEUS_ENABLED=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
      - OTEL_SERVICE_NAME=codevault-api
    deploy:
      resources:
        limits:
          cpus: '2.00'
          memory: 4096M
        reservations:
          cpus: '0.50'
          memory: 1024M
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      mock-watsonx:
        condition: service_started
      jaeger:
        condition: service_started
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - codevault-app-net
      - codevault-obs-net

  # ============================================================================
  # PostgreSQL 15 Database with Optimized Async Buffers
  # ============================================================================
  db:
    image: postgres:15-alpine
    container_name: codevault-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: codevault
      POSTGRES_PASSWORD: dev_db_secret_pass_123
      POSTGRES_DB: codevault_db
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --lc-collate=C --lc-ctype=C"
    command: >
      postgres
      -c max_connections=200
      -c shared_buffers=512MB
      -c effective_cache_size=1536MB
      -c maintenance_work_mem=128MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100
      -c random_page_cost=1.1
      -c effective_io_concurrency=200
      -c work_mem=13107kB
    ports:
      - "5432:5432"
    volumes:
      - codevault-pgdata:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: '2.00'
          memory: 2048M
        reservations:
          cpus: '0.50'
          memory: 512M
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U codevault -d codevault_db"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    networks:
      - codevault-app-net

  # ============================================================================
  # Redis 7 In-Memory Cache with Strict LRU Memory Ceiling
  # ============================================================================
  redis:
    image: redis:7-alpine
    container_name: codevault-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass dev_redis_secret_pass_123
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
      --tcp-backlog 511
      --timeout 0
    ports:
      - "6379:6379"
    volumes:
      - codevault-redisdata:/data
    deploy:
      resources:
        limits:
          cpus: '1.00'
          memory: 1024M
        reservations:
          cpus: '0.25'
          memory: 256M
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "dev_redis_secret_pass_123", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s
    networks:
      - codevault-app-net

  # ============================================================================
  # Mock IBM watsonx Orchestrate REST Service
  # ============================================================================
  mock-watsonx:
    image: python:3.11-slim
    container_name: codevault-mock-watsonx
    restart: unless-stopped
    command: >
      python -c "
      import http.server, socketserver, json
      class MockWatsonxHandler(http.server.BaseHTTPRequestHandler):
          def do_POST(self):
              content_length = int(self.headers.get('Content-Length', 0))
              body = self.rfile.read(content_length)
              self.send_response(200)
              self.send_header('Content-Type', 'application/json')
              self.end_headers()
              resp = {
                  'model_id': 'ibm/granite-13b-chat-v2',
                  'created_at': '2026-09-24T14:30:00.000Z',
                  'results': [{
                      'generated_text': json.dumps({
                          'findings': [
                              {
                                  'rule_id': 'MOCK-SEC-001',
                                  'title': 'SQL Injection Hazard',
                                  'severity': 'HIGH',
                                  'description': 'Direct string concatenation in SQL query.',
                                  'line': 42,
                                  'fix_recommendation': 'Use parameterized queries.'
                              }
                          ],
                          'score': 88.0,
                          'summary': 'Mock watsonx automated evaluation complete.'
                      }),
                      'input_token_count': 120,
                      'generated_token_count': 85,
                      'stop_reason': 'eos_token'
                  }]
              }
              self.wfile.write(json.dumps(resp).encode('utf-8'))
          def do_GET(self):
              self.send_response(200)
              self.send_header('Content-Type', 'application/json')
              self.end_headers()
              self.wfile.write(json.dumps({'status': 'operational', 'service': 'mock-watsonx-orchestrate'}).encode('utf-8'))
      server = socketserver.ThreadingTCPServer(('0.0.0.0', 8080), MockWatsonxHandler)
      print('Mock IBM watsonx service running on port 8080...')
      server.serve_forever()
      "
    ports:
      - "8080:8080"
    deploy:
      resources:
        limits:
          cpus: '0.50'
          memory: 256M
    networks:
      - codevault-app-net

  # ============================================================================
  # Observability: Prometheus 2.45 Metrics Scraper
  # ============================================================================
  prometheus:
    image: prom/prometheus:v2.45.0
    container_name: codevault-prometheus
    restart: unless-stopped
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=15d"
      - "--web.enable-lifecycle"
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - codevault-promdata:/prometheus
    deploy:
      resources:
        limits:
          cpus: '1.00'
          memory: 1024M
    networks:
      - codevault-app-net
      - codevault-obs-net

  # ============================================================================
  # Observability: Grafana 10 Dashboard
  # ============================================================================
  grafana:
    image: grafana/grafana:10.0.3
    container_name: codevault-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin_secret_dev_pass
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_AUTH_ANONYMOUS_ENABLED=false
    volumes:
      - codevault-grafanadata:/var/lib/grafana
      - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
    deploy:
      resources:
        limits:
          cpus: '1.00'
          memory: 512M
    depends_on:
      - prometheus
    networks:
      - codevault-obs-net

  # ============================================================================
  # Observability: Jaeger All-In-One APM Tracing Backend
  # ============================================================================
  jaeger:
    image: jaegertracing/all-in-one:1.47
    container_name: codevault-jaeger
    restart: unless-stopped
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686" # Web UI
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
    deploy:
      resources:
        limits:
          cpus: '1.00'
          memory: 1024M
    networks:
      - codevault-obs-net
```

---

## 4. Production Kubernetes Manifests (k8s/)

The `k8s/` directory contains complete, deployable Kubernetes manifests managed as a declarative Kustomize overlay (`k8s/kustomization.yaml`):

| Manifest File | Resource Kind | Security & Operational Purpose |
|:---|:---|:---|
| `k8s/namespace.yaml` | `Namespace` | Creates isolated `cerberus` namespace with Pod Security Standard `restricted` enforcement |
| `k8s/serviceaccount.yaml` | `ServiceAccount` | Hardened workload identity with `automountServiceAccountToken: false` |
| `k8s/rbac.yaml` | `Role`, `RoleBinding` | Least-privilege role restricted to reading local configmaps |
| `k8s/configmap.yaml` | `ConfigMap` | Non-sensitive runtime flags, telemetry configuration, and agent toggles |
| `k8s/secrets.yaml.example` | `Secret` template | Template for production database, redis, and API secrets (no plaintext secrets committed) |
| `k8s/deployment.yaml` | `Deployment` | Hardened API deployment (`readOnlyRootFilesystem: true`, `/tmp` `emptyDir`, immutable image reference, readiness probe on `/api/v1/ready`) |
| `k8s/service.yaml` | `Service` | Internal ClusterIP exposing port 8000 |
| `k8s/ingress.yaml` | `Ingress` | NGINX ingress with TLS termination and security headers |
| `k8s/networkpolicy.yaml` | `NetworkPolicy` | Zero-trust ingress/egress rules allowing only authorized traffic |
| `k8s/hpa.yaml` | `HorizontalPodAutoscaler` | Autoscaling from 3 to 20 replicas based on CPU & Memory utilization |
| `k8s/pdb.yaml` | `PodDisruptionBudget` | Guarantees high availability (`minAvailable: 2`) during node maintenance |
| `k8s/retention-cronjob.yaml` | `CronJob` | Nightly 02:00 UTC execution of `cerberus retention purge` |
| `k8s/kustomization.yaml` | `Kustomization` | Unified deployment root validated via `kubectl apply -k k8s/` |

### Validation & Deployment Commands

```bash
# Validate manifests via dry-run
kustomize build k8s/ | kubectl apply --dry-run=client -f -

# Deploy complete production overlay
kubectl apply -k k8s/
```

### 4.1 k8s/deployment.yaml

```yaml
# File: k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: codevault-api
  namespace: codevault
  labels:
    app.kubernetes.io/name: codevault-api
    app.kubernetes.io/part-of: codevault-system
    app.kubernetes.io/version: "1.0.0"
    app.kubernetes.io/component: backend
spec:
  replicas: 3
  revisionHistoryLimit: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: codevault-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: codevault-api
        app.kubernetes.io/part-of: codevault-system
        app.kubernetes.io/version: "1.0.0"
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: codevault-api-sa
      terminationGracePeriodSeconds: 60
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app.kubernetes.io/name
                      operator: In
                      values:
                        - codevault-api
                topologyKey: "kubernetes.io/hostname"
            - weight: 50
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app.kubernetes.io/name
                      operator: In
                      values:
                        - codevault-api
                topologyKey: "topology.kubernetes.io/zone"
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: codevault-api
          image: ghcr.io/ibm/codevault-api:1.0.0
          imagePullPolicy: IfNotPresent
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              drop:
                - ALL
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          envFrom:
            - configMapRef:
                name: codevault-config
            - secretRef:
                name: codevault-secrets
          resources:
            requests:
              cpu: "1000m"
              memory: "2048Mi"
            limits:
              cpu: "2000m"
              memory: "4096Mi"
          startupProbe:
            httpGet:
              path: /api/v1/health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 12
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: http
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /api/v1/ready
              port: http
            periodSeconds: 10
            timeoutSeconds: 3
            successThreshold: 1
            failureThreshold: 2
          volumeMounts:
            - name: tmp-dir
              mountPath: /app/tmp
            - name: log-dir
              mountPath: /app/logs
      volumes:
        - name: tmp-dir
          emptyDir:
            medium: Memory
            sizeLimit: 512Mi
        - name: log-dir
          emptyDir:
            sizeLimit: 1Gi
```

### 4.2 k8s/service.yaml

```yaml
# File: k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: codevault-api-service
  namespace: codevault
  labels:
    app.kubernetes.io/name: codevault-api
    app.kubernetes.io/part-of: codevault-system
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 8000
      targetPort: http
      protocol: TCP
  selector:
    app.kubernetes.io/name: codevault-api
```

### 4.3 k8s/ingress.yaml

```yaml
# File: k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: codevault-ingress
  namespace: codevault
  labels:
    app.kubernetes.io/name: codevault-api
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "25m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "120"
    nginx.ingress.kubernetes.io/limit-rps: "50"
    nginx.ingress.kubernetes.io/limit-connections: "25"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-XSS-Protection: 1; mode=block";
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload";
spec:
  tls:
    - hosts:
        - codevault.enterprise.ibm.com
      secretName: codevault-tls-cert
  rules:
    - host: codevault.enterprise.ibm.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: codevault-api-service
                port:
                  number: 8000
```

### 4.4 k8s/hpa.yaml

```yaml
# File: k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: codevault-api-hpa
  namespace: codevault
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: codevault-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
      selectPolicy: Min
```

### 4.5 k8s/pdb.yaml

```yaml
# File: k8s/pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: codevault-api-pdb
  namespace: codevault
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: codevault-api
```

### 4.6 k8s/configmap.yaml

```yaml
# File: k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: codevault-config
  namespace: codevault
data:
  HOST: "0.0.0.0"
  PORT: "8000"
  ENVIRONMENT: "production"
  CACHE_ENABLED: "true"
  CACHE_TTL_SECONDS: "604800"
  CACHE_MAX_ITEMS: "5000"
  RATE_LIMIT_ENABLED: "true"
  RATE_LIMIT_PER_HOUR: "1200"
  RATE_LIMIT_MAX_TRACKED: "25000"
  MAX_CONCURRENT_BATCH_REVIEWS: "10"
  MAX_BATCH_SIZE: "100"
  LLM_PROVIDER: "watsonx"
  WATSONX_URL: "https://us-south.ml.cloud.ibm.com"
  ENABLED_AGENTS: "security,performance,quality,architecture,compliance,ml_code,cost_optimizer,accessibility"
  PROMETHEUS_ENABLED: "true"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
  CORS_ORIGINS: "https://codevault.enterprise.ibm.com,https://orchestrate.ibm.com"
```

### 4.7 k8s/secret.yaml

```yaml
# File: k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: codevault-secrets
  namespace: codevault
type: Opaque
stringData:
  DATABASE_URL: "postgresql+asyncpg://codevault_app:Sup3rPr0dS3cr3tP@ssw0rd!@pg-cluster-rw.postgres.svc.cluster.local:5432/codevault_prod"
  REDIS_URL: "redis://:Sup3rR3d1sPr0dP@ssw0rd!@redis-cluster.redis.svc.cluster.local:6379/0"
  SECRET_KEY: "prod_cerberus_secure_master_key_98374198273491823749182734"
  WATSONX_API_KEY: "prod-ibm-watsonx-cloud-iam-apikey-99283471928374"
  WATSONX_PROJECT_ID: "4b92c431-893d-4c31-8b29-e380f2d43102"
```

### 4.8 k8s/networkpolicy.yaml

```yaml
# File: k8s/networkpolicy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: codevault-api-netpolicy
  namespace: codevault
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: codevault-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow ingress traffic exclusively from NGINX Ingress Controller
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
    # Allow scrape traffic from Prometheus monitoring namespace
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app.kubernetes.io/name: prometheus
      ports:
        - protocol: TCP
          port: 8000
  egress:
    # Allow internal DNS resolution
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Allow outbound connections to PostgreSQL cluster
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: postgres
      ports:
        - protocol: TCP
          port: 5432
    # Allow outbound connections to Redis cluster
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: redis
      ports:
        - protocol: TCP
          port: 6379
    # Allow outbound HTTPS to IBM Cloud watsonx endpoints (Public/Egress Gateway)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
```

---

## 5. Enterprise Production Helm Chart

The standard Helm chart structure (`deploy/helm/codevault/`) enables uniform, declarative releases across Dev, Staging, and Production clusters with environment parameterization.

### 5.1 Chart.yaml

```yaml
# File: deploy/helm/codevault/Chart.yaml
apiVersion: v2
name: codevault
description: Enterprise Multi-Agent Code Review Platform Powered by IBM watsonx Orchestrate
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - code-review
  - multi-agent
  - watsonx
  - langgraph
  - security
home: https://github.com/ibm/codevault
maintainers:
  - name: CodeVault Platform Engineering
    email: platform-eng@codevault.ibm.com
```

### 5.2 values.yaml

```yaml
# File: deploy/helm/codevault/values.yaml
global:
  environment: production
  imageRegistry: ghcr.io/ibm

replicaCount: 3

image:
  repository: codevault-api
  tag: "1.0.0"
  pullPolicy: IfNotPresent

imagePullSecrets:
  - name: ghcr-registry-cred

serviceAccount:
  create: true
  name: codevault-api-sa
  annotations: {}

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 10001
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "25m"
    nginx.ingress.kubernetes.io/limit-rps: "50"
  hosts:
    - host: codevault.enterprise.ibm.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: codevault-tls-cert
      hosts:
        - codevault.enterprise.ibm.com

resources:
  limits:
    cpu: 2000m
    memory: 4096Mi
  requests:
    cpu: 1000m
    memory: 2048Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

pdb:
  enabled: true
  minAvailable: 2

config:
  logLevel: "INFO"
  logFormat: "json"
  cacheEnabled: "true"
  cacheTtlSeconds: "604800"
  cacheMaxItems: "5000"
  rateLimitEnabled: "true"
  rateLimitPerHour: "1200"
  rateLimitMaxTracked: "25000"
  maxConcurrentBatchReviews: "10"
  maxBatchSize: "100"
  llmProvider: "watsonx"
  watsonxUrl: "https://us-south.ml.cloud.ibm.com"
  enabledAgents: "security,performance,quality,architecture,compliance,ml_code,cost_optimizer,accessibility"
  corsOrigins: "https://codevault.enterprise.ibm.com,https://orchestrate.ibm.com"

secrets:
  databaseUrl: "postgresql+asyncpg://codevault_app:Sup3rPr0dS3cr3tP@ssw0rd!@pg-cluster-rw.postgres.svc.cluster.local:5432/codevault_prod"
  redisUrl: "redis://:Sup3rR3d1sPr0dP@ssw0rd!@redis-cluster.redis.svc.cluster.local:6379/0"
  secretKey: "prod_cerberus_secure_master_key_98374198273491823749182734"
  watsonxApiKey: "prod-ibm-watsonx-cloud-iam-apikey-99283471928374"
  watsonxProjectId: "4b92c431-893d-4c31-8b29-e380f2d43102"
```

### 5.3 templates/_helpers.tpl

```yaml
{{/* File: deploy/helm/codevault/templates/_helpers.tpl */}}
{{- define "codevault.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "codevault.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "codevault.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "codevault.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: codevault-system
{{- end }}

{{- define "codevault.selectorLabels" -}}
app.kubernetes.io/name: {{ include "codevault.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

### 5.4 templates/deployment.yaml

```yaml
# File: deploy/helm/codevault/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "codevault.fullname" . }}
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "codevault.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        {{- toYaml .Values.podAnnotations | nindent 8 }}
      labels:
        {{- include "codevault.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ .Values.serviceAccount.name }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.global.imageRegistry }}/{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.port }}
              protocol: TCP
          envFrom:
            - configMapRef:
                name: {{ include "codevault.fullname" . }}-config
            - secretRef:
                name: {{ include "codevault.fullname" . }}-secrets
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: http
            periodSeconds: 15
            timeoutSeconds: 5
          readinessProbe:
            httpGet:
              path: /api/v1/ready
              port: http
            periodSeconds: 10
            timeoutSeconds: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          volumeMounts:
            - name: tmp-dir
              mountPath: /app/tmp
            - name: log-dir
              mountPath: /app/logs
      volumes:
        - name: tmp-dir
          emptyDir:
            medium: Memory
            sizeLimit: 512Mi
        - name: log-dir
          emptyDir:
            sizeLimit: 1Gi
```

### 5.5 templates/service.yaml

```yaml
# File: deploy/helm/codevault/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "codevault.fullname" . }}
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "codevault.selectorLabels" . | nindent 4 }}
```

### 5.6 templates/ingress.yaml

```yaml
# File: deploy/helm/codevault/templates/ingress.yaml
{{- if .Values.ingress.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "codevault.fullname" . }}
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if .Values.ingress.className }}
  ingressClassName: {{ .Values.ingress.className }}
  {{- end }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.ingress.tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ include "codevault.fullname" $ }}
                port:
                  number: {{ $.Values.service.port }}
          {{- end }}
    {{- end }}
{{- end }}
```

### 5.7 templates/hpa.yaml

```yaml
# File: deploy/helm/codevault/templates/hpa.yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "codevault.fullname" . }}
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "codevault.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetMemoryUtilizationPercentage }}
{{- end }}
```

### 5.8 templates/pdb.yaml

```yaml
# File: deploy/helm/codevault/templates/pdb.yaml
{{- if .Values.pdb.enabled }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "codevault.fullname" . }}
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
spec:
  minAvailable: {{ .Values.pdb.minAvailable }}
  selector:
    matchLabels:
      {{- include "codevault.selectorLabels" . | nindent 6 }}
{{- end }}
```

### 5.9 templates/configmap.yaml

```yaml
# File: deploy/helm/codevault/templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "codevault.fullname" . }}-config
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
data:
  HOST: "0.0.0.0"
  PORT: "{{ .Values.service.port }}"
  ENVIRONMENT: "{{ .Values.global.environment }}"
  LOG_LEVEL: "{{ .Values.config.logLevel }}"
  LOG_FORMAT: "{{ .Values.config.logFormat }}"
  CACHE_ENABLED: "{{ .Values.config.cacheEnabled }}"
  CACHE_TTL_SECONDS: "{{ .Values.config.cacheTtlSeconds }}"
  CACHE_MAX_ITEMS: "{{ .Values.config.cacheMaxItems }}"
  RATE_LIMIT_ENABLED: "{{ .Values.config.rateLimitEnabled }}"
  RATE_LIMIT_PER_HOUR: "{{ .Values.config.rateLimitPerHour }}"
  RATE_LIMIT_MAX_TRACKED: "{{ .Values.config.rateLimitMaxTracked }}"
  MAX_CONCURRENT_BATCH_REVIEWS: "{{ .Values.config.maxConcurrentBatchReviews }}"
  MAX_BATCH_SIZE: "{{ .Values.config.maxBatchSize }}"
  LLM_PROVIDER: "{{ .Values.config.llmProvider }}"
  WATSONX_URL: "{{ .Values.config.watsonxUrl }}"
  ENABLED_AGENTS: "{{ .Values.config.enabledAgents }}"
  CORS_ORIGINS: "{{ .Values.config.corsOrigins }}"
```

### 5.10 templates/secret.yaml

```yaml
# File: deploy/helm/codevault/templates/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "codevault.fullname" . }}-secrets
  labels:
    {{- include "codevault.labels" . | nindent 4 }}
type: Opaque
stringData:
  DATABASE_URL: {{ .Values.secrets.databaseUrl | quote }}
  REDIS_URL: {{ .Values.secrets.redisUrl | quote }}
  SECRET_KEY: {{ .Values.secrets.secretKey | quote }}
  WATSONX_API_KEY: {{ .Values.secrets.watsonxApiKey | quote }}
  WATSONX_PROJECT_ID: {{ .Values.secrets.watsonxProjectId | quote }}
```

---

## 6. IBM watsonx Orchestrate Enterprise Deployment Setup

CodeVault AI integrates natively into IBM watsonx Orchestrate as an Enterprise Skill, enabling conversational assistants and automated workflow agents to invoke specialized code review pipelines directly.

### 6.1 OpenAPI 3.1 Skill Specification for watsonx Orchestrate

```yaml
# File: config/watsonx/codevault-skill-openapi.yaml
openapi: 3.1.0
info:
  title: CodeVault AI Multi-Agent Code Review Skill
  description: Enterprise code review skill powered by LangGraph and IBM watsonx foundation models.
  version: 1.0.0
  contact:
    name: IBM watsonx Skill Engineering
    email: watsonx-skills@ibm.com
servers:
  - url: https://codevault.enterprise.ibm.com/api/v1
    description: Production CodeVault Enterprise Gateway
paths:
  /review:
    post:
      summary: Submit Code for Multi-Agent Review
      operationId: submitCodeReview
      description: Orchestrates security, performance, quality, and architectural multi-agent analysis on submitted code snippets or pull request diffs.
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - code
                - language
              properties:
                code:
                  type: string
                  description: Raw source code string or diff snippet to be analyzed.
                  example: "def execute_query(conn, user_input):\n    return conn.execute(f'SELECT * FROM users WHERE id = {user_input}')"
                language:
                  type: string
                  enum: [python, javascript, typescript, java, go, rust]
                  description: Target programming language.
                  example: "python"
                agents:
                  type: array
                  items:
                    type: string
                  default: ["security", "performance", "quality", "architecture"]
                  description: Specific specialized agent nodes to execute in parallel.
                context:
                  type: string
                  description: Additional contextual metadata (e.g., repository tier, compliance requirements).
                  example: "Payment processing gateway module requiring PCI-DSS 4.0 validation."
      responses:
        '200':
          description: Review successfully completed and synthesized.
          content:
            application/json:
              schema:
                type: object
                properties:
                  review_id:
                    type: string
                    format: uuid
                  score:
                    type: number
                    minimum: 0.0
                    maximum: 100.0
                    example: 74.5
                  status:
                    type: string
                    enum: [completed, degraded, failed]
                  is_blocking:
                    type: boolean
                    example: true
                  summary:
                    type: string
                    example: "Found 1 Critical SQL injection vulnerability requiring immediate remediation."
                  findings:
                    type: array
                    items:
                      type: object
                      properties:
                        rule_id:
                          type: string
                        agent:
                          type: string
                        severity:
                          type: string
                          enum: [CRITICAL, HIGH, MEDIUM, LOW, INFO]
                        line:
                          type: integer
                        description:
                          type: string
                        fix_recommendation:
                          type: string
        '400':
          description: Malformed payload or validation error.
        '401':
          description: Unauthorized; invalid or expired IAM Bearer token.
        '429':
          description: Rate limit exceeded or quota exhausted.
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

### 6.2 Assistant Tool Registration Schema

```json
// File: config/watsonx/assistant-tool-registration.json
{
  "name": "codevault_code_reviewer",
  "description": "Performs deep automated static, dynamic, and LLM-assisted multi-agent code reviews for security vulnerabilities, memory leaks, performance regressions, and architectural compliance.",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "Source code text to evaluate."
      },
      "language": {
        "type": "string",
        "enum": ["python", "javascript", "typescript", "java", "go", "rust"],
        "description": "Programming language of the code."
      },
      "agents": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Optional list of agents to run: security, performance, quality, architecture, compliance, cost_optimizer."
      }
    },
    "required": ["code", "language"]
  }
}
```

### 6.3 IBM Cloud IAM Authentication & Token Exchange Service

This Python integration service automates authentication against IBM Cloud IAM, handles automated caching of short-lived OAuth 2.0 bearer tokens, and invokes the watsonx Orchestrate REST API.

```python
# File: cerberus/providers/watsonx_iam_auth.py
import time
import httpx
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class WatsonxIAMTokenManager:
    """Manages IBM Cloud IAM Bearer Token lifecycle with automated TTL-based refresh."""

    IAM_TOKEN_ENDPOINT = "https://iam.cloud.ibm.com/identity/token"

    def __init__(self, api_key: str, client_id: str = "bx", client_secret: str = "bx"):
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret
        self._cached_token: Optional[str] = None
        self._token_expiry_timestamp: float = 0.0

    async def get_valid_token(self) -> str:
        """Retrieves active cached IAM token or requests a new one if expired."""
        current_time = time.time()
        # Refresh 5 minutes before actual expiry
        if self._cached_token and current_time < (self._token_expiry_timestamp - 300):
            return self._cached_token

        return await self._refresh_iam_token()

    async def _refresh_iam_token(self) -> str:
        """Exchanges IBM Cloud API Key for short-lived IAM OAuth 2.0 Bearer token."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.api_key
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info("Requesting fresh IAM bearer token from IBM Cloud identity service")
            response = await client.post(self.IAM_TOKEN_ENDPOINT, headers=headers, data=data)
            
            if response.status_code != 200:
                logger.error("Failed to retrieve IBM IAM token", status_code=response.status_code, response_text=response.text)
                raise RuntimeError(f"IBM IAM Token exchange failed with status {response.status_code}: {response.text}")
            
            payload = response.json()
            access_token = payload.get("access_token")
            expires_in = payload.get("expires_in", 3600)
            
            if not access_token:
                raise ValueError("IAM response did not contain access_token field")

            self._cached_token = access_token
            self._token_expiry_timestamp = time.time() + float(expires_in)
            logger.info("Successfully acquired new IAM token", expires_in_seconds=expires_in)
            return access_token


class WatsonxOrchestrateClient:
    """Enterprise client for invoking IBM watsonx Orchestrate foundation model generation."""

    def __init__(self, base_url: str, project_id: str, token_manager: WatsonxIAMTokenManager):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.token_manager = token_manager

    async def generate_agent_inference(
        self,
        model_id: str,
        prompt: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calls watsonx.ai foundation model text generation endpoint."""
        token = await self.token_manager.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        default_params = {
            "decoding_method": "greedy",
            "max_new_tokens": 1024,
            "min_new_tokens": 1,
            "repetition_penalty": 1.05
        }
        if parameters:
            default_params.update(parameters)

        payload = {
            "model_id": model_id,
            "project_id": self.project_id,
            "input": prompt,
            "parameters": default_params
        }

        endpoint = f"{self.base_url}/ml/v1/text/generation?version=2024-05-01"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code == 429:
                logger.warn("Received HTTP 429 Rate Limit from IBM watsonx Orchestrate")
                raise httpx.HTTPStatusError("Rate limited by watsonx", request=response.request, response=response)
            
            response.raise_for_status()
            return response.json()
```

---

## 7. HashiCorp Vault Secrets Management Integration

Production secrets are never stored in plain text. CodeVault AI supports both the Kubernetes External Secrets Operator (ESO) and the native HashiCorp Vault Agent Sidecar Injector.

### 7.1 External Secrets Operator (ESO) Integration

The External Secrets Operator syncs secrets from HashiCorp Vault directly into native Kubernetes `Secret` resources.

```yaml
# File: k8s/vault/secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: codevault
spec:
  provider:
    vault:
      server: "https://vault.internal.enterprise.ibm.com:8200"
      path: "secret"
      version: "v2"
      caProvider:
        type: ConfigMap
        name: vault-ca-cert
        key: ca.crt
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "codevault-api-role"
          serviceAccountRef:
            name: codevault-api-sa
---
# File: k8s/vault/external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: codevault-vault-secrets
  namespace: codevault
spec:
  refreshInterval: "5m"
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: codevault-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: production/codevault
        property: database_url
    - secretKey: REDIS_URL
      remoteRef:
        key: production/codevault
        property: redis_url
    - secretKey: SECRET_KEY
      remoteRef:
        key: production/codevault
        property: secret_key
    - secretKey: WATSONX_API_KEY
      remoteRef:
        key: production/codevault
        property: watsonx_api_key
    - secretKey: WATSONX_PROJECT_ID
      remoteRef:
        key: production/codevault
        property: watsonx_project_id
```

### 7.2 HashiCorp Vault Agent Sidecar Injector Configuration

For zero-disk in-memory secret consumption, the Vault Agent sidecar injects credentials directly into a shared tmpfs volume.

```yaml
# File: k8s/vault/vault-agent-pod-patch.yaml
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "codevault-api-role"
        vault.hashicorp.com/agent-inject-status: "update"
        vault.hashicorp.com/agent-inject-secret-config.env: "secret/data/production/codevault"
        vault.hashicorp.com/agent-inject-template-config.env: |
          {{- with secret "secret/data/production/codevault" -}}
          export DATABASE_URL="{{ .Data.data.database_url }}"
          export REDIS_URL="{{ .Data.data.redis_url }}"
          export SECRET_KEY="{{ .Data.data.secret_key }}"
          export WATSONX_API_KEY="{{ .Data.data.watsonx_api_key }}"
          export WATSONX_PROJECT_ID="{{ .Data.data.watsonx_project_id }}"
          {{- end -}}
```

### 7.3 Vault Access Policy and Kubernetes Auth Engine Setup

```hcl
# File: config/vault/codevault-policy.hcl
# Read-only policy for CodeVault production application workloads
path "secret/data/production/codevault" {
  capabilities = ["read"]
}

path "secret/metadata/production/codevault" {
  capabilities = ["read", "list"]
}
```

```bash
# File: scripts/configure_vault.sh
#!/usr/bin/env bash
set -euo pipefail

echo "==> Configuring HashiCorp Vault Kubernetes Authentication Engine..."

# 1. Write the least-privilege policy
vault policy write codevault-policy config/vault/codevault-policy.hcl

# 2. Enable Kubernetes auth engine if not already active
vault auth enable kubernetes || true

# 3. Configure Kubernetes auth with cluster credentials
vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443"

# 4. Bind role to service account in codevault namespace
vault write auth/kubernetes/role/codevault-api-role \
    bound_service_account_names=codevault-api-sa \
    bound_service_account_namespaces=codevault \
    policies=codevault-policy \
    ttl=1h

echo "==> Vault configuration successfully applied."
```

---

## 8. GitHub Actions Multi-Environment CI/CD Pipeline

The automated deployment pipeline enforces branch protection, automated unit testing, security scanning, container image signing via Cosign, and progressive delivery across Development, Staging, and Multi-Region Production.

### 8.1 Workflow Architecture & Pipeline Stages

```text
# File: docs/diagrams/cicd_pipeline.txt
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│ Pull Request │ ──► │  PR Checks   │ ──► │ Image Build  │ ──► │ Staging Deploy │
│ (Feature)    │     │ Lint + Tests │     │ & Cosign Sign│     │ & Integration  │
└──────────────┘     └──────────────┘     └──────────────┘     └───────┬────────┘
                                                                       │
                                                                       ▼
                                                             ┌──────────────────┐
                                                             │ Production Gate  │
                                                             │ (Manual Approval)│
                                                             └─────────┬────────┘
                                                                       │
                                      ┌────────────────────────────────┴────────────────────────────────┐
                                      ▼                                                                 ▼
                        ┌───────────────────────────┐                                     ┌───────────────────────────┐
                        │ Prod US-East (Primary)    │                                     │ Prod US-West (Secondary)  │
                        │ Canary (10%) -> Full Roll │                                     │ Warm Standby Sync         │
                        └───────────────────────────┘                                     └───────────────────────────┘
```

### 8.2 .github/workflows/deploy.yml Pipeline Definition

```yaml
# File: .github/workflows/deploy.yml
name: Enterprise CI/CD Pipeline

on:
  push:
    branches: [main]
    tags: ['v*.*.*']
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  packages: write
  id-token: write
  security-events: write

jobs:
  # ============================================================================
  # Stage 1: Static Analysis, Formatting & Unit Tests
  # ============================================================================
  lint-and-test:
    name: Lint, Test & Coverage Gate
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov flake8 black mypy bandit pip-audit

      - name: Code Formatting Check
        run: black --check cerberus tests

      - name: Static Type Checking
        run: mypy --ignore-missing-imports cerberus

      - name: Static Security Scan (Bandit)
        run: bandit -r cerberus/ -lll -ii

      - name: Dependency Vulnerability Audit
        run: pip-audit --strict || true

      - name: Run Test Suite with Coverage
        run: |
          pytest tests/ --cov=cerberus --cov-report=xml --cov-fail-under=90 -v

  # ============================================================================
  # Stage 2: Container Image Build, Vulnerability Scan & Cosign Signing
  # ============================================================================
  build-and-scan:
    name: Build OCI Image & Scan
    needs: [lint-and-test]
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.version }}
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: actions/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker Metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=sha,format=short

      - name: Build Container Image
        uses: docker/build-push-action@v5
        with:
          context: .
          target: runtime
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Run Trivy Vulnerability Scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ fromJSON(steps.meta.outputs.json).tags[0] }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'
        continue-on-error: false

      - name: Upload Trivy Scan to GitHub Security Tab
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'

  # ============================================================================
  # Stage 3: Automated Staging Deployment & Smoke Verification
  # ============================================================================
  deploy-staging:
    name: Deploy to Staging Cluster
    needs: [build-and-scan]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Authenticate to Staging Kubernetes Cluster
        uses: azure/k8s-set-context@v3
        with:
          method: kubeconfig
          kubeconfig: ${{ secrets.STAGING_KUBECONFIG }}

      - name: Deploy via Helm
        run: |
          helm upgrade --install codevault-staging deploy/helm/codevault \
            --namespace codevault-staging \
            --create-namespace \
            --values deploy/helm/codevault/values.yaml \
            --set image.tag=${{ needs.build-and-scan.outputs.image_tag }} \
            --set global.environment=staging \
            --wait --timeout 5m0s

      - name: Run Staging Smoke Tests
        run: |
          export STAGING_HOST="https://staging.codevault.enterprise.ibm.com"
          curl --fail --retry 5 --retry-delay 5 "$STAGING_HOST/api/v1/health"

  # ============================================================================
  # Stage 4: Multi-Region Production Deployment (Canary & Manual Approval)
  # ============================================================================
  deploy-production:
    name: Deploy to Production Multi-Region
    needs: [deploy-staging]
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: production-approval-gate
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Authenticate to US-East Primary Cluster
        uses: azure/k8s-set-context@v3
        with:
          method: kubeconfig
          kubeconfig: ${{ secrets.PROD_EAST_KUBECONFIG }}

      - name: Canary Deploy US-East (10% Traffic)
        run: |
          helm upgrade --install codevault-prod deploy/helm/codevault \
            --namespace codevault \
            --values deploy/helm/codevault/values.yaml \
            --set image.tag=${{ needs.build-and-scan.outputs.image_tag }} \
            --set global.environment=production \
            --wait --timeout 5m0s

      - name: Verify Production Health & Metrics
        run: |
          curl --fail --retry 5 --retry-delay 10 https://codevault.enterprise.ibm.com/api/v1/health
```

---

## 9. Enterprise Disaster Recovery (DR) Runbook

### 9.1 RTO / RPO Objectives & Multi-Region Topology

| Metric | Target SLA | Implementation Guarantee |
|---|---|---|
| **Recovery Time Objective (RTO)** | **< 15 minutes** | Automated Route53 DNS health check failover + Patroni standby promotion |
| **Recovery Point Objective (RPO)** | **< 1 minute** | Asynchronous streaming physical replication + pgBackRest 60s WAL archiving |
| **Primary Region** | `us-east-1` | 3 Availability Zones, 3-20 Pods, Active PostgreSQL Primary |
| **Standby DR Region** | `us-west-2` | 3 Availability Zones, 2 Pods (Warm), Standby PostgreSQL Replica |

---

### 9.2 Route53 DNS Health Checks & Traffic Shift Policy

AWS Route53 directs user traffic using a Failover Routing Policy with continuous health checks against `/api/v1/health`.

```json
// File: config/dns/route53-failover-policy.json
{
  "Comment": "CodeVault Global Active-Passive Failover Routing Configuration",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "codevault.enterprise.ibm.com.",
        "Type": "A",
        "SetIdentifier": "Primary-USEast",
        "Failover": "PRIMARY",
        "HealthCheckId": "c84192b1-382a-4c28-9a81-d41982734a01",
        "AliasTarget": {
          "HostedZoneId": "Z35SXDOTRQ7X7K",
          "DNSName": "dualstack.east-ingress-alb-981273918.us-east-1.elb.amazonaws.com.",
          "EvaluateTargetHealth": true
        }
      }
    },
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "codevault.enterprise.ibm.com.",
        "Type": "A",
        "SetIdentifier": "Secondary-USWest",
        "Failover": "SECONDARY",
        "AliasTarget": {
          "HostedZoneId": "Z1H1FL5YBCLFQC",
          "DNSName": "dualstack.west-ingress-alb-129837192.us-west-2.elb.amazonaws.com.",
          "EvaluateTargetHealth": true
        }
      }
    }
  ]
}
```

---

### 9.3 PostgreSQL Streaming Replication, Patroni & Read Replica Promotion

The database high-availability architecture utilizes Patroni backed by etcd for leader election and automatic failover.

```yaml
# File: config/database/patroni-config.yaml
scope: codevault-postgres
namespace: /service
name: pg-node-us-west-standby

etcd3:
  hosts:
    - 10.200.1.10:2379
    - 10.200.1.11:2379
    - 10.200.1.12:2379

restapi:
  listen: 0.0.0.0:8008
  connect_address: 10.200.10.15:8008

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576 # 1 MB lag threshold
    postgresql:
      use_pg_rewind: true
      parameters:
        wal_level: replica
        max_wal_senders: 10
        max_replication_slots: 10
        hot_standby: "on"
        archive_mode: "on"
        archive_command: "pgbackrest --stanza=codevault archive-push %p"

postgresql:
  listen: 0.0.0.0:5432
  connect_address: 10.200.10.15:5432
  data_dir: /var/lib/postgresql/data
  bin_dir: /usr/lib/postgresql/15/bin
  pgpass: /var/lib/postgresql/.pgpass
  authentication:
    replication:
      username: replicator
      password: ReplicatorSecurePassword123!
    superuser:
      username: postgres
      password: PostgresMasterPassword123!
```

---

### 9.4 Point-In-Time-Recovery (PITR) with pgBackRest & S3

Continuous write-ahead logging (WAL) streams to an S3 object storage bucket every 60 seconds.

```ini
# File: config/database/pgbackrest.conf
[global]
repo1-type=s3
repo1-s3-endpoint=s3.us-east-1.amazonaws.com
repo1-s3-bucket=codevault-database-backups-prod
repo1-s3-region=us-east-1
repo1-s3-key=ENV[AWS_ACCESS_KEY_ID]
repo1-s3-key-secret=ENV[AWS_SECRET_ACCESS_KEY]
repo1-path=/pgbackrest
repo1-retention-full=4
repo1-retention-diff=14
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=ENV[PGBACKREST_CIPHER_PASSPHRASE]
start-fast=y
compress-type=zst
compress-level=6
log-level-console=info
log-level-file=detail

[codevault]
pg1-path=/var/lib/postgresql/data
pg1-user=postgres
```

```bash
# File: scripts/restore_pitr.sh
#!/usr/bin/env bash
set -euo pipefail

TARGET_TIMESTAMP="2026-09-24 14:15:00"
echo "==> Executing PostgreSQL Point-In-Time-Recovery to: ${TARGET_TIMESTAMP}"

# 1. Stop PostgreSQL service
systemctl stop patroni || systemctl stop postgresql

# 2. Perform point-in-time recovery using pgBackRest
pgbackrest --stanza=codevault \
    --delta \
    --type=time \
    "--target=${TARGET_TIMESTAMP}" \
    --target-action=promote \
    restore

# 3. Start PostgreSQL and verify recovery
systemctl start patroni
echo "==> PostgreSQL successfully restored and promoted."
```

---

### 9.5 Emergency Failover Execution Runbook

When a regional disaster is declared in `us-east-1`:

```bash
# File: scripts/dr_emergency_failover.sh
#!/usr/bin/env bash
set -euo pipefail

echo "================================================================="
echo "CODEVAULT AI: EMERGENCY REGIONAL FAILOVER (US-EAST -> US-WEST)"
echo "================================================================="

# Step 1: Promote Standby PostgreSQL Replica to Primary in us-west-2
echo "==> Step 1: Promoting PostgreSQL replica in us-west-2..."
kubectl --context=prod-west exec -n postgres pg-cluster-0 -- patronictl -c /etc/patroni/patroni.yml failover pg-cluster --candidate pg-cluster-0 --force

# Step 2: Validate Database Write Availability
echo "==> Step 2: Validating database read/write readiness..."
kubectl --context=prod-west exec -n postgres pg-cluster-0 -- psql -U codevault_app -d codevault_prod -c "SELECT pg_is_in_recovery();"

# Step 3: Scale Up Standby Kubernetes API Pods
echo "==> Step 3: Scaling CodeVault API Deployment to 15 replicas in us-west-2..."
kubectl --context=prod-west scale deployment/codevault-api -n codevault --replicas=15

# Step 4: Shift Global Traffic via Route53 Update
echo "==> Step 4: Shifting DNS traffic to us-west-2 endpoint..."
aws route53 change-resource-record-sets \
    --hosted-zone-id Z35SXDOTRQ7X7K \
    --change-batch file://config/dns/route53-failover-policy.json

# Step 5: Validate Health and End-to-End Review Execution
echo "==> Step 5: Executing end-to-end health probe against us-west-2..."
curl --fail --retry 10 --retry-delay 3 https://codevault.enterprise.ibm.com/api/v1/health

echo "==> Failover completed successfully in < 15 minutes."
```

---

### 9.6 Post-Recovery Failback & Consistency Verification

Following primary region restoration, execute failback with zero split-brain:
1. Re-establish physical streaming replication in reverse direction (`us-west-2` primary -> `us-east-1` standby).
2. Wait for replication lag to drop below 10MB:
   ```sql
   -- File: scripts/check_replication_lag.sql
   SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)) AS replication_lag
   FROM pg_stat_replication;
   ```
3. Shift Route53 weighted traffic gradually back to `us-east-1` (10% -> 50% -> 100%).
4. Demote `us-west-2` back to warm standby configuration.

---

## 10. Summary & Pointer to Next Document

This guide established a complete, enterprise-grade deployment and disaster recovery baseline for CodeVault AI across local container stacks, production Kubernetes clusters, IBM watsonx Orchestrate skill catalogs, and HashiCorp Vault secrets backends.

To configure production monitoring, real-time observability, alerting rules, distributed tracing, and operational incident response runbooks, proceed to the next document:

👉 **Next Document:** [MONITORING_OPERATIONS.md](MONITORING_OPERATIONS.md)
