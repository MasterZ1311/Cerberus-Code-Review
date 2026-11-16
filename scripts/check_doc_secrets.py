#!/usr/bin/env python3
"""
Documentation Credential and Secret Hygiene Validator for Cerberus.
Scans documentation (*.md) and examples for production-looking secrets, API keys,
passwords, and obsolete internal infrastructure domains.
Ensures nonfunctional environment variable placeholders (e.g., ${WATSONX_API_KEY})
are used instead of committed secrets.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Patterns identifying committed credentials or obsolete internal domains
SUSPICIOUS_PATTERNS = [
    (
        r"(?:postgresql|postgres|redis|mysql)://[^:\s]+:[^@\s]+@",
        "Committed database/cache URI containing inline plaintext password",
    ),
    (
        r"(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][A-Za-z0-9_\-\.!@#$%^&*]{16,}['\"]",
        "Committed high-entropy secret, password, or token literal",
    ),
    (
        r"prod-ibm-watsonx-[A-Za-z0-9_\-]{8,}",
        "Realistic IBM Cloud / watsonx production API key",
    ),
    (
        r"prod_cerberus_[A-Za-z0-9_\-]{8,}",
        "Realistic Cerberus production secret or master key",
    ),
    (
        r"codevault\.enterprise\.ibm\.com",
        "Obsolete internal enterprise domain (codevault.enterprise.ibm.com)",
    ),
    (
        r"orchestrate\.ibm\.com",
        "Obsolete internal enterprise domain (orchestrate.ibm.com)",
    ),
    (
        r"\bcodevault\b",
        "Obsolete legacy 'CodeVault' branding found in documentation",
    ),
]

# Whitelisted test fixtures or explicit development references
ALLOWED_EXEMPTIONS = [
    "${",  # Standard environment variable placeholder ${VAR}
    "{{",  # Helm template variable
    "cerberus_ci_test_password",  # Explicit CI test password
    "cvai_dev_key_123",  # Explicit local dev mock key
    "cerberus_dev_secret_key",  # Explicit dev secret key
    "cerberus_dev_password",  # Explicit dev password
    "cvai_live_00000000",  # Explicit fabricated rejection test token
    "sk-live-1234567890abcdef",  # Synthetic secret detection test fixture
    "sk-1234567890abcdef",  # Documentation anti-pattern example
]


def scan_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """Scan a single file for suspicious secret patterns."""
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    lines = content.splitlines()
    for line_num, line in enumerate(lines, start=1):
        # Skip lines using explicit allowed exemptions
        if any(exempt in line for exempt in ALLOWED_EXEMPTIONS):
            continue

        for pattern, desc in SUSPICIOUS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append((line_num, desc, line.strip()[:80]))

    return findings


def scan_documentation(root_dir: Path) -> Tuple[bool, Dict[str, List[Tuple[int, str, str]]]]:
    """Scan all markdown files across repository."""
    results: Dict[str, List[Tuple[int, str, str]]] = {}
    md_files = list(root_dir.glob("*.md")) + list(root_dir.glob("docs/**/*.md"))

    for md_path in md_files:
        # Exclude pytest cache or brag output if any
        if ".pytest_cache" in md_path.parts or "brag-output" in md_path.parts:
            continue
        findings = scan_file(md_path)
        if findings:
            rel_path = str(md_path.relative_to(root_dir))
            results[rel_path] = findings

    total_violations = sum(len(f) for f in results.values())
    return total_violations == 0, results


def main() -> int:
    parser = argparse.ArgumentParser(description="Check documentation for secret hygiene and credential leakage")
    parser.add_argument("--root", default=".", help="Root directory to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    print(f"Scanning documentation files in {root} for secret hygiene...")
    clean, results = scan_documentation(root)

    if not clean:
        print("FAILED: Committed credentials or obsolete domains detected in documentation!", file=sys.stderr)
        for doc, findings in results.items():
            print(f"\nIn {doc}:", file=sys.stderr)
            for line_no, desc, snippet in findings:
                # Obfuscate snippet to avoid echoing secrets in output
                obfuscated = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", snippet)
                obfuscated = re.sub(r"(=|:)\s*['\"][^'\"]{8,}['\"]", r"\1 '***'", obfuscated)
                print(f"  Line {line_no}: {desc}", file=sys.stderr)
                print(f"    Snippet: {obfuscated}", file=sys.stderr)
        return 1

    print("SUCCESS: Documentation secret hygiene verified. All credentials properly placeholdered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
