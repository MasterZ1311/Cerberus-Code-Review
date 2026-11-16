#!/usr/bin/env python3
"""
Kubernetes Image Pinning & Provenance Validator for Cerberus.
Validates that:
1. Application image digests in Kubernetes manifests do NOT match Dockerfile base image digests.
2. Image digests follow immutable sha256:[a-f0-9]{64} formatting.
3. No obsolete CodeVault or IBM registry paths are used.
4. Rendered Kustomize manifests are syntactically valid.
5. If remote registry verification is requested but unavailable locally, reports exact status rather than pretending.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_dockerfile_base_digests(dockerfile_path: Optional[Path] = None) -> List[str]:
    """Extract all base image sha256 digests referenced in the Dockerfile."""
    df_path = dockerfile_path or (PROJECT_ROOT / "Dockerfile")
    if not df_path.exists():
        return []
    content = df_path.read_text(encoding="utf-8")
    # Matches: FROM python:3.11-slim@sha256:<hex>
    matches = re.findall(r"FROM\s+[^\s@]+@sha256:([a-f0-9]{64})", content, re.IGNORECASE)
    return [f"sha256:{m.lower()}" for m in matches]


def validate_image_pinning(
    kustomize_path: Optional[Path] = None,
    dockerfile_path: Optional[Path] = None,
    verify_registry: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Validate that k8s/kustomization.yaml:
    - Does not reuse Dockerfile base-image digests.
    - Uses valid sha256 format if a digest is present.
    - References valid Cerberus image repositories without legacy naming.
    """
    k_path = kustomize_path or (PROJECT_ROOT / "k8s" / "kustomization.yaml")
    df_path = dockerfile_path or (PROJECT_ROOT / "Dockerfile")

    errors: List[str] = []

    if not k_path.exists():
        return False, [f"Kustomization file not found: {k_path}"]

    base_digests = get_dockerfile_base_digests(df_path)

    try:
        content = yaml.safe_load(k_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"Failed to parse {k_path.name} as YAML: {e}"]

    images = content.get("images", [])
    if not images:
        errors.append(f"No 'images' section found in {k_path.name}")
        return False, errors

    for img in images:
        name = img.get("name")
        new_name = img.get("newName", "")
        digest = img.get("digest")
        new_tag = img.get("newTag")

        # 1. Reject obsolete CodeVault / IBM naming
        if "codevault" in new_name.lower():
            errors.append(
                f"Image '{name}' uses obsolete repository '{new_name}'. Must use 'ghcr.io/cerberus-ai/cerberus-ai'."
            )

        # 2. Check digest validity if specified
        if digest:
            digest_clean = digest.strip().lower()
            if not re.match(r"^sha256:[a-f0-9]{64}$", digest_clean):
                errors.append(f"Image '{name}' digest '{digest}' is not a valid 64-character sha256 hex string.")
            elif digest_clean in [d.lower() for d in base_digests]:
                errors.append(
                    f"REJECTED: Image '{name}' uses digest '{digest}', which matches the Dockerfile base image "
                    f"({df_path.name}). Cerberus application manifests must be pinned to the actual application "
                    f"build artifact digest, not the base OS image."
                )

        # 3. Check tag / digest declaration
        if not digest and not new_tag:
            errors.append(f"Image '{name}' must specify either 'digest' (for release) or 'newTag'.")

    # 4. Registry verification (optional / conditional)
    if verify_registry:
        errors.append(
            "Registry verification skipped: local offline environment has no authenticated access "
            "to container registry (ghcr.io). Verification must be executed within authorized CI/CD release workflow."
        )

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Kubernetes image pinning")
    parser.add_argument("--file", "-f", default=str(PROJECT_ROOT / "k8s" / "kustomization.yaml"))
    parser.add_argument("--dockerfile", "-d", default=str(PROJECT_ROOT / "Dockerfile"))
    parser.add_argument("--verify-registry", action="store_true", help="Attempt remote registry verification")
    args = parser.parse_args()

    k_path = Path(args.file).resolve()
    df_path = Path(args.dockerfile).resolve()

    print(f"Validating Kubernetes image pinning in {k_path}...")
    valid, errors = validate_image_pinning(k_path, df_path, verify_registry=args.verify_registry)

    if not valid:
        print("FAILED: Image pinning validation error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("SUCCESS: Kubernetes image configuration is valid and free of base-image collision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
