"""
Tests for Multi-Agent Reflection, Confidence Calibration, and Risk Tiering.
"""

from cerberus.agents.consensus_agent import ConsensusAgent
from cerberus.models.schemas import Finding, SeverityEnum


def test_reflection_zero_findings():
    agent = ConsensusAgent()
    calibration = agent._calibrate_confidence_and_reflect([], {})
    assert calibration["confidence_score"] == 0.99
    assert calibration["risk_tier"] == "MINIMAL"
    assert "Zero defects" in calibration["reflection"]


def test_reflection_critical_finding():
    agent = ConsensusAgent()
    findings = [
        Finding(
            id="CRIT-001",
            severity=SeverityEnum.CRITICAL,
            category="security",
            title="Remote Code Execution",
            message="Unsafe eval on user input",
            false_positive_probability=0.01,
        )
    ]
    agent_scores = {"security": 20.0, "architecture": 80.0}
    calibration = agent._calibrate_confidence_and_reflect(findings, agent_scores)
    assert calibration["risk_tier"] == "CRITICAL"
    assert 0.70 <= calibration["confidence_score"] <= 0.99
    assert "critical vulnerability" in calibration["reflection"]


def test_reflection_elevated_risk():
    agent = ConsensusAgent()
    findings = [
        Finding(
            id="HIGH-001",
            severity=SeverityEnum.HIGH,
            category="architecture",
            title="Cyclomatic Complexity",
            message="Complexity exceeds 35",
            false_positive_probability=0.04,
        )
    ]
    agent_scores = {"security": 90.0, "architecture": 75.0}
    calibration = agent._calibrate_confidence_and_reflect(findings, agent_scores)
    assert calibration["risk_tier"] == "ELEVATED"
    assert 0.70 <= calibration["confidence_score"] <= 0.99
    assert "high-severity" in calibration["reflection"]


def test_reflection_low_risk():
    agent = ConsensusAgent()
    findings = [
        Finding(
            id="LOW-001",
            severity=SeverityEnum.LOW,
            category="style",
            title="Trailing Whitespace",
            message="Whitespace at EOL",
            false_positive_probability=0.02,
        )
    ]
    agent_scores = {"security": 100.0, "architecture": 95.0}
    calibration = agent._calibrate_confidence_and_reflect(findings, agent_scores)
    assert calibration["risk_tier"] == "LOW"
    assert 0.70 <= calibration["confidence_score"] <= 0.99
    assert "informational/minor" in calibration["reflection"]


def test_score_divergence_penalty():
    agent = ConsensusAgent()
    finding = Finding(
        id="MED-001",
        severity=SeverityEnum.MEDIUM,
        category="performance",
        title="O(n^2) Loop",
        message="Nested lookup",
        false_positive_probability=0.02,
    )
    # Uniform scores (no divergence)
    cal_uniform = agent._calibrate_confidence_and_reflect([finding], {"agent_a": 80.0, "agent_b": 80.0})

    # High divergence (variance 60)
    cal_divergent = agent._calibrate_confidence_and_reflect([finding], {"agent_a": 95.0, "agent_b": 35.0})

    # Divergent confidence should be equal to or lower than uniform confidence
    assert cal_divergent["confidence_score"] <= cal_uniform["confidence_score"]
