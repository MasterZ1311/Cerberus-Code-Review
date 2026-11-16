"""
Tests for 10/10 Architecture, Security, Heuristics, Schema, and DevOps Hardening.
"""

import pytest

from cerberus.agents.architecture_agent import ArchitectureAgent
from cerberus.config import Settings
from cerberus.core.security import RateLimiter
from cerberus.models.schemas import (
    CodeReviewResponse,
    ReviewResults,
)
from cerberus.providers.heuristic_engine import HeuristicEngine

# ============================================================================
# 1. Security & Production Guard Tests
# ============================================================================


def test_production_guard_disables_insecure_dev_key():
    """Production mode must automatically neutralize insecure default dev api key."""
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        DEFAULT_DEV_API_KEY="cvai_dev_key_123",
    )
    assert s.DEFAULT_DEV_API_KEY is None


def test_production_guard_accepts_clean_production_settings():
    """Production mode with high-entropy SECRET_KEY and cleared dev key must succeed."""
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="super_secure_random_production_secret_key_12345",
        DEFAULT_DEV_API_KEY="",
    )
    assert s.ENVIRONMENT == "production"
    assert s.DEFAULT_DEV_API_KEY == ""


# ============================================================================
# 2. Distributed Rate Limiter & Fallback Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limiter_async_fallback_to_in_memory():
    """is_allowed_async gracefully falls back to local in-memory sliding window."""
    limiter = RateLimiter(limit_per_hour=2, max_tracked=10)
    # No Redis connected, falls back to memory
    allowed1, remaining1, _ = await limiter.is_allowed_async("user_token_1")
    assert allowed1 is True
    assert remaining1 == 1

    allowed2, remaining2, _ = await limiter.is_allowed_async("user_token_1")
    assert allowed2 is True
    assert remaining2 == 0

    allowed3, remaining3, retry_after = await limiter.is_allowed_async("user_token_1")
    assert allowed3 is False
    assert remaining3 == 0
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rate_limiter_async_with_mock_redis():
    """Verify is_allowed_async sliding window with simulated Redis pipeline."""

    class MockPipeline:
        def __init__(self):
            self.actions = []

        def zremrangebyscore(self, key, min_score, max_score):
            self.actions.append(("zremrangebyscore", key))
            return self

        def zcard(self, key):
            self.actions.append(("zcard", key))
            return self

        def zrange(self, key, start, stop, withscores=False):
            self.actions.append(("zrange", key))
            return self

        def zadd(self, key, mapping):
            self.actions.append(("zadd", key, mapping))
            return self

        def expire(self, key, seconds):
            self.actions.append(("expire", key, seconds))
            return self

        async def execute(self):
            # Simulate count = 0, oldest = []
            return [0, 0, []]

    class MockRedis:
        def pipeline(self):
            return MockPipeline()

    limiter = RateLimiter(limit_per_hour=50)
    limiter._redis_client = MockRedis()

    allowed, remaining, retry_after = await limiter.is_allowed_async("distributed_token")
    assert allowed is True
    assert remaining == 49
    assert retry_after == 0


# ============================================================================
# 3. Heuristic Engine: False Positive Reduction Tests
# ============================================================================


def test_heuristic_security_ignores_commented_sqli():
    """SQL injection patterns in comments must NOT be flagged."""
    commented_code = """
# query = "SELECT * FROM users WHERE id = " + user_id
// db.execute(f"SELECT * FROM users WHERE id = {user_id}")
/* SELECT * FROM accounts WHERE id = ' + account_id */
def get_user_safe(user_id):
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
"""
    findings, score = HeuristicEngine.analyze_security(commented_code)
    sqli = [f for f in findings if f.category == "injection"]
    assert len(sqli) == 0
    assert score == 100.0


def test_heuristic_security_ignores_placeholder_credentials():
    """Placeholder credentials and template variables must not trigger false positives."""
    code_with_placeholders = """
API_KEY = "your_api_key_here"
SECRET = "dummy_secret_placeholder"
AUTH_TOKEN = "${YOUR_AUTH_TOKEN}"
OPENAI_KEY = "sk-placeholder-do-not-use"
"""
    findings, score = HeuristicEngine.analyze_security(code_with_placeholders)
    secrets = [f for f in findings if f.category == "secrets"]
    assert len(secrets) == 0
    assert score == 100.0


def test_heuristic_security_ignores_mock_in_test_files():
    """Test files with dummy keys should not trigger CRITICAL secret leaks."""
    test_code = """
def test_login():
    api_key = "abcdef1234567890abcdef"
    assert api_key is not None
"""
    findings, score = HeuristicEngine.analyze_security(test_code, filename="tests/test_auth.py")
    secrets = [f for f in findings if f.category == "secrets"]
    assert len(secrets) == 0
    assert score == 100.0


# ============================================================================
# 4. Advanced Architecture Agent & Heuristics
# ============================================================================


def test_heuristic_architecture_detects_god_class():
    """Classes with excessive methods (>15) must trigger God Object warning."""
    methods = "\n".join([f"    def action_{i}(self):\n        pass" for i in range(18)])
    god_class_code = f"""
class MonolithicManager:
{methods}
"""
    findings, score = HeuristicEngine.analyze_architecture(god_class_code, filename="manager.py")
    god_findings = [f for f in findings if f.category == "modularity"]
    assert len(god_findings) > 0
    assert "God Object" in god_findings[0].title
    assert score < 100.0


def test_heuristic_architecture_detects_circular_self_import():
    """Module importing itself must be flagged as circular self-import risk."""
    circular_code = """
import order_service
from order_service import process_order

def place_order():
    return process_order()
"""
    findings, score = HeuristicEngine.analyze_architecture(circular_code, filename="order_service.py")
    cyclic = [f for f in findings if f.category == "dependency"]
    assert len(cyclic) > 0
    assert "Circular Self-Import" in cyclic[0].title


def test_heuristic_architecture_detects_tramp_data():
    """Functions with excessive parameters (>=7) must be flagged."""
    tramp_code = """
def create_customer(first, last, email, phone, street, city, state, zip_code):
    return True
"""
    findings, score = HeuristicEngine.analyze_architecture(tramp_code)
    tramp = [f for f in findings if "Tramp" in f.id or "Excessive Function Parameters" in f.title]
    assert len(tramp) > 0


@pytest.mark.asyncio
async def test_architecture_agent_capabilities():
    """ArchitectureAgent lists advanced architectural analysis capabilities."""
    agent = ArchitectureAgent()
    caps = agent.get_capabilities()
    assert "God Object & Low Cohesion Class Detection" in caps
    assert "High Fan-Out & External Coupling Analysis" in caps


# ============================================================================
# 5. Schema Harmonization Tests
# ============================================================================


def test_review_results_schema_and_dictionary_access():
    """ReviewResults supports both attribute and dict-like key access for backwards compatibility."""
    results = ReviewResults(
        overall_score=92.5,
        severity_summary={"critical": 0, "high": 1, "medium": 0, "low": 2, "info": 1},
        agents=[{"name": "security", "score": 100.0}],
    )
    assert results.overall_score == 92.5
    assert results["overall_score"] == 92.5
    assert results.get("overall_score") == 92.5
    assert results["severity_summary"]["high"] == 1
    assert len(results["agents"]) == 1

    resp = CodeReviewResponse(
        review_id="rev_10_out_of_10",
        status="completed",
        created_at="2026-11-13T20:00:00Z",
        results=results,
    )
    assert resp.results["overall_score"] == 92.5
    serialized = resp.model_dump()
    assert serialized["results"]["overall_score"] == 92.5
