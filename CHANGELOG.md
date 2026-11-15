# Changelog
All notable changes to the **Cerberus** project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-11-15 - Master 10/10 Hardening Release

### 🛡️ Security & Authentication
- **Fixed RBAC Scope Dependency Injection:** Corrected `require_scopes` in `cerberus/api/dependencies.py` by using `Depends(verify_api_key)` instead of default parameter assignment, ensuring FastAPI dependency injection executes authentication and scope resolution before endpoint evaluation.
- **Enforced Admin RBAC on Sensitive Endpoints:** Secured `POST /api/v1/config/runtime` and all API key management endpoints with `require_scopes("admin")`.
- **Enforced Human Approval Authorization:** Secured `POST /api/v1/review/{review_id}/approve` with `require_scopes("review:write")`.
- **RESTful API Key Management Router:** Created `cerberus/api/v1/keys.py` exposing `POST /api/v1/keys` (creation with expiration and custom scopes), `GET /api/v1/keys` (listing without raw token leakage), `DELETE /api/v1/keys/{key_id}` (revocation), and `POST /api/v1/keys/{key_id}/rotate` (atomic rotation).
- **GitHub Webhook Replay Protection:** Implemented an LRU-bounded delivery cache `_webhook_deliveries` with 10-minute TTL tracking `X-GitHub-Delivery` headers, ignoring replayed delivery payloads.
- **Strict Production Webhook Secrets:** Webhook handler rejects missing, weak, or default secrets (`changeme`, `secret`, `admin`, `password`) with HTTP 500 when `ENVIRONMENT=production`.
- **Webhook Request Size Cap:** Enforced `MAX_WEBHOOK_PAYLOAD_BYTES = 10MB`, rejecting oversized requests with HTTP 413.
- **Safe Markdown PR Code Parsing:** Replaced naive string concatenation with regex extraction targeting fenced markdown code blocks.
- **Chunked Streaming Zip Decompression:** Refactored `cerberus/core/zip_processor.py` to stream decompression in 64KB increments with live per-file (10MB) and cumulative (50MB) caps, defeating deceptive-header zip bombs without memory buffering.
- **Symlink & Path Traversal Rejection in Archives:** Added `is_symlink_entry()` to reject Unix symbolic links (`S_IFLNK`), enforced a maximum nesting depth of 15, and canonicalized extracted file paths.
- **Duplicate Archive Entry Detection:** Added `seen_entries` tracking to prevent shadow file replacement attacks.

### 🧠 Multi-Agent Intelligence & Consensus
- **Expanded Polyglot Heuristic Security Rules:** Added static detection rules in `cerberus/providers/heuristic_engine.py` for:
  - Python SSRF (CWE-918) and Path Traversal (CWE-22).
  - JavaScript / TypeScript DOM XSS (CWE-79), Node.js Command Injection (CWE-78), and Prototype Pollution (CWE-1321).
  - Go SQL Injection via `fmt.Sprintf` (CWE-89) and unhandled error swallowing via `_ = err` (CWE-703).
  - Rust undocumented `unsafe` blocks without `// SAFETY:` rationale (CWE-242).
- **Consensus Agent Safety Invariant Guard:** In `cerberus/agents/consensus_agent.py`, enforced an invariant preventing LLM outputs from downgrading `BLOCKED_ON_ISSUES` to `MERGE_READY` when active `CRITICAL` findings exist.
- **Finding Deduplication:** In `cerberus/agents/orchestrator.py`, added cross-agent deduplication filtering redundant reports by line number, category, CWE ID, and title.

### ⚡ Architecture, Caching & Reliability
- **Multi-Parameter Cache Fingerprint:** Upgraded `CacheManager.compute_cache_key` in `cerberus/core/cache.py` to canonicalize and hash `filename`, `context`, `config`, and `ruleset_version` alongside code and language.
- **Cache Invalidation:** Added synchronous `invalidate(key)` and asynchronous `invalidate_async(key)` methods.
- **Live Health & Database Ping:** Upgraded `GET /api/v1/health` to execute live `SELECT 1` database pings and Redis probes, reporting `degraded` if any dependency is unreachable.
- **Genuine Repository Analytics:** Upgraded `GET /api/v1/analytics/repositories/{owner}/{repo}` and `GET /api/v1/analytics/trends` to compute genuine aggregated counts, scores, and severity distributions from database records.
- **5-Stage In-Memory Patch Verification Pipeline:** Created `cerberus/core/patch_verifier.py` with stages `GENERATED`, `SYNTAX_VALID`, `APPLIED_CLEANLY`, `STATIC_ANALYSIS_PASSED`, and `REGRESSION_FREE`, validating repairs without executing untrusted code.

### 🧪 Quality Assurance & DevOps
- **Master Hardening Test Suite:** Added `tests/test_master_hardening_suite.py` with 7 dedicated verification tests. Total test suite expanded to **495 automated tests passing with 0 failures**.
- **Hardened CI/CD Matrix:** Updated `.github/workflows/ci.yml` with Ruff linter checks, Bandit AST security analysis, Python 3.11/3.12/3.13 matrix, and Docker build validation.
- **Standardized Container Config:** Updated `Dockerfile` and `docker-compose.yml` with health-gated dependencies, dedicated `cerberus` non-root user (UID 1000), and unified database naming.
- **Comprehensive Master Documentation:** Delivered 6 exhaustive engineering reports in `reports/`:
  - `reports/MASTER_ENGINEERING_AUDIT.md`
  - `reports/SECURITY_AUDIT.md`
  - `reports/TEST_RESULTS.md`
  - `reports/AI_EVALUATION.md`
  - `reports/PERFORMANCE_BENCHMARKS.md`
  - `reports/PRODUCTION_READINESS.md`
