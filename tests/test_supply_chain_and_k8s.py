"""
Tests for Reproducible Supply Chain, Security Scanner Policy, and Kubernetes Hardening.
Verifies:
1. check_lockfile_drift accurately enforces version equality and catches drift.
2. verify_security_exceptions rejects expired, unowned, or unjustified scan waivers.
3. bootstrap_k8s_secrets generates high-entropy cryptographic secrets.
4. Kustomize manifests declare immutable container image digests.
"""

from pathlib import Path

import pytest

from scripts.bootstrap_k8s_secrets import generate_secrets_manifest
from scripts.check_doc_secrets import scan_documentation, scan_file
from scripts.check_lockfile_drift import (
    verify_drift,
    verify_hash_enforcement,
)
from scripts.generate_lockfile import generate_lockfile
from scripts.verify_security_exceptions import verify_exceptions_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_lockfile_drift_detector_clean():
    """Verify that current repository requirements.txt and requirements-lock.txt have zero drift."""
    req_file = PROJECT_ROOT / "requirements.txt"
    lock_file = PROJECT_ROOT / "requirements-lock.txt"
    valid, errors = verify_drift(req_file, lock_file)
    assert valid, f"Drift detected in production lockfile: {errors}"


def test_lockfile_hash_enforcement_clean():
    """Verify that every package in requirements-lock.txt is protected by SHA-256 hashes."""
    lock_file = PROJECT_ROOT / "requirements-lock.txt"
    valid, errors = verify_hash_enforcement(lock_file)
    assert valid, f"Hash enforcement failed on checked-in lockfile: {errors}"


def test_lockfile_hash_enforcement_catches_unhashed_packages(tmp_path: Path):
    """Verify that unhashed package definitions are rejected."""
    tmp_lock = tmp_path / "lock.txt"
    tmp_lock.write_text(
        "fastapi==0.141.1 \\\n"
        "    --hash=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "uvicorn==0.40.0\n",  # Missing hash line!
        encoding="utf-8",
    )
    valid, errors = verify_hash_enforcement(tmp_lock)
    assert not valid
    assert any("uvicorn" in err and "lacks required SHA-256 hash" in err for err in errors)


def test_lockfile_generator_fails_closed_when_pip_compile_missing(monkeypatch, tmp_path: Path):
    """Verify generator fails closed with exit code 1 if pip-compile is not installed."""
    import subprocess

    def mock_run(cmd, *args, **kwargs):
        raise FileNotFoundError("pip-compile not found")

    monkeypatch.setattr(subprocess, "run", mock_run)

    out_file = tmp_path / "failed-lock.txt"
    exit_code = generate_lockfile(out_file)
    assert exit_code == 1
    assert not out_file.exists(), "Should fail closed and not produce an unhashed fallback lockfile"


def test_lockfile_drift_detector_catches_divergence(tmp_path: Path):
    """Verify that any divergence in version constraint is strictly caught."""
    tmp_req = tmp_path / "req.txt"
    tmp_lock = tmp_path / "lock.txt"

    tmp_req.write_text("fastapi==0.141.1\nuvicorn==0.40.0\n", encoding="utf-8")
    tmp_lock.write_text("fastapi==0.141.1\nuvicorn==0.39.0\n", encoding="utf-8")  # Out of sync!

    valid, errors = verify_drift(tmp_req, tmp_lock)
    assert not valid
    assert any("uvicorn" in err for err in errors)


def test_security_exceptions_policy_validates_repo_trivyignore():
    """Verify that repository .trivyignore passes exception policy check."""
    ignore_file = PROJECT_ROOT / ".trivyignore"
    valid, errors = verify_exceptions_file(ignore_file)
    assert valid, f"Repository .trivyignore failed policy check: {errors}"


def test_security_exceptions_policy_rejects_expired_or_unjustified(tmp_path: Path):
    """Verify that expired exceptions or missing metadata fail with non-zero errors."""
    tmp_ignore = tmp_path / ".trivyignore"

    # 1. Expired exception
    tmp_ignore.write_text(
        "# CVE-2023-99999 [exp:2020-01-01] [owner:sec@cerberus.internal] [justification:Valid justification string]\n"
        "CVE-2023-99999\n",
        encoding="utf-8",
    )
    valid, errors = verify_exceptions_file(tmp_ignore)
    assert not valid
    assert any("EXPIRED" in err for err in errors)

    # 2. Insufficient justification (< 15 chars)
    tmp_ignore.write_text(
        "# CVE-2024-11111 [exp:2099-01-01] [owner:sec@cerberus.internal] [justification:too short]\nCVE-2024-11111\n",
        encoding="utf-8",
    )
    valid_short, errors_short = verify_exceptions_file(tmp_ignore)
    assert not valid_short
    assert any("Insufficient justification" in err for err in errors_short)


def test_bootstrap_k8s_secrets_generation():
    """Verify that bootstrap_k8s_secrets produces secure, compliant Secret manifests."""
    manifest = generate_secrets_manifest()
    assert "kind: Secret" in manifest
    assert "name: cerberus-secrets" in manifest
    assert "SECRET_KEY:" in manifest
    assert "DATABASE_URL:" in manifest

    # Custom secret key length check
    import sys

    from scripts.bootstrap_k8s_secrets import main

    with pytest.MonkeyPatch().context() as m:
        m.setattr(sys, "argv", ["bootstrap", "--secret-key", "too_short"])
        exit_code = main()
        assert exit_code == 1


def test_k8s_kustomize_image_pinning_and_base_image_rejection(tmp_path: Path):
    """Verify Kubernetes manifests enforce valid image configuration and reject base-image digest collision."""
    from scripts.update_k8s_image_digest import update_image_digest
    from scripts.validate_k8s_image_pinning import get_dockerfile_base_digests, validate_image_pinning

    kustomize_file = PROJECT_ROOT / "k8s" / "kustomization.yaml"
    valid, errors = validate_image_pinning(kustomize_file)
    assert valid, f"Base kustomization failed image validation: {errors}"

    content = kustomize_file.read_text(encoding="utf-8")
    assert "codevault" not in content.lower(), "Must not reference obsolete CodeVault registry"
    assert "ghcr.io/cerberus-ai/cerberus-ai" in content

    # 1. Collision detection: reject Docker base image digest
    base_digests = get_dockerfile_base_digests()
    assert len(base_digests) > 0, "Expected at least one base image digest in Dockerfile"
    base_sha = base_digests[0]

    mock_kustomize = tmp_path / "kustomization.yaml"
    mock_kustomize.write_text(
        f"apiVersion: kustomize.config.k8s.io/v1beta1\n"
        f"kind: Kustomization\n"
        f"images:\n"
        f"  - name: cerberus-ai\n"
        f"    newName: ghcr.io/cerberus-ai/cerberus-ai\n"
        f"    digest: {base_sha}\n",
        encoding="utf-8",
    )
    is_valid, collision_errors = validate_image_pinning(mock_kustomize)
    assert not is_valid
    assert any("matches the Dockerfile base image" in err for err in collision_errors)

    # 2. Rejection via update_k8s_image_digest
    ret_collision = update_image_digest(mock_kustomize, "cerberus-ai", base_sha)
    assert ret_collision == 1

    # 3. Successful update with genuine distinct application digest
    app_sha = "sha256:1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"
    ret_valid = update_image_digest(mock_kustomize, "cerberus-ai", app_sha)
    assert ret_valid == 0
    valid_updated, update_errors = validate_image_pinning(mock_kustomize)
    assert valid_updated, f"Distinct application digest should pass: {update_errors}"

    # 4. Local registry verification gracefully reports requirement
    valid_reg, reg_errors = validate_image_pinning(mock_kustomize, verify_registry=True)
    assert not valid_reg
    assert any("local offline environment has no authenticated access" in err for err in reg_errors)


def test_doc_secrets_hygiene_clean():
    """Verify that all markdown documentation files are clean of committed credentials."""
    clean, results = scan_documentation(PROJECT_ROOT)
    assert clean, f"Secret leakage detected in documentation: {results}"


def test_doc_secrets_catches_leakage(tmp_path: Path):
    """Verify that committed plaintext database passwords or tokens are caught."""
    tmp_doc = tmp_path / "leaky_guide.md"
    tmp_doc.write_text(
        "# Leaky Guide\nConnect using: postgresql://admin:MySecretPassword123@db.example.com:5432/prod\n",
        encoding="utf-8",
    )
    findings = scan_file(tmp_doc)
    assert len(findings) > 0
    assert any("Committed database/cache URI" in desc for _, desc, _ in findings)
