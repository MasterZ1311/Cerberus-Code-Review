"""
Unit Tests for Review Orchestrator Multi-Agent Coordination and Prioritization.
"""

import pytest

from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.models.schemas import CodeReviewRequest, ReviewConfig


@pytest.mark.asyncio
async def test_orchestrator_parallel_execution():
    orchestrator = ReviewOrchestrator()

    request = CodeReviewRequest(
        code="""
API_KEY = "sk-1234567890abcdef12345678"

def bad_func(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    for a in range(10):
        for b in range(10):
            pass
""",
        language="python",
        agents=["security", "performance", "quality"],
    )

    response = await orchestrator.execute_review(request)

    assert response.status == "completed"
    assert response.review_id.startswith("rev_")
    assert response.overall_score is not None
    assert response.overall_score < 70.0
    assert len(response.critical_issues) >= 2  # SQLi + API Key
    assert len(response.warnings) >= 1  # O(n^2) loop


@pytest.mark.asyncio
async def test_orchestrator_blocking_mode():
    orchestrator = ReviewOrchestrator()

    request = CodeReviewRequest(
        code="""
API_KEY = "sk-1234567890abcdef12345678"
""",
        language="python",
        config=ReviewConfig(blocking_mode=True),
    )

    response = await orchestrator.execute_review(request)
    assert response.blocking is True
    assert response.should_block is True
    assert "Blocking threshold triggered" in response.block_reason
