"""
Compliance Data Models & Framework Definitions.
Supports HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA regulatory frameworks.
"""

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field

from cerberus.models.schemas import Finding, SeverityEnum


class FrameworkType(str, Enum):
    HIPAA = "HIPAA"
    GDPR = "GDPR"
    SOC2 = "SOC2"
    PCIDSS = "PCI-DSS"
    CCPA = "CCPA"


class ComplianceStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    NON_COMPLIANT = "NON_COMPLIANT"


class ComplianceCheck(BaseModel):
    """Definition of an individual regulatory compliance rule."""

    id: str
    framework: FrameworkType
    standard_clause: str
    name: str
    description: str
    severity: SeverityEnum
    remediation_guidance: str
    sla_hours: int = 168  # Default 7 days


class FrameworkScore(BaseModel):
    """Compliance score and statistics for a specific regulatory framework."""

    framework: FrameworkType
    score: float = Field(default=100.0, ge=0.0, le=100.0)
    status: ComplianceStatus = ComplianceStatus.COMPLIANT
    passed_checks: int = 0
    failed_checks: int = 0
    critical_violations: int = 0
    high_violations: int = 0
    medium_violations: int = 0
    findings: List[Finding] = Field(default_factory=list)


class RemediationTimeline(BaseModel):
    """Estimated compliance resolution SLA timeline."""

    critical_sla: str = "Immediate (24 hours)"
    high_sla: str = "7 business days"
    medium_sla: str = "30 calendar days"
    low_sla: str = "90 calendar days"
    estimated_remediation_hours: float = 0.0


class ComplianceReport(BaseModel):
    """Full comprehensive compliance audit report across all frameworks."""

    overall_compliance_score: float = 100.0
    overall_status: ComplianceStatus = ComplianceStatus.COMPLIANT
    frameworks: Dict[str, FrameworkScore] = Field(default_factory=dict)
    remediation_timeline: RemediationTimeline = Field(default_factory=RemediationTimeline)
    audit_trail: List[str] = Field(default_factory=list)
