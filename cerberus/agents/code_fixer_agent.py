"""
Collaborative Code Fixer Agent (Agent 6).
Synthesizes AST-verified unified diff patches (.patch) resolving findings flagged across
all specialized agents (Security, Performance, Quality, Architecture, Compliance).
"""

import ast
import difflib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from cerberus.agents.ai_helper import parse_llm_json
from cerberus.agents.base import BaseAgent
from cerberus.models.schemas import AgentResult, Finding, SeverityEnum
from cerberus.providers import get_llm_provider
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.agents.code_fixer")


class CodeFixerAgent(BaseAgent):
    name: str = "code_fixer"
    version: str = "1.0.0"
    purpose = "Collaboratively synthesize AST-verified unified diff patches resolving flagged findings"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Multi-Agent Unified Diff Patch (.patch) Generation",
            "Automated Code Repair & Refactoring",
            "AST Syntactic Validity Verification",
            "Cross-Domain Issue Remediation (Security + Performance + Quality + Compliance)",
            "Git-Compatible Unified Diff Emission"
        ]

    def _verify_python_syntax(self, code: str) -> bool:
        """Verifies if repaired code parses without syntax errors."""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def _generate_unified_diff(self, original_code: str, repaired_code: str, filename: str = "repaired_code.py") -> str:
        """Generates standard git-compatible unified diff."""
        orig_lines = original_code.splitlines(keepends=True)
        repaired_lines = repaired_code.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            repaired_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        )
        return "".join(diff)

    def _apply_heuristic_fixes(self, code: str, findings: List[Finding]) -> str:
        """Applies deterministic code repairs using findings' suggested fixes."""
        repaired = code
        lines = repaired.split("\n")

        # Sort findings with line numbers in reverse so editing lines does not offset earlier line indices
        line_findings = [f for f in findings if f.line is not None and f.suggestion]
        line_findings.sort(key=lambda x: x.line or 0, reverse=True)

        for f in line_findings:
            idx = (f.line or 1) - 1
            if 0 <= idx < len(lines):
                # If finding has code_snippet and suggestion
                if f.code_snippet and f.code_snippet.strip() in lines[idx]:
                    indent = len(lines[idx]) - len(lines[idx].lstrip())
                    indent_str = " " * indent
                    lines[idx] = indent_str + f.suggestion.strip()

        candidate = "\n".join(lines)
        if self._verify_python_syntax(candidate):
            return candidate

        return code

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()
        findings: List[Finding] = (context or {}).get("findings", [])
        filename = (context or {}).get("filename", "snippet.py")

        repaired_code = code
        unified_diff = ""

        # 1. First attempt heuristic fixes
        heuristic_repaired = self._apply_heuristic_fixes(code, findings)
        if heuristic_repaired != code:
            repaired_code = heuristic_repaired

        # 2. If AI provider is available, request comprehensive multi-agent refactoring
        provider = self.provider or get_llm_provider(agent_name=self.name)
        if provider and await provider.is_available() and findings:
            try:
                findings_payload = [
                    {
                        "severity": f.severity.value,
                        "category": f.category,
                        "title": f.title,
                        "line": f.line,
                        "code_snippet": f.code_snippet,
                        "recommendation": f.recommendation,
                        "suggestion": f.suggestion
                    }
                    for f in findings[:15]
                ]

                system_prompt = (
                    "[ROLE]: Principal Software Engineer and Automated Code Repair Specialist.\n"
                    "[TASK]: Review all findings identified by the multi-agent panel (Security, Performance, Quality, Architecture, Compliance). "
                    "Generate a clean, complete, fully repaired version of the source code that resolves all flagged issues simultaneously without regressions.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. Ensure repaired_code is syntactically valid.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "repaired_code": "<full clean repaired code>",\n'
                    '  "explanation": "Summary of changes made to fix all agent issues",\n'
                    '  "confidence_score": 0.95\n'
                    "}"
                )

                bounded_code = code[:12000]
                if len(code) > 12000:
                    bounded_code += "\n# ... [Remaining code truncated for LLM context window]"

                user_prompt = (
                    f"Identified Multi-Agent Findings:\n{json.dumps(findings_payload)}\n\n"
                    f"Original {language} Code to Repair:\n```{language}\n{bounded_code}\n```"
                )

                raw_res = await provider.generate_response(system_prompt, user_prompt)
                llm_parsed = parse_llm_json(raw_res)
                if llm_parsed and isinstance(llm_parsed, dict) and "repaired_code" in llm_parsed:
                    candidate_code = str(llm_parsed["repaired_code"]).strip()
                    # Strip any markdown fences if present inside repaired_code string
                    match = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", candidate_code)
                    if match:
                        candidate_code = match.group(1).strip()

                    # Verify syntax
                    if language.lower() == "python":
                        if self._verify_python_syntax(candidate_code):
                            repaired_code = candidate_code
                    else:
                        repaired_code = candidate_code
            except Exception as e:
                logger.warning(f"CodeFixerAgent LLM patch generation failed; keeping heuristic fix: {e}")

        # Compute diff if changes occurred
        if repaired_code and repaired_code != code:
            unified_diff = self._generate_unified_diff(code, repaired_code, filename=filename)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        fix_finding = Finding(
            id="COLLAB-FIXER-001",
            severity=SeverityEnum.INFO,
            category="code_repair",
            title="Automated Multi-Agent Fix Generated" if unified_diff else "No Automated Fix Required",
            message=(
                "Collaborative patch synthesized resolving multi-agent issues."
                if unified_diff else "Code is either clean or no safe automated fix could be determined."
            ),
            suggestion=unified_diff if unified_diff else None,
            recommendation="Review the unified diff patch generated by the Code Fixer Agent before applying."
        )

        return AgentResult(
            name=self.name,
            status="completed",
            score=100.0 if unified_diff else 95.0,
            execution_time_ms=elapsed_ms,
            findings=[fix_finding]
        )

    async def synthesize_fixes(
        self,
        original_code: str,
        findings: List[Finding],
        filename: str = "snippet.py",
        language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method to synthesize repaired code, diff patch, and AST validity."""
        heuristic_repaired = self._apply_heuristic_fixes(original_code, findings)
        diff = ""
        repaired = original_code
        if heuristic_repaired != original_code:
            repaired = heuristic_repaired
            diff = self._generate_unified_diff(original_code, repaired, filename=filename)
        return {
            "patch_applied": bool(diff),
            "unified_diff": diff,
            "repaired_code": repaired,
            "syntax_valid": self._verify_python_syntax(repaired) if language.lower() == "python" else True,
        }

    async def generate_patch(
        self,
        code: str,
        findings: List[Finding],
        filename: str = "snippet.py",
        language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method to generate patch and repaired code."""
        res = await self.analyze(code, language=language, context={"findings": findings, "filename": filename})
        diff = ""
        repaired = code
        heuristic_repaired = self._apply_heuristic_fixes(code, findings)
        if heuristic_repaired != code:
            repaired = heuristic_repaired
            diff = self._generate_unified_diff(code, repaired, filename=filename)
        return {
            "unified_diff": diff,
            "repaired_code": repaired,
            "has_patch": bool(diff)
        }
