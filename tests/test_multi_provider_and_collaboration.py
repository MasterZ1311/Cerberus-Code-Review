"""
Tests for Multi-Provider AI Support (Groq, Anthropic, Gemini, DeepSeek, OpenAI)
and Multi-Agent Collaborative Workflows (ConsensusAgent, CodeFixerAgent, Per-Agent Routing).
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest

from cerberus.config import settings
from cerberus.models.schemas import CodeReviewRequest, Finding, SeverityEnum
from cerberus.providers import (
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    DeepSeekProvider,
    OpenAIProvider,
    resolve_auto_provider,
    get_llm_provider,
)
from cerberus.agents.consensus_agent import ConsensusAgent
from cerberus.agents.code_fixer_agent import CodeFixerAgent
from cerberus.agents.orchestrator import ReviewOrchestrator


# =====================================================================
# 1. PROVIDER TESTS (Anthropic, Gemini, Groq, DeepSeek)
# =====================================================================


@pytest.mark.asyncio
async def test_anthropic_provider_generate():
    provider = AnthropicProvider(api_key="test-anthropic-key", model="claude-3-5-sonnet-20241022")
    assert await provider.is_available() is True

    fake_response = {"content": [{"type": "text", "text": '{"score": 88.0, "findings": []}'}]}

    mock_client = AsyncMock()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = fake_response
    mock_post_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_post_resp

    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("You are a reviewer", "Analyze this code")
        assert result == '{"score": 88.0, "findings": []}'

        call_args = mock_client.post.call_args
        assert call_args is not None
        headers = call_args[1]["headers"]
        assert headers["x-api-key"] == "test-anthropic-key"
        assert headers["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_gemini_provider_generate():
    provider = GeminiProvider(api_key="test-gemini-key", model="gemini-1.5-flash")
    assert await provider.is_available() is True

    fake_response = {"candidates": [{"content": {"parts": [{"text": '{"score": 95.0, "findings": []}'}]}}]}

    mock_client = AsyncMock()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = fake_response
    mock_post_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_post_resp

    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("System prompt", "Review code")
        assert result == '{"score": 95.0, "findings": []}'
        url = mock_client.post.call_args[0][0]
        assert "key=test-gemini-key" in url


@pytest.mark.asyncio
async def test_groq_provider_generate():
    provider = GroqProvider(api_key="gsk_testgroqkey", model="llama-3.3-70b-versatile")
    assert await provider.is_available() is True

    fake_response = {"choices": [{"message": {"content": '{"score": 90.0, "findings": []}'}}]}

    mock_client = AsyncMock()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = fake_response
    mock_post_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_post_resp

    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("System prompt", "Analyze this code")
        assert result == '{"score": 90.0, "findings": []}'


@pytest.mark.asyncio
async def test_deepseek_provider_generate():
    provider = DeepSeekProvider(api_key="sk-deepseek-key", model="deepseek-chat")
    assert await provider.is_available() is True

    fake_response = {"choices": [{"message": {"content": '{"score": 82.0, "findings": []}'}}]}

    mock_client = AsyncMock()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = fake_response
    mock_post_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_post_resp

    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("System prompt", "Analyze this code")
        assert result == '{"score": 82.0, "findings": []}'


@pytest.mark.asyncio
async def test_openrouter_provider_generate():
    from cerberus.providers.openrouter_provider import OpenRouterProvider

    provider = OpenRouterProvider(api_key="sk-or-test-key", model="auto")
    assert await provider.is_available() is True
    assert provider.effective_model == "anthropic/claude-3.5-sonnet"
    assert provider.effective_base_url == "https://openrouter.ai/api/v1"

    fake_response = {"choices": [{"message": {"content": '{"score": 92.0, "findings": []}'}}]}

    mock_client = AsyncMock()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = fake_response
    mock_client.post.return_value = mock_post_resp

    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("System prompt", "Review code")
        assert result == '{"score": 92.0, "findings": []}'

    # Error branch
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 500
    mock_err_resp.text = "Internal Server Error"
    mock_client.post.return_value = mock_err_resp
    with patch.object(provider, "get_client", return_value=mock_client):
        result = await provider.generate_response("System prompt", "Review code")
        assert result is None


# =====================================================================
# 2. AUTO-DETECTION & PER-AGENT ROUTING TESTS
# =====================================================================


def test_resolve_auto_provider():
    # If no keys set
    with (
        patch.object(settings, "GROQ_API_KEY", ""),
        patch.object(settings, "OPENAI_API_KEY", ""),
        patch.object(settings, "ANTHROPIC_API_KEY", ""),
        patch.object(settings, "GEMINI_API_KEY", ""),
        patch.object(settings, "DEEPSEEK_API_KEY", ""),
        patch.object(settings, "WATSONX_API_KEY", ""),
    ):
        assert resolve_auto_provider() == "heuristic"

    # If Groq is set
    with patch.object(settings, "GROQ_API_KEY", "gsk_test"), patch.object(settings, "OPENAI_API_KEY", ""):
        assert resolve_auto_provider() == "groq"

    # If OpenAI is set without Groq
    with patch.object(settings, "GROQ_API_KEY", ""), patch.object(settings, "OPENAI_API_KEY", "sk-proj-test"):
        assert resolve_auto_provider() == "openai"


def test_per_agent_provider_routing():
    with (
        patch.object(settings, "SECURITY_AGENT_PROVIDER", "groq"),
        patch.object(settings, "PERFORMANCE_AGENT_PROVIDER", "anthropic"),
        patch.object(settings, "GROQ_API_KEY", "gsk_123"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-123"),
    ):
        sec_prov = get_llm_provider("auto", agent_name="security")
        perf_prov = get_llm_provider("auto", agent_name="performance")
        other_prov = get_llm_provider("auto", agent_name="quality")

        assert isinstance(sec_prov, GroqProvider)
        assert isinstance(perf_prov, AnthropicProvider)
        # Quality falls back to auto-detected Groq
        assert isinstance(other_prov, GroqProvider)


# =====================================================================
# 3. CONSENSUS AGENT TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_consensus_agent_clean():
    agent = ConsensusAgent()
    consensus = await agent.reach_consensus(findings=[], scores={"security": 100.0, "performance": 95.0})
    assert consensus["pr_action"] == "MERGE_READY"
    assert "MERGE_READY" in consensus["summary"]


@pytest.mark.asyncio
async def test_consensus_agent_blocked_on_critical():
    agent = ConsensusAgent()
    critical_finding = Finding(
        id="SEC-01",
        severity=SeverityEnum.CRITICAL,
        category="injection",
        title="SQL Injection",
        message="Critical injection vulnerability",
        line=10,
    )
    compliance_finding = Finding(
        id="COMP-01",
        severity=SeverityEnum.HIGH,
        category="gdpr",
        title="GDPR Data Leak",
        message="PII exposure in database call",
        line=10,
    )
    consensus = await agent.reach_consensus(
        findings=[critical_finding, compliance_finding], scores={"security": 45.0, "compliance": 50.0}
    )
    assert consensus["pr_action"] == "BLOCKED_ON_ISSUES"
    assert len(consensus["cross_domain_correlations"]) > 0
    assert any("Fix 1 critical severity issue" in p for p in consensus["priority_action_plan"])


@pytest.mark.asyncio
async def test_consensus_agent_needs_revision_on_medium():
    agent = ConsensusAgent()
    med_finding = Finding(
        id="QUAL-01",
        severity=SeverityEnum.MEDIUM,
        category="complexity",
        title="Cyclomatic Complexity",
        message="Function exceeds cyclomatic complexity 15",
    )
    consensus = await agent.reach_consensus(findings=[med_finding], scores={"quality": 65.0})
    assert consensus["pr_action"] == "NEEDS_REVISION"


# =====================================================================
# 4. CODE FIXER AGENT TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_code_fixer_generates_valid_patch():
    fixer = CodeFixerAgent()
    original_code = "import os\ndef ping(host):\n    os.system('ping ' + host)\n"
    finding = Finding(
        id="SEC-INJ",
        severity=SeverityEnum.HIGH,
        category="injection",
        title="Command Injection",
        message="os.system is vulnerable",
        line=3,
        code_snippet="    os.system('ping ' + host)",
        suggestion="    subprocess.run(['ping', '-c', '1', host], check=True)",
    )

    patch_result = await fixer.synthesize_fixes(original_code=original_code, findings=[finding], filename="network.py")

    assert patch_result is not None
    assert patch_result["patch_applied"] is True
    assert "--- a/network.py" in patch_result["unified_diff"]
    assert "+++ b/network.py" in patch_result["unified_diff"]
    assert "subprocess.run" in patch_result["repaired_code"]
    assert patch_result["syntax_valid"] is True


# =====================================================================
# 5. COLLABORATIVE MULTI-AGENT END-TO-END PIPELINE
# =====================================================================


@pytest.mark.asyncio
async def test_orchestrator_collaborative_workflow():
    orch = ReviewOrchestrator()
    code = "import os\nos.system('echo test')\n"
    req = CodeReviewRequest(code=code, language="python", filename="app.py", agents=["security", "performance"])

    res = await orch.execute_review(req)
    assert res.status == "completed"
    # Verify collaborative consensus is attached
    assert res.collaborative_consensus is not None
    assert "pr_action" in res.collaborative_consensus
    # Verify automated unified patch is generated
    assert res.unified_patch is not None
    assert "--- a/app.py" in res.unified_patch
