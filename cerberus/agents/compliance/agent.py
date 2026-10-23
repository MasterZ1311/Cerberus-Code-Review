"""
Comprehensive Compliance Checking Agent for Regulated Code.
Evaluates source code against HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA regulatory frameworks.
"""

import asyncio
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
from cerberus.agents.compliance.ccpa_evaluator import CCPARegulatoryEvaluator
from cerberus.agents.compliance.gdpr_evaluator import GDPRRegulatoryEvaluator
from cerberus.agents.compliance.hipaa_evaluator import HIPAARegulatoryEvaluator
from cerberus.agents.compliance.models import (
    ComplianceCheck,
    ComplianceReport,
    ComplianceStatus,
    FrameworkScore,
    FrameworkType,
    RemediationTimeline,
)
from cerberus.agents.compliance.pcidss_evaluator import PCIDSSRegulatoryEvaluator
from cerberus.agents.compliance.soc2_evaluator import SOC2RegulatoryEvaluator
from cerberus.models.schemas import AgentResult, Finding, SeverityEnum
from cerberus.providers import get_llm_provider
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.agents.compliance")


class ComprehensiveComplianceAgent(BaseAgent):
    """
    Autonomous Enterprise Regulatory Compliance Agent.
    Validates code against HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA.
    """

    name: str = "compliance"
    version: str = "2.1.0"
    purpose: str = "Audit code against HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA regulatory mandates"

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def get_capabilities(self) -> List[str]:
        return [
            "HIPAA Security Rule (45 CFR §164.312 - ePHI, In-Transit TLS, Audit Logging)",
            "GDPR Data Protection (Articles 5, 6, 17, 25, 32 - Minimization, Consent, Erasure)",
            "SOC 2 Trust Services Criteria (CC6.1, CC6.6, CC7.1, CC7.2 - Secrets, RBAC, Masking)",
            "PCI-DSS v4.0 (Req 3.2, 3.4, 3.5 - PAN Luhn Validation, CVV Storage Prohibition)",
            "CCPA / CPRA (§1798.105, §1798.120 - Do-Not-Sell Opt-Out, DSAR Verification)",
            "Automated Regulatory Remediation Timelines & SLA Generation",
            "Multi-Framework Individual Compliance Scoring Matrix"
        ]

    def _evaluate_synchronously(self, code: str, language: str) -> ComplianceReport:
        """Executes all 5 framework evaluations and compiles the regulatory audit report."""
        hipaa_findings = HIPAARegulatoryEvaluator.evaluate(code, language)
        gdpr_findings = GDPRRegulatoryEvaluator.evaluate(code, language)
        soc2_findings = SOC2RegulatoryEvaluator.evaluate(code, language)
        pcidss_findings = PCIDSSRegulatoryEvaluator.evaluate(code, language)
        ccpa_findings = CCPARegulatoryEvaluator.evaluate(code, language)

        framework_runs = [
            (FrameworkType.HIPAA, hipaa_findings),
            (FrameworkType.GDPR, gdpr_findings),
            (FrameworkType.SOC2, soc2_findings),
            (FrameworkType.PCIDSS, pcidss_findings),
            (FrameworkType.CCPA, ccpa_findings),
        ]

        framework_scores: Dict[str, FrameworkScore] = {}
        all_findings: List[Finding] = []
        total_hours = 0.0

        for ftype, findings in framework_runs:
            all_findings.extend(findings)
            score = 100.0
            crit_cnt = 0
            high_cnt = 0
            med_cnt = 0

            for f in findings:
                if f.severity == SeverityEnum.CRITICAL:
                    score -= 35.0
                    crit_cnt += 1
                    total_hours += 8.0
                elif f.severity == SeverityEnum.HIGH:
                    score -= 20.0
                    high_cnt += 1
                    total_hours += 4.0
                elif f.severity == SeverityEnum.MEDIUM:
                    score -= 10.0
                    med_cnt += 1
                    total_hours += 2.0
                else:
                    score -= 5.0
                    total_hours += 0.5

            clamped_score = max(0.0, min(100.0, score))

            if clamped_score >= 90.0:
                status = ComplianceStatus.COMPLIANT
            elif clamped_score >= 70.0:
                status = ComplianceStatus.NEEDS_ATTENTION
            else:
                status = ComplianceStatus.NON_COMPLIANT

            framework_scores[ftype.value] = FrameworkScore(
                framework=ftype,
                score=round(clamped_score, 1),
                status=status,
                passed_checks=max(0, 10 - len(findings)),
                failed_checks=len(findings),
                critical_violations=crit_cnt,
                high_violations=high_cnt,
                medium_violations=med_cnt,
                findings=findings
            )

        # Calculate overall compliance score directly from total findings
        overall_score = 100.0
        for f in all_findings:
            if f.severity == SeverityEnum.CRITICAL:
                overall_score -= 30.0
            elif f.severity == SeverityEnum.HIGH:
                overall_score -= 20.0
            elif f.severity == SeverityEnum.MEDIUM:
                overall_score -= 10.0
            else:
                overall_score -= 5.0

        overall_score = round(max(0.0, min(100.0, overall_score)), 1)
        if overall_score >= 90.0:
            overall_status = ComplianceStatus.COMPLIANT
        elif overall_score >= 70.0:
            overall_status = ComplianceStatus.NEEDS_ATTENTION
        else:
            overall_status = ComplianceStatus.NON_COMPLIANT

        report = ComplianceReport(
            overall_compliance_score=overall_score,
            overall_status=overall_status,
            frameworks=framework_scores,
            remediation_timeline=RemediationTimeline(
                estimated_remediation_hours=round(total_hours, 1)
            ),
            audit_trail=[
                f"HIPAA: {framework_scores['HIPAA'].score}% ({framework_scores['HIPAA'].status.value})",
                f"GDPR: {framework_scores['GDPR'].score}% ({framework_scores['GDPR'].status.value})",
                f"SOC 2: {framework_scores['SOC2'].score}% ({framework_scores['SOC2'].status.value})",
                f"PCI-DSS: {framework_scores['PCI-DSS'].score}% ({framework_scores['PCI-DSS'].status.value})",
                f"CCPA: {framework_scores['CCPA'].score}% ({framework_scores['CCPA'].status.value})",
            ]
        )
        return report

    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """Analyze code asynchronously across all regulatory compliance frameworks."""
        start_time = time.perf_counter()

        # 1. Safely offload regex and AST evaluation to threadpool
        report: ComplianceReport = await asyncio.to_thread(
            self._evaluate_synchronously,
            code,
            language
        )

        all_findings: List[Finding] = []
        for fs in report.frameworks.values():
            all_findings.extend(fs.findings)

        final_score = report.overall_compliance_score

        # 2. Check if LLM provider is available for deeper regulatory audit
        provider = self.provider or get_llm_provider()
        if provider and await provider.is_available():
            try:
                bounded_code = code[:12000]
                if len(code) > 12000:
                    bounded_code += "\n# ... [Remaining code truncated for LLM context window]"

                system_prompt = (
                    "[ROLE]: Enterprise Regulatory Compliance Auditor utilizing IBM Granite foundation models.\n"
                    "[TASK]: Audit the source code against regulatory mandates: HIPAA (ePHI logging, cleartext transmission), "
                    "GDPR (PII exposure, data minimization, consent/erasure), SOC 2 (secrets in code, audit logging, RBAC), "
                    "PCI-DSS (cardholder PANs, CVV storage), and CCPA.\n"
                    "[CONSTRAINTS]: Return strictly a valid JSON object matching the requested schema. No conversational filler.\n"
                    "[FORMAT]:\n"
                    "{\n"
                    '  "score": 85.0,\n'
                    '  "findings": [\n'
                    "    {\n"
                    '      "severity": "critical|high|medium|low|info",\n'
                    '      "category": "hipaa|gdpr|soc2|pcidss|ccpa",\n'
                    '      "title": "Short title citing standard",\n'
                    '      "message": "Detailed description of compliance violation",\n'
                    '      "line": 1,\n'
                    '      "code_snippet": "offending code",\n'
                    '      "explanation": "Regulatory framework violation explanation and risk",\n'
                    '      "recommendation": "Remediation guidance",\n'
                    '      "suggestion": "Compliant code replacement"\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )

                user_prompt = (
                    f"Audit this {language} code against regulatory frameworks (HIPAA, GDPR, SOC 2, PCI-DSS, CCPA):\n"
                    f"```{language}\n"
                    f"{bounded_code}\n"
                    f"```"
                )

                raw_response = await provider.generate_response(system_prompt, user_prompt)
                llm_data = parse_llm_json(raw_response)

                if llm_data and isinstance(llm_data, dict):
                    raw_findings = llm_data.get("findings", [])
                    ai_findings = build_findings_from_llm(raw_findings, self.name, code)
                    all_findings = merge_findings(all_findings, ai_findings)
                    final_score = compute_composite_score(
                        all_findings,
                        llm_score=llm_data.get("score"),
                        heuristic_score=report.overall_compliance_score,
                    )
            except Exception as e:
                logger.warning(f"ComplianceAgent LLM analysis failed; falling back to heuristic engine: {e}")

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return AgentResult(
            name=self.name,
            status="completed",
            score=round(final_score, 1),
            execution_time_ms=elapsed_ms,
            findings=all_findings
        )
