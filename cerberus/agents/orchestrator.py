"""
Review Orchestrator: Multi-Agent Parallel Execution, Caching, and Report Synthesis.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cerberus.agents.architecture_agent import ArchitectureAgent
from cerberus.agents.base import BaseAgent
from cerberus.agents.code_fixer_agent import CodeFixerAgent
from cerberus.agents.compliance_agent import ComplianceAgent
from cerberus.agents.consensus_agent import ConsensusAgent
from cerberus.agents.performance_agent import PerformanceAgent
from cerberus.agents.quality_agent import QualityAgent
from cerberus.agents.security_agent import SecurityAgent
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.telemetry import (
    AGENT_EXECUTION_SECONDS,
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    FINDINGS_DETECTED_TOTAL,
    REVIEW_DURATION_SECONDS,
    REVIEW_REQUESTS_TOTAL,
)
from cerberus.models.schemas import (
    AgentResult,
    CodeReviewRequest,
    CodeReviewResponse,
    Finding,
    SeverityEnum,
)

logger = logging.getLogger("cerberus.orchestrator")


class ReviewOrchestrator:
    """Coordinates parallel agent analysis, caching, and prioritization."""

    def __init__(self):
        self.registry: Dict[str, BaseAgent] = {
            "security": SecurityAgent(),
            "performance": PerformanceAgent(),
            "quality": QualityAgent(),
            "architecture": ArchitectureAgent(),
            "compliance": ComplianceAgent(),
            "consensus": ConsensusAgent(),
            "code_fixer": CodeFixerAgent(),
        }

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents and their active capabilities."""
        return [
            {
                "id": agent_id,
                "name": agent.name,
                "version": agent.version,
                "purpose": agent.purpose,
                "capabilities": agent.get_capabilities(),
                "status": "active" if (agent_id in settings.enabled_agents_list or (settings.COLLABORATIVE_MODE and agent_id in ("consensus", "code_fixer"))) else "disabled",
            }
            for agent_id, agent in self.registry.items()
        ]

    async def execute_review(self, request: CodeReviewRequest) -> CodeReviewResponse:
        """
        Execute full multi-agent review with two-tier caching and prioritization.
        """
        start_time = time.perf_counter()
        review_id = f"rev_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Determine which agents to execute
        requested_agents = request.agents or settings.enabled_agents_list
        active_agents = [a for a in requested_agents if a in self.registry]
        if not active_agents:
            active_agents = ["security", "performance", "quality"]

        # 2. Check Cache
        cache_key = cache_manager.compute_cache_key(
            code=request.code,
            language=request.language or "python",
            agents=active_agents,
        )
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            CACHE_HITS_TOTAL.inc()
            REVIEW_REQUESTS_TOTAL.labels(status="completed", language=request.language or "python").inc()
            logger.info(f"Cache hit for review: {review_id}")
            
            cached_resp = CodeReviewResponse(**cached_data)
            cached_resp.review_id = review_id
            cached_resp.cache_hit = True
            cached_resp.created_at = now_iso
            cached_resp.completed_at = now_iso
            return cached_resp

        CACHE_MISSES_TOTAL.inc()

        # 3. Execute Agents in Parallel
        async def run_agent(agent_name: str) -> AgentResult:
            agent = self.registry[agent_name]
            a_start = time.perf_counter()
            try:
                res = await agent.analyze(
                    code=request.code,
                    language=request.language or "python",
                    context=request.context.model_dump() if request.context else None,
                )
                AGENT_EXECUTION_SECONDS.labels(agent_name=agent_name).observe(time.perf_counter() - a_start)
                for f in res.findings:
                    FINDINGS_DETECTED_TOTAL.labels(agent_name=agent_name, severity=f.severity.value).inc()
                return res
            except Exception as e:
                logger.error(f"Agent '{agent_name}' failed during review: {e}")
                return AgentResult(
                    name=agent_name,
                    status="failed",
                    score=0.0,
                    execution_time_ms=int((time.perf_counter() - a_start) * 1000),
                    error=str(e),
                )

        tasks = [run_agent(agent_name) for agent_name in active_agents]
        agent_results: List[AgentResult] = await asyncio.gather(*tasks)

        # 4. Synthesize Findings and Scores
        all_findings: List[Finding] = []
        scores: Dict[str, float] = {}
        agents_payload: List[Dict[str, Any]] = []

        for res in agent_results:
            scores[res.name] = res.score
            all_findings.extend(res.findings)
            agents_payload.append(res.model_dump())

        # Determine review status
        failed_count = sum(1 for res in agent_results if res.status == "failed")
        if failed_count == len(agent_results) and len(agent_results) > 0:
            review_status = "failed"
        elif failed_count > 0:
            review_status = "degraded"
        else:
            review_status = "completed"

        # Categorize findings by urgency
        critical_issues = [f for f in all_findings if f.severity in (SeverityEnum.CRITICAL, SeverityEnum.HIGH)]
        warnings = [f for f in all_findings if f.severity == SeverityEnum.MEDIUM]
        suggestions = [f for f in all_findings if f.severity in (SeverityEnum.LOW, SeverityEnum.INFO)]

        # Calculate weighted overall score
        weights = {
            "security": 0.40,
            "performance": 0.25,
            "quality": 0.25,
            "architecture": 0.05,
            "compliance": 0.05,
        }
        total_weight = sum(weights.get(name, 0.2) for name in scores)
        if total_weight > 0:
            overall_score = sum(scores[name] * weights.get(name, 0.2) for name in scores) / total_weight
        else:
            overall_score = 0.0 if failed_count > 0 else 100.0
        overall_score = round(max(0.0, min(100.0, overall_score)), 1)

        # Severity Summary
        summary = {
            "critical": sum(1 for f in all_findings if f.severity == SeverityEnum.CRITICAL),
            "high": sum(1 for f in all_findings if f.severity == SeverityEnum.HIGH),
            "medium": sum(1 for f in all_findings if f.severity == SeverityEnum.MEDIUM),
            "low": sum(1 for f in all_findings if f.severity == SeverityEnum.LOW),
            "info": sum(1 for f in all_findings if f.severity == SeverityEnum.INFO),
        }

        # Blocking determination
        blocking_mode = (
            request.config.blocking_mode
            if (request.config and request.config.blocking_mode is not None)
            else settings.BLOCKING_MODE
        )
        should_block = False
        block_reason = None
        if blocking_mode:
            if summary["critical"] > 0 or summary["high"] > 0:
                should_block = True
                block_reason = f"Blocking threshold triggered: Found {summary['critical']} critical and {summary['high']} high issues."

        total_elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        completed_iso = datetime.now(timezone.utc).isoformat()

        # 5. Multi-Agent Collaborative Consensus & Patch Generation
        collaborative_consensus = None
        unified_patch = None
        consensus_summary = None

        if getattr(settings, "COLLABORATIVE_MODE", True) and ("consensus" in self.registry):
            try:
                consensus_agent = self.registry["consensus"]
                consensus_res = await consensus_agent.analyze(
                    code=request.code,
                    language=request.language or "python",
                    context={"findings": all_findings, "agent_scores": scores}
                )
                if consensus_res.findings:
                    cf = consensus_res.findings[0]
                    consensus_summary = cf.message
                    collaborative_consensus = {
                        "status": "completed",
                        "summary": cf.message,
                        "pr_action": cf.title.replace("Multi-Agent Consensus: ", "").upper(),
                        "verdict": cf.explanation,
                    }
                    if "consensus" in active_agents:
                        agents_payload.append(consensus_res.model_dump())
            except Exception as e:
                logger.warning(f"Collaborative consensus step failed: {e}")

        if getattr(settings, "AUTO_GENERATE_FIXES", True) and ("code_fixer" in self.registry) and all_findings:
            try:
                fixer_agent = self.registry["code_fixer"]
                fixer_res = await fixer_agent.analyze(
                    code=request.code,
                    language=request.language or "python",
                    context={"findings": all_findings, "filename": request.filename or "snippet.py"}
                )
                if fixer_res.findings and fixer_res.findings[0].suggestion:
                    unified_patch = fixer_res.findings[0].suggestion
                if "code_fixer" in active_agents:
                    agents_payload.append(fixer_res.model_dump())
            except Exception as e:
                logger.warning(f"Collaborative code fixer step failed: {e}")

        results_data = {
            "overall_score": overall_score,
            "severity_summary": summary,
            "agents": agents_payload,
            "collaborative_consensus": collaborative_consensus,
            "unified_patch": unified_patch,
        }

        response = CodeReviewResponse(
            review_id=review_id,
            status=review_status,
            created_at=now_iso,
            completed_at=completed_iso,
            cache_hit=False,
            blocking=blocking_mode,
            should_block=should_block,
            block_reason=block_reason,
            overall_score=overall_score,
            processing_time_ms=total_elapsed_ms,
            results=results_data,
            critical_issues=critical_issues,
            warnings=warnings,
            suggestions=suggestions,
            agents_scheduled=active_agents,
            webhook_url=request.webhook_url,
            _links={
                "self": f"/api/v1/review/{review_id}",
                "results": f"/api/v1/review/{review_id}/results",
            },
            summary=consensus_summary,
            collaborative_consensus=collaborative_consensus,
            unified_patch=unified_patch,
        )

        # 5. Save to Cache only if all agents completed successfully (prevent cache poisoning)
        if review_status == "completed":
            await cache_manager.set(cache_key, response.model_dump())

        # 6. Record Metrics
        REVIEW_REQUESTS_TOTAL.labels(status=review_status, language=request.language or "python").inc()
        REVIEW_DURATION_SECONDS.observe(total_elapsed_ms / 1000.0)

        return response


# Singleton orchestrator
orchestrator = ReviewOrchestrator()
