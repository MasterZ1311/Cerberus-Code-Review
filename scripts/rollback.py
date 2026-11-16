#!/usr/bin/env python3
"""
Automated Production Rollback Utility for Cerberus.
Executes deterministic rollbacks to previous Kubernetes deployment revisions
with automated post-rollback health checks and verification probes.
"""

import argparse
import logging
import shutil
import subprocess
import sys
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cerberus.rollback")


def execute_rollback(
    deployment_name: str = "cerberus",
    namespace: str = "cerberus",
    revision: Optional[int] = None,
    dry_run: bool = False,
    timeout_seconds: int = 120,
) -> int:
    """
    Executes a rollback on the specified deployment and waits for successful readiness.
    """
    kubectl_bin = shutil.which("kubectl")
    if not kubectl_bin:
        if dry_run:
            logger.info(
                "[DRY RUN] (kubectl not in PATH) Would execute: kubectl rollout undo deployment/%s -n %s%s",
                deployment_name,
                namespace,
                f" --to-revision={revision}" if revision else "",
            )
            return 0
        logger.error("kubectl executable not found in PATH.")
        return 1

    cmd = [kubectl_bin, "rollout", "undo", f"deployment/{deployment_name}", "-n", namespace]
    if revision is not None:
        cmd.append(f"--to-revision={revision}")

    if dry_run:
        cmd.append("--dry-run=client")
        logger.info("[DRY RUN] Would execute command: %s", " ".join(cmd))
        return 0

    logger.info("Executing rollback: %s", " ".join(cmd))
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Rollback initiated: %s", res.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.error("Rollback execution failed (code %d): %s", e.returncode, e.stderr.strip())
        return 1

    # Wait for rollout completion
    status_cmd = [
        kubectl_bin,
        "rollout",
        "status",
        f"deployment/{deployment_name}",
        "-n",
        namespace,
        f"--timeout={timeout_seconds}s",
    ]
    logger.info("Waiting for rollback deployment to stabilize...")
    try:
        status_res = subprocess.run(status_cmd, check=True, capture_output=True, text=True)
        logger.info("Rollout successfully completed: %s", status_res.stdout.strip())
        return 0
    except subprocess.CalledProcessError as e:
        logger.error("Rollback stabilization timed out or failed: %s", e.stderr.strip())
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Cerberus Production Rollback Gatekeeper")
    parser.add_argument("--deployment", default="cerberus", help="Kubernetes Deployment name")
    parser.add_argument("--namespace", "-n", default="cerberus", help="Target Kubernetes namespace")
    parser.add_argument("--revision", type=int, default=None, help="Specific revision to undo to (default: previous)")
    parser.add_argument("--timeout", type=int, default=120, help="Stabilization timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Simulate rollback without altering cluster state")
    args = parser.parse_args()

    return execute_rollback(
        deployment_name=args.deployment,
        namespace=args.namespace,
        revision=args.revision,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
