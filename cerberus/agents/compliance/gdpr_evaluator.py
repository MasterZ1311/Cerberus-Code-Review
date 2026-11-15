"""
GDPR Regulatory Compliance Evaluator (General Data Protection Regulation - EU 2016/679).
Audits code for data minimization, consent verification, right to erasure, and PII hygiene.
"""

import ast
import re
from typing import List

from cerberus.models.schemas import Finding, SeverityEnum


class GDPRRegulatoryEvaluator:
    """Audits code against GDPR Principles (Articles 5, 6, 17, 25, 32)."""

    # Data minimization: SELECT * on personal data tables
    UNBOUNDED_SELECT_PATTERN = re.compile(
        r"""SELECT\s+\*\s+FROM\s+(?:users|customers|employees|accounts|profiles|contacts)\b""", re.IGNORECASE
    )

    # PII in URLs / query params
    PII_IN_URL_PATTERN = re.compile(
        r"""(?:https?://[^\s"']+[?&](?:email|ssn|phone|user_name|full_name)=)""", re.IGNORECASE
    )

    # IP address logging without anonymization / masking
    RAW_IP_LOG_PATTERN = re.compile(
        r"""(?:logger|logging)\.(?:debug|info|warning|warn|error)\s*\(.*(?:client_ip|remote_addr|request\.ip)""",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(cls, code: str, language: str = "python") -> List[Finding]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Data Minimization Check: Article 5(1)(c)
        for idx, line in enumerate(lines, 1):
            if cls.UNBOUNDED_SELECT_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"GDPR-MIN-{idx}",
                        severity=SeverityEnum.MEDIUM,
                        category="compliance",
                        title="GDPR Data Minimization Violation (Unbounded 'SELECT *')",
                        message="Query fetches all personal columns ('SELECT *') from a user-related table.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="GDPR Article 5(1)(c) mandates that personal data shall be adequate, relevant, and limited to what is necessary in relation to the purposes for which they are processed.",
                        recommendation="Explicitly enumerate only the specific columns required for this operation.",
                        suggestion="SELECT id, email, created_at FROM users WHERE id = :id",
                        cwe_id="CWE-200",
                    )
                )

        # 2. PII in Query Parameters: Article 25 (Privacy by Design)
        for idx, line in enumerate(lines, 1):
            if cls.PII_IN_URL_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"GDPR-URL-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title="GDPR Violation: Plaintext PII in URL Query Parameters",
                        message="Personal Identifiable Information (PII) is passed in HTTP URL parameters.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="URLs are routinely cached by browser histories, proxy servers, and access logs. Passing PII in query strings violates Article 25 and 32 confidentiality safeguards.",
                        recommendation="Pass sensitive identifiers in encrypted POST/PUT request bodies or authorization headers.",
                        suggestion="requests.post(url, json={'email': user_email})",
                        cwe_id="CWE-598",
                    )
                )

        # 3. Raw IP Address Logging: Article 4(1)
        for idx, line in enumerate(lines, 1):
            if cls.RAW_IP_LOG_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"GDPR-IP-{idx}",
                        severity=SeverityEnum.LOW,
                        category="compliance",
                        title="GDPR Personal Data: Raw IP Address Logged Without Anonymization",
                        message="Full client IP address logged directly. Under GDPR (Breyer case C-582/14), dynamic IP addresses are classified as personal data.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="IP addresses identify natural persons and must be pseudonymized or truncated before storage in non-temporary application logs.",
                        recommendation="Mask the last octet of IPv4 addresses or anonymize using a one-way salt hash.",
                        suggestion="logger.info('Access from: %s', anonymize_ip(request.client.host))",
                        cwe_id="CWE-359",
                    )
                )

        # 4. AST Analysis for Consent and Erasure
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name.lower()

                    # Tracking without consent verification
                    if any(t_kw in name for t_kw in ("track_user", "send_analytics", "log_activity", "profile_user")):
                        code_body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                        if not any(
                            c_kw in code_body for c_kw in ("consent", "opt_in", "user_permission", "is_allowed")
                        ):
                            findings.append(
                                Finding(
                                    id=f"GDPR-CONSENT-{node.lineno}",
                                    severity=SeverityEnum.HIGH,
                                    category="compliance",
                                    title=f"GDPR Article 6: Tracking Routine Lacks Consent Verification on '{node.name}'",
                                    message="Telemetry/analytics routine processes user behavior without asserting prior opt-in consent.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="GDPR Article 6(1)(a) requires that the data subject has given consent to the processing of their personal data for one or more specific purposes.",
                                    recommendation="Wrap tracking routines with a consent verification check.",
                                    suggestion="if not user.has_consent('analytics'): return",
                                    cwe_id="CWE-862",
                                )
                            )

                    # Deletion handler that fails to scrub personal data (Article 17 Right to Erasure)
                    if any(d_kw in name for d_kw in ("delete_user", "remove_account", "erase_profile")):
                        code_body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                        if "is_deleted = true" in code_body.lower() and not any(
                            a_kw in code_body.lower()
                            for a_kw in ("anonymize", "scrub", "purge", "hard_delete", "cascade")
                        ):
                            findings.append(
                                Finding(
                                    id=f"GDPR-ERASURE-{node.lineno}",
                                    severity=SeverityEnum.MEDIUM,
                                    category="compliance",
                                    title=f"GDPR Article 17: Incomplete Erasure in '{node.name}' (Soft-delete only)",
                                    message="User deletion marks account as inactive without scrubbing or purging PII.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="Article 17 gives data subjects the Right to Erasure ('Right to be Forgotten'). Retaining un-anonymized PII permanently post-deletion request violates the regulation.",
                                    recommendation="Anonymize personal fields (name, email, address) upon account closure.",
                                    suggestion="user.email = f'deleted_{user.id}@anonymized.local'\nuser.name = 'Deleted User'",
                                    cwe_id="CWE-459",
                                )
                            )
        except Exception:
            pass

        return findings
