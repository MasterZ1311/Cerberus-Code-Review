# Supply Chain Security & Dependency Release Procedures

This document details the software supply-chain security architecture, dependency governance, lockfile workflows, vulnerability scanning gates, and release procedures for **cerberus</>**.

---

## 1. Supply-Chain Security Principles

Cerberus strictly follows zero-trust software supply-chain controls in accordance with NIST SP 800-218 (Secure Software Development Framework) and SLSA Level 3 guidelines:

1. **Deterministic Pinning**: All production dependencies and container base images are pinned with exact versions and immutable cryptographic digests (`sha256`).
2. **Reproducible Builds**: Virtual environments and containers build from `requirements-lock.txt`, avoiding floating versions in CI/CD and deployment.
3. **Automated Vulnerability Gating**: Commits and pull requests must pass automated audits via `pip-audit`, Trivy, Semgrep, and TruffleHog. Any unresolved High or Critical CVE blocks deployment.
4. **Machine-Readable SBOM**: Every release builds and signs a standard CycloneDX v1.5 Software Bill of Materials (`sbom.json`).

---

## 2. Dependency Management & Lockfile Workflow

Production builds install from `requirements-lock.txt` rather than unconstrained `requirements.txt`.

### 2.1 Updating Dependencies

To update or add a dependency:

1. Edit the core requirements in `requirements.txt` with minimum acceptable bounds (e.g., `fastapi>=0.141.0`).
2. Generate the resolved lockfile:
   ```bash
   pip install pip-tools
   pip-compile --generate-hashes --output-file=requirements-lock.txt requirements.txt
   ```
   *(Or generate deterministic frozen versions using `pip freeze > requirements-lock.txt` in a clean Python 3.11 virtual environment)*.
3. Validate the lockfile against known vulnerabilities:
   ```bash
   pip-audit -r requirements-lock.txt
   ```
4. Run static security and secret scanning:
   ```bash
   semgrep scan --config semgrep.yaml --error cerberus/
   trufflehog3 --no-history -v cerberus/
   ```
5. Run the complete test suite with 85% branch-coverage enforcement:
   ```bash
   pytest tests/ --cov=cerberus --cov-branch --cov-fail-under=85
   ```

---

## 3. Vulnerability Remediation Policy

| Severity | Target SLA | CI/CD Action | Policy Action |
|:---|:---|:---|:---|
| **Critical** | 24 Hours | **Hard Failure** (Build Blocked) | Immediate hotfix; upgrade or patch package. |
| **High** | 7 Days | **Hard Failure** (Build Blocked) | Mandatory upgrade in next sprint cycle. |
| **Medium** | 30 Days | Warning / Informational | Review for exploitability and patch. |
| **Low / Info** | 90 Days | Informational | Routine dependency refresh. |

### False Positive or Mitigation Exceptions
If a vulnerability cannot be immediately upgraded due to upstream delays and is non-exploitable in Cerberus's execution context, an explicit exception must be documented in `audit-exceptions.yaml` with:
- CVE ID
- Package name & version
- Non-exploitability proof
- Architecture review sign-off
- Expiry date (max 30 days)

---

## 4. Container & Base Image Governance

All Docker images must adhere to strict hardening:
- **Base Image**: `python:3.11-slim@sha256:...` (multi-arch immutable digest).
- **Least Privilege**: Application runs exclusively as non-root user `cerberus` (UID `1000`, GID `1000`).
- **Filesystem Security**: Runtime containers mount root filesystem as read-only (`readOnlyRootFilesystem: true`), utilizing scoped `emptyDir` volumes on `/tmp`.
- **Probes**: Container healthchecks invoke `/api/v1/ready` to ensure downstream DB and Redis connectivity before routing traffic.

---

## 5. Production Release Procedure

1. **Pre-Flight Verification**:
   - Verify `git status` is clean.
   - Run Ruff check and format: `ruff check cerberus/ && ruff format --check cerberus/`
   - Run Mypy with untyped checks: `mypy cerberus/`
   - Run Semgrep: `semgrep scan --config semgrep.yaml --error cerberus/`
   - Run complete test suite: `pytest tests/ --cov=cerberus --cov-branch --cov-fail-under=85`
   - Run deployment smoke tests: `python scripts/test_deployment_smoke.py`
2. **Version Bump**:
   - Update `__version__` in `cerberus/__init__.py`.
   - Update `pyproject.toml`.
   - Update `CHANGELOG.md` with release notes and CVE remediations.
3. **Artifact Generation**:
   - Generate release SBOM: `cyclonedx-py requirements requirements-lock.txt -o sbom.json`
   - Build container image tagged with SemVer: `docker build -t cerberus-ai:0.1.0 .`
4. **Git Tagging & Signing**:
   - Create signed git tag: `git tag -s v0.1.0 -m "Release v0.1.0"`
   - Push tag to upstream repository to trigger CI release pipeline.
