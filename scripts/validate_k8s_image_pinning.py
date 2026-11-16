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
import hashlib
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


def verify_sibling_checksum(artifact_path: Path) -> Tuple[bool, Optional[str]]:
    """
    If a sibling .sha256 exists (e.g. <artifact>.sha256 or <artifact_stem>.sha256),
    verifies that the artifact's SHA-256 matches the sibling checksum file.
    Returns (True, None) if no sibling exists or if it matches.
    Returns (False, error_msg) if mismatch or invalid checksum format.
    """
    candidate_1 = artifact_path.parent / f"{artifact_path.name}.sha256"
    candidate_2 = artifact_path.with_suffix(".sha256")
    sha_path = candidate_1 if candidate_1.exists() else (candidate_2 if candidate_2.exists() else None)

    if not sha_path:
        return True, None

    try:
        content = sha_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        return False, f"Failed to read sibling checksum file {sha_path.name}: {e}"

    match = re.search(r"\b([a-f0-9]{64})\b", content, re.IGNORECASE)
    if not match:
        return False, f"Sibling checksum file {sha_path.name} does not contain a valid 64-character SHA-256 hash"

    expected_hash = match.group(1).lower()
    actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest().lower()

    if actual_hash != expected_hash:
        return (
            False,
            f"Checksum verification failed for {artifact_path.name}: "
            f"sibling checksum in {sha_path.name} ({expected_hash}) does not match actual artifact hash ({actual_hash}).",
        )

    return True, None


def validate_image_pinning(
    kustomize_path: Optional[Path] = None,
    dockerfile_path: Optional[Path] = None,
    verify_registry: bool = False,
    production_mode: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Validate Kubernetes manifests or Kustomization files:
    - Verifies sibling .sha256 checksum if present.
    - Supports both Kustomization files (with 'images' section) and rendered multi-document Kubernetes YAML.
    - Traverses all workload types (Deployment, StatefulSet, DaemonSet, Job, CronJob, Pod, initContainers).
    - In production mode, strictly requires immutable @sha256:<64 hex> digests and rejects mutable tags.
    - Rejects digests matching Dockerfile base image digests.
    - Rejects obsolete CodeVault or IBM registry paths.
    - Never leaks secret data.
    """
    target_path = kustomize_path or (PROJECT_ROOT / "k8s" / "kustomization.yaml")
    df_path = dockerfile_path or (PROJECT_ROOT / "Dockerfile")

    errors: List[str] = []

    if not target_path.exists():
        return False, [f"Target manifest file not found: {target_path}"]

    # 1. Sibling checksum verification
    checksum_valid, checksum_err = verify_sibling_checksum(target_path)
    if not checksum_valid and checksum_err:
        return False, [checksum_err]

    base_digests = get_dockerfile_base_digests(df_path)

    try:
        raw_content = target_path.read_text(encoding="utf-8")
        docs = [d for d in yaml.safe_load_all(raw_content) if d is not None]
    except Exception as e:
        return False, [f"Failed to parse {target_path.name} as YAML: {e}"]

    if not docs:
        return False, [f"Manifest file {target_path.name} is empty or contains no valid YAML documents"]

    is_prod = production_mode or ("production" in str(target_path).lower())

    # Detect if target is Kustomization or Rendered Kubernetes YAML
    is_kustomization = (
        len(docs) == 1
        and isinstance(docs[0], dict)
        and (docs[0].get("kind") == "Kustomization" or "images" in docs[0])
    )

    if is_kustomization:
        images = docs[0].get("images", [])
        if not images:
            errors.append(f"No 'images' section found in Kustomization file {target_path.name}")
            return False, errors

        for img in images:
            name = img.get("name")
            new_name = img.get("newName", "")
            digest = img.get("digest")
            new_tag = img.get("newTag")

            # 1. Reject obsolete CodeVault / IBM naming
            if "codevault" in new_name.lower() or "ibm" in new_name.lower():
                errors.append(
                    f"Image '{name}' uses obsolete repository '{new_name}'. Must use 'ghcr.io/cerberus-ai/cerberus-ai'."
                )

            # 2. In production mode, enforce strict immutable digest and forbid mutable tags
            if is_prod:
                if not digest:
                    errors.append(
                        f"Production deployment rejected: image '{name}' lacks an immutable digest. "
                        f"Found tag '{new_tag}'. Direct deployment from unpinned source templates is forbidden; "
                        f"production must deploy from signed, digest-pinned release artifacts."
                    )
                elif "template" in str(new_tag).lower() or "unpinned" in str(new_tag).lower():
                    errors.append(
                        f"Production deployment rejected: image '{name}' references unpinned release template tag '{new_tag}'."
                    )

            # 3. Check digest validity if specified
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

            # 4. Check tag / digest declaration
            if not digest and not new_tag:
                errors.append(f"Image '{name}' must specify either 'digest' (for release) or 'newTag'.")
    else:
        # Rendered Kubernetes multi-document YAML
        total_containers = 0
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            kind = doc.get("kind", "UnknownKind")
            metadata = doc.get("metadata", {})
            doc_name = metadata.get("name", "unnamed")

            # Locate pod spec template based on workload kind
            pod_spec = None
            if kind == "Pod":
                pod_spec = doc.get("spec", {})
            elif kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet", "ReplicationController"):
                pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
            elif kind == "CronJob":
                pod_spec = (
                    doc.get("spec", {})
                    .get("jobTemplate", {})
                    .get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )

            if not pod_spec or not isinstance(pod_spec, dict):
                continue

            containers: List[dict] = []
            for c_key in ("containers", "initContainers", "ephemeralContainers"):
                c_list = pod_spec.get(c_key)
                if isinstance(c_list, list):
                    containers.extend(c_list)

            for c in containers:
                if not isinstance(c, dict):
                    continue
                total_containers += 1
                c_name = c.get("name", "unnamed")
                image = str(c.get("image", "")).strip()

                if not image:
                    errors.append(f"Container '{c_name}' in {kind}/{doc_name} has empty image reference.")
                    continue

                # 1. Reject obsolete CodeVault / IBM naming
                if "codevault" in image.lower() or "ibm" in image.lower():
                    errors.append(
                        f"Container '{c_name}' in {kind}/{doc_name} uses obsolete repository '{image}'. "
                        f"Must use 'ghcr.io/cerberus-ai/cerberus-ai'."
                    )

                # 2. Check for digest: @sha256:<64 hex>
                digest_match = re.search(r"@sha256:([^\s@]+)", image, re.IGNORECASE)
                if digest_match:
                    digest_hex = digest_match.group(1).strip().lower()
                    full_digest = f"sha256:{digest_hex}"

                    # Validate 64 hex characters
                    if not re.match(r"^[a-f0-9]{64}$", digest_hex):
                        errors.append(
                            f"Container '{c_name}' in {kind}/{doc_name} image '{image}' digest is not a valid 64-character sha256 hex string."
                        )
                    elif full_digest in [d.lower() for d in base_digests]:
                        errors.append(
                            f"REJECTED: Container '{c_name}' in {kind}/{doc_name} uses digest '{full_digest}', which matches the Dockerfile base image "
                            f"({df_path.name}). Cerberus application manifests must be pinned to the actual application build artifact digest, not the base OS image."
                        )
                else:
                    if is_prod:
                        errors.append(
                            f"Production deployment rejected: container '{c_name}' in {kind}/{doc_name} lacks an immutable digest. "
                            f"Found image '{image}'. Production manifests must specify an immutable @sha256:<hex> digest."
                        )

        if total_containers == 0 and is_prod:
            errors.append(f"No container workloads found to validate in production manifest: {target_path.name}")

    # Optional / conditional registry verification
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
    parser.add_argument(
        "--production", action="store_true", help="Enforce strict production digest pinning (reject tags)"
    )
    args = parser.parse_args()

    k_path = Path(args.file).resolve()
    df_path = Path(args.dockerfile).resolve()

    print(f"Validating Kubernetes image pinning in {k_path}...")
    valid, errors = validate_image_pinning(
        k_path, df_path, verify_registry=args.verify_registry, production_mode=args.production
    )

    if not valid:
        print("FAILED: Image pinning validation error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("SUCCESS: Kubernetes image configuration is valid and free of base-image collision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
