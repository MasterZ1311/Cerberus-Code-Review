"""
Review Orchestrator: Multi-Agent Parallel Execution, Caching, and Report Synthesis.
"""

import asyncio
import hashlib
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
from cerberus.core.zip_processor import extract_code_from_zip
from cerberus.models.schemas import (
    AgentResult,
    CodeReviewRequest,
    CodeReviewResponse,
    Finding,
    ReviewConfig,
    SeverityEnum,
    SeveritySummary,
    ZipFileReview,
    ZipReviewResponse,
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

        # Separate primary analytical agents from post-processing collaborative synthesis agents
        primary_agents = [a for a in active_agents if a not in ("consensus", "code_fixer")]
        if not primary_agents:
            primary_agents = [a for a in ["security", "performance", "quality"] if a in self.registry]

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

        # 3. Execute Primary Agents in Parallel
        agent_context = request.context.model_dump() if request.context else {}
        if request.filename and not agent_context.get("filename"):
            agent_context["filename"] = request.filename

        async def run_agent(agent_name: str) -> AgentResult:
            agent = self.registry[agent_name]
            a_start = time.perf_counter()
            try:
                res = await agent.analyze(
                    code=request.code,
                    language=request.language or "python",
                    context=agent_context,
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

        tasks = [run_agent(agent_name) for agent_name in primary_agents]
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

        # Calculate weighted overall score from primary diagnostic agents
        weights = {
            "security": 0.40,
            "performance": 0.25,
            "quality": 0.25,
            "architecture": 0.05,
            "compliance": 0.05,
        }
        diagnostic_scores = {k: v for k, v in scores.items() if k not in ("consensus", "code_fixer")}
        total_weight = sum(weights.get(name, 0.2) for name in diagnostic_scores)
        if total_weight > 0:
            overall_score = sum(diagnostic_scores[name] * weights.get(name, 0.2) for name in diagnostic_scores) / total_weight
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

        run_consensus = getattr(settings, "COLLABORATIVE_MODE", True) or ("consensus" in active_agents)
        if run_consensus and ("consensus" in self.registry):
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
                    plan_items = [p.strip() for p in cf.recommendation.split(" • ")] if cf.recommendation else []
                    collaborative_consensus = {
                        "status": "completed",
                        "summary": cf.message,
                        "pr_action": cf.title.replace("Multi-Agent Consensus: ", "").upper(),
                        "verdict": cf.explanation,
                        "priority_action_plan": plan_items,
                    }
                    if "consensus" in active_agents:
                        agents_payload.append(consensus_res.model_dump())
            except Exception as e:
                logger.warning(f"Collaborative consensus step failed: {e}")

        run_fixer = getattr(settings, "AUTO_GENERATE_FIXES", True) or ("code_fixer" in active_agents)
        if run_fixer and ("code_fixer" in self.registry) and all_findings:
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

        # 6. Save to Cache only if all agents completed successfully (prevent cache poisoning)
        if review_status == "completed":
            await cache_manager.set(cache_key, response.model_dump())

        # 7. Record Metrics
        REVIEW_REQUESTS_TOTAL.labels(status=review_status, language=request.language or "python").inc()
        REVIEW_DURATION_SECONDS.observe(total_elapsed_ms / 1000.0)

        return response

    async def execute_zip_review(
        self,
        zip_source: Any,
        project_name: Optional[str] = None,
        agents: Optional[List[str]] = None,
        config: Optional[ReviewConfig] = None,
        concurrency: int = 5,
        max_files: int = 100,
    ) -> ZipReviewResponse:
        """
        Extract and review an entire project from a ZIP archive.
        Executes parallel multi-agent reviews across all detected code files.
        """
        start_time = time.perf_counter()
        project_review_id = f"zip_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Archive-level cache lookup if raw bytes supplied
        zip_cache_key = None
        if isinstance(zip_source, bytes):
            agents_str = ",".join(sorted(agents or []))
            digest = hashlib.sha256(zip_source).hexdigest()
            zip_cache_key = f"cvai:zip_cache:{digest}:{agents_str}"
            cached_zip = await cache_manager.get(zip_cache_key)
            if cached_zip:
                CACHE_HITS_TOTAL.inc()
                REVIEW_REQUESTS_TOTAL.labels(status="completed", language="zip").inc()
                cached_resp = ZipReviewResponse(**cached_zip)
                cached_resp.review_id = project_review_id
                return cached_resp

        # 1. Safely extract code files
        extraction = extract_code_from_zip(
            zip_source=zip_source,
            project_name=project_name,
            max_files=max_files,
        )

        if not extraction.code_files:
            return ZipReviewResponse(
                project_name=extraction.project_name,
                review_id=project_review_id,
                status="completed",
                created_at=now_iso,
                completed_at=datetime.now(timezone.utc).isoformat(),
                total_files_discovered=extraction.total_entries_in_zip,
                reviewed_files_count=0,
                skipped_files_count=len(extraction.skipped_files),
                total_lines_of_code=0,
                overall_project_score=100.0,
                severity_summary=SeveritySummary(),
                language_distribution={},
                file_reviews=[],
                top_critical_findings=[],
                processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                summary="No supported source code files detected in the provided ZIP archive.",
            )

        # 2. Concurrently review all extracted files with concurrency throttling
        semaphore = asyncio.Semaphore(concurrency)

        async def _review_single_file(extracted_file) -> ZipFileReview:
            async with semaphore:
                req = CodeReviewRequest(
                    code=extracted_file.content,
                    language=extracted_file.language,
                    filename=extracted_file.path,
                    agents=agents,
                    config=config or ReviewConfig(),
                )
                file_resp = await self.execute_review(req)

                sev_summary = file_resp.results.get("severity_summary", {}) if file_resp.results else {}
                crit = sev_summary.get("critical", 0)
                high = sev_summary.get("high", 0)
                med = sev_summary.get("medium", 0)
                low = sev_summary.get("low", 0) + sev_summary.get("info", 0)
                total_findings = crit + high + med + low

                return ZipFileReview(
                    file_path=extracted_file.path,
                    filename=extracted_file.filename,
                    language=extracted_file.language,
                    lines_of_code=extracted_file.line_count,
                    score=file_resp.overall_score or 100.0,
                    status=file_resp.status,
                    review_id=file_resp.review_id,
                    critical_count=crit,
                    high_count=high,
                    medium_count=med,
                    low_count=low,
                    findings_count=total_findings,
                    review=file_resp,
                )

        tasks = [_review_single_file(f) for f in extraction.code_files]
        file_reviews: List[ZipFileReview] = await asyncio.gather(*tasks)

        # 3. Aggregate Metrics & Scores
        total_loc = sum(fr.lines_of_code for fr in file_reviews)
        if total_loc > 0:
            weighted_score = sum(fr.score * max(1, fr.lines_of_code) for fr in file_reviews) / total_loc
        else:
            weighted_score = sum(fr.score for fr in file_reviews) / max(1, len(file_reviews))

        overall_score = round(max(0.0, min(100.0, weighted_score)), 1)

        cum_crit = sum(fr.critical_count for fr in file_reviews)
        cum_high = sum(fr.high_count for fr in file_reviews)
        cum_med = sum(fr.medium_count for fr in file_reviews)
        cum_low = sum(fr.low_count for fr in file_reviews)

        sev_summary = SeveritySummary(
            critical=cum_crit,
            high=cum_high,
            medium=cum_med,
            low=cum_low,
            info=0,
        )

        # 4. Extract Top Critical Findings across all files (annotated with file path)
        all_crit_findings: List[Finding] = []
        for fr in file_reviews:
            for f in fr.review.critical_issues:
                # Add file context if not already present in title
                annotated = f.model_copy()
                if not annotated.title.startswith(f"[{fr.file_path}]"):
                    annotated.title = f"[{fr.file_path}] {annotated.title}"
                all_crit_findings.append(annotated)

        # Sort: critical first, then high
        all_crit_findings.sort(
            key=lambda x: (0 if x.severity == SeverityEnum.CRITICAL else 1, -(x.cvss_score or 0))
        )
        top_critical = all_crit_findings[:30]

        # 5. Project-wide Collaborative Consensus
        pr_action = "MERGE_READY"
        if cum_crit > 0:
            pr_action = "BLOCKED_ON_ISSUES"
        elif cum_high > 0 or overall_score < 75.0:
            pr_action = "NEEDS_REVISION"

        project_summary = (
            f"Project review completed for {len(file_reviews)} files ({total_loc:,} LOC). "
            f"Overall health score: {overall_score}/100. "
            f"Detected {cum_crit} critical, {cum_high} high, and {cum_med} medium issues."
        )

        consensus_data = {
            "status": "completed",
            "pr_action": pr_action,
            "verdict": f"Scanned {len(file_reviews)} files. Recommended action: {pr_action.replace('_', ' ')}.",
            "summary": project_summary,
            "priority_action_plan": [
                f"Remediate {cum_crit} critical security/compliance flaws across project",
                f"Address {cum_high} high-severity bottlenecks and defects",
                f"Maintain quality standard across {len(extraction.language_distribution)} programming languages"
            ] if (cum_crit > 0 or cum_high > 0) else ["Project is in clean, healthy state for merge/deployment."]
        }

        total_elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        completed_iso = datetime.now(timezone.utc).isoformat()

        resp = ZipReviewResponse(
            project_name=extraction.project_name,
            review_id=project_review_id,
            status="completed",
            created_at=now_iso,
            completed_at=completed_iso,
            total_files_discovered=extraction.total_entries_in_zip,
            reviewed_files_count=len(file_reviews),
            skipped_files_count=len(extraction.skipped_files),
            total_lines_of_code=total_loc,
            overall_project_score=overall_score,
            severity_summary=sev_summary,
            language_distribution=extraction.language_distribution,
            file_reviews=file_reviews,
            top_critical_findings=top_critical,
            processing_time_ms=total_elapsed_ms,
            collaborative_consensus=consensus_data,
            summary=project_summary,
        )

        # 6. Cache zip project response and record metrics
        if zip_cache_key:
            await cache_manager.set(zip_cache_key, resp.model_dump())

        REVIEW_REQUESTS_TOTAL.labels(status="completed", language="zip").inc()
        REVIEW_DURATION_SECONDS.observe(total_elapsed_ms / 1000.0)

        return resp


# Singleton orchestrator
orchestrator = ReviewOrchestrator()
