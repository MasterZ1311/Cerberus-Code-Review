"""
Comprehensive Unit & Integration Tests for Compliance Checking Agent.
Verifies HIPAA, GDPR, SOC 2, PCI-DSS (Luhn algorithm), and CCPA evaluations.
"""

import pytest
from cerberus.agents.compliance import (
    ComprehensiveComplianceAgent,
    ComplianceStatus,
    mask_pan,
    validate_luhn,
)
from cerberus.agents.compliance_agent import ComplianceAgent
from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.models.schemas import CodeReviewRequest, SeverityEnum


def test_luhn_algorithm_validation():
    # Valid credit cards (standard test numbers conforming to Luhn algorithm)
    valid_visa = "4532 0151 1283 0366"
    valid_mc = "5105-1051-0510-5100"
    assert validate_luhn(valid_visa) is True
    assert validate_luhn(valid_mc) is True

    # Invalid cards (wrong checksum, sequential, or repeated digits)
    invalid_seq = "1234567890123456"
    invalid_zeros = "0000000000000000"
    invalid_checksum = "4532015112830367"  # Off by 1
    short_num = "12345"

    assert validate_luhn(invalid_seq) is False
    assert validate_luhn(invalid_zeros) is False
    assert validate_luhn(invalid_checksum) is False
    assert validate_luhn(short_num) is False

    # Masking
    assert mask_pan("4532015112830366") == "453201******0366"


@pytest.mark.asyncio
async def test_hipaa_phi_and_cleartext_http():
    agent = ComprehensiveComplianceAgent()
    vulnerable_hipaa_code = """
import requests

patient_diagnosis = "Type 2 Diabetes Mellitus"
medical_record_number = "MRN-90210"

def transmit_record(data):
    # Violation: Cleartext HTTP transmission of ePHI
    requests.post("http://health-exchange.net/api/v1/records", json=data)
"""
    result = await agent.analyze(vulnerable_hipaa_code)
    assert result.status == "completed"
    assert result.score < 70.0

    hipaa_findings = [f for f in result.findings if "HIPAA" in f.title]
    assert len(hipaa_findings) >= 2

    # Check for in-transit violation
    transit_findings = [f for f in hipaa_findings if "In-Transit" in f.title]
    assert len(transit_findings) > 0
    assert transit_findings[0].severity == SeverityEnum.CRITICAL


@pytest.mark.asyncio
async def test_gdpr_data_minimization_and_url_pii():
    agent = ComprehensiveComplianceAgent()
    gdpr_code = """
import requests

def get_all_users():
    # Violation: Data minimization
    return db.execute("SELECT * FROM users")

def notify_user(email):
    # Violation: Plaintext PII in URL
    requests.get(f"https://api.service.com/notify?email={email}")
"""
    result = await agent.analyze(gdpr_code)
    assert result.status == "completed"

    gdpr_findings = [f for f in result.findings if "GDPR" in f.title]
    assert len(gdpr_findings) >= 2
    assert any("Data Minimization" in f.title for f in gdpr_findings)
    assert any("Plaintext PII in URL" in f.title for f in gdpr_findings)


@pytest.mark.asyncio
async def test_soc2_credentials_and_logging():
    agent = ComprehensiveComplianceAgent()
    soc2_code = """
import logging
logger = logging.getLogger(__name__)

jwt_secret = "master_jwt_secret_key_production_123456"

def login(token):
    # Violation: Token emission in application logs
    logger.info(f"User login attempt with token: {token}")
"""
    result = await agent.analyze(soc2_code)
    assert result.status == "completed"

    soc2_findings = [f for f in result.findings if "SOC 2" in f.title]
    assert len(soc2_findings) >= 2
    assert any("CC6.1" in f.title for f in soc2_findings)
    assert any("CC7.2" in f.title for f in soc2_findings)


@pytest.mark.asyncio
async def test_pcidss_pan_and_cvv_storage():
    agent = ComprehensiveComplianceAgent()
    pci_code = """
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class PaymentCard(Base):
    __tablename__ = "cards"
    # Severe Violation: CVV storage is strictly prohibited post-auth
    cvv = Column(String(4), nullable=False)
    # Violation: Hardcoded card number
    card_number = "4532 0151 1283 0366"
"""
    result = await agent.analyze(pci_code)
    assert result.status == "completed"
    assert result.score < 60.0

    pci_findings = [f for f in result.findings if "PCI-DSS" in f.title]
    assert len(pci_findings) >= 2

    cvv_finding = next(f for f in pci_findings if "CVV" in f.title)
    assert cvv_finding.severity == SeverityEnum.CRITICAL

    pan_finding = next(f for f in pci_findings if "PAN" in f.title)
    assert pan_finding.severity == SeverityEnum.CRITICAL


@pytest.mark.asyncio
async def test_ccpa_opt_out_enforcement():
    agent = ComprehensiveComplianceAgent()
    ccpa_code = """
def share_data_with_partners(user):
    # Violation: Sharing with third-party ad brokers without checking opt-out
    sell_data_to_broker(user)
"""
    result = await agent.analyze(ccpa_code)
    assert result.status == "completed"

    ccpa_findings = [f for f in result.findings if "CCPA" in f.title]
    assert len(ccpa_findings) >= 1
    assert any("Do Not Sell" in f.title or "Opt-Out" in f.title for f in ccpa_findings)


@pytest.mark.asyncio
async def test_clean_code_full_compliance():
    agent = ComprehensiveComplianceAgent()
    clean_code = """
import os
import hashlib
import requests
import logging

logger = logging.getLogger(__name__)

API_URL = "https://secure.hospital.org/api/v2"

def get_user_summary(user_id: int):
    # Parameterized query with minimal fields
    query = "SELECT id, email, role FROM users WHERE id = :id"
    return db.execute(query, {"id": user_id})

def process_secure_payment(amount: float, card_token: str):
    # Tokenized card payment via TLS 1.3
    headers = {"Authorization": f"Bearer {os.getenv('GATEWAY_KEY')}"}
    return requests.post(f"{API_URL}/charge", json={"amount": amount, "token": card_token}, headers=headers)
"""
    result = await agent.analyze(clean_code)
    assert result.status == "completed"
    # Score must be in the "compliant" range (>=70). An LLM may add minor advisory
    # findings on genuinely clean code; exact 100.0 is only guaranteed heuristic-only.
    # The blended scorer applies a heuristic floor (100 - 30 = 70) to prevent
    # an over-aggressive LLM from dragging a clean result into the failing band.
    assert result.score >= 70.0, f"Expected score>=70 for clean code, got {result.score}"
    # No critical violations should be raised on clearly clean code
    critical_findings = [f for f in result.findings if f.severity == SeverityEnum.CRITICAL]
    assert len(critical_findings) == 0, (
        f"Unexpected critical findings on clean code: {[f.title for f in critical_findings]}"
    )


@pytest.mark.asyncio
async def test_orchestrator_integration_with_compliance():
    orchestrator = ReviewOrchestrator()
    # Confirm compliance agent is in registry
    assert "compliance" in orchestrator.registry
    assert isinstance(orchestrator.registry["compliance"], ComplianceAgent)

    req = CodeReviewRequest(
        code="""
API_KEY = "sk-live-1234567890abcdef"
cvv = "Column(String(4))"
""",
        language="python",
        agents=["compliance"],
    )
    response = await orchestrator.execute_review(req)
    assert response.status == "completed"
    assert response.overall_score is not None
    assert len(response.critical_issues) > 0
