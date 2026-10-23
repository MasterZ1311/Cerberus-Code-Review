"""
Security Agent: Specializes in Threat Modeling, Vulnerability Detection, and OWASP Compliance.
Combines deterministic AST / regex heuristics with IBM Granite foundation model reasoning.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from cerberus.agents.ai_helper import (
    build_findings_from_llm,
    compute_composite_score,
    merge_findings,
    parse_llm_json,
)
from cerberus.agents.base import BaseAgent
from cerberus.models.schemas import AgentResult
from cerberus.providers import get_llm_provider
from cerberus.providers.base import BaseLLMProvider
from cerberus.providers.heuristic_engine import HeuristicEngine

logger = logging.getLogger("cerberus.agents.security")


class SecurityAgent(BaseAgent):
    name = "security"
    version = "1.3.0"
    purpose = "Identify security vulnerabilities, secrets leakage, injection flaws, and CVSS risks"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "SQL Injection Detection (CWE-89)",
            "Command Injection (CWE-78)",
            "Hardcoded Credentials & API Secrets (CWE-798)",
            "Weak Cryptographic Algorithms (CWE-328)",
            "Insecure Object Deserialization (CWE-502)",
            "CVSS 3.1 Severity Scoring",
            "OWASP Top 10 Threat Analysis",
            "Exploitability Probability Estimation",
        ]

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()

        # 1. Always execute baseline deterministic heuristic & AST rules
        h_findings, h_score = HeuristicEngine.analyze_security(code, language=language)

        final_findings = h_findings
        final_score = h_score

        # 2. Check if LLM foundation model provider is configured & available
        provider = self.provider or get_llm_provider()
        if provider and await provider.is_available():
            try:
                bounded_code = code[:12000]
                if len(code) > 12000:
                    bounded_code += "\n# ... [Remaining code truncated for LLM context window]"

                system_prompt = (
                    "[ROLE]: Enterprise Application Security Specialist utilizing IBM Granite foundation models.\n"
                    "[TASK]: Deeply analyze the provided source code for security vulnerabilities: injection flaws "
                    "(SQLi, Command Injection, XSS, Path Traversal), hardcoded credentials/secrets/API keys, weak "
                    "cryptography/hashing, insecure deserialization, broken authentication/authorization, and OWASP Top 10.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "score": 85.0,\n'
                    '  "findings": [\n'
                    "    {\n"
                    '      "severity": "critical|high|medium|low|info",\n'
                    '      "category": "injection|secrets|cryptography|auth|deserialization",\n'
                    '      "title": "Short title",\n'
                    '      "message": "Detailed description of vulnerability",\n'
                    '      "line": 1,\n'
                    '      "code_snippet": "offending line",\n'
                    '      "explanation": "Why this vulnerability matters",\n'
                    '      "recommendation": "How to fix it securely",\n'
                    '      "suggestion": "Safe replacement code",\n'
                    '      "cwe_id": "CWE-89",\n'
                    '      "cvss_score": 9.8\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )

                user_prompt = (
                    f"Review this {language} code for security flaws and vulnerabilities:\n"
                    f"```{language}\n"
                    f"{bounded_code}\n"
                    f"```"
                )

                raw_response = await provider.generate_response(system_prompt, user_prompt)
                llm_data = parse_llm_json(raw_response)

                if llm_data and isinstance(llm_data, dict):
                    raw_findings = llm_data.get("findings", [])
                    ai_findings = build_findings_from_llm(raw_findings, self.name, code)
                    final_findings = merge_findings(h_findings, ai_findings)
                    final_score = compute_composite_score(
                        final_findings,
                        llm_score=llm_data.get("score"),
                        heuristic_score=h_score,
                    )
            except Exception as e:
                logger.warning(f"SecurityAgent LLM analysis failed; falling back to heuristic engine: {e}")
                final_findings = h_findings
                final_score = h_score

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return AgentResult(
            name=self.name,
            status="completed",
            score=round(final_score, 1),
            execution_time_ms=elapsed_ms,
            findings=final_findings,
        )
