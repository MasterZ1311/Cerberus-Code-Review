"""
Code Quality Agent: Specializes in Clean Code, Maintainability, and Cognitive Complexity.
Combines deterministic AST heuristics with IBM Granite foundation model reasoning.
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

logger = logging.getLogger("cerberus.agents.quality")


class QualityAgent(BaseAgent):
    name = "quality"
    version = "1.2.0"
    purpose = "Evaluate readability, maintainability, docstring coverage, and clean coding standards"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Docstring Completeness & API Documentation",
            "Cognitive & Cyclomatic Complexity",
            "Long Method & Monolith Detection",
            "Dangerous Bare Except Clauses",
            "Wildcard Import Pollution",
            "Refactoring & Clean Code Suggestions",
        ]

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()

        # 1. Baseline heuristic analysis
        h_findings, h_score = HeuristicEngine.analyze_quality(code, language=language)

        final_findings = h_findings
        final_score = h_score

        # 2. Check if LLM provider is available
        provider = self.provider or get_llm_provider()
        if provider and await provider.is_available():
            try:
                bounded_code = code[:12000]
                if len(code) > 12000:
                    bounded_code += "\n# ... [Remaining code truncated for LLM context window]"

                system_prompt = (
                    "[ROLE]: Clean Code and Software Quality Specialist utilizing IBM Granite foundation models.\n"
                    "[TASK]: Evaluate the source code for maintainability, readability, cognitive/cyclomatic complexity, "
                    "PEP 257 docstring completeness, dangerous bare exceptions, wildcard imports, monolithic functions, "
                    "and clean code standards.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "score": 85.0,\n'
                    '  "findings": [\n'
                    "    {\n"
                    '      "severity": "critical|high|medium|low|info",\n'
                    '      "category": "maintainability|documentation|error_handling|complexity",\n'
                    '      "title": "Short title",\n'
                    '      "message": "Detailed description of quality issue",\n'
                    '      "line": 1,\n'
                    '      "code_snippet": "offending code",\n'
                    '      "explanation": "Why this impacts code quality",\n'
                    '      "recommendation": "Clean code refactoring guidance",\n'
                    '      "suggestion": "Refactored code snippet"\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )

                user_prompt = (
                    f"Analyze this {language} code for clean code practices, maintainability, and code smells:\n"
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
                logger.warning(f"QualityAgent LLM analysis failed; falling back to heuristic engine: {e}")
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
