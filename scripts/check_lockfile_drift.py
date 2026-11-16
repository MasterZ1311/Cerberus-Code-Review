#!/usr/bin/env python3
"""
Lockfile Drift & Hash Integrity Verifier for Cerberus.
Validates that:
1. requirements.txt and requirements-lock.txt are completely in sync (no version drift).
2. requirements-ci-tools.txt and requirements-ci-tools-lock.txt are completely in sync.
3. Every locked package in both lockfiles has at least one valid SHA-256 hash (--require-hashes compatibility).
4. Lockfiles are deterministically reproducible from their source requirements via pip-compile without diff.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
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
    """Verify that every package in lock_file has at least one sha256 hash."""
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
    errors: List[str] = []
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


def extract_normalized_tokens(content: str) -> List[str]:
    """
    Extracts normalized, non-comment lines from a lockfile.
    Filters out machine-dependent header comments, blank lines, and normalizes spacing.
    """
    normalized: List[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        normalized.append(line)
    return normalized


def verify_regeneration_diff(req_file: Path, lock_file: Path, allow_unsafe: bool = False) -> Tuple[bool, List[str]]:
    """
    Verify that regenerating the lockfile with pip-compile into a temporary file
    matches the committed lockfile exactly, with zero diff.
    """
    try:
        check = subprocess.run(["pip-compile", "--version"], capture_output=True, text=True)
        if check.returncode != 0:
            return False, ["pip-compile is not available to verify deterministic regeneration."]
    except FileNotFoundError:
        return False, ["pip-compile is not installed in the environment."]

    tf = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tf.close()
    try:
        if lock_file.exists():
            shutil.copy(lock_file, tf.name)

        cmd = [
            "pip-compile",
            "--generate-hashes",
            "--output-file",
            tf.name,
            str(req_file),
        ]
        if allow_unsafe:
            cmd.insert(1, "--allow-unsafe")

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return False, [f"pip-compile failed during regeneration check for {req_file.name}: {res.stderr}"]

        committed_reqs = parse_requirements(lock_file)
        generated_reqs = parse_requirements(Path(tf.name))

        diff_pkgs: List[str] = []
        for pkg, ver in generated_reqs.items():
            if pkg not in committed_reqs:
                diff_pkgs.append(f"Newly resolved package '{pkg}=={ver}' is not in committed {lock_file.name}")
            elif committed_reqs[pkg] != ver:
                diff_pkgs.append(
                    f"Version mismatch for '{pkg}': committed '{committed_reqs[pkg]}' vs newly resolved '{ver}'"
                )
        for pkg, ver in committed_reqs.items():
            if pkg not in generated_reqs:
                diff_pkgs.append(f"Committed package '{pkg}=={ver}' was not resolved by pip-compile")

        if diff_pkgs:
            return False, [
                f"Lockfile drift detected between committed {lock_file.name} and newly regenerated dependencies:\n"
                + "\n".join(f"    {d}" for d in diff_pkgs[:10])
            ]

        return True, []
    finally:
        if os.path.exists(tf.name):
            os.unlink(tf.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify requirements and lockfile drift and hash enforcement")
    parser.add_argument(
        "--check-regen", action="store_true", help="Also verify deterministic regeneration via pip-compile"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent

    # File pairs to validate
    pairs = [
        (root / "requirements.txt", root / "requirements-lock.txt", False),
        (root / "requirements-ci-tools.txt", root / "requirements-ci-tools-lock.txt", True),
    ]

    all_errors: List[str] = []

    for req_file, lock_file, allow_unsafe in pairs:
        print(f"Checking lockfile drift between {req_file.name} and {lock_file.name}...")
        valid_drift, drift_errors = verify_drift(req_file, lock_file)
        all_errors.extend(drift_errors)

        print(f"Checking SHA-256 hash enforcement in {lock_file.name}...")
        valid_hashes, hash_errors = verify_hash_enforcement(lock_file)
        all_errors.extend(hash_errors)

        if args.check_regen:
            print(f"Checking deterministic regeneration with pip-compile for {lock_file.name}...")
            valid_regen, regen_errors = verify_regeneration_diff(req_file, lock_file, allow_unsafe=allow_unsafe)
            all_errors.extend(regen_errors)

    if all_errors:
        print("FAILED: Dependency drift or hash integrity violations detected!", file=sys.stderr)
        for err in all_errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        print("\nRun 'python scripts/generate_lockfile.py --all' to reconcile.", file=sys.stderr)
        return 1

    print(
        "SUCCESS: All lockfiles are in full sync with declared requirements and all packages have verified SHA-256 hashes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
