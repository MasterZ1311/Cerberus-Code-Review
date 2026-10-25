"""
Collaborative Review & Consensus Agent (Agent 20).
Synthesizes findings across all specialized review agents (Security, Performance, Quality,
Architecture, Compliance) to resolve cross-domain trade-offs, compute overall merge readiness,
and produce an executive collaborative consensus brief.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from cerberus.agents.ai_helper import parse_llm_json
from cerberus.agents.base import BaseAgent
from cerberus.models.schemas import AgentResult, Finding, SeverityEnum
from cerberus.providers import get_llm_provider
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.agents.consensus")


class ConsensusAgent(BaseAgent):
    name: str = "consensus"
    version: str = "1.0.0"
    purpose: str = "Coordinate multi-agent consensus, resolve cross-domain conflicts, and determine merge readiness"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Multi-Agent Finding Cross-Correlation",
            "Cross-Domain Conflict & Trade-Off Resolution",
            "Automated PR Merge Gate Decision (MERGE_READY, BLOCKED, NEEDS_REVISION)",
            "Collaborative Multi-Agent Executive Brief Generation",
            "Risk Interlock Detection (Security + Compliance + Performance)"
        ]

    def _evaluate_heuristic_consensus(
        self,
        findings: List[Finding],
        agent_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """Deterministic consensus evaluation when offline."""
        critical_count = sum(1 for f in findings if f.severity == SeverityEnum.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == SeverityEnum.HIGH)
        medium_count = sum(1 for f in findings if f.severity == SeverityEnum.MEDIUM)

        # Detect line overlaps (same line flagged by multiple agents)
        line_map: Dict[int, List[str]] = {}
        for f in findings:
            if f.line is not None:
                if f.line not in line_map:
                    line_map[f.line] = []
                line_map[f.line].append(f.category)

        intersections = [
            {"line": line, "categories": list(set(cats))}
            for line, cats in line_map.items()
            if len(set(cats)) > 1
        ]

        # Determine merge action
        min_score = min(agent_scores.values()) if agent_scores else 100.0
        if critical_count > 0 or high_count >= 2 or min_score < 50.0:
            pr_action = "BLOCKED_ON_ISSUES"
            verdict = "Merge blocked due to critical / high severity issues."
        elif high_count > 0 or medium_count >= 1 or min_score < 80.0:
            pr_action = "NEEDS_REVISION"
            verdict = "Revision required before pull request can be approved."
        else:
            pr_action = "MERGE_READY"
            verdict = "Code meets multi-agent quality standards and is ready to merge."

        summary = (
            f"Multi-Agent Review Panel consensus: {pr_action}. "
            f"Flagged {critical_count} critical, {high_count} high, and {medium_count} medium issues. "
            f"{verdict}"
        )
        if intersections:
            summary += f" Detected cross-domain overlaps on line(s): {', '.join(str(i['line']) for i in intersections)}."

        priority_plan = []
        if critical_count:
            priority_plan.append(f"Fix {critical_count} critical severity issue(s) immediately")
        if high_count:
            priority_plan.append(f"Remediate {high_count} high severity issue(s)")
        if medium_count:
            priority_plan.append(f"Address {medium_count} medium severity issue(s)")
        if not priority_plan:
            priority_plan.append("LGTM: No blocking issues flagged across agents")

        return {
            "pr_action": pr_action,
            "consensus_reached": True,
            "cross_domain_intersections": intersections,
            "cross_domain_correlations": intersections,
            "summary": summary,
            "consensus_summary": summary,
            "verdict": verdict,
            "priority_action_plan": priority_plan,
        }

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        start_time = time.perf_counter()
        findings: List[Finding] = (context or {}).get("findings", [])
        agent_scores: Dict[str, float] = (context or {}).get("agent_scores", {})

        consensus_data = self._evaluate_heuristic_consensus(findings, agent_scores)

        # Check if LLM is available for deep collaborative synthesis
        provider = self.provider or get_llm_provider(agent_name=self.name)
        if provider and await provider.is_available() and findings:
            try:
                findings_summary = [
                    {
                        "severity": f.severity.value,
                        "category": f.category,
                        "title": f.title,
                        "line": f.line,
                        "recommendation": f.recommendation,
                    }
                    for f in findings[:15]
                ]

                system_prompt = (
                    "[ROLE]: Lead Software Architect and Multi-Agent Code Review Consensus Moderator.\n"
                    "[TASK]: Review findings from the multi-agent specialist panel (Security, Performance, Quality, Architecture, Compliance). "
                    "Synthesize a unified consensus verdict, resolve trade-offs, and recommend the definitive action plan.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "pr_action": "MERGE_READY|BLOCKED_ON_ISSUES|NEEDS_REVISION",\n'
                    '  "consensus_summary": "Concise executive brief of consensus recommendations",\n'
                    '  "verdict": "Clear verdict explanation",\n'
                    '  "priority_action_plan": ["Step 1...", "Step 2..."]\n'
                    "}"
                )

                user_prompt = (
                    f"Specialist Agent Scores: {json.dumps(agent_scores)}\n"
                    f"Agent Findings: {json.dumps(findings_summary)}\n"
                    f"Source Code Excerpt:\n```{language}\n{code[:3000]}\n```"
                )

                raw_res = await provider.generate_response(system_prompt, user_prompt)
                llm_parsed = parse_llm_json(raw_res)
                if llm_parsed and isinstance(llm_parsed, dict):
                    if "consensus_summary" in llm_parsed:
                        consensus_data["consensus_summary"] = llm_parsed["consensus_summary"]
                    if "pr_action" in llm_parsed:
                        consensus_data["pr_action"] = llm_parsed["pr_action"]
                    if "priority_action_plan" in llm_parsed:
                        consensus_data["priority_action_plan"] = llm_parsed["priority_action_plan"]
                    if "verdict" in llm_parsed:
                        consensus_data["verdict"] = llm_parsed["verdict"]
            except Exception as e:
                logger.warning(f"ConsensusAgent LLM synthesis failed; keeping heuristic consensus: {e}")

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Create finding representing the consensus decision
        consensus_finding = Finding(
            id="COLLAB-CONSENSUS-001",
            severity=SeverityEnum.CRITICAL if consensus_data["pr_action"] == "BLOCKED_ON_ISSUES" else (
                SeverityEnum.MEDIUM if consensus_data["pr_action"] == "NEEDS_REVISION" else SeverityEnum.INFO
            ),
            category="consensus",
            title=f"Multi-Agent Consensus: {consensus_data['pr_action'].replace('_', ' ')}",
            message=consensus_data["consensus_summary"],
            explanation=consensus_data.get("verdict"),
            recommendation="Review and address the prioritized action items agreed upon by the multi-agent review team."
        )

        score = 100.0 if consensus_data["pr_action"] == "MERGE_READY" else (
            50.0 if consensus_data["pr_action"] == "NEEDS_REVISION" else 20.0
        )

        return AgentResult(
            name=self.name,
            status="completed",
            score=score,
            execution_time_ms=elapsed_ms,
            findings=[consensus_finding],
        )

    async def reach_consensus(
        self,
        findings: List[Finding],
        scores: Dict[str, float],
        code: str = ""
    ) -> Dict[str, Any]:
        """Convenience method to calculate consensus directly from findings and scores."""
        return self._evaluate_heuristic_consensus(findings, scores)

    async def generate_consensus(
        self,
        code: str,
        findings: List[Finding],
        agent_scores: Dict[str, float],
        language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method for direct consensus generation."""
        res = await self.analyze(code, language=language, context={"findings": findings, "agent_scores": agent_scores})
        return self._evaluate_heuristic_consensus(findings, agent_scores)
