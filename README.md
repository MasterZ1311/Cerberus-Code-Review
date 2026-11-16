<p align="center">
  <img src="assets/cerberus_logo.png" alt="cerberus</> Official Logo" width="180">
</p>

<h1 align="center">cerberus&lt;/&gt;</h1>

<p align="center">
  <strong>Autonomous Multi-Agent Code Review &amp; Static Security Analysis Platform</strong><br>
  <em>Enterprise Automated Code Inspection, AST-Verified Remediation &amp; Compliance Gating — v1.4.0</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg" alt="Python: 3.11+"></a>
  <a href="https://github.com/MasterZ1311/Cerberus-Code-Review/actions/workflows/ci.yml"><img src="https://github.com/MasterZ1311/Cerberus-Code-Review/actions/workflows/ci.yml/badge.svg" alt="CI Status"></a>
  <a href="reports/TEST_RESULTS.md"><img src="https://img.shields.io/badge/tests-685%20passing-brightgreen.svg" alt="Tests Passing"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/coverage-%E2%89%A585%25%20branch-brightgreen.svg" alt="Coverage: >=85% Branch Enforced"></a>
  <a href="SECURITY.md"><img src="https://img.shields.io/badge/security-hardened-success.svg" alt="Security Hardened"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

---

## Overview

**Cerberus** is an automated multi-agent code inspection and static analysis platform engineered for enterprise engineering teams and CI/CD pipelines. It dispatches specialized analysis agents across security, algorithmic performance, code quality, software architecture, and regulatory compliance, synthesizing verified findings and generating deterministic, AST-validated unified git diff patches.

- **High-Throughput Evaluation:** Sub-millisecond cached analysis (<0.3 ms) and ~17.5 ms cold heuristic AST inspection.
- **Polyglot Coverage:** Native AST and heuristic analysis for 11 programming languages: **Python, JavaScript, TypeScript, Go, Rust, Java, C#, Ruby, PHP, Kotlin, and Swift** across 130+ static rules.
- **AST-Verified Remediation:** Synthesizes verified unified git diff patches validated against language parsers before recommendation (`Cmd/Ctrl+H` or CLI `apply-fix`).
- **Model-Agnostic Inference:** Operates 100% offline via native AST heuristics with zero external network access, or connects to external LLM providers (Groq, Anthropic, Gemini, OpenAI, DeepSeek, Ollama).
- **Enterprise Gating:** Enforces fail-closed database consistency, SingleFlight thundering-herd cache coalescing, timing-safe API key validation, and granular JWT RBAC scopes.
- **Standardized CI/CD Artifacts:** Native export to OASIS SARIF v2.1.0, GitLab Code Quality JSON, and SonarQube Generic Issue Import.

---

## Specialized Inspection Agents

Rather than relying on generic, non-deterministic prompt evaluations, Cerberus partitions code review across 7 isolated agents with distinct evaluation domains:

| Agent | Core Discipline | Coverage & Target Invariants | Output / Artifact |
| :--- | :--- | :--- | :--- |
| **Security Agent** | Static Application Security Testing (SAST) | SQL Injection (CWE-89), XSS (CWE-79), Command Injection (CWE-78), Hardcoded Credentials (CWE-798), Insecure Cryptography (CWE-327), SSRF (CWE-918), Path Traversal (CWE-22). | Severity-ranked CVE/CWE findings with line and column precision. |
| **Performance Agent** | Algorithmic Complexity & Systems Efficiency | $O(N^2)$ algorithmic loops, blocking I/O in async routines, memory allocation leaks, unindexed database queries, redundant deserialization. | Latency impact estimates and algorithmic complexity metrics. |
| **Quality Agent** | Maintainability & Static Code Analysis | Cyclomatic complexity bounds, exception-handling anti-patterns, maintainability index, dead code detection, type annotation soundness. | Code smell diagnostics and readability score deductions. |
| **Architecture Agent** | Structural Design & Modularity | SOLID principle violations, circular package dependencies, component coupling metrics, architectural boundary violations. | Structural coupling analysis and refactoring recommendations. |
| **Compliance Agent** | Regulatory Policy Auditing | Automated mapping across **HIPAA** (PHI cleartext), **GDPR** (data minimization, raw IP retention), **PCI-DSS** (unmasked PAN, CVV storage), and **SOC 2**. | Regulatory compliance pass/fail scorecard and policy citation. |
| **Consensus Arbiter** | Multi-Agent Dispute Resolution | Risk-weighted severity aggregation, balancing performance versus security trade-offs to compute final gating decisions. | Unified verdict: `Ready to Merge`, `Needs Revision`, or `Blocked`. |
| **Remediation Agent** | Automated Patch Synthesis | Generates minimal unified git diff patches verified against language syntax parsers before proposal. | Ready-to-merge unified git diff patch with rollback safeguards (`.bak`). |

---

## Review Pipeline

```
  Source / Archive        Ingress & Parse              Concurrent Inspection            Consensus & Remediation
 ─────────────────      ───────────────────          ─────────────────────────        ───────────────────────────
 [ Source Snippet ] ──► [ Language Detection ] ──┬──► [ Security Agent        ] ──┬──► [ Consensus Arbiter      ]
 [ Git Webhook    ]     [ Tree-sitter AST    ]   ├──► [ Performance Agent     ]   │    (Risk Scoring & Gating)
 [ .ZIP Archive   ]     [ SingleFlight Cache ]   ├──► [ Quality Agent         ]   │                 │
                                                 ├──► [ Architecture Agent    ]   │                 ▼
                                                 ├──► [ Compliance Agent      ]   │    [ Remediation Agent      ]
                                                 └──► [ Plugin Lifecycle Bus  ] ──┘    (AST-Verified Git Patch)
```

1. **Ingress & Invariant Verification:** Source snippets or `.zip` archives are ingested via API, CLI, or GitHub webhook, validated against size boundaries (bounded streaming, Zip-Slip path sanitization), and parsed into AST representations.
2. **Concurrent Inspection:** Specialized agents analyze code concurrently in isolated worker threads with strict per-line execution bounds to prevent ReDoS.
3. **Consensus Arbitration & Patch Generation:** The Consensus Arbiter computes composite scores, resolves conflicting requirements, and dispatches the Remediation Agent to synthesize an AST-validated Git patch.

---

## Web Dashboard

The built-in web console runs locally at `http://localhost:8000`:

- **Component Activity Rings:** Visual breakdown across Security, Performance, Quality, and Compliance dimensions.
- **Unified Diff Viewer:** Side-by-side Git diff frame highlighting exact replacements with syntax coloring.
- **Finding Filters & Search:** Filtering by severity (`All`, `Critical`, `High`, `Medium`, `Low`) and rule ID.
- **Human-in-the-Loop PR Approval Gate:** Authorized leads record sign-off justification with immutable audit records.
- **Telemetry & Health Indicators:** Real-time latency tracking, cache hit rates, throughput metrics, and database status.

---

## Supported Inference Providers

Cerberus is model-agnostic and functions out-of-the-box offline without external API keys:

| Provider | Mode | Typical Latency | Operational Profile |
| :--- | :--- | :--- | :--- |
| **Heuristic Engine** | Local / Offline | **~17.5 ms** (cold) / **<0.3 ms** (cached) | Zero cloud dependency, 100% offline privacy, zero cost. |
| **Groq** | Cloud API | **<500 ms** | Ultra-low latency cloud inference using Llama 3 models. |
| **Google Gemini** | Cloud API | **~1.2 s** | High-context architectural reasoning via Gemini 1.5/2.0. |
| **Ollama** | Local / Offline | Hardware-dependent | Private on-premise execution using local open-weight models. |
| **Anthropic Claude** | Cloud API | **~1.5 s** | Nuanced security analysis and regulatory auditing via Claude 3.5. |
| **OpenAI** | Cloud API | **~1.1 s** | Standardized code review workflows via GPT-4o. |
| **DeepSeek** | Cloud API | **~800 ms** | Cost-effective, high-reasoning coding benchmarks. |

> Set `LLM_PROVIDER=auto` in `.env`. Cerberus detects configured API keys and selects the optimal provider automatically.

---

## Quick Start

### 1. Installation

```bash
git clone https://github.com/MasterZ1311/Cerberus-Code-Review.git
cd Cerberus-Code-Review

# Create and activate virtual environment (optional but recommended)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies (Python 3.11+)
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)

```bash
cp .env.example .env
```
*(Leave `.env` as-is to use the offline Heuristic Engine, or insert any AI API key you wish).*

### 3. Launch Dashboard & Review

```bash
# Start local API server & Web Dashboard (http://localhost:8000)
python -m cerberus.cli serve

# Check system health & active agent status
python -m cerberus.cli health

# Run a review directly in your terminal
python -m cerberus.cli review --snippet "import os; os.system('rm -rf /')"

# Review an entire project ZIP archive
python -m cerberus.cli review --zip my_project.zip
```

---

## Command-Line Interface (CLI)

The Cerberus CLI provides terminal commands for CI/CD pipelines, local development, and operations:

```bash
# Review a local file with CI/CD blocking gate (exits with code 1 on critical flaws)
python -m cerberus.cli review --file path/to/script.py --blocking

# Review an entire project ZIP archive
python -m cerberus.cli review --zip my_project.zip

# Export findings to OASIS SARIF v2.1.0, GitLab Code Quality, or SonarQube
python -m cerberus.cli export-sarif --file app.py --output results.sarif
python -m cerberus.cli export-gitlab --file app.py --output gl-code-quality-report.json
python -m cerberus.cli export-sonarqube --file app.py --output sonar-generic-issues.json

# Apply AST-verified code fixes in-place with automatic .bak backup
python -m cerberus.cli apply-fix --file app.py --backup

# Format review output (text, json, sarif, gitlab, sonarqube, markdown)
python -m cerberus.cli review --file app.py --format markdown --output review.md

# Run only specific agents
python -m cerberus.cli review --file app.py --agents "security,compliance"

# List available specialized AI agents
python -m cerberus.cli list-agents

# List registered extensible plugins and custom rules
python -m cerberus.cli list-plugins

# Inspect multi-tenant quota usage meter and tier allocations
python -m cerberus.cli quotas --tenant-id "default"

# Enforce data retention lifecycle and purge historical reviews
python -m cerberus.cli retention purge --days 30

# Environment Doctor & System Diagnostics
python -m cerberus.cli doctor

# Bootstrap environment, database schema, and git hooks
python -m cerberus.cli init

# Git Hooks (pre-commit & pre-push automatic reviews)
python -m cerberus.cli hooks install
python -m cerberus.cli hooks uninstall

# Generate cryptographically secure API keys for your CI/CD runners
python -m cerberus.cli create-api-key --name "github-actions-ci"

# List all registered API keys
python -m cerberus.cli list-api-keys

# Revoke an API key
python -m cerberus.cli revoke-api-key github-actions-ci
```

---

## RESTful API, Webhooks & WebSocket Reference

Cerberus provides a production-grade FastAPI backend with interactive OpenAPI / Swagger documentation at `http://localhost:8000/docs`:

```bash
# Submit source code for multi-agent review
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def login(user_id):\n    return db.execute(f\"SELECT * FROM users WHERE id = {user_id}\")",
    "language": "python"
  }'

# Review an entire project .ZIP file
curl -X POST http://localhost:8000/api/v1/review/upload-zip \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -F "file=@project.zip"

# Review project from Base64 encoded ZIP payload
curl -X POST http://localhost:8000/api/v1/review/zip-base64 \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{"zip_base64": "<BASE64_PAYLOAD>", "project_name": "my_app"}'

# Export review as OASIS SARIF v2.1.0 (for GitHub Code Scanning & CI/CD)
curl http://localhost:8000/api/v1/review/{review_id}/sarif \
  -H "Authorization: Bearer cvai_dev_key_123"

# Export review as GitLab CI Code Quality Report
curl http://localhost:8000/api/v1/review/{review_id}/gitlab \
  -H "Authorization: Bearer cvai_dev_key_123"

# Export review as SonarQube Generic Issue Import JSON
curl http://localhost:8000/api/v1/review/{review_id}/sonarqube \
  -H "Authorization: Bearer cvai_dev_key_123"

# Submit Human-in-the-Loop review feedback
curl -X POST http://localhost:8000/api/v1/review/{review_id}/feedback \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{"rating": 5, "is_helpful": true, "comments": "Accurate findings and verified patch"}'

# GitHub App Webhook Listener (pull_request.opened review)
curl -X POST http://localhost:8000/api/v1/review/webhooks/github \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=..." \
  -H "Content-Type: application/json" \
  -d '{
    "action": "opened",
    "number": 42,
    "pull_request": {
      "title": "Add Auth Service",
      "body": "def authenticate(token): return token == \"secret\"",
      "head": {"sha": "6dcb09b"},
      "base": {"ref": "main"}
    },
    "repository": {"name": "core", "owner": {"login": "acme"}, "full_name": "acme/core"}
  }'

# Check review status (Lightweight for CI/CD Gates)
curl http://localhost:8000/api/v1/review/{review_id}/status \
  -H "Authorization: Bearer cvai_dev_key_123"

# Human-in-the-Loop PR Approval
curl -X POST http://localhost:8000/api/v1/review/{review_id}/approve \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "Senior Lead", "override_blocking": true}'

# Generate short-lived single-use stream token
curl -X POST http://localhost:8000/api/v1/review/{review_id}/stream-token \
  -H "Authorization: Bearer cvai_dev_key_123"

# Live Server-Sent Events (SSE) Stream
curl -N http://localhost:8000/api/v1/review/{review_id}/stream \
  -H "Authorization: Bearer cvai_dev_key_123"

# Mint cryptographically verified JWT bearer token
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "service-worker", "client_secret": "secret", "scopes": ["reviews:write", "reviews:read"]}'

# Inspect multi-tenant monthly quota consumption
curl http://localhost:8000/api/v1/tenants/quota \
  -H "Authorization: Bearer cvai_dev_key_123"

# Upgrade tenant tier (Admin only)
curl -X POST http://localhost:8000/api/v1/tenants/acme-corp/tier \
  -H "Authorization: Bearer cvai_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"tier": "enterprise"}'

# List registered plugins and custom rule metadata
curl http://localhost:8000/api/v1/plugins \
  -H "Authorization: Bearer cvai_dev_key_123"

# Prometheus Telemetry Metrics
curl http://localhost:8000/metrics
```

---

## Testing, Quality & Verification

Cerberus enforces **685 automated tests across 52 test suites with >=85% branch coverage** running in CI across Python 3.11, 3.12, and 3.13:

```bash
# Run full automated test suite with enforced branch coverage
python -m pytest --cov=cerberus --cov-branch --cov-report=term-missing --cov-fail-under=85
```

- **Privilege Escalation & Scope Hierarchy (`tests/test_privilege_escalation.py`):** Proves tenant admins cannot mint `platform:admin`, cannot grant arbitrary scopes, cannot access or rotate keys belonging to other tenants, and that global runtime configuration (`/api/v1/config`) is restricted strictly to platform administrators.
- **Complete Zero-Retention Privacy (`tests/test_privacy_complete.py`):** Inspects L1 cache, Redis, database records, child findings, and telemetry spans to verify complete absence of original source code when `RETAIN_SOURCE_CODE=false`.
- **Database Fallback Consistency & Fail-Closed Durability (`tests/test_database_fallback_consistency.py`, `tests/test_webhook_durability.py`):** Proves that single reviews, batch reviews, and GitHub webhook reviews synchronously commit critical records to durable storage before issuing IDs, exposing cache/memory, or posting external PR reviews. Verifies cross-worker retrieval upon total memory eviction and asserts fail-closed HTTP 500 rejection without orphan IDs on database outages.
- **Supply Chain & Kubernetes Verification (`tests/test_supply_chain_and_k8s.py`):** Validates zero drift between requirements and hashed lockfiles (`requirements-lock.txt` and `requirements-ci-tools-lock.txt`), enforces SHA-256 hashes on every package, verifies regeneration diff via `pip-compile`, validates `.trivyignore` exception format, and ensures immutable image digest pinning.
- **Accessibility Testing (`tests/test_browser_accessibility.py`):** Playwright headless browser suite asserting full keyboard navigation, ARIA landmarks, screen reader labels, high-contrast visual tokens, and `prefers-reduced-motion` compliance.
- **Master Hardening Verification Suite (`tests/test_perfect_10_master_coverage.py`):** 22 end-to-end test cases exercising CLI subcommands, API v1 routes, SingleFlight cache stampede coalescing, zlib payload compression, DB retry resilience, and polyglot syntax verification.
- **Tree-sitter AST Multi-Language Parity:** C-binding native AST verification for TypeScript, TSX, JavaScript, Go, Rust, and Python with line-and-column error precision.
- **GitHub PR Reviews:** Native `pull_request.opened` webhook ingestion with HMAC SHA-256 verification and line-anchored comments.
- **Timing-Safe Security:** `hmac.compare_digest` constant-time API key verification and granular scope RBAC (`require_scopes`).
- **Production Connection Pooling:** PostgreSQL connection pool (`pool_size=20`, `max_overflow=10`, `pool_recycle=3600`, `pool_pre_ping=True`) with asynchronous SQLite fallback using `NullPool` and WAL mode for zero lock contention.
- **Bytecode Verification:** `python -m compileall cerberus tests` (100% pass across all modules).
- **Security Headers:** Strict CSP, HSTS, X-Content-Type-Options, X-Frame-Options.
- **Sensitive Data Masking:** Automatic redaction of API keys and bearer tokens in application logs.
- **Zip-Slip & Zip-Bomb Mitigation:** Bounded decompression thresholds and path traversal protection.

---

## Extensible Plugin Architecture & Custom Rules

Cerberus v1.4.0 features an isolated plugin system allowing engineering teams to enforce proprietary guidelines, internal compliance rules, and custom linters without modifying core agent code:

- **Isolated Fault-Tolerant Execution:** Each plugin executes within a protected try/catch sandbox. If a third-party plugin raises an unhandled exception, Cerberus logs the error, isolates the failure, and completes the review with full agent consensus.
- **Pre- & Post-Review Hooks:** Intercept code requests before execution (`on_review_start`) to inject custom metadata, and inspect finalized verdicts (`on_review_complete`) to add company-specific compliance findings.
- **Shipped Plugins:**
  - `SecretScannerPlugin`: Proactively flags high-entropy API tokens, RSA private keys, AWS credentials, and GitHub PATs.
  - `TeamStylePlugin`: Enforces team coding conventions, mandatory docstrings, type annotations, and naming standards.

```python
from cerberus.core.plugins import BasePlugin
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse, Finding, SeverityEnum

class CustomLicensePlugin(BasePlugin):
    name = "custom_license_scanner"
    version = "1.0.0"
    description = "Enforces enterprise header license notices."

    async def on_review_complete(self, response: CodeReviewResponse, context: dict) -> None:
        if "Copyright (c) Acme Corp" not in context.get("raw_code", ""):
            response.findings.append(Finding(
                id="ACME-LIC-001",
                agent="CustomLicensePlugin",
                severity=SeverityEnum.MEDIUM,
                message="Missing standard Acme Corp copyright header in source file.",
                line=1
            ))
```

---

## Multi-Tenant Tiered Quotas & Burst Protection

For enterprise SaaS and shared internal platforms, Cerberus provides isolated multi-tenant resource governance with automatic monthly consumption tracking:

| Tier | Monthly Review Limit | Burst Allowance | Intended Use Case |
| :--- | :--- | :--- | :--- |
| **Free** | 50 reviews / month | 5 concurrent | Individual developers and open-source hobby projects |
| **Developer** | 500 reviews / month | 20 concurrent | Professional developers & independent contractors |
| **Team** | 2,500 reviews / month | 50 concurrent | Growth engineering teams and active CI/CD pipelines |
| **Enterprise** | **Unlimited** (`-1`) | 100 concurrent | Large-scale multi-repo organizations with dedicated SLAs |

- **Automatic Monthly Rollover:** Usage counters automatically reset on the 1st of each calendar month.
- **Atomic Thread-Safe Metering:** In-memory high-throughput quota evaluation with fail-closed HTTP 429 response when exhaustion limits are breached.
- **Administrative Tier Upgrades:** Dynamically adjust tenant tiers via CLI (`python -m cerberus.cli quotas`) or REST API (`POST /api/v1/tenants/{tenant_id}/tier`).

---

## Enterprise JWT Authentication & Scope Hierarchy

Cerberus implements cryptographically signed JSON Web Tokens (HS256) alongside timing-safe API keys for secure multi-tenant microservice integration:

```
┌───────────────────────────────────────────────────────────────┐
│                      Scope Hierarchy Matrix                   │
├───────────────────────────────────────────────────────────────┤
│  platform:admin     ──► Full access to /api/v1/config & all   │
│  tenant:admin       ──► Manage tenant keys, quotas & tiers    │
│  reviews:write      ──► Submit code, batch & ZIP reviews      │
│  reviews:read       ──► Retrieve review results, SARIF & SSE  │
│  keys:manage        ──► Rotate & revoke tenant API keys       │
└───────────────────────────────────────────────────────────────┘
```

- **Ephemeral Stream Tokens:** Live WebSocket and Server-Sent Events (SSE) connections require short-lived, single-use stream tokens (`POST /api/v1/review/{id}/stream-token`) preventing long-lived credential leakage in browser URLs.
- **Timing-Safe Invariant:** `hmac.compare_digest` constant-time verification completely neutralizes timing-attack vectors on API key inspection.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Clients & CI/CD Pipelines                             │
│  Web Dashboard  •  Typer CLI  •  GitHub App Webhooks  •  REST / SSE / WS    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / WebSocket (Port 8000)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    Enterprise Gateway (cerberus/api/)                       │
│   Security Headers  •  JWT / API Key RBAC  •  Sliding Token Rate Limiter    │
│   Multi-Tenant Quota Meter  •  Two-Tier LRU & Redis Cache  •  OTel Tracing  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│             Review Orchestrator (cerberus/agents/orchestrator.py)           │
│   Concurrent Agent Dispatch  •  Plugin Lifecycle Hooks  •  Zip Slip Defense  │
└──────────┬───────────┬───────────┬───────────┬───────────┬───────────┬──────┘
           │           │           │           │           │           │
           ▼           ▼           ▼           ▼           ▼           ▼
      ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
      │Security │ │Perform. │ │ Quality │ │Architect│ │Complian.│ │Consensus│
      │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │(Judge)  │
      └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
           │           │           │           │           │           │
           └───────────┴───────────┴─────┬─────┴───────────┴───────────┘
                                         ▼
                         ┌───────────────────────────────┐
                         │   Multi-Language AST Engine   │
                         │   • Tree-sitter (TS, Go, Rust)│
                         │   • Python ast.parse & Delims │
                         └───────────────┬───────────────┘
                                         ▼
                         ┌───────────────────────────────┐
                         │   Code Fixer Agent (Repair)   │
                         │   AST-Verified Git Patch      │
                         │   OASIS SARIF 2.1.0 & PR API  │
                         └───────────────┬───────────────┘
                                         ▼
                         ┌───────────────────────────────┐
                         │       Pluggable Providers     │
                         │  • HeuristicEngine (14ms AST) │
                         │  • Groq (Llama 3 Ultra-fast)  │
                         │  • OpenAI (GPT-4o)            │
                         │  • Anthropic (Claude 3.5)     │
                         │  • Google Gemini (2.0 Flash)  │
                         │  • DeepSeek (V3 / R1)         │
                         │  • Ollama (Private Local)     │
                         └───────────────────────────────┘
```

---

## Enterprise Deployment, Hardening & Security Policy

Cerberus provides verified infrastructure-as-code and security manifests for production:

- **Multi-Stage Container Image (`Dockerfile`):** Unprivileged runtime user (`cerberus`, UID `1000`), immutable non-editable wheels, pinned base image (`python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`), and native curl-based healthchecks.
- **Isolated Compose Network (`docker-compose.yml`):** Internal container-only network `cerberus_net`, PostgreSQL (`5432`) and Redis (`6379`) ports completely unexposed to host/public networks, strict healthcheck dependency gating.
- **Production Kubernetes Topology (`k8s/`):** Committed [`deployment.yaml`](k8s/deployment.yaml) and [`service.yaml`](k8s/service.yaml) featuring `readOnlyRootFilesystem`, `drop: ["ALL"]` capabilities, resource requests/limits, and truthful `/api/v1/ready` probe integration.
- **Production Deployment Gatekeeper (`scripts/deploy_production.py`):** Validates that production deployments only proceed from signed, digest-pinned release artifacts (`release-dist/cerberus-production-manifests.yaml`). Inspects all containers (`cerberus-api`, retention CronJobs, etc.), rejects unpinned tags, detects base-image digest collisions, and verifies sibling `.sha256` checksums. Operates in validation-only mode by default; cluster modifications require explicit `--apply` and `--confirm` flags and execute pre-flight `kubectl apply --dry-run=server` checks.
- **Verified Pre-Publish Release Engineering (`.github/workflows/release.yml`):** Enforces a build-once candidate container workflow. Trivy container vulnerability scanning (blocking on CRITICAL/HIGH), Docker Compose startup/auth/readiness smoke testing, and deployment smoke tests all execute against the local candidate image *before* pushing to GHCR. Upon verification, the exact image is pushed, signed via keyless Cosign OIDC, attested with build provenance, and rendered into immutable, checksummed Kubernetes release manifests published to GitHub Release assets.
- **Static Analysis Security Testing (`semgrep.yaml`):** Enforced SAST rules catching SQL injection patterns (CWE-89) and hard-coded production secrets (CWE-798).

---

## Engineering Audit Reports

- **[Master Engineering Audit](reports/MASTER_ENGINEERING_AUDIT.md)** — Comprehensive scorecard, architecture evaluation, and audit across 10 pillars
- **[Security Audit & Threat Model](reports/SECURITY_AUDIT.md)** — OWASP ASVS v4.0.3 analysis, STRIDE threat model, negative testing, and Red-Team results
- **[Test Results & Quality Assurance Report](reports/TEST_RESULTS.md)** — 685 automated tests execution summary, zero-flakiness analysis, and module breakdown
- **[AI/LLM Systems & Evaluation Report](reports/AI_EVALUATION.md)** — Foundation model routing, invariant safety guards, and consensus arbitration
- **[Performance Benchmarks Report](reports/PERFORMANCE_BENCHMARKS.md)** — Profiling, sub-millisecond cache latency, and SingleFlight thundering-herd defense
- **[Production Readiness & SRE Review](reports/PRODUCTION_READINESS.md)** — Launch checklist, deployment topologies, SLOs, and zero-downtime procedures
- **[Changelog](CHANGELOG.md)** — Historical record of all improvements and features

---

## Documentation Index

- **[System Architecture](docs/01-architecture-overview.md)** — Detailed multi-agent orchestration and design patterns
- **[API Reference](docs/02-api-reference.md)** — Complete OpenAPI 3.1 endpoints and payload schemas
- **[Agent Specifications](docs/03-agent-specifications.md)** — Comprehensive rules for all 7 specialized agents
- **[Installation & Docker Setup](docs/04-installation-setup.md)** — Step-by-step production deployment guide
- **[Configuration Reference](docs/05-configuration-reference.md)** — Environment variables and runtime tuning
- **[Monitoring & Operations](docs/06-monitoring-operations.md)** — Prometheus metrics, Grafana dashboards, and alerts
- **[Security & Compliance](docs/07-security-compliance.md)** — Zero-retention privacy, ASVS v4.0.3, and regulatory mappings
- **[Developer Guide](docs/08-developer-guide.md)** — Contribution workflows, local environment, and testing instructions
- **[Database Migrations](docs/09-database-migration.md)** — Schema versioning, Alembic, and connection pooling
- **[SLO Definitions](docs/09-slo-definitions.md)** — Service level objectives, error budgets, and latency thresholds
- **[Disaster Recovery](docs/10-disaster-recovery.md)** — Fail-closed consistency, backup restoration, and failover runbooks

---

## Contributing & Community

Contributions are welcomed:
- [Contributing Guide](CONTRIBUTING.md) for pull request instructions.
- [Security Policy](SECURITY.md) for responsible vulnerability disclosures.
- [Code of Conduct](CODE_OF_CONDUCT.md) for community standards.

---

## License

Distributed under the open-source **MIT License**. See [LICENSE](LICENSE) for full details.
