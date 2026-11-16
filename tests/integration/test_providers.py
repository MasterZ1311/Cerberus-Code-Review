"""
Integration and resilience tests for LLM providers and heuristic fallback.
Includes live cloud provider tests gated behind API key environment variables,
circuit breaker trip verification, and transient error recovery.
"""

import os

import pytest

from cerberus.core.circuit_breaker import CircuitBreaker, CircuitState
from cerberus.core.exceptions import CircuitBreakerOpenError
from cerberus.providers import get_llm_provider
from cerberus.providers.heuristic_engine import HeuristicEngine


@pytest.mark.asyncio
async def test_heuristic_provider_zero_config_review():
    """Verify default zero-config heuristic engine analyzes code and outputs findings without cloud keys."""
    # Heuristic engine resolves to None for LLM, activating local AST rules
    provider = get_llm_provider("heuristic")
    assert provider is None  # Offline engine operates without remote LLM provider

    python_snippet = """
    import os
    def unsafe(user_input):
        eval(user_input)
        os.system("echo " + user_input)
    """
    findings, score = HeuristicEngine.analyze_security(python_snippet)
    assert len(findings) >= 2
    assert any(getattr(f, "cwe_id", None) == "CWE-95" or "eval" in f.title.lower() for f in findings)
    assert any(
        getattr(f, "cwe_id", None) == "CWE-78" or "os.system" in f.title.lower() or "command" in f.title.lower()
        for f in findings
    )
    assert 0.0 <= score <= 100.0


@pytest.mark.asyncio
async def test_circuit_breaker_trip_and_fast_fail():
    """Verify that a failing external provider trips the circuit breaker to OPEN."""
    breaker = CircuitBreaker("mock-failing-provider", failure_threshold=3, recovery_timeout=0.5)

    async def failing_call():
        raise ConnectionError("Remote LLM connection reset by peer")

    # Call 3 times to hit threshold
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await breaker.call(failing_call)

    # Breaker must now be in OPEN state
    assert breaker.state == CircuitState.OPEN

    # Next call should fail immediately with CircuitBreakerOpenError without invoking failing_call
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await breaker.call(failing_call)

    assert "mock-failing-provider" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY environment variable not configured")
async def test_live_openai_provider():
    """Gated integration test against live OpenAI API when credentials are provided."""
    provider = get_llm_provider("openai")
    assert await provider.is_available() is True
    res = await provider.generate_response(
        system_prompt="You are a code review assistant. Output JSON.",
        user_prompt="Review this code: def add(a, b): return a + b",
    )
    assert res is not None
    assert len(res) > 0


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY environment variable not configured")
async def test_live_anthropic_provider():
    """Gated integration test against live Anthropic API when credentials are provided."""
    provider = get_llm_provider("anthropic")
    assert await provider.is_available() is True
    res = await provider.generate_response(
        system_prompt="You are a code review assistant.",
        user_prompt="Say ready",
    )
    assert res is not None
    assert len(res) > 0


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY environment variable not configured")
async def test_live_gemini_provider():
    """Gated integration test against live Gemini API when credentials are provided."""
    provider = get_llm_provider("gemini")
    assert await provider.is_available() is True
    res = await provider.generate_response(
        system_prompt="You are a code review assistant.",
        user_prompt="Say ready",
    )
    assert res is not None
    assert len(res) > 0
