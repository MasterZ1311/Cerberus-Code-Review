"""
SARIF (Static Analysis Results Interchange Format v2.1.0) Serializer for cerberus</>.
Enables native export and integration with GitHub Code Scanning, SonarQube, and Microsoft Security DevOps.
"""

from typing import Any, Dict, List, Optional

from cerberus import __version__
from cerberus.models.schemas import CodeReviewResponse, Finding, SeverityEnum, ZipReviewResponse


def severity_to_sarif_level(severity: SeverityEnum) -> str:
    """Maps Cerberus finding severity to OASIS SARIF level."""
    if severity in (SeverityEnum.CRITICAL, SeverityEnum.HIGH):
        return "error"
    elif severity == SeverityEnum.MEDIUM:
        return "warning"
    else:
        return "note"


def generate_sarif_from_findings(
    findings: List[Finding],
    artifact_uri: str = "snippet.py",
    tool_version: str = __version__,
) -> Dict[str, Any]:
    """Generates standard SARIF 2.1.0 dictionary from a list of findings."""
    rules_map: Dict[str, Dict[str, Any]] = {}
    sarif_results: List[Dict[str, Any]] = []

    for f in findings:
        rule_id = f.cwe_id or f.id or f"CERBERUS-{f.category.upper()}"
        if rule_id not in rules_map:
            level = severity_to_sarif_level(f.severity)
            help_uri = (
                f"https://cwe.mitre.org/data/definitions/{f.cwe_id.replace('CWE-', '')}.html" if f.cwe_id else None
            )
            rule_entry: Dict[str, Any] = {
                "id": rule_id,
                "name": f.title.replace(" ", ""),
                "shortDescription": {"text": f.title},
                "fullDescription": {"text": f.explanation or f.message},
                "defaultConfiguration": {"level": level},
                "properties": {
                    "category": f.category,
                    "severity": f.severity.value,
                    "cvssScore": f.cvss_score,
                    "exploitability": f.exploitability,
                },
            }
            if help_uri:
                rule_entry["helpUri"] = help_uri
            if f.recommendation:
                rule_entry["help"] = {"text": f.recommendation}
            rules_map[rule_id] = rule_entry

        level = severity_to_sarif_level(f.severity)
        line = f.line or 1
        col = f.column or 1

        result_item: Dict[str, Any] = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": f.message or f.title},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": artifact_uri, "uriBaseId": "%SRCROOT%"},
                        "region": {
                            "startLine": line,
                            "startColumn": col,
                            "snippet": {"text": f.code_snippet} if f.code_snippet else None,
                        },
                    }
                }
            ],
        }

        if f.suggestion:
            result_item["fixes"] = [
                {
                    "description": {"text": f.recommendation or "Suggested code remediation"},
                    "fileChanges": [
                        {
                            "artifactLocation": {"uri": artifact_uri},
                            "replacements": [
                                {
                                    "deletedRegion": {"startLine": line, "startColumn": col},
                                    "insertedContent": {"text": f.suggestion},
                                }
                            ],
                        }
                    ],
                }
            ]

        sarif_results.append(result_item)

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "cerberus</>",
                        "version": tool_version,
                        "informationUri": "https://github.com/MasterZ1311/MultiAgent-CodeReview",
                        "rules": list(rules_map.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def review_response_to_sarif(response: CodeReviewResponse, filename: Optional[str] = None) -> Dict[str, Any]:
    """Converts a CodeReviewResponse into full SARIF 2.1.0 report."""
    target_uri = filename or "snippet.py"
    all_findings: List[Finding] = []
    all_findings.extend(response.critical_issues)
    all_findings.extend(response.warnings)
    all_findings.extend(response.suggestions)

    return generate_sarif_from_findings(
        findings=all_findings,
        artifact_uri=target_uri,
    )


def zip_review_response_to_sarif(response: ZipReviewResponse) -> Dict[str, Any]:
    """Converts a multi-file ZipReviewResponse into standard SARIF 2.1.0 report."""
    rules_map: Dict[str, Dict[str, Any]] = {}
    sarif_results: List[Dict[str, Any]] = []

    for file_review in response.file_reviews:
        f_path = file_review.file_path
        fr = file_review.review
        file_findings: List[Finding] = []
        file_findings.extend(fr.critical_issues)
        file_findings.extend(fr.warnings)
        file_findings.extend(fr.suggestions)

        for f in file_findings:
            rule_id = f.cwe_id or f.id or f"CERBERUS-{f.category.upper()}"
            if rule_id not in rules_map:
                level = severity_to_sarif_level(f.severity)
                rule_entry: Dict[str, Any] = {
                    "id": rule_id,
                    "name": f.title.replace(" ", ""),
                    "shortDescription": {"text": f.title},
                    "fullDescription": {"text": f.explanation or f.message},
                    "defaultConfiguration": {"level": level},
                }
                if f.recommendation:
                    rule_entry["help"] = {"text": f.recommendation}
                rules_map[rule_id] = rule_entry

            level = severity_to_sarif_level(f.severity)
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": f.message or f.title},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f_path, "uriBaseId": "%SRCROOT%"},
                                "region": {
                                    "startLine": f.line or 1,
                                    "startColumn": f.column or 1,
                                    "snippet": {"text": f.code_snippet} if f.code_snippet else None,
                                },
                            }
                        }
                    ],
                }
            )

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "cerberus</>",
                        "version": __version__,
                        "informationUri": "https://github.com/MasterZ1311/MultiAgent-CodeReview",
                        "rules": list(rules_map.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def review_response_to_gitlab_code_quality(
    response: CodeReviewResponse, filename: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Exports Cerberus review findings to standard GitLab CI Code Quality JSON format
    (gl-code-quality-report.json) for native GitLab MR diff widget integration.
    """
    import hashlib

    file_path = filename or "snippet.py"
    all_findings = response.critical_issues + response.warnings + response.suggestions
    gl_issues: List[Dict[str, Any]] = []

    for f in all_findings:
        sev_map = {
            SeverityEnum.CRITICAL: "critical",
            SeverityEnum.HIGH: "major",
            SeverityEnum.MEDIUM: "minor",
            SeverityEnum.LOW: "info",
            SeverityEnum.INFO: "info",
        }
        severity_str = sev_map.get(f.severity, "minor")
        line_num = f.line or 1
        fp = hashlib.sha256(
            f"{file_path}:{line_num}:{f.category}:{f.title}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:32]

        gl_issues.append(
            {
                "description": f"{f.title}: {f.message}",
                "check_name": f.cwe_id or f.id or f"cerberus/{f.category}",
                "fingerprint": fp,
                "severity": severity_str,
                "location": {"path": file_path, "lines": {"begin": line_num}},
            }
        )

    return gl_issues


def zip_review_response_to_gitlab_code_quality(response: ZipReviewResponse) -> List[Dict[str, Any]]:
    """Exports full project ZIP archive review to GitLab CI Code Quality JSON format."""
    gl_issues: List[Dict[str, Any]] = []
    for fr in response.file_reviews:
        gl_issues.extend(review_response_to_gitlab_code_quality(fr.review, filename=fr.file_path))
    return gl_issues


def review_response_to_sonarqube(response: CodeReviewResponse, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Exports Cerberus review findings to standard SonarQube Generic Issue Import format
    (sonar-generic-issues.json) for enterprise SonarQube / SonarCloud dashboard ingestion.
    """
    target_file = filename or "snippet.py"
    all_findings = response.critical_issues + response.warnings + response.suggestions
    issues: List[Dict[str, Any]] = []

    sev_map = {
        SeverityEnum.CRITICAL: "BLOCKER",
        SeverityEnum.HIGH: "CRITICAL",
        SeverityEnum.MEDIUM: "MAJOR",
        SeverityEnum.LOW: "MINOR",
        SeverityEnum.INFO: "INFO",
    }
    effort_map = {
        SeverityEnum.CRITICAL: 60,
        SeverityEnum.HIGH: 30,
        SeverityEnum.MEDIUM: 15,
        SeverityEnum.LOW: 5,
        SeverityEnum.INFO: 2,
    }

    for f in all_findings:
        cat = (f.category or "").lower()
        if cat in (
            "security",
            "injection",
            "secrets",
            "cryptography",
            "auth",
            "deserialization",
            "cwe",
            "hipaa",
            "pcidss",
        ):
            issue_type = "VULNERABILITY"
        elif cat in ("performance", "bug", "concurrency", "complexity"):
            issue_type = "BUG"
        else:
            issue_type = "CODE_SMELL"

        line_num = max(1, f.line or 1)
        issues.append(
            {
                "engineId": "cerberus",
                "ruleId": f.cwe_id or f.id or f"CERBERUS-{f.category.upper()}",
                "severity": sev_map.get(f.severity, "MAJOR"),
                "type": issue_type,
                "primaryLocation": {
                    "message": f"{f.title}: {f.message}",
                    "filePath": target_file,
                    "textRange": {
                        "startLine": line_num,
                        "endLine": line_num,
                    },
                },
                "effortMinutes": effort_map.get(f.severity, 15),
            }
        )

    return {"issues": issues}


def zip_review_response_to_sonarqube(response: ZipReviewResponse) -> Dict[str, Any]:
    """Exports full project ZIP archive review to SonarQube Generic Issue Import JSON format."""
    all_issues: List[Dict[str, Any]] = []
    for fr in response.file_reviews:
        file_sonar = review_response_to_sonarqube(fr.review, filename=fr.file_path)
        all_issues.extend(file_sonar.get("issues", []))
    return {"issues": all_issues}
