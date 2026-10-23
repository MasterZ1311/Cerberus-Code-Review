"""
Comprehensive Integration Tests for AI Foundation Model Integration & Dual Engine Execution.
Verifies Watsonx / OpenAI / Ollama interaction, AI response parsing, graceful fallbacks,
heuristic de-duplication, and multi-agent synthesis.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from cerberus.agents.ai_helper import (
    build_findings_from_llm,
    compute_composite_score,
    merge_findings,
    parse_llm_json,
)
from cerberus.agents.architecture_agent import ArchitectureAgent
from cerberus.agents.compliance_agent import ComplianceAgent
from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.agents.performance_agent import PerformanceAgent
from cerberus.agents.quality_agent import QualityAgent
from cerberus.agents.security_agent import SecurityAgent
from cerberus.config import settings
from cerberus.models.schemas import CodeReviewRequest, Finding, SeverityEnum
from cerberus.providers.base import BaseLLMProvider
from cerberus.providers.watsonx_provider import WatsonxProvider


class MockLLMProvider(BaseLLMProvider):
    def __init__(self, response_text: str = None, should_fail: bool = False, available: bool = True):
        super().__init__()
        self.response_text = response_text
        self.should_fail = should_fail
        self.available = available
        self.call_count = 0

    async def is_available(self) -> bool:
        return self.available

    async def generate_response(self, system_prompt: str, user_prompt: str):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Simulated upstream LLM network timeout or connection refused")
        return self.response_text


# =====================================================================
# 1. AI HELPER PARSING & SYNTHESIS TESTS
# =====================================================================

def test_parse_llm_json_raw():
    raw = '{"score": 85.0, "findings": [{"title": "Test Issue", "severity": "high"}]}'
    result = parse_llm_json(raw)
    assert result is not None
    assert result["score"] == 85.0
    assert len(result["findings"]) == 1


def test_parse_llm_json_markdown_fences():
    raw = """
    Here is the requested analysis:
    ```json
    {
      "score": 75.0,
      "findings": [
        {
          "severity": "critical",
          "category": "injection",
          "title": "SQL Injection",
          "line": 4
        }
      ]
    }
    ```
    Please review the code carefully.
    """
    result = parse_llm_json(raw)
    assert result is not None
    assert result["score"] == 75.0
    assert result["findings"][0]["severity"] == "critical"


def test_parse_llm_json_trailing_commas():
    raw = '{"score": 90.0, "findings": [{"title": "Trailing Comma Test", "severity": "medium",},],}'
    result = parse_llm_json(raw)
    assert result is not None
    assert result["score"] == 90.0


def test_parse_llm_json_invalid():
    assert parse_llm_json(None) is None
    assert parse_llm_json("") is None
    assert parse_llm_json("This is pure conversational output without any json whatsoever.") is None


def test_build_findings_from_llm():
    raw_findings = [
        {
            "severity": "CRITICAL",
            "category": "injection",
            "title": "SQL Injection Detected",
            "message": "User input concatenated into query string",
            "line": 3,
            "explanation": "Allows attackers to extract data",
            "recommendation": "Use bind parameters",
            "suggestion": "cursor.execute('SELECT * FROM tbl WHERE id = ?', (val,))",
            "cwe_id": "CWE-89",
            "cvss_score": 9.8,
        },
        {
            "severity": "info",
            "title": "Informational Notice",
            "message": "General observation",
        }
    ]
    code = "x = 1\ny = 2\nquery = 'SELECT * FROM u WHERE id = ' + uid\n"
    findings = build_findings_from_llm(raw_findings, "security", code)
    assert len(findings) == 2
    assert findings[0].severity == SeverityEnum.CRITICAL
    assert findings[0].line == 3
    assert findings[0].code_snippet == "query = 'SELECT * FROM u WHERE id = ' + uid"
    assert findings[0].cwe_id == "CWE-89"
    assert findings[1].severity == SeverityEnum.INFO


def test_merge_findings_enrichment():
    heuristic_findings = [
        Finding(
            id="SEC-SQLI-4",
            severity=SeverityEnum.CRITICAL,
            category="injection",
            title="SQL Injection Vulnerability",
            message="SQL injection via string concatenation.",
            line=4,
            code_snippet="query = 'SELECT * FROM users WHERE id = ' + user_id",
            cwe_id="CWE-89",
            cvss_score=9.8
        )
    ]
    llm_findings = [
        Finding(
            id="SEC-AI-1",
            severity=SeverityEnum.CRITICAL,
            category="injection",
            title="Tainted Dynamic SQL Query",
            message="Unsanitized user_id parameter flows directly into SQL statement",
            line=4,
            explanation="Detailed neural explanation of attacker payload injection techniques.",
            recommendation="Parameterized queries via ORM or placeholder syntax.",
            suggestion="db.execute('SELECT * FROM users WHERE id = :id', {'id': user_id})",
        ),
        Finding(
            id="SEC-AI-2",
            severity=SeverityEnum.MEDIUM,
            category="cryptography",
            title="Insecure Random Number Generator",
            message="Using random instead of secrets for token generation",
            line=10,
        )
    ]
    merged = merge_findings(heuristic_findings, llm_findings)
    assert len(merged) == 2
    # The first finding is the enriched heuristic finding
    assert merged[0].cwe_id == "CWE-89"
    assert "Detailed neural explanation" in merged[0].explanation
    assert "db.execute" in merged[0].suggestion
    # The second finding is the newly discovered AI finding
    assert merged[1].category == "cryptography"


def test_compute_composite_score():
    findings = [
        Finding(severity=SeverityEnum.CRITICAL, category="sec", title="T1", message="M1"),
        Finding(severity=SeverityEnum.HIGH, category="sec", title="T2", message="M2"),
    ]
    score = compute_composite_score(findings, llm_score=40.0)
    assert score <= 45.0
    assert score >= 0.0


# =====================================================================
# 2. SPECIALIZED AGENT AI INTEGRATION TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_security_agent_with_ai_provider():
    ai_payload = json.dumps({
        "score": 35.0,
        "findings": [
            {
                "severity": "critical",
                "category": "injection",
                "title": "SQL Injection in User Query",
                "message": "Dynamic query allows arbitrary SQL execution.",
                "line": 4,
                "explanation": "Untrusted input injected directly into DB query.",
                "recommendation": "Use parameterized queries.",
                "suggestion": "db.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                "cwe_id": "CWE-89",
                "cvss_score": 9.8
            },
            {
                "severity": "high",
                "category": "auth",
                "title": "Missing Authorization Check",
                "message": "Endpoint does not verify user roles before DB query.",
                "line": 3,
                "explanation": "Broken access control allows horizontal privilege escalation."
            }
        ]
    })
    provider = MockLLMProvider(response_text=ai_payload)
    agent = SecurityAgent(provider=provider)

    code = """
import os
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    db.execute(query)
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    assert result.score <= 45.0
    # Both the SQL injection (heuristic + AI) and the new Missing Authorization (AI) findings should exist
    assert any(f.category == "auth" for f in result.findings)
    assert any(f.category == "injection" for f in result.findings)


@pytest.mark.asyncio
async def test_security_agent_fallback_on_ai_failure():
    """Verify SecurityAgent seamlessly falls back to heuristics if AI times out or crashes."""
    provider = MockLLMProvider(should_fail=True)
    agent = SecurityAgent(provider=provider)

    code = """
import os
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    db.execute(query)
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    # Fallback to heuristic engine must detect the SQL injection
    assert any(f.category == "injection" for f in result.findings)
    assert result.score <= 70.0


@pytest.mark.asyncio
async def test_performance_agent_with_ai_provider():
    ai_payload = json.dumps({
        "score": 50.0,
        "findings": [
            {
                "severity": "high",
                "category": "algorithmic_complexity",
                "title": "O(N^2) Nested Iteration Bottleneck",
                "message": "Nested iteration over list items causes quadratic scaling.",
                "line": 3,
                "explanation": "Doubling items increases CPU cycles by 4x.",
                "recommendation": "Use set intersection for O(N) linear performance.",
                "suggestion": "return list(set(items_a) & set(items_b))"
            }
        ]
    })
    provider = MockLLMProvider(response_text=ai_payload)
    agent = PerformanceAgent(provider=provider)

    code = """
def compare(items_a, items_b):
    common = []
    for a in items_a:
        for b in items_b:
            if a == b:
                common.append(a)
    return common
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    assert result.score <= 60.0
    assert any(f.category == "algorithmic_complexity" for f in result.findings)


@pytest.mark.asyncio
async def test_quality_agent_with_ai_provider():
    ai_payload = json.dumps({
        "score": 60.0,
        "findings": [
            {
                "severity": "medium",
                "category": "error_handling",
                "title": "Suppressed Exception in Worker",
                "message": "Silent pass statement conceals operational failures.",
                "line": 4,
                "recommendation": "Log exception or re-raise."
            }
        ]
    })
    provider = MockLLMProvider(response_text=ai_payload)
    agent = QualityAgent(provider=provider)

    code = """
def process():
    try:
        do_work()
    except Exception:
        pass
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    assert any("Exception" in f.title or f.category == "error_handling" for f in result.findings)


@pytest.mark.asyncio
async def test_architecture_agent_with_ai_provider():
    ai_payload = json.dumps({
        "score": 70.0,
        "findings": [
            {
                "severity": "medium",
                "category": "coupling",
                "title": "Tight Coupling to Concrete Infrastructure",
                "message": "Direct instantiation of PostgresDatabase in domain service violates DIP.",
                "line": 5,
                "recommendation": "Inject database interface via constructor."
            }
        ]
    })
    provider = MockLLMProvider(response_text=ai_payload)
    agent = ArchitectureAgent(provider=provider)

    code = """
from ..infra.db import PostgresDatabase

class OrderService:
    def __init__(self):
        self.db = PostgresDatabase()
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    assert any(f.category == "coupling" for f in result.findings)


@pytest.mark.asyncio
async def test_compliance_agent_with_ai_provider():
    ai_payload = json.dumps({
        "score": 40.0,
        "findings": [
            {
                "severity": "critical",
                "category": "hipaa",
                "title": "HIPAA 45 CFR §164.312 - Unencrypted ePHI Exposure",
                "message": "Patient diagnosis logged to standard application logs without masking.",
                "line": 4,
                "recommendation": "Mask or tokenize all ePHI identifiers."
            }
        ]
    })
    provider = MockLLMProvider(response_text=ai_payload)
    agent = ComplianceAgent(provider=provider)

    code = """
import logging
logger = logging.getLogger(__name__)
def log_patient(name, condition):
    logger.info(f"Patient {name} diagnosed with {condition}")
"""
    result = await agent.analyze(code)
    assert result.status == "completed"
    assert provider.call_count == 1
    assert any(f.category == "hipaa" for f in result.findings)
    assert result.score <= 50.0


# =====================================================================
# 3. END-TO-END ORCHESTRATOR REVIEW WITH AI PROVIDER
# =====================================================================

@pytest.mark.asyncio
async def test_orchestrator_multi_agent_review_with_ai_provider():
    ai_payload = json.dumps({
        "score": 40.0,
        "findings": [
            {
                "severity": "critical",
                "category": "injection",
                "title": "Remote Code Execution Hazard",
                "message": "os.system receives unsanitized parameter",
                "line": 4,
                "suggestion": "subprocess.run(['ping', '-c', '1', host], check=True)"
            }
        ]
    })
    mock_provider = MockLLMProvider(response_text=ai_payload)

    orch = ReviewOrchestrator()
    for agent in orch.registry.values():
        agent.provider = mock_provider

    req = CodeReviewRequest(
        code="import os\ndef ping(host):\n    os.system('ping ' + host)\n",
        language="python",
        agents=["security", "performance", "quality"]
    )
    res = await orch.execute_review(req)
    assert res.status == "completed"
    assert res.overall_score < 70.0
    assert len(res.critical_issues) > 0
    assert any("Command Injection" in f.title or "Remote Code Execution" in f.title for f in res.critical_issues)
