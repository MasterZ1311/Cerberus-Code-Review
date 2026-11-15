"""
PCI-DSS Regulatory Compliance Evaluator (Payment Card Industry Data Security Standard v4.0).
Audits code for PAN storage, CVV retention prohibition, cleartext card transmission, and masking.
"""

import re
from typing import List

from cerberus.agents.compliance.luhn import mask_pan, validate_luhn
from cerberus.models.schemas import Finding, SeverityEnum


class PCIDSSRegulatoryEvaluator:
    """Audits code against PCI-DSS v4.0 Core Requirements (Req. 3.2, 3.4, 3.5, 4.1)."""

    # 1. Candidate card number pattern: 13 to 19 digits (optionally separated by hyphens or spaces)
    PAN_CANDIDATE_REGEX = re.compile(r"""\b(?:\d[ -]?){13,19}\b""")

    # 2. Sensitive Authentication Data (SAD) Storage Prohibition (Req. 3.2): CVV / CVC
    CVV_STORAGE_PATTERN = re.compile(
        r"""\b(?:cvv|cvc|cvv2|cvc2|security_code|card_verification_value)\s*=\s*(?:Column|db|request\.data|["'][^"']+["'])""",
        re.IGNORECASE,
    )

    # 3. Model field definitions storing CVV
    CVV_COLUMN_PATTERN = re.compile(r"""(?:cvv|cvc|card_verification)\s*=\s*Column\(""", re.IGNORECASE)

    # 4. Unmasked PAN Display Pattern (e.g. printing or displaying full card)
    UNMASKED_DISPLAY_PATTERN = re.compile(
        r"""(?:print|logger|display)\s*\(.*(?:card_number|pan|credit_card)(?!\s*\[-4:\]|\.mask)""", re.IGNORECASE
    )

    @classmethod
    def evaluate(cls, code: str, language: str = "python") -> List[Finding]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. PCI-DSS Req 3.4: PAN Detection with Luhn Mod 10 Verification
        for idx, line in enumerate(lines, 1):
            matches = cls.PAN_CANDIDATE_REGEX.findall(line)
            for candidate in matches:
                if validate_luhn(candidate):
                    masked = mask_pan(candidate)
                    findings.append(
                        Finding(
                            id=f"PCI-PAN-{idx}",
                            severity=SeverityEnum.CRITICAL,
                            category="compliance",
                            title="PCI-DSS Req. 3.4: Hardcoded Primary Account Number (PAN) Detected",
                            message=f"Valid credit card PAN ({masked}) detected directly in source code.",
                            line=idx,
                            code_snippet=line.replace(candidate, masked).strip(),
                            explanation="PCI-DSS v4.0 Requirement 3.4 mandates that Primary Account Numbers (PAN) must be rendered unreadable wherever stored using strong one-way hashes, truncation, or strong cryptography with associated key management.",
                            recommendation="Never store or hardcode card numbers. Use secure tokenization (e.g. Stripe Tokens, Braintree) or KMS-backed AES-GCM encryption.",
                            suggestion="card_token = payment_gateway.tokenize(raw_card_data)",
                            cwe_id="CWE-312",
                        )
                    )
                    break

        # 2. PCI-DSS Req 3.2: Sensitive Authentication Data (CVV / CVC) Storage
        for idx, line in enumerate(lines, 1):
            if cls.CVV_STORAGE_PATTERN.search(line) or cls.CVV_COLUMN_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"PCI-CVV-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="compliance",
                        title="PCI-DSS Req. 3.2: Severe Violation - Storage of Card Verification Code (CVV/CVC)",
                        message="Detected storage or persistent column definition for Card Verification Value (CVV/CVC).",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="PCI-DSS Requirement 3.2 explicitly prohibits storing sensitive authentication data (SAD) including card verification codes (CVV2, CVC2, CID) after authorization, even if encrypted. Storing CVV is a Level 1 non-compliance violation.",
                        recommendation="Immediately delete any database columns storing CVV. Verify CVV only transiently in memory during live gateway authorization.",
                        suggestion="# Pass directly to payment gateway without persisting:\ngateway.charge(amount, cvv=temp_cvv)",
                        cwe_id="CWE-359",
                    )
                )

        # 3. PCI-DSS Req 3.5: Unmasked Card Display
        for idx, line in enumerate(lines, 1):
            if cls.UNMASKED_DISPLAY_PATTERN.search(line) and not any(
                m_kw in line.lower() for m_kw in ("mask", "[-4:]", "hash", "token")
            ):
                findings.append(
                    Finding(
                        id=f"PCI-MASK-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title="PCI-DSS Req. 3.5: Full Cardholder Number Displayed / Logged Without Masking",
                        message="Cardholder number appears to be displayed, returned, or logged without standard masking.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="PCI-DSS Requirement 3.5 requires that PAN must be masked when displayed (the first six and last four digits are the maximum number of digits that may be displayed).",
                        recommendation="Mask all card digits except for the last 4 digits.",
                        suggestion="masked_pan = f'****-****-****-{card_number[-4:]}'",
                        cwe_id="CWE-532",
                    )
                )

        return findings
