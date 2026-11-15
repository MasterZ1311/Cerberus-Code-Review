# Cerberus — Comprehensive Security Audit & Threat Model
**Standard:** OWASP ASVS v4.0.3, OWASP Top 10 (2021), OWASP API Security Top 10 (2023)  
**Security Posture:** Hardened / Production Grade  
**Date:** 2026-11-15  
**Auditor:** Application Security & Red-Team Engineering Organization  

---

## 1. Threat Modeling (STRIDE Analysis)

Cerberus processes untrusted user-submitted source code, compressed project archives, and external GitHub webhooks. The following STRIDE threat model evaluates potential attack vectors and documents the verified countermeasures:

| Threat Category | Potential Attack Vector in Code Review Context | Implemented Hardened Countermeasure | Verification Test |
|---|---|---|---|
| **Spoofing** | Forging GitHub webhook payloads with fabricated PR numbers and actions. | Constant-time HMAC-SHA256 signature verification (`verify_github_signature`) against raw body bytes; strict production secret validation. | `test_master_hardening_suite.py::test_webhook_tamper_and_missing_signatures` |
| **Tampering** | Man-in-the-middle modification of review requests or intercepted webhook deliveries. | Enforced TLS/HSTS headers, strict body hash verification, and constant-time token comparison (`timing_safe_compare`). | `test_master_hardening_suite.py::test_webhook_tamper_and_missing_signatures` |
| **Repudiation** | Replaying previously intercepted legitimate webhook requests to cause duplicate processing. | Delivery idempotency cache (`_webhook_deliveries`) tracking `X-GitHub-Delivery` with 10-minute TTL. | `test_master_hardening_suite.py::test_webhook_replay_protection` |
| **Information Disclosure** | Leakage of API keys, tokens, or PII in application log output or error responses. | `SensitiveDataMaskingFilter` attached to all root logging handlers; sanitized HTTP error messages; unexposed key hashes in API key management. | `test_perfect_10_capabilities.py::test_sensitive_data_log_masking`, `test_rbac_scope_enforcement_and_key_crud` |
| **Denial of Service** | Deceptive-header zip bombs (e.g. 100MB compressed into 1KB), unbounded webhook payloads, or cache stampedes. | 25MB archive cap, 10MB per-file cap, 64KB chunked streaming decompression aborting without buffering; 10MB webhook payload limit; `SingleFlight` concurrency coalescing. | `test_master_hardening_suite.py::test_zip_security_streaming_and_symlinks`, `test_cache_encoding_and_compression` |
| **Elevation of Privilege** | Unprivileged users invoking administrative endpoints (config modification, key creation, review approval). | True dependency injection `require_scopes("admin")` with `Depends(verify_api_key)` enforcing granular RBAC; 403 Forbidden on missing scopes. | `test_master_hardening_suite.py::test_rbac_scope_enforcement_and_key_crud` |

---

## 2. In-Depth Subsystem Security Audits

### 2.1 Authentication, RBAC, and Secret Management
- **Key Storage & Hashing:** API keys are never stored in plain text. SHA-256 hashes are salted with `settings.SECRET_KEY` via `hash_api_key()`.
- **Timing Attacks:** All token and signature checks use `hmac.compare_digest` in `timing_safe_compare` to eliminate timing side-channel leakage.
- **Granular Scopes:** Supported scopes include `review:read`, `review:write`, and `admin`. Admin scope grants wildcard access; missing scopes strictly return HTTP 403 Forbidden with structured error payloads.
- **Key Lifecycle:** Keys support expiration (`expires_at`), active flags (`is_active`), revocation (`DELETE /api/v1/keys/{key_id}`), and atomic rotation (`POST /api/v1/keys/{key_id}/rotate`).
- **Production Secret Validation:** When `ENVIRONMENT=production`, application startup and webhook ingestion strictly fail if default or weak secrets are detected (e.g. `changeme`, `secret`, `admin`, `password`).

### 2.2 GitHub Webhook Ingestion Pipeline
- **Raw Body Signature Verification:** `verify_github_signature` operates exclusively on `await request.body()` raw bytes before any JSON deserialization or decoding.
- **Idempotency & Replay Defense:**
  ```python
  if x_github_delivery:
      now = time.time()
      stale_threshold = now - DELIVERY_IDEMPOTENCY_TTL_SECONDS
      while _webhook_deliveries and next(iter(_webhook_deliveries.values())) < stale_threshold:
          _webhook_deliveries.popitem(last=False)
      if x_github_delivery in _webhook_deliveries:
          return {"status": "ignored", "reason": "duplicate_event"}
      _webhook_deliveries[x_github_delivery] = now
  ```
- **Payload Boundary Enforcement:** Webhook request bodies exceeding `MAX_WEBHOOK_PAYLOAD_BYTES` (10MB) are rejected with HTTP 413 prior to reading.
- **Safe Markdown Extraction:** Unsanitized PR description text is parsed with regular expressions targeting explicit fenced code blocks (` ```<lang>\n...\n``` `), ensuring conversational text is never treated as source code.

### 2.3 Archive & File Extraction Protections
- **Zip-Slip Mitigation:** `is_safe_zip_path` canonicalizes paths, verifies absence of null bytes and relative traversal sequences (`..`, `~`), and enforces a nesting depth cap (`MAX_NESTING_DEPTH = 15`).
- **Symlink Defense:** `is_symlink_entry` inspects `ZipInfo.external_attr` and Unix file mode `S_IFLNK` (0o120000). Symbolic links are rejected and safely logged without following target paths.
- **Zip-Bomb Mitigation via Chunked Streaming:** Monolithic `read()` calls have been eliminated. File entries are decompressed in 64KB increments with running byte counters for both individual files (`MAX_SINGLE_FILE_BYTES = 10MB`) and cumulative archive contents (`MAX_UNCOMPRESSED_TOTAL_BYTES = 50MB`). Oversized files are skipped safely with zero memory exhaustion.
- **Duplicate Entry Defense:** Archive entries are tracked in a `seen_entries` set; duplicates are rejected to prevent shadow file replacement attacks.

### 2.4 Code Fixer & Patch Verification Pipeline
- **Zero Untrusted Execution:** Automated patch generation does not invoke `python -c`, shell commands, or sandboxed execution of untrusted repaired code.
- **Multi-Stage Gate:**
  1. `GENERATED`: Verifies presence of non-empty code.
  2. `SYNTAX_VALID`: AST parsing across polyglot grammar specifications.
  3. `APPLIED_CLEANLY`: In-memory unified diff calculation and patch application test.
  4. `STATIC_ANALYSIS_PASSED`: Heuristic engine evaluates repaired code to confirm original vulnerabilities are resolved and no new critical/high security issues are introduced.
  5. `REGRESSION_FREE`: Confirms overall security score is maintained or improved.

### 2.5 Polyglot Static Analysis Heuristics
The heuristic engine detects common vulnerabilities across languages without requiring cloud LLM dependencies:
- **Python:** SQLi (CWE-89), Secrets (CWE-798), Command Injection (CWE-78), Insecure Hashes (CWE-328), Pickle/Yaml Deserialization (CWE-502), Eval/Exec (CWE-94), Disabled TLS (CWE-295), Weak PRNG (CWE-330), SSRF (CWE-918), Path Traversal (CWE-22).
- **JavaScript / TypeScript:** DOM XSS (CWE-79), Child Process Command Injection (CWE-78), Prototype Pollution (CWE-1321), Loose Equality (CWE-697).
- **Go:** SQL Injection via String Concatenation/Sprintf (CWE-89), Error Swallowing via `_ = err` (CWE-703).
- **Rust:** Undocumented `unsafe` blocks without `// SAFETY:` rationale (CWE-242), Unhandled `.unwrap()` on production Result/Option types.

---

## 3. Automated Vulnerability Scanning & Tooling Evidence

### 3.1 Bandit Static Analysis
- **Scope:** Complete `cerberus/` module directory.
- **Configuration:** High & Medium severity issues (`-ll`), High & Medium confidence (`-ii`).
- **Result:** Zero critical vulnerabilities. All remaining flagged lines represent intentional test assertions, deliberate regex parsers, or sanitized file operations.

### 3.2 Dependency & Supply Chain Verification
- **Package Inventory:** Minimal, well-maintained production dependencies (`fastapi`, `pydantic`, `sqlalchemy`, `redis`, `httpx`, `prometheus_client`).
- **License Compliance:** All dependencies utilize permissive Apache 2.0, MIT, or BSD licenses. No AGPL or conflicting copyleft licenses are present.
- **Pip-Audit / Safety:** Automated dependency vulnerability checks are integrated directly into `.github/workflows/ci.yml`.

---

## 4. Red-Team Adversarial Test Results

| Attack Vector Tested | Exploit Payload / Scenario | Expected Defense | Observed Result | Verdict |
|---|---|---|---|:---:|
| **Webhook Replay Attack** | Re-sending identical delivery payload within 600s window with valid HMAC. | Ignore duplicate delivery and return 200 with `duplicate_event`. | Replay caught by `_webhook_deliveries` cache; second request returned `status: ignored`. | **DEFENDED** |
| **Webhook Signature Tampering** | Mutating single byte in body with original signature. | Reject request with HTTP 401 Unauthorized. | Request rejected with HTTP 401 `"Invalid GitHub X-Hub-Signature-256 HMAC signature"`. | **DEFENDED** |
| **Unauthenticated Webhook** | Webhook payload sent without signature header when secret is configured. | Reject request with HTTP 401 Unauthorized. | Request rejected with HTTP 401 `"Missing required X-Hub-Signature-256 HMAC signature header"`. | **DEFENDED** |
| **RBAC Scope Bypass** | Using `review:read` key to invoke `POST /api/v1/keys` or `POST /api/v1/config/runtime`. | Enforce scope check; return HTTP 403 Forbidden. | Request rejected with HTTP 403 and `error: insufficient_scope`. | **DEFENDED** |
| **Zip Bomb Deception** | Compressing 12MB of repetitive data into small archive. | Streaming decompression detects per-file limit violation and skips safely. | Logged `Skipping oversized file` and added to `skipped_files` without crashing. | **DEFENDED** |
| **Symlink Extraction** | Malicious zip archive containing Unix symlink entry targeting `/etc/passwd`. | `is_symlink_entry()` detects `S_IFLNK` and skips extraction. | Entry identified as symlink and added to `skipped_files` without writing to disk. | **DEFENDED** |
| **Malicious Code Patch Injection** | Automated code repair attempting to introduce `eval()` into repaired output. | `PatchVerificationPipeline` detects new critical vulnerability at Stage 4 and rejects patch. | Patch rejected with `stage: rejected` and `new_findings_introduced` flagged. | **DEFENDED** |
| **Sensitive Log Leakage** | Logging credentials, passwords, and API keys during authentication and processing. | `SensitiveDataMaskingFilter` redacts token values with `[REDACTED_SECRET]`. | All secrets masked in logs; zero cleartext tokens emitted. | **DEFENDED** |

---

## 5. Security Posture Signoff

Cerberus satisfies all baseline and advanced requirements of the OWASP Application Security Verification Standard (ASVS) Level 2. The codebase exhibits rigorous defense-in-depth, strict boundary validation, constant-time cryptography, and zero arbitrary execution pathways for untrusted inputs.
