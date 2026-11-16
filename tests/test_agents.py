"""
Unit Tests for Specialized Review Agents (Security, Performance, Quality, Architecture, Compliance).
"""

import pytest

from cerberus.agents.compliance_agent import ComplianceAgent
from cerberus.agents.performance_agent import PerformanceAgent
from cerberus.agents.quality_agent import QualityAgent
from cerberus.agents.security_agent import SecurityAgent
from cerberus.models.schemas import SeverityEnum


@pytest.mark.asyncio
async def test_security_agent_detects_sqli_and_secrets():
    agent = SecurityAgent()
    vulnerable_code = """
import os
API_KEY = "sk-live-1234567890abcdef123456"

def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    db.execute(query)
"""
    result = await agent.analyze(vulnerable_code)
    assert result.status == "completed"
    assert result.score < 60.0
    assert len(result.findings) >= 2

    # Check for SQL injection finding
    sqli_findings = [f for f in result.findings if f.category == "injection"]
    assert len(sqli_findings) > 0
    assert sqli_findings[0].severity == SeverityEnum.CRITICAL
    assert sqli_findings[0].cwe_id == "CWE-89"

    # Check for Secrets finding
    secret_findings = [f for f in result.findings if f.category == "secrets"]
    assert len(secret_findings) > 0
    assert secret_findings[0].severity == SeverityEnum.CRITICAL


@pytest.mark.asyncio
async def test_security_agent_clean_code():
    agent = SecurityAgent()
    clean_code = """
import os

def get_user(user_id: int):
    api_key = os.getenv("API_KEY")
    query = "SELECT * FROM users WHERE id = ?"
    return db.execute(query, (user_id,))
"""
    result = await agent.analyze(clean_code)
    assert result.status == "completed"
    assert result.score == 100.0
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_performance_agent_detects_quadratic_complexity():
    agent = PerformanceAgent()
    code_with_loop = """
def find_duplicates(items):
    dups = []
    for a in items:
        for b in items:
            if a == b:
                dups.append(a)
    return dups
"""
    result = await agent.analyze(code_with_loop)
    assert result.status == "completed"
    assert result.score < 90.0
    assert any(f.category == "algorithmic_complexity" for f in result.findings)


@pytest.mark.asyncio
async def test_quality_agent_detects_bare_except_and_missing_docs():
    agent = QualityAgent()
    bad_quality_code = """
def calculate():
    try:
        do_something()
    except:
        pass
"""
    result = await agent.analyze(bad_quality_code)
    assert result.status == "completed"
    assert result.score < 90.0
    assert any(f.category == "error_handling" for f in result.findings)


@pytest.mark.asyncio
async def test_compliance_agent_detects_sensitive_logging():
    agent = ComplianceAgent()
    violating_code = """
import logging
logger = logging.getLogger(__name__)

def login(user, password):
    logger.info(f"User login attempt: {user}, password={password}")
"""
    result = await agent.analyze(violating_code)
    assert result.status == "completed"
    assert result.score < 100.0
    assert any(f.category == "compliance" for f in result.findings)
