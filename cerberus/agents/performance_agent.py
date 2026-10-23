"""
Performance Agent: Specializes in Algorithmic Profiling, Bottlenecks, and Resource Optimization.
Combines deterministic AST / loop analysis heuristics with IBM Granite foundation model reasoning.
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

logger = logging.getLogger("cerberus.agents.performance")


class PerformanceAgent(BaseAgent):
    name = "performance"
    version = "1.2.0"
    purpose = "Detect algorithmic bottlenecks, O(n²) loops, N+1 queries, and memory inefficiencies"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Algorithmic Complexity Analysis (Big-O)",
            "Nested Iteration Detection (O(n²))",
            "Database N+1 Query Antipatterns",
            "String Concatenation Memory Leaks",
            "Caching Opportunity Identification",
            "Estimated Latency Improvement Calculations",
        ]

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()

        # 1. Baseline heuristic analysis
        h_findings, h_score = HeuristicEngine.analyze_performance(code, language=language)

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
                    "[ROLE]: High-Performance Systems Engineer utilizing IBM Granite foundation models.\n"
                    "[TASK]: Analyze the source code for performance bottlenecks: algorithmic complexity issues "
                    "(quadratic O(n²) or cubic O(n³) nested iterations), database N+1 query patterns in loops, "
                    "inefficient string concatenation inside loops, unbounded memory allocations, CPU churn, and missing caching.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "score": 80.0,\n'
                    '  "findings": [\n'
                    "    {\n"
                    '      "severity": "critical|high|medium|low|info",\n'
                    '      "category": "algorithmic_complexity|database_query|memory_churn|caching",\n'
                    '      "title": "Short title",\n'
                    '      "message": "Detailed description of bottleneck",\n'
                    '      "line": 1,\n'
                    '      "code_snippet": "offending code",\n'
                    '      "explanation": "Complexity analysis and scaling impact",\n'
                    '      "recommendation": "Optimization strategy",\n'
                    '      "suggestion": "Optimized replacement code"\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )

                user_prompt = (
                    f"Profile this {language} code for performance bottlenecks and algorithmic efficiency:\n"
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
                logger.warning(f"PerformanceAgent LLM analysis failed; falling back to heuristic engine: {e}")
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
