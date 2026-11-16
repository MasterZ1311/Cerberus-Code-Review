#!/usr/bin/env python3
"""
Lockfile Generator & Workflow Tool for Cerberus.
Regenerates requirements-lock.txt and requirements-ci-tools-lock.txt deterministically
using pip-compile with strict SHA-256 hash generation.
Fails closed if pip-compile is not installed or fails.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def generate_lockfile(output_path: Path, req_file: Path | None = None, allow_unsafe: bool = False) -> int:
    """Generate deterministic hashed lockfile using pip-compile with hashes."""
    root = Path(__file__).resolve().parent.parent
    if req_file is None:
        req_file = root / "requirements.txt"

    if not req_file.exists():
        print(f"Error: Requirements input file {req_file} does not exist.", file=sys.stderr)
        return 1

    print(f"Generating deterministic hashed lockfile from {req_file.name} to {output_path.name}...")
    try:
        res = subprocess.run(["pip-compile", "--version"], capture_output=True, text=True)
        if res.returncode != 0:
            print(
                "Error: pip-compile (from pip-tools) is not installed or failed to execute.\n"
                "A secure supply chain requires pip-compile to generate cryptographic hashes.\n"
                "Install pip-tools via 'pip install pip-tools' and re-run.",
                file=sys.stderr,
            )
            return 1
    except FileNotFoundError:
        print(
            "Error: pip-compile command not found in PATH.\n"
            "Unpinned or unhashed fallback generators are strictly forbidden for supply-chain integrity.\n"
            "Install pip-tools via 'pip install pip-tools' and re-run.",
            file=sys.stderr,
        )
        return 1

    cmd = [
        "pip-compile",
        "--generate-hashes",
        "--output-file",
        str(output_path),
        str(req_file),
    ]
    if allow_unsafe:
        cmd.insert(1, "--allow-unsafe")

    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Successfully generated hashed lockfile at {output_path.name}.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error: pip-compile failed with exit code {e.returncode}: {e.stderr}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate Cerberus requirements lockfile(s)")
    parser.add_argument("--ci-tools", action="store_true", help="Regenerate requirements-ci-tools-lock.txt")
    parser.add_argument("--all", action="store_true", help="Regenerate both runtime and CI tools lockfiles")
    parser.add_argument("--output", "-o", default=None, help="Custom output lockfile path")
    parser.add_argument("--input", "-i", default=None, help="Custom input requirements path")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent

    if args.input and args.output:
        return generate_lockfile(Path(args.output).resolve(), Path(args.input).resolve())

    exit_code = 0
    if args.all or not args.ci_tools:
        # Runtime lockfile
        req_runtime = root / "requirements.txt"
        lock_runtime = root / "requirements-lock.txt"
        ret = generate_lockfile(lock_runtime, req_runtime, allow_unsafe=False)
        if ret != 0:
            exit_code = ret

    if args.all or args.ci_tools:
        # CI tools lockfile
        req_ci = root / "requirements-ci-tools.txt"
        lock_ci = root / "requirements-ci-tools-lock.txt"
        ret = generate_lockfile(lock_ci, req_ci, allow_unsafe=True)
        if ret != 0:
            exit_code = ret

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
