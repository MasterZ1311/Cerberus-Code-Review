"""
CCPA / CPRA Regulatory Compliance Evaluator (California Consumer Privacy Act).
Audits code for 'Do Not Sell' opt-out enforcement, third-party data broker sharing, and consumer deletion rights.
"""

import ast
import re
from typing import List

from cerberus.models.schemas import Finding, SeverityEnum


class CCPARegulatoryEvaluator:
    """Audits code against California Consumer Privacy Act (§1798.105, §1798.120)."""

    # Data sale or broker sharing keywords
    DATA_SALE_PATTERN = re.compile(
        r"""\b(?:sell_data\w*|share_with_broker\w*|export_to_advertiser\w*|send_to_ad_network\w*)\s*\(""", re.IGNORECASE
    )

    @classmethod
    def evaluate(cls, code: str, language: str = "python") -> List[Finding]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Check Data Sale/Sharing without Opt-Out Verification (§1798.120)
        for idx, line in enumerate(lines, 1):
            if cls.DATA_SALE_PATTERN.search(line):
                # Verify if opt-out check is present on same line or preceding lines
                has_opt_out = any(
                    "do_not_sell" in lines[p].lower() or "opt_out" in lines[p].lower()
                    for p in range(max(0, idx - 5), idx)
                )
                if not has_opt_out:
                    findings.append(
                        Finding(
                            id=f"CCPA-OPT-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="compliance",
                            title="CCPA §1798.120: Data Sharing with Third-Parties Without Opt-Out Check",
                            message="Consumer personal information appears to be shared with ad networks or data brokers without verifying the consumer's 'Do Not Sell or Share My Personal Info' preference.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="CCPA Section 1798.120 grants California consumers the fundamental right to direct a business that sells or shares personal information about the consumer to third parties not to sell or share their personal data.",
                            recommendation="Verify consumer opt-out status prior to triggering any external data syndication or advertising share.",
                            suggestion="if user.opted_out_of_sale: return\nshare_with_partner(user)",
                            cwe_id="CWE-862",
                        )
                    )

        # 2. AST Check for Consumer Rights Management (Right to Know & Delete)
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name.lower()
                    if "process_ccpa_request" in name or "handle_dsar" in name:
                        body_code = ast.unparse(node) if hasattr(ast, "unparse") else ""
                        if not any(
                            v_kw in body_code.lower() for v_kw in ("verify_identity", "authenticate", "is_verified")
                        ):
                            findings.append(
                                Finding(
                                    id=f"CCPA-VERIFY-{node.lineno}",
                                    severity=SeverityEnum.MEDIUM,
                                    category="compliance",
                                    title=f"CCPA §1798.140: Missing Identity Verification in '{node.name}'",
                                    message="Consumer Data Subject Access Request (DSAR) routine lacks consumer identity verification.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="CCPA regulations require businesses to verify the identity of the consumer submitting a request to know or delete before disclosing or erasing personal information to prevent identity theft.",
                                    recommendation="Assert that the request has passed two-factor authentication or verifiable consumer request checks.",
                                    suggestion="if not verify_consumer_identity(request): raise UnauthorizedException()",
                                    cwe_id="CWE-306",
                                )
                            )
        except Exception:
            pass

        return findings
