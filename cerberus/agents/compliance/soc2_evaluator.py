"""
SOC 2 Compliance Evaluator (AICPA Trust Services Criteria: Security, Confidentiality, Availability).
Audits code for access controls, credential hygiene, logging integrity, and exception leakage.
"""

import ast
import re
from typing import List

from cerberus.models.schemas import Finding, SeverityEnum


class SOC2RegulatoryEvaluator:
    """Audits code against SOC 2 Trust Services Criteria (CC6.1, CC6.6, CC7.1, CC7.2)."""

    # 1. Hardcoded Secrets & Master Credentials (CC6.1)
    SECRET_PATTERNS = [
        (
            r"""(?:jwt_secret|private_key|master_key|api_secret|api_key|secret_key|auth_token)\s*=\s*["'][A-Za-z0-9_\-\.]{12,}["']""",
            "Hardcoded Master Secret or Private Key",
        ),
        (r"""(?:admin_password|root_password|password)\s*=\s*["'][^"']+["']""", "Hardcoded Administrative Credential"),
    ]

    # 2. Plaintext Credential Logging (CC7.2)
    CRED_LOG_PATTERN = re.compile(
        r"""(?:logger|logging|log)\.(?:debug|info|warning|warn|error|critical)\s*\(.*(?:password|token|secret|jwt|bearer|auth_header)""",
        re.IGNORECASE,
    )

    # 3. Stack Trace Leakage to Clients (CC7.1)
    TRACEBACK_LEAK_PATTERN = re.compile(
        r"""return\s+.*(?:traceback\.format_exc\(\)|str\(\s*e\s*\)|detail\s*=\s*str\(\s*e\s*\))""", re.IGNORECASE
    )

    # 4. Insecure Permissive CORS / Debug Mode (CC6.6)
    DEBUG_MODE_PATTERN = re.compile(r"""\bDEBUG\s*=\s*True\b""")
    WILDCARD_CORS_PATTERN = re.compile(r"""allow_origins\s*=\s*\[\s*["']\*["']\s*\]""")

    @classmethod
    def evaluate(cls, code: str, language: str = "python") -> List[Finding]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Check Hardcoded Secrets (CC6.1 Logical Access Controls)
        for idx, line in enumerate(lines, 1):
            for pat, desc in cls.SECRET_PATTERNS:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append(
                        Finding(
                            id=f"SOC2-KEY-{idx}",
                            severity=SeverityEnum.CRITICAL,
                            category="compliance",
                            title=f"SOC 2 CC6.1 Violation: {desc}",
                            message=f"{desc} identified in source code repository.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="SOC 2 Trust Services Criterion CC6.1 mandates that logical access to system components must be secured via dynamic secret vaults (e.g. AWS Secrets Manager, HashiCorp Vault).",
                            recommendation="Store secrets outside version control and load via secure environment variables or vault clients.",
                            suggestion="SECRET_KEY = os.environ['APP_SECRET_KEY']",
                            cwe_id="CWE-798",
                        )
                    )

        # 2. Check Plaintext Credential Logging (CC7.2 Monitoring & Integrity)
        for idx, line in enumerate(lines, 1):
            if cls.CRED_LOG_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"SOC2-LOG-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title="SOC 2 CC7.2: Sensitive Authentication Token/Credential in Logs",
                        message="Credentials, bearer tokens, or secrets are being formatted directly into application logs.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="SOC 2 Common Criteria 7.2 requires that security events and logs are monitored and protected from data pollution that exposes authentication secrets to centralized log stores.",
                        recommendation="Mask tokens or hash values before logging.",
                        suggestion="logger.info('User authenticated successfully')",
                        cwe_id="CWE-532",
                    )
                )

        # 3. Stack Trace Leakage to Clients (CC7.1 Confidentiality Safeguards)
        for idx, line in enumerate(lines, 1):
            if cls.TRACEBACK_LEAK_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"SOC2-LEAK-{idx}",
                        severity=SeverityEnum.MEDIUM,
                        category="compliance",
                        title="SOC 2 CC7.1: Internal Exception Stack Trace Returned to Client",
                        message="Raw exception details or tracebacks are being passed directly to API client responses.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Leaking internal stack traces discloses system file paths, database schemas, and library versions to unauthorized third parties.",
                        recommendation="Log the full error internally and return a generic sanitized error code (e.g., HTTP 500: Internal Server Error).",
                        suggestion="raise HTTPException(status_code=500, detail='An internal error occurred. Ref: ' + trace_id)",
                        cwe_id="CWE-209",
                    )
                )

        # 4. Insecure Configuration (CC6.6 Boundary Security)
        for idx, line in enumerate(lines, 1):
            if cls.DEBUG_MODE_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"SOC2-DEBUG-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title="SOC 2 CC6.6: Production Debug Mode Enabled",
                        message="Application configuration sets 'DEBUG = True'.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Enabling debug mode in production environments exposes interactive debuggers, memory inspectors, and verbose internal states.",
                        recommendation="Ensure DEBUG is loaded dynamically from environment variables with a default of False.",
                        suggestion="DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'",
                        cwe_id="CWE-489",
                    )
                )
            if cls.WILDCARD_CORS_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"SOC2-CORS-{idx}",
                        severity=SeverityEnum.MEDIUM,
                        category="compliance",
                        title="SOC 2 CC6.6: Permissive Wildcard CORS Origin ('*')",
                        message="Cross-Origin Resource Sharing (CORS) configured with wildcard allow_origins=['*'].",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Wildcard CORS permits arbitrary untrusted web domains to make credentialed cross-origin requests to internal endpoints.",
                        recommendation="Explicitly list authorized production domain origins.",
                        suggestion="allow_origins=['https://app.company.com', 'https://portal.company.com']",
                        cwe_id="CWE-942",
                    )
                )

        # 5. AST Check for Sensitive Administrative Routes lacking RBAC / Auth Decorators
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name.lower()
                    if any(
                        adm in name
                        for adm in (
                            "admin_reset",
                            "delete_all",
                            "update_privileges",
                            "change_user_role",
                            "purge_database",
                        )
                    ):
                        decorator_names = []
                        for dec in node.decorator_list:
                            if isinstance(dec, ast.Name):
                                decorator_names.append(dec.id.lower())
                            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                                decorator_names.append(dec.func.id.lower())
                            elif isinstance(dec, ast.Attribute):
                                decorator_names.append(dec.attr.lower())

                        if not any(
                            auth_kw in d
                            for d in decorator_names
                            for auth_kw in ("auth", "role", "permission", "security", "require")
                        ):
                            findings.append(
                                Finding(
                                    id=f"SOC2-RBAC-{node.lineno}",
                                    severity=SeverityEnum.HIGH,
                                    category="compliance",
                                    title=f"SOC 2 CC6.1: Administrative Action '{node.name}' Lacks Access Control Decorator",
                                    message="Privileged administrative function has no explicit authorization or role-verification decorator.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="SOC 2 CC6.1 requires establishing role-based access control (RBAC) to ensure only authorized system administrators can invoke high-privilege operations.",
                                    recommendation="Decorate the function with `@require_role('admin')` or a dependency verifying administrative permissions.",
                                    suggestion="@require_role('admin')\ndef " + node.name + "(...):",
                                    cwe_id="CWE-285",
                                )
                            )
        except Exception:
            pass

        return findings
