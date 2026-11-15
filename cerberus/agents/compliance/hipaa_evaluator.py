"""
HIPAA Regulatory Compliance Evaluator (Health Insurance Portability and Accountability Act).
Audits code for PHI exposure, in-transit encryption, audit controls, and cipher standards.
"""

import ast
import re
from typing import List

from cerberus.models.schemas import Finding, SeverityEnum


class HIPAARegulatoryEvaluator:
    """Audits code against HIPAA Security Rule 45 CFR Part 164 Subpart C."""

    # 1. PHI Identifiers
    PHI_PATTERNS = [
        (
            r"""\b(?:medical_record_number|mrn|patient_id|patient_name|patient_dob|date_of_birth)\b""",
            "Direct Patient Identifier (MRN / Name / DOB)",
        ),
        (
            r"""\b(?:diagnosis_code|patient_diagnosis|icd9|icd10|icd_code|medical_history|health_condition)\b""",
            "Medical Condition / Diagnostic Data",
        ),
        (
            r"""\b(?:prescription|rx_number|medication_name|dosage_mg|ndc_code)\b""",
            "Prescription / Pharmacy Data (e-Prescribing)",
        ),
        (
            r"""\b(?:health_plan_id|insurance_policy_number|beneficiary_number)\b""",
            "Health Plan Beneficiary Identifier",
        ),
    ]

    # 2. In-transit Cleartext HTTP
    CLEARTEXT_HTTP_PATTERN = re.compile(r"""["']http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[a-zA-Z0-9\.\-_]+""")

    # 3. Weak Hashes/Ciphers
    WEAK_CRYPTO_PATTERNS = [
        (r"""hashlib\.md5\s*\(""", "MD5 Cryptographic Hash"),
        (r"""hashlib\.sha1\s*\(""", "SHA-1 Cryptographic Hash"),
        (r"""(?:DES|Blowfish|ARC4|RC4)\.new\s*\(""", "Deprecated Broken Symmetric Cipher"),
    ]

    # 4. Sensitive Logging
    PHI_LOG_PATTERN = re.compile(
        r"""(?:logger|logging|log)\.(?:debug|info|warning|warn|error|critical)\s*\(.*(?:patient|diagnosis|prescription|mrn|medical_record|health_plan)""",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(cls, code: str, language: str = "python") -> List[Finding]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Check for PHI variable exposures in plaintext models/variables
        for idx, line in enumerate(lines, 1):
            for pat, desc in cls.PHI_PATTERNS:
                if re.search(pat, line, re.IGNORECASE):
                    # Check if it's plaintext string assignment or unencrypted schema field
                    if re.search(r"""=\s*["'][^"']+["']""", line) or "Column(" in line:
                        findings.append(
                            Finding(
                                id=f"HIPAA-PHI-{idx}",
                                severity=SeverityEnum.HIGH,
                                category="compliance",
                                title=f"HIPAA PHI Exposure: {desc}",
                                message=f"Detected unencrypted Protected Health Information (PHI) field: {desc}.",
                                line=idx,
                                code_snippet=line.strip(),
                                explanation="HIPAA §164.312(a)(2)(iv) mandates that electronic Protected Health Information (ePHI) at rest must be encrypted using NIST-approved algorithms.",
                                recommendation="Encrypt sensitive health data before persistence or transport using AES-256-GCM.",
                                suggestion="# Encrypt field value with KMS or Fernet:\npatient_data = encrypt_phi(raw_patient_data)",
                                cwe_id="CWE-311",
                            )
                        )
                        break

        # 2. Check for In-Transit Cleartext HTTP
        for idx, line in enumerate(lines, 1):
            if cls.CLEARTEXT_HTTP_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"HIPAA-TRANSIT-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="compliance",
                        title="HIPAA In-Transit Encryption Violation (Cleartext HTTP)",
                        message="Cleartext HTTP endpoint detected for remote transmission of potential healthcare data.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="HIPAA §164.312(e)(1) requires transmission security with technical encryption mechanisms to guard against unauthorized access over electronic networks.",
                        recommendation="Enforce HTTPS/TLS 1.3 for all external communication.",
                        suggestion=line.strip().replace("http://", "https://"),
                        cwe_id="CWE-319",
                    )
                )

        # 3. Check for Weak Ciphers
        for idx, line in enumerate(lines, 1):
            for pat, desc in cls.WEAK_CRYPTO_PATTERNS:
                if re.search(pat, line):
                    findings.append(
                        Finding(
                            id=f"HIPAA-CRYPTO-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="compliance",
                            title=f"HIPAA Insecure Cipher Standard: {desc}",
                            message=f"{desc} does not satisfy HIPAA/NIST encryption requirements.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="HIPAA Security Series requires encryption conforming to NIST Special Publication 800-52/800-175B. MD5 and legacy ciphers are strictly prohibited.",
                            recommendation="Use SHA-256/SHA-512 for cryptographic hashing and AES-256 for data encryption.",
                            suggestion="hashlib.sha256(data.encode()).hexdigest()",
                            cwe_id="CWE-327",
                        )
                    )

        # 4. Check for PHI in Application Logs
        for idx, line in enumerate(lines, 1):
            if cls.PHI_LOG_PATTERN.search(line):
                findings.append(
                    Finding(
                        id=f"HIPAA-LOG-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title="HIPAA Violation: PHI Emitted in Application Logs",
                        message="Protected Health Information or diagnostic data is being emitted to application logs.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="HIPAA §164.530(c) requires safeguarding ePHI from incidental disclosures. Emitting health identifiers in logs exposes patient privacy to system administrators and log aggregator services.",
                        recommendation="Redact or mask sensitive patient attributes before logging.",
                        suggestion="logger.info('Processed patient record: %s', mask_identifier(patient_id))",
                        cwe_id="CWE-532",
                    )
                )

        # 5. AST Check for Medical Record Retrieval lacking Audit Logs
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_name = node.name.lower()
                    if any(
                        kw in func_name for kw in ("get_patient", "fetch_patient", "get_medical_record", "view_record")
                    ):
                        code_body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                        if not any(audit_kw in code_body for audit_kw in ("audit", "log_access", "record_access")):
                            findings.append(
                                Finding(
                                    id=f"HIPAA-AUDIT-{node.lineno}",
                                    severity=SeverityEnum.MEDIUM,
                                    category="compliance",
                                    title=f"HIPAA Audit Controls Missing on '{node.name}'",
                                    message="Function accesses electronic medical records without generating an access audit log.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="HIPAA §164.312(b) requires audit controls that record and examine access and other activity in information systems that contain or use ePHI.",
                                    recommendation="Invoke a compliance audit logger recording who accessed the record, when, and the patient ID.",
                                    suggestion="audit_log.record(user=current_user, action='read_phi', patient_id=patient_id)",
                                    cwe_id="CWE-778",
                                )
                            )
        except Exception:
            pass

        return findings
