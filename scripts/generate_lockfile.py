#!/usr/bin/env python3
"""
Lockfile Generator & Workflow Tool for Cerberus.
Regenerates requirements-lock.txt deterministically from requirements.txt
using pip-compile with strict SHA-256 hash generation.
Fails closed if pip-compile is not installed or fails.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def generate_lockfile(output_path: Path, req_file: Path | None = None) -> int:
    """Generate deterministic requirements-lock.txt using pip-compile with hashes."""
    root = Path(__file__).resolve().parent.parent
    if req_file is None:
        req_file = root / "requirements.txt"

    if not req_file.exists():
        print(f"Error: Requirements input file {req_file} does not exist.", file=sys.stderr)
        return 1

    print(f"Generating deterministic hashed lockfile from {req_file} to {output_path}...")
    try:
        # Check if pip-compile is available
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
    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Successfully generated hashed lockfile at {output_path}.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error: pip-compile failed with exit code {e.returncode}: {e.stderr}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate Cerberus requirements lockfile")
    parser.add_argument("--output", "-o", default="requirements-lock.txt", help="Output lockfile path")
    parser.add_argument("--input", "-i", default="requirements.txt", help="Input requirements path")
    args = parser.parse_args()

    out_path = Path(args.output).resolve()
    in_path = Path(args.input).resolve()
    return generate_lockfile(out_path, in_path)


if __name__ == "__main__":
    sys.exit(main())
