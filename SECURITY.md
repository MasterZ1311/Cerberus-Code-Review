# Security Policy & Enterprise Threat Model

The **Cerberus** team takes the security of our multi-agent code intelligence platform and its users seriously. This document details our security architecture, multi-tenant boundaries, streaming security, data retention lifecycle, threat model, and vulnerability reporting procedures.

---

## 🛡️ Supported Versions

We actively maintain and provide security patches for the following versions:

| Version | Supported | Security Notes |
|:-------:|:---------:|:---------------|
| `0.1.x` | :white_check_mark: | Current active release branch with multi-tenant isolation & hardened ASGI streaming |
| `< 0.1.0` | :x: | Development prototypes (unsupported) |

---

## 🔐 Multi-Tenant Authorization & Identity Model

Cerberus implements a strict **defense-in-depth multi-tenant security architecture**:

1. **Explicit Tenant Attribution**:
   - Every API key is explicitly bound to a `tenant_id` at creation time.
   - Key generation, listing, rotation, and revocation are tenant-scoped by default. A tenant administrator can only manage keys belonging to their own tenant.
   - A dedicated `platform:admin` scope exists for cross-tenant operations and system operators.
   - Key rotation preserves tenant identity, ensuring rotated credentials cannot accidentally escalate or switch tenants.

2. **Tenant-Scoped Review Operations**:
   - Every review record created via REST, multipart ZIP, base64 ZIP, or webhook is stored with an explicit `owner_id` (the submitting `tenant_id`).
   - Every review endpoint (`GET /{review_id}`, `GET /{review_id}/results`, `GET /{review_id}/sarif`, `GET /{review_id}/gitlab`, `GET /{review_id}/sonarqube`, `POST /{review_id}/approve`, `POST /{review_id}/feedback`, `GET /zip/{zip_id}/report`, SSE streams, and WebSockets) strictly verifies tenant ownership.
   - If a caller attempts to access a review owned by a different tenant, Cerberus returns **HTTP 404 Not Found** (preventing enumeration attacks).

3. **Legacy Backfill and Fail-Closed Policy**:
   - Database migrations automatically backfill unowned pre-existing records to an explicit `'legacy_unassigned'` tenant identity.
   - In production mode (`ENVIRONMENT=production`), unowned API keys or missing tenant identities immediately fail closed with **HTTP 401 Unauthorized**.

---

## ⚡ Streaming Security & Horizontal Scalability

Cerberus enforces secure, scalable streaming across distributed worker nodes:

1. **Query Parameter Deprecation**:
   - Raw API keys in query parameters (`?token=...` or `?api_key=...`) are strictly forbidden across **all environments**, including development mode.
   - Any connection attempt providing raw keys in query parameters is immediately terminated with **HTTP 400 Bad Request** (SSE) or **WebSocket Policy Violation 1008**.

2. **Scoped Stream Tokens**:
   - Clients obtain a short-lived (default 60s), single-use stream token via `POST /api/v1/review/{review_id}/stream-token` using standard `Authorization: Bearer <API_KEY>`.
   - The stream token stores both the `review_id` and `tenant_id`.

3. **Atomic Single-Use Consumption**:
   - Token consumption executes atomically in Redis using native `GETDEL` (Redis 6.2+) with an automated fallback to atomic Lua script evaluation (`LUA_ATOMIC_GETDEL`).
   - In-memory single-worker deployments protect token consumption using an `asyncio.Lock`.
   - A stream token **can never be consumed twice**, even under high concurrent race conditions.

4. **Multi-Worker Event Broadcasting**:
   - Real-time review events (agent status transitions, score computations, completion events) are published to a distributed Redis pub/sub channel (`cvai:review:events:{review_id}`).
   - SSE and WebSocket handlers on any application worker subscribe to the Redis pub/sub channel, ensuring consistent real-time delivery regardless of which worker processes the review or holds the client socket.

---

## 🧱 ASGI Receive-Layer Request Size Protection

To prevent memory exhaustion and denial-of-service (DoS) attacks from unbounded request streams:

1. **ASGI Metering Middleware**:
   - Cerberus employs `ASGIRequestSizeLimitMiddleware`, which intercepts incoming requests at the pure ASGI receive layer before framework parsing.
   - The middleware inspects `Content-Length` headers early and streams and meters chunked/streaming requests chunk-by-chunk.
   - If an incoming payload exceeds configured boundaries, the middleware immediately closes the stream with **HTTP 413 Payload Too Large**, preventing buffering of oversized payloads in memory.

2. **Configured Payload Limits**:
   - JSON Code Review Submissions: **5 MB**
   - Base64 ZIP Payloads: **25 MB**
   - Multipart ZIP Uploads: **25 MB**
   - Webhook Ingestion Payloads: **10 MB**
   - General API Payloads: **2 MB**

3. **Archive Security Defense-in-Depth**:
   - Zip Slip / Directory Traversal protection: paths with `../`, absolute root components, or drive letters are rejected during extraction.
   - Decompression ratio / Zip Bomb protection: maximum extracted size (100 MB default) and max file entry counts (1,000 files default) are strictly enforced.
   - Symlink rejection: symbolic links inside archives are logged and ignored to prevent arbitrary file reading.

---

## 🔒 Privacy & Data Retention Lifecycle

Cerberus provides strict data minimization and regulatory compliance (GDPR, HIPAA, SOC 2):

1. **Recursive Source Code Redaction (`RETAIN_SOURCE_CODE=false`)**:
   - When source code retention is disabled, Cerberus guarantees that raw code snippets, unified diffs, patches, and code contexts are absent from:
     - Relational database columns (`code_snippet` in `code_reviews` and `review_findings`).
     - JSON results stored in database records (`results_json`).
     - L1 in-memory cache and L2 Redis cache payloads.
     - OpenTelemetry trace spans and telemetry attributes.
     - Application logs and error messages.
   - Redaction is performed recursively across all arbitrary nested dictionaries and lists via `redact_source_code_recursively()`.

2. **Automated Data Retention Purge**:
   - Records older than `DATA_RETENTION_DAYS` (default 30 days) are purged via cascading deletes across feedback, findings, and reviews.
   - The retention purge is coordinated across workers via a distributed Redis lock (`cvai:retention:lock`, 300s TTL) with an in-memory fallback lock.
   - Prometheus metrics record retention operations: `cerberus_retention_runs_total{status="success|failure"}`, `cerberus_retention_purged_records_total{record_type="review|finding|feedback"}`, and `cerberus_retention_last_run_timestamp_seconds`.
   - The purge can be executed as a background scheduler or via an external Kubernetes CronJob (`cerberus retention purge`).

3. **Encryption at Rest & Responsibility Boundary**:
   - Cerberus enforces encryption in transit via TLS 1.3 across all HTTP, SSE, WebSocket, and Redis connections.
   - Encryption at rest is the operational responsibility of the underlying storage infrastructure (PostgreSQL AWS RDS / Azure Database storage encryption with KMS/Vault, Redis encrypted EBS/persistent disks, Kubernetes encrypted Secrets).

---

## 🎯 Threat Model & Attack Surface Analysis (STRIDE)

| Threat Category | Potential Attack Vector | Cerberus Defense Mechanism |
|:---|:---|:---|
| **Spoofing** | Forged API key or stolen stream token | SHA-256 hashed keys in DB; timing-safe comparisons; atomic single-use stream tokens; tenant binding. |
| **Tampering** | Forged GitHub webhook event | HMAC SHA-256 signature verification via `X-Hub-Signature-256` using constant-time `hmac.compare_digest`. |
| **Repudiation** | Unverified review approvals | Human-in-the-loop approval records with timestamps, reviewer identity, and justification stored in `CodeReviewRecord`. |
| **Information Disclosure** | Cross-tenant review data leak | Strict tenant ownership validation on all review and export routes; HTTP 404 response to prevent ID enumeration. |
| **Denial of Service** | Unbounded chunked upload or Zip Bomb | Pure ASGI receive-layer byte metering; zip extraction ratio limits (max 100 MB / 1,000 files); Redis sliding-window rate limiting. |
| **Elevation of Privilege** | Key rotation escalation | Tenant identity is preserved during rotation; only `platform:admin` scope can perform cross-tenant actions. |

---

## 🚨 Reporting a Vulnerability

**Please do not report security vulnerabilities via public GitHub issues, discussions, or pull requests.**

If you discover a potential security vulnerability in Cerberus:

1. **Email the Maintainers**: Send a detailed advisory to `thenappanmasterz1311@gmail.com` with the subject tag `[SECURITY] Cerberus Vulnerability Report`.
2. **GitHub Private Security Advisory**: Navigate to the **Security** tab of this repository and click **"Report a vulnerability"** to open a private advisory.

### What to include in your report:
- Descriptive summary and affected component (API Gateway, Multi-Tenant Engine, WebSocket Stream, Zip Processor).
- Step-by-step reproduction instructions or a minimal proof-of-concept (PoC) script.
- Potential impact and severity assessment (CVSS estimate).
- Any proposed mitigations or workarounds.

---

## ⏱️ Response Timelines & SLA

- **Initial Acknowledgment**: Within 24-48 hours.
- **Triage & Severity Assessment**: Within 5 business days.
- **Patch Development & Release**: Critical security vulnerabilities will be prioritized for expedited release.
- **Public Disclosure**: Coordinated after a fix has been verified and deployed to users.

---

## 🔒 Safe Harbor

We will not pursue legal action against individuals who conduct security research in good faith, provided that:
- You make every effort to avoid privacy violations, data destruction, and service interruption.
- You give us reasonable time to remedy the issue before making any details public.
- You do not exploit the vulnerability beyond what is strictly necessary to demonstrate proof-of-concept.
