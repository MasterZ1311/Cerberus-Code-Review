#!/usr/bin/env python3
"""
Production Deployment Gatekeeper for Cerberus.
Validates that production deployments are only performed from signed,
digest-pinned release manifests, and strictly rejects unpinned templates
or tag-only deployments.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.validate_k8s_image_pinning import validate_image_pinning
except ImportError:
    from validate_k8s_image_pinning import validate_image_pinning  # type: ignore


def check_production_deploy_readiness(target_path: Path) -> int:
    """
    Check that target manifest/overlay is digest-pinned, checksum-verified,
    and safe for production deployment. Returns 0 if valid, 1 if blocked.
    """
    if not target_path.exists():
        print(f"ERROR: Deployment target not found: {target_path}", file=sys.stderr)
        return 1

    valid, errors = validate_image_pinning(target_path, production_mode=True)
    if not valid:
        print("DEPLOYMENT BLOCKED: The target artifact is not certified for production:", file=sys.stderr)
        for err in errors:
            print(f"  [X] {err}", file=sys.stderr)
        print("\nProduction deployments must use verified, digest-pinned release artifacts.", file=sys.stderr)
        print("Example: kubectl apply -f release-dist/cerberus-production-manifests.yaml", file=sys.stderr)
        return 1

    print(f"SUCCESS: Target {target_path.name} is verified and certified for production deployment.")
    return 0


def deploy_production(
    target_path: Path,
    namespace: str = "cerberus",
    apply: bool = False,
    confirm: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Production deployment controller:
    - Default behavior is validation only; never applies cluster changes unless explicitly requested.
    - If apply is True, requires confirm=True.
    - If apply and confirm are True, runs server-side dry run (kubectl apply --dry-run=server) first.
    - Safely fails closed if cluster tooling (kubectl) is missing or cluster rejects manifests.
    """
    # 1. Validation phase (always executed first)
    readiness_rc = check_production_deploy_readiness(target_path)
    if readiness_rc != 0:
        return readiness_rc

    # 2. Default behavior: validation only
    if not apply:
        print("NOTE: Default execution is validation-only. No cluster modifications were attempted.")
        print("To apply this certified artifact to a cluster, rerun with explicit --apply and --confirm flags.")
        return 0

    # 3. Explicit apply requested - verify authorization confirmation
    if not confirm:
        print(
            "ERROR: --apply requires explicit confirmation (--confirm flag). Refusing to modify cluster state without authorization.",
            file=sys.stderr,
        )
        return 1

    # 4. Check for cluster deployment tooling (fail closed safely if absent)
    kubectl_bin = shutil.which("kubectl")
    if not kubectl_bin:
        print(
            "ERROR: Cluster deployment tooling ('kubectl') is not installed or not found on PATH. Cannot apply manifests to cluster.",
            file=sys.stderr,
        )
        return 1

    target_args = (
        ["-k", str(target_path.parent)]
        if target_path.name == "kustomization.yaml"
        else ["-f", str(target_path)]
    )

    # 5. Pre-flight server-side dry-run
    print(f"Executing pre-flight server dry-run in namespace '{namespace}'...")
    dry_run_cmd = [kubectl_bin, "apply", "--dry-run=server", "-n", namespace] + target_args
    proc_dry = subprocess.run(dry_run_cmd, capture_output=True, text=True)
    if proc_dry.returncode != 0:
        print(
            f"ERROR: Server-side dry-run validation failed (exit code {proc_dry.returncode}):\n{proc_dry.stderr}",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print("SUCCESS: Server-side dry run passed (--dry-run flag supplied; skipping real apply).")
        return 0

    # 6. Apply certified manifests to cluster
    print(f"Applying certified manifests to cluster in namespace '{namespace}'...")
    apply_cmd = [kubectl_bin, "apply", "-n", namespace] + target_args
    proc_apply = subprocess.run(apply_cmd, capture_output=True, text=True)
    if proc_apply.returncode != 0:
        print(
            f"ERROR: Deployment apply failed (exit code {proc_apply.returncode}):\n{proc_apply.stderr}",
            file=sys.stderr,
        )
        return 1

    print(f"SUCCESS: Successfully applied {target_path.name} to cluster in namespace '{namespace}'.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cerberus Production Deployment Gatekeeper")
    parser.add_argument(
        "--target",
        "--manifests",
        "-t",
        dest="target",
        default=str(PROJECT_ROOT / "k8s" / "overlays" / "production" / "kustomization.yaml"),
        help="Path to manifest or Kustomize overlay to validate before deploying",
    )
    parser.add_argument(
        "--namespace",
        "-n",
        default="cerberus",
        help="Target Kubernetes namespace",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the validated release artifact to the Kubernetes cluster (requires --confirm)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required to apply cluster changes with --apply",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate deployment gate validation without applying to cluster",
    )
    args = parser.parse_args()

    return deploy_production(
        target_path=Path(args.target).resolve(),
        namespace=args.namespace,
        apply=args.apply,
        confirm=args.confirm,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
