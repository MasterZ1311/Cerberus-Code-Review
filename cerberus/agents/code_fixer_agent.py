"""
Collaborative Code Fixer Agent (Agent 6).
Synthesizes AST-verified unified diff patches (.patch) resolving findings flagged across
all specialized agents (Security, Performance, Quality, Architecture, Compliance).
"""

import difflib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from cerberus.agents.ai_helper import parse_llm_json
from cerberus.agents.base import BaseAgent
from cerberus.core.patch_verifier import PatchVerificationPipeline
from cerberus.core.syntax_verifier import SyntaxVerifier
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
            "Git-Compatible Unified Diff Emission",
        ]

    def _verify_syntax(self, code: str, language: str = "python") -> bool:
        """Verifies if repaired code parses without syntax errors across supported languages."""
        valid, _ = SyntaxVerifier.verify(code, language=language)
        return valid

    def _verify_python_syntax(self, code: str) -> bool:
        """Verifies if repaired code parses without syntax errors (backward compatibility)."""
        return self._verify_syntax(code, language="python")

    def _generate_unified_diff(self, original_code: str, repaired_code: str, filename: str = "repaired_code.py") -> str:
        """Generates standard git-compatible unified diff."""
        orig_lines = original_code.splitlines(keepends=False)
        repaired_lines = repaired_code.splitlines(keepends=False)
        diff = difflib.unified_diff(
            orig_lines, repaired_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm=""
        )
        diff_list = list(diff)
        if not diff_list:
            return ""
        return "\n".join(diff_list) + "\n"

    def _apply_language_specific_repairs(
        self, code: str, language: str = "python", findings: Optional[List[Finding]] = None
    ) -> str:
        """Applies multi-language AST-guided code transformations for Python, TypeScript, Go, and Rust."""
        lang = (language or "python").lower()
        repaired = code

        # 1. Python AST / Pattern Transformations
        if lang in ("python", "py"):
            # Transform bare except: -> except Exception:
            repaired = re.sub(
                r"^\s*except\s*:",
                lambda m: m.group(0).replace("except:", "except Exception:"),
                repaired,
                flags=re.MULTILINE,
            )

        # 2. TypeScript & JavaScript Transformations
        elif lang in ("typescript", "ts", "tsx", "javascript", "js", "jsx"):
            # Transform loose equality == / != to strict === / !== where appropriate
            for f in findings or []:
                if f.category in ("quality", "security") and (
                    "equality" in f.title.lower() or "===" in (f.suggestion or "")
                ):
                    if f.line and f.line <= len(repaired.split("\n")):
                        lines = repaired.split("\n")
                        target_line = lines[f.line - 1]
                        replaced_line = re.sub(r"(?<!=)==(?!=)", "===", target_line)
                        replaced_line = re.sub(r"!=([^=])", r"!==\1", replaced_line)
                        lines[f.line - 1] = replaced_line
                        candidate = "\n".join(lines)
                        if self._verify_syntax(candidate, language=lang):
                            repaired = candidate

        # 3. Go Error Handling Transformations
        elif lang in ("go", "golang"):
            for f in findings or []:
                if "error" in f.title.lower() and f.suggestion and f.line:
                    lines = repaired.split("\n")
                    if 0 < f.line <= len(lines):
                        indent = len(lines[f.line - 1]) - len(lines[f.line - 1].lstrip())
                        ind_str = " " * indent
                        replacement = "\n".join(ind_str + sl.strip() for sl in f.suggestion.splitlines())
                        lines[f.line - 1] = replacement
                        candidate = "\n".join(lines)
                        if self._verify_syntax(candidate, language=lang):
                            repaired = candidate

        # 4. Rust Panic / Unwrap Safety Transformations
        elif lang in ("rust", "rs"):
            for f in findings or []:
                if "unwrap" in f.title.lower() and f.suggestion and f.line:
                    lines = repaired.split("\n")
                    if 0 < f.line <= len(lines):
                        if ".unwrap()" in lines[f.line - 1]:
                            lines[f.line - 1] = lines[f.line - 1].replace(".unwrap()", f.suggestion.strip())
                            candidate = "\n".join(lines)
                            if self._verify_syntax(candidate, language=lang):
                                repaired = candidate

        return repaired

    def _apply_heuristic_fixes(self, code: str, findings: List[Finding], language: str = "python") -> str:
        """Applies deterministic code repairs using findings' suggested fixes across multiple languages."""
        lines = code.split("\n")

        # Sort findings with line numbers in reverse so editing lines does not offset earlier line indices
        line_findings = [f for f in findings if f.line is not None and f.suggestion]
        line_findings.sort(key=lambda x: x.line or 0, reverse=True)

        for f in line_findings:
            idx = (f.line or 1) - 1
            if 0 <= idx < len(lines):
                indent = len(lines[idx]) - len(lines[idx].lstrip())
                indent_str = " " * indent
                sugg_lines = (f.suggestion or "").strip().splitlines()
                indented_sugg = [indent_str + sl for sl in sugg_lines]
                replacement = "\n".join(indented_sugg)

                # Incremental syntactic verification
                temp_lines = list(lines)
                temp_lines[idx] = replacement
                candidate = "\n".join(temp_lines)
                if self._verify_syntax(candidate, language=language):
                    lines[idx] = replacement

        candidate = "\n".join(lines)
        # Apply language-specific semantic improvements
        candidate = self._apply_language_specific_repairs(candidate, language=language, findings=findings)

        if self._verify_syntax(candidate, language=language):
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
        heuristic_repaired = self._apply_heuristic_fixes(code, findings, language=language)
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
                        "suggestion": f.suggestion,
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
                    if self._verify_syntax(candidate_code, language=language):
                        repaired_code = candidate_code
            except Exception as e:
                logger.warning(f"CodeFixerAgent LLM patch generation failed; keeping heuristic fix: {e}")

        # Multi-Stage In-Memory Patch Verification Pipeline
        verification = PatchVerificationPipeline.verify_patch(
            original_code=code,
            repaired_code=repaired_code,
            language=language,
            filename=filename,
            original_findings=findings,
        )

        if not verification.is_valid:
            logger.warning(
                f"Patch verification failed at stage '{verification.stage}': {verification.explanation}. Reverting to safe code."
            )
            repaired_code = code
            unified_diff = ""
        else:
            unified_diff = verification.patch_diff or ""

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        fix_finding = Finding(
            id="COLLAB-FIXER-001",
            severity=SeverityEnum.INFO,
            category="code_repair",
            title="Automated Multi-Agent Fix Generated" if unified_diff else "No Automated Fix Required",
            message=(
                f"Collaborative patch synthesized and verified (Stage: {verification.stage.value}). "
                f"{verification.explanation}"
                if unified_diff
                else "Code is either clean or no safe automated fix could be determined."
            ),
            suggestion=unified_diff if unified_diff else None,
            recommendation="Review the unified diff patch generated by the Code Fixer Agent before applying.",
        )

        return AgentResult(
            name=self.name,
            status="completed",
            score=100.0 if unified_diff else 95.0,
            execution_time_ms=elapsed_ms,
            findings=[fix_finding],
        )

    def generate_pr_review_comments(
        self, findings: List[Finding], filename: str = "snippet.py"
    ) -> List[Dict[str, Any]]:
        """
        Formats findings into standard GitHub Pull Request review comment payloads.
        Ready for GitHub PR Review Comments API (POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews).
        """
        comments: List[Dict[str, Any]] = []
        for f in findings:
            if f.line is not None:
                body = f"### [{f.severity.value.upper()}] {f.title}\n\n{f.message}"
                if f.explanation:
                    body += f"\n\n**Why this matters:** {f.explanation}"
                if f.recommendation:
                    body += f"\n\n> 💡 **Recommendation:** {f.recommendation}"
                if f.suggestion:
                    body += f"\n\n```suggestion\n{f.suggestion}\n```"
                comments.append(
                    {
                        "path": filename,
                        "line": f.line,
                        "side": "RIGHT",
                        "body": body,
                    }
                )
        return comments

    async def synthesize_fixes(
        self, original_code: str, findings: List[Finding], filename: str = "snippet.py", language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method to synthesize repaired code, diff patch, and syntactic validity."""
        heuristic_repaired = self._apply_heuristic_fixes(original_code, findings, language=language)
        diff = ""
        repaired = original_code
        if heuristic_repaired != original_code:
            repaired = heuristic_repaired
            diff = self._generate_unified_diff(original_code, repaired, filename=filename)
        return {
            "patch_applied": bool(diff),
            "unified_diff": diff,
            "repaired_code": repaired,
            "syntax_valid": self._verify_syntax(repaired, language=language),
        }

    async def generate_patch(
        self, code: str, findings: List[Finding], filename: str = "snippet.py", language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method to generate patch and repaired code."""
        _ = await self.analyze(code, language=language, context={"findings": findings, "filename": filename})
        diff = ""
        repaired = code
        heuristic_repaired = self._apply_heuristic_fixes(code, findings, language=language)
        if heuristic_repaired != code:
            repaired = heuristic_repaired
            diff = self._generate_unified_diff(code, repaired, filename=filename)
        return {"unified_diff": diff, "repaired_code": repaired, "has_patch": bool(diff)}
