"""
Multi-Agent Collaborative Consensus Agent (Agent 5).
Resolves cross-domain conflicts (e.g. Security vs. Performance trade-offs),
synthesizes finding severities, and delivers a unified pull request verdict.
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
    purpose = "Collaboratively resolve trade-offs, align multi-agent findings, and produce unified consensus"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "Multi-Agent Finding Reconciliation & Cross-Domain Arbitration",
            "Security vs. Performance Trade-off Optimization",
            "Unified Merge Readiness Determination (MERGE_READY, NEEDS_REVISION, BLOCKED_ON_ISSUES)",
            "Cross-Domain Vulnerability & Bottleneck Intersection Mapping",
            "Autonomous Code Review Alignment",
        ]

    def _evaluate_heuristic_consensus(self, findings: List[Finding], agent_scores: Dict[str, float]) -> Dict[str, Any]:
        """Calculates deterministic consensus metrics across all specialized agent reports."""
        critical_count = sum(1 for f in findings if f.severity == SeverityEnum.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == SeverityEnum.HIGH)
        medium_count = sum(1 for f in findings if f.severity == SeverityEnum.MEDIUM)

        # Cross-domain intersections: lines where multiple agents reported issues
        line_map: Dict[int, List[Finding]] = {}
        for f in findings:
            if f.line is not None:
                line_map.setdefault(f.line, []).append(f)

        intersections = []
        for line, line_findings in line_map.items():
            categories = {f.category for f in line_findings}
            if len(categories) > 1:
                intersections.append(
                    {"line": line, "categories": list(categories), "finding_count": len(line_findings)}
                )

        # PR action determination
        min_score = min(agent_scores.values()) if agent_scores else 100.0
        if critical_count > 0 or high_count >= 2 or min_score < 50.0:
            pr_action = "BLOCKED_ON_ISSUES"
            verdict = "Merge blocked due to critical / high severity issues."
        elif high_count > 0 or medium_count >= 1 or min_score < 80.0:
            pr_action = "NEEDS_REVISION"
            verdict = "Requires revision before merge."
        else:
            pr_action = "MERGE_READY"
            verdict = "Code meets multi-agent quality standards and is ready to merge."

        summary = (
            f"Multi-Agent Review Panel consensus: {pr_action}. "
            f"Flagged {critical_count} critical, {high_count} high, and {medium_count} medium issues. "
            f"{verdict}"
        )
        if intersections:
            summary += (
                f" Detected cross-domain overlaps on line(s): {', '.join(str(i['line']) for i in intersections)}."
            )

        priority_plan = []
        if critical_count:
            priority_plan.append(f"Fix {critical_count} critical severity issue(s) immediately")
        if high_count:
            priority_plan.append(f"Remediate {high_count} high severity issue(s)")
        if medium_count:
            priority_plan.append(f"Address {medium_count} medium severity issue(s)")
        if not priority_plan:
            priority_plan.append("LGTM: No blocking issues flagged across agents")

        # Domain Trade-off Arbitration Matrix
        arbitrations = []
        categories_present = {f.category.lower() for f in findings}
        has_security = any(
            c in categories_present for c in ("injection", "secrets", "cryptography", "security", "deserialization")
        )
        has_perf = any(
            c in categories_present for c in ("performance", "algorithmic_complexity", "database", "memory_efficiency")
        )
        has_compliance = any(c in categories_present for c in ("compliance", "hipaa", "gdpr", "pcidss", "ccpa"))
        has_arch = any(c in categories_present for c in ("architecture", "dependency", "circular_import"))

        if has_security and has_perf:
            arbitrations.append(
                "Security vs. Performance Invariant: Parameterized inputs and cryptographic hardening are mandatory invariants. Resolve latency via asynchronous workers or caching rather than relaxing security validations."
            )
        if has_compliance:
            arbitrations.append(
                "Regulatory Compliance Invariant: Statutory data protections (HIPAA, GDPR, PCI-DSS) are non-negotiable legal mandates and supersede stylistic brevity."
            )
        if has_arch:
            arbitrations.append(
                "Architecture Decoupling Invariant: Circular imports and deep parent references must be resolved via dependency inversion or domain event boundaries."
            )

        # Multi-Agent Confidence Calibration & Reflection Pass
        calibration = self._calibrate_confidence_and_reflect(findings, agent_scores)

        return {
            "pr_action": pr_action,
            "consensus_reached": True,
            "cross_domain_intersections": intersections,
            "cross_domain_correlations": intersections,
            "arbitration_principles": arbitrations,
            "summary": summary,
            "consensus_summary": summary,
            "verdict": verdict,
            "priority_action_plan": priority_plan,
            "confidence_score": calibration["confidence_score"],
            "confidence_reflection": calibration["reflection"],
            "calibrated_risk_tier": calibration["risk_tier"],
        }

    def _calibrate_confidence_and_reflect(
        self, findings: List[Finding], agent_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Executes a deterministic multi-agent reflection loop to calibrate confidence
        and filter borderline false positives across agent reports.
        """
        if not findings:
            return {
                "confidence_score": 0.99,
                "risk_tier": "MINIMAL",
                "reflection": "High confidence consensus: Zero defects or security violations detected across specialist agents.",
            }

        # Calculate average finding probability and cross-agent corroboration
        total_findings = len(findings)
        critical_count = sum(1 for f in findings if f.severity == SeverityEnum.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == SeverityEnum.HIGH)

        # Baseline confidence from individual finding false-positive probabilities
        fp_probs = [getattr(f, "false_positive_probability", 0.02) or 0.02 for f in findings]
        avg_precision = 1.0 - (sum(fp_probs) / max(1, len(fp_probs)))

        # Adjust confidence based on score consensus spread
        scores_list = list(agent_scores.values())
        if len(scores_list) > 1:
            score_variance = max(scores_list) - min(scores_list)
            # High divergence between agents slightly reduces certainty
            divergence_penalty = min(0.15, (score_variance / 100.0) * 0.15)
        else:
            divergence_penalty = 0.0

        calibrated_score = round(max(0.70, min(0.99, avg_precision - divergence_penalty)), 2)

        if critical_count > 0:
            risk_tier = "CRITICAL"
            reflection = (
                f"Multi-agent reflection confirms {critical_count} critical vulnerability(ies) "
                f"with {int(calibrated_score * 100)}% verified confidence. Immediate human patch required."
            )
        elif high_count > 0:
            risk_tier = "ELEVATED"
            reflection = (
                f"Multi-agent reflection confirms {high_count} high-severity issue(s) "
                f"with {int(calibrated_score * 100)}% calibrated confidence. Code requires revision."
            )
        else:
            risk_tier = "LOW"
            reflection = (
                f"Multi-agent reflection completed for {total_findings} informational/minor finding(s). "
                f"Calibrated confidence: {int(calibrated_score * 100)}%."
            )

        return {
            "confidence_score": calibrated_score,
            "risk_tier": risk_tier,
            "reflection": reflection,
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
                    '  "consensus_summary": "Synthesized executive evaluation of code quality and risks",\n'
                    '  "priority_action_plan": ["Specific prioritized remediation step 1", "Step 2"],\n'
                    '  "verdict": "Clear final recommendation statement"\n'
                    "}"
                )

                user_prompt = (
                    f"Specialist Agent Scores: {json.dumps(agent_scores)}\n"
                    f"Agent Findings: {json.dumps(findings_summary)}\n"
                    f"Language: {language}\n"
                    f"Code excerpt:\n```{language}\n{code[:5000]}\n```"
                )

                raw_res = await provider.generate_response(system_prompt, user_prompt)
                llm_parsed = parse_llm_json(raw_res)
                if llm_parsed and isinstance(llm_parsed, dict):
                    proposed_action = llm_parsed.get("pr_action")
                    if proposed_action in ("MERGE_READY", "BLOCKED_ON_ISSUES", "NEEDS_REVISION"):
                        # Safety Invariant: Never allow LLM to downgrade BLOCKED_ON_ISSUES to MERGE_READY if critical issues are active
                        critical_count = sum(1 for f in findings if f.severity == SeverityEnum.CRITICAL)
                        if critical_count > 0 and proposed_action == "MERGE_READY":
                            logger.warning(
                                "Safety Invariant Enforced: Refusing LLM attempt to downgrade critical blocking verdict to MERGE_READY."
                            )
                            consensus_data["pr_action"] = "BLOCKED_ON_ISSUES"
                        else:
                            consensus_data["pr_action"] = proposed_action
                    if "consensus_summary" in llm_parsed:
                        consensus_data["consensus_summary"] = llm_parsed["consensus_summary"]
                        consensus_data["summary"] = llm_parsed["consensus_summary"]
                    if "priority_action_plan" in llm_parsed and isinstance(llm_parsed["priority_action_plan"], list):
                        consensus_data["priority_action_plan"] = llm_parsed["priority_action_plan"]
                    if "verdict" in llm_parsed:
                        consensus_data["verdict"] = llm_parsed["verdict"]
            except Exception as e:
                logger.warning("ConsensusAgent LLM synthesis failed; keeping heuristic consensus: %s", e)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        plan = consensus_data.get("priority_action_plan", [])
        recommendation_str = (
            " • ".join(plan)
            if plan
            else "Review and address the prioritized action items agreed upon by the multi-agent review team."
        )

        # Create finding representing the consensus decision
        consensus_finding = Finding(
            id="COLLAB-CONSENSUS-001",
            severity=SeverityEnum.CRITICAL
            if consensus_data["pr_action"] == "BLOCKED_ON_ISSUES"
            else (SeverityEnum.MEDIUM if consensus_data["pr_action"] == "NEEDS_REVISION" else SeverityEnum.INFO),
            category="consensus",
            title=f"Multi-Agent Consensus: {consensus_data['pr_action'].replace('_', ' ')}",
            message=consensus_data["consensus_summary"],
            explanation=consensus_data.get("verdict"),
            recommendation=recommendation_str,
        )

        score = (
            100.0
            if consensus_data["pr_action"] == "MERGE_READY"
            else (50.0 if consensus_data["pr_action"] == "NEEDS_REVISION" else 20.0)
        )

        return AgentResult(
            name=self.name,
            status="completed",
            score=score,
            execution_time_ms=elapsed_ms,
            findings=[consensus_finding],
        )

    async def reach_consensus(
        self, findings: List[Finding], scores: Dict[str, float], code: str = ""
    ) -> Dict[str, Any]:
        """Convenience method to calculate consensus directly from findings and scores."""
        return self._evaluate_heuristic_consensus(findings, scores)

    async def generate_consensus(
        self, code: str, findings: List[Finding], agent_scores: Dict[str, float], language: str = "python"
    ) -> Dict[str, Any]:
        """Convenience method for direct consensus generation."""
        _ = await self.analyze(code, language=language, context={"findings": findings, "agent_scores": agent_scores})
        return self._evaluate_heuristic_consensus(findings, agent_scores)
