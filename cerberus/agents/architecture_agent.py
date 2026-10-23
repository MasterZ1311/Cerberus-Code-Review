"""
Architecture Agent: Specializes in Modular Design, Coupling, and Anti-Patterns.
Combines deterministic AST import graph heuristics with IBM Granite foundation model reasoning.
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

logger = logging.getLogger("cerberus.agents.architecture")


class ArchitectureAgent(BaseAgent):
    name = "architecture"
    version = "1.1.0"
    purpose = "Validate system architecture, module coupling, and structural anti-patterns"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Deep Coupling & Relative Import Detection",
            "Cyclic Dependency Risk Analysis",
            "Single Responsibility Principle (SRP) Verification",
            "Architectural Modularity Scoring",
        ]

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()

        # 1. Baseline heuristic analysis
        h_findings, h_score = HeuristicEngine.analyze_architecture(code, language=language)

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
                    "[ROLE]: Enterprise Software Architect utilizing IBM Granite foundation models.\n"
                    "[TASK]: Analyze the source code for architectural anti-patterns, module coupling, "
                    "Single Responsibility Principle (SRP) violations, circular dependency risks, "
                    "deep relative imports, and structural layer integrity.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "score": 90.0,\n'
                    '  "findings": [\n'
                    "    {\n"
                    '      "severity": "critical|high|medium|low|info",\n'
                    '      "category": "modularity|coupling|dependency|architecture",\n'
                    '      "title": "Short title",\n'
                    '      "message": "Detailed description of architectural flaw",\n'
                    '      "line": 1,\n'
                    '      "code_snippet": "offending code",\n'
                    '      "explanation": "Architectural impact and maintainability risk",\n'
                    '      "recommendation": "Decoupling or architectural guidance",\n'
                    '      "suggestion": "Improved architectural structure"\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )

                user_prompt = (
                    f"Analyze this {language} code for architectural integrity and modular design:\n"
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
                logger.warning(f"ArchitectureAgent LLM analysis failed; falling back to heuristic engine: {e}")
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
