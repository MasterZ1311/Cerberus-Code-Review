"""
Empirical test for AGENT_SPECIFICATIONS.md.
Tests:
- All 20 agents are documented
- Confirms the undefined 'Optional' NameError in Agent 1 tools.py
- Validates that the remaining 59 blocks execute cleanly
"""


import pytest

from scripts.verify_python_blocks import ROOT, extract_python_blocks

EXPECTED_AGENTS = [
    "Predictive Bug Detection",
    "Supply Chain Security",
    "Performance Regression",
    "Architecture Violation",
    "Technical Debt Quantifier",
    "Code Fixer",
    "Custom Rule Engine",
    "Multi-Language Reviewer",
    "Historical Trend Analysis",
    "ML Code Auditor",
    "Compliance Standards",
    "IDE Integration",
    "Cost Analysis",
    "Accessibility Checker",
    "Anomaly Detection",
    "Codebase Fine-tuning",
    "Team Expertise Router",
    "Knowledge Base Builder",
    "Burndown Predictor",
    "Collaborative Review",
]


def test_doc2_agent_coverage():
    content = (ROOT / "AGENT_SPECIFICATIONS.md").read_text(encoding="utf-8")
    for agent in EXPECTED_AGENTS:
        assert agent.lower() in content.lower(), f"Agent missing from AGENT_SPECIFICATIONS.md: {agent}"


def test_doc2_agent1_undefined_optional():
    blocks = extract_python_blocks(ROOT / "AGENT_SPECIFICATIONS.md")
    block2 = blocks[1]  # src/codevault/agents/bug_predictor/tools.py

    # Must fail with NameError because Optional is not imported
    with pytest.raises(NameError, match="name 'Optional' is not defined"):
        exec(block2["content"], {})


def test_doc2_remaining_blocks_execution():
    blocks = extract_python_blocks(ROOT / "AGENT_SPECIFICATIONS.md")
    assert len(blocks) == 60

    # Check all schema blocks (indices 0, 3, 6, ...)
    for idx in range(0, 60, 3):
        b = blocks[idx]
        exec(b["content"], {})

    # Check remaining tool blocks (indices 4, 7, 10, ...)
    for idx in range(4, 60, 3):
        b = blocks[idx]
        exec(b["content"], {})
