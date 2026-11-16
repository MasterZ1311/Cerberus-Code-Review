#!/usr/bin/env python3
"""
Security Scanner Exception Policy Verifier for Cerberus.
Validates .trivyignore entries to guarantee that any security scan exception
has an unexpired expiration date, an assigned owner, and an audited justification.
"""

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_metadata_comment(comment_line: str) -> Optional[Dict[str, str]]:
    """Extract exp, owner, and justification from metadata comment."""
    exp_match = re.search(r"\[exp:(\d{4}-\d{2}-\d{2})\]", comment_line)
    owner_match = re.search(r"\[owner:([^\]]+)\]", comment_line)
    just_match = re.search(r"\[justification:([^\]]+)\]", comment_line)

    if not (exp_match and owner_match and just_match):
        return None

    return {
        "exp": exp_match.group(1).strip(),
        "owner": owner_match.group(1).strip(),
        "justification": just_match.group(1).strip(),
    }


def verify_exceptions_file(file_path: Path) -> Tuple[bool, List[str]]:
    """
    Validates exceptions file against policy:
    1. Every vulnerability ID must have an immediate preceding metadata comment.
    2. Expiration date must not be in the past (UTC).
    3. Owner must be specified.
    4. Justification must be at least 15 characters.
    """
    errors: List[str] = []
    if not file_path.exists():
        # Missing file is not an error if no exceptions are claimed, but let's report warning
        return True, []

    lines = file_path.read_text(encoding="utf-8").splitlines()
    today = datetime.now(UTC).date()

    last_comment = ""
    active_exceptions_count = 0

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            last_comment = ""
            continue

        if stripped.startswith("#"):
            last_comment = stripped
            continue

        # If we reach here, this is a vulnerability ID (exception)
        vuln_id = stripped
        active_exceptions_count += 1

        if not last_comment:
            errors.append(
                f"Line {line_num}: Vulnerability '{vuln_id}' lacks mandatory metadata comment. "
                f"Expected format: '# {vuln_id} [exp:YYYY-MM-DD] [owner:...] [justification:...]' immediately preceding."
            )
            continue

        meta = parse_metadata_comment(last_comment)
        if not meta:
            errors.append(
                f"Line {line_num}: Metadata comment for '{vuln_id}' is malformed. "
                f"Must include [exp:YYYY-MM-DD], [owner:team@domain], and [justification:reason]."
            )
            last_comment = ""
            continue

        # Check expiration
        try:
            exp_date = datetime.strptime(meta["exp"], "%Y-%m-%d").date()
            if exp_date < today:
                errors.append(
                    f"Line {line_num}: Exception for '{vuln_id}' EXPIRED on {meta['exp']} (owner: {meta['owner']}). "
                    f"Expired exceptions must be removed or remediated."
                )
        except ValueError:
            errors.append(f"Line {line_num}: Invalid date format '{meta['exp']}' for '{vuln_id}'. Expected YYYY-MM-DD.")

        # Check owner
        if not meta["owner"]:
            errors.append(f"Line {line_num}: Missing owner for exception '{vuln_id}'.")

        # Check justification
        if len(meta["justification"]) < 15:
            errors.append(
                f"Line {line_num}: Insufficient justification for '{vuln_id}' (minimum 15 characters required)."
            )

        last_comment = ""

    if errors:
        return False, errors

    print(f"Verified {active_exceptions_count} active security exceptions in {file_path.name}: ALL VALID.")
    return True, []


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify security scan exceptions policy")
    parser.add_argument("--file", "-f", default=".trivyignore", help="Path to ignore/exceptions file")
    args = parser.parse_args()

    path = Path(args.file)
    valid, errors = verify_exceptions_file(path)

    if not valid:
        print(f"FAILED: {len(errors)} security exception policy violation(s) found in {path}:", file=sys.stderr)
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
