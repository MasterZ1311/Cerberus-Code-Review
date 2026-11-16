"""
Custom Secret Scanner Plugin for cerberus</>.
Demonstrates plugin extension adding high-entropy secret detection rules across languages.
"""

from typing import Any, Dict, List

from cerberus.core.plugins import BasePlugin


class CustomSecretScannerPlugin(BasePlugin):
    name: str = "secret_scanner"
    version: str = "1.1.0"
    description: str = "Enhanced cloud provider credential & token scanner"
    author: str = "Cerberus Security Engineering"
    is_enabled: bool = True

    def get_custom_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "python": [
                {
                    "id": "SEC-CUSTOM-AWS-KEY",
                    "pattern": r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}",
                    "severity": "CRITICAL",
                    "category": "secrets",
                    "title": "AWS Access Key ID Hardcoded",
                    "message": "AWS Access Key ID pattern detected in source code.",
                    "explanation": "Hardcoded AWS credentials allow unauthorized access to cloud resources.",
                    "recommendation": "Rotate compromised AWS key immediately and inject credentials via AWS IAM Roles or Secrets Manager.",
                    "cwe_id": "CWE-798",
                    "cvss_score": 9.8,
                },
                {
                    "id": "SEC-CUSTOM-SLACK-TOKEN",
                    "pattern": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
                    "severity": "CRITICAL",
                    "category": "secrets",
                    "title": "Slack API Token Hardcoded",
                    "message": "Slack API token pattern detected in source code.",
                    "recommendation": "Revoke token and retrieve via environment variables.",
                    "cwe_id": "CWE-798",
                    "cvss_score": 9.1,
                },
            ],
            "typescript": [
                {
                    "id": "SEC-CUSTOM-GITHUB-TOKEN",
                    "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,255}",
                    "severity": "CRITICAL",
                    "category": "secrets",
                    "title": "GitHub Personal Access Token Hardcoded",
                    "message": "GitHub PAT detected in TypeScript source.",
                    "recommendation": "Revoke PAT and use GitHub Actions secrets or vault.",
                    "cwe_id": "CWE-798",
                    "cvss_score": 9.5,
                }
            ],
        }


# Alias for backward compatibility & testing
SecretScannerPlugin = CustomSecretScannerPlugin
