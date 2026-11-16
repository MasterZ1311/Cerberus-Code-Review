#!/usr/bin/env python3
"""
Lockfile Drift & Hash Integrity Verifier for Cerberus.
Validates that:
1. requirements.txt and requirements-lock.txt are completely in sync (no version drift).
2. Every locked package has at least one valid SHA-256 hash (--require-hashes compatibility).
3. The lockfile is deterministically reproducible from requirements.txt via pip-compile.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def parse_requirements(file_path: Path) -> Dict[str, str]:
    """Parse requirement file into package_name -> version_spec mapping."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    reqs: Dict[str, str] = {}
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--"):
            continue
        # Remove line continuation backslash if present
        if stripped.endswith("\\"):
            stripped = stripped[:-1].strip()
        # Strip environment markers for comparison
        clean_line = stripped.split(";")[0].strip()
        # Handle package name and version
        if "==" in clean_line:
            pkg, ver = clean_line.split("==", 1)
            # Remove extras like [standard]
            pkg_name = pkg.split("[")[0].strip().lower().replace("_", "-")
            # Clean version of any trailing slash or comment
            ver_clean = ver.split("#")[0].strip()
            if ver_clean.endswith("\\"):
                ver_clean = ver_clean[:-1].strip()
            reqs[pkg_name] = ver_clean
        elif ">=" in clean_line:
            pkg, ver = clean_line.split(">=", 1)
            pkg_name = pkg.split("[")[0].strip().lower().replace("_", "-")
            ver_clean = ver.split("#")[0].strip()
            if ver_clean.endswith("\\"):
                ver_clean = ver_clean[:-1].strip()
            reqs[pkg_name] = f">={ver_clean}"
        else:
            pkg_name = clean_line.split("[")[0].strip().lower().replace("_", "-")
            if not pkg_name.startswith("-"):
                reqs[pkg_name] = "*"
    return reqs


def verify_hash_enforcement(lock_file: Path) -> Tuple[bool, List[str]]:
    """Verify that every package in requirements-lock.txt has at least one sha256 hash."""
    if not lock_file.exists():
        return False, [f"Lockfile {lock_file.name} does not exist."]

    errors: List[str] = []
    lines = lock_file.read_text(encoding="utf-8").splitlines()

    current_pkg: str | None = None
    packages_with_hashes: Set[str] = set()
    all_packages: Set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("--hash=sha256:"):
            if current_pkg:
                packages_with_hashes.add(current_pkg)
            continue

        # Check for new package entry
        clean = stripped.split(";")[0].strip()
        if clean.endswith("\\"):
            clean = clean[:-1].strip()

        if "==" in clean:
            pkg = clean.split("==", 1)[0].split("[")[0].strip().lower().replace("_", "-")
            current_pkg = pkg
            all_packages.add(pkg)
        elif not stripped.startswith("--"):
            # Line without == and not an option might reset current package
            current_pkg = None

    missing_hashes = all_packages - packages_with_hashes
    if missing_hashes:
        for pkg in sorted(missing_hashes):
            errors.append(f"Package '{pkg}' in {lock_file.name} lacks required SHA-256 hash (--hash=sha256:...).")

    return len(errors) == 0, errors


def verify_drift(req_file: Path, lock_file: Path) -> Tuple[bool, List[str]]:
    """Verify that every package in req_file is pinned to the exact version in lock_file."""
    errors = []
    base_reqs = parse_requirements(req_file)
    lock_reqs = parse_requirements(lock_file)

    for pkg, ver in base_reqs.items():
        if pkg not in lock_reqs:
            errors.append(f"Package '{pkg}' is in {req_file.name} but missing from {lock_file.name}.")
            continue
        lock_ver = lock_reqs[pkg]
        if ver.startswith(">=") or ver == "*":
            # If base has a range, lock must have exact version pinned
            if not lock_ver or lock_ver.startswith(">="):
                errors.append(f"Package '{pkg}' must be strictly pinned (==) in {lock_file.name}, found '{lock_ver}'.")
        else:
            if ver != lock_ver:
                errors.append(
                    f"Version drift for '{pkg}': {req_file.name} specifies '{ver}' "
                    f"but {lock_file.name} has '{lock_ver}'."
                )

    return len(errors) == 0, errors


def verify_regeneration_diff(req_file: Path, lock_file: Path) -> Tuple[bool, List[str]]:
    """Verify that regenerating the lockfile with pip-compile produces no drift."""
    try:
        check = subprocess.run(["pip-compile", "--version"], capture_output=True, text=True)
        if check.returncode != 0:
            return False, ["pip-compile is not available to verify deterministic regeneration."]
    except FileNotFoundError:
        return False, ["pip-compile is not installed in the environment."]

    cmd = [
        "pip-compile",
        "--dry-run",
        "--generate-hashes",
        "--output-file",
        str(lock_file),
        str(req_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return False, [f"pip-compile failed during regeneration check: {res.stderr}"]

    return True, []


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify requirements and lockfile drift and hash enforcement")
    parser.add_argument(
        "--check-regen", action="store_true", help="Also verify deterministic regeneration via pip-compile"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    req_file = root / "requirements.txt"
    lock_file = root / "requirements-lock.txt"

    print(f"Checking lockfile drift between {req_file.name} and {lock_file.name}...")
    valid_drift, drift_errors = verify_drift(req_file, lock_file)

    print(f"Checking SHA-256 hash enforcement in {lock_file.name}...")
    valid_hashes, hash_errors = verify_hash_enforcement(lock_file)

    all_errors = drift_errors + hash_errors

    if args.check_regen:
        print("Checking deterministic regeneration with pip-compile...")
        valid_regen, regen_errors = verify_regeneration_diff(req_file, lock_file)
        if not valid_regen:
            all_errors.extend(regen_errors)

    if all_errors:
        print("FAILED: Dependency drift or hash integrity violations detected!", file=sys.stderr)
        for err in all_errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        print("\nRun 'python scripts/generate_lockfile.py' to reconcile.", file=sys.stderr)
        return 1

    print("SUCCESS: Lockfile is in full sync with declared requirements and all packages have verified SHA-256 hashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
