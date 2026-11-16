"""
Milestone 3 & 4 Verification Suite:
Tests Orchestrator Reliability, Agent Crash Scoring, Cache Poisoning Prevention,
WebSocket Authentication, and Connection Cleanup.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.api.app import app
from cerberus.api.v1.review import ws_connections
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.security import generate_api_key, hash_api_key
from cerberus.core.database import AsyncSessionLocal
from cerberus.models.database import ApiKeyRecord
from cerberus.models.schemas import CodeReviewRequest


@pytest.mark.asyncio
async def test_orchestrator_agent_crash_scoring_and_degraded_status():
    """Verify that crashed agents score 0.0 and review status is degraded."""
    orchestrator = ReviewOrchestrator()

    # Mock the security agent to raise an unhandled exception
    with patch.object(
        orchestrator.registry["security"], "analyze", side_effect=RuntimeError("Simulated LLM network timeout or crash")
    ):
        request = CodeReviewRequest(code="def sample(): pass", language="python", agents=["security", "performance"])
        response = await orchestrator.execute_review(request)

        # Status must be degraded, not completed
        assert response.status == "degraded"

        # Security agent must be recorded as failed with 0.0 score
        results_agents = {a["name"]: a for a in response.results["agents"]}
        assert results_agents["security"]["status"] == "failed"
        assert results_agents["security"]["score"] == 0.0
        assert "Simulated LLM network timeout or crash" in results_agents["security"]["error"]

        # Performance agent should have completed normally
        assert results_agents["performance"]["status"] == "completed"
        assert results_agents["performance"]["score"] == 100.0

        # Overall score must reflect the 0.0 from security (weight 0.40) and 100.0 from performance (weight 0.25)
        # Expected: (0*0.40 + 100*0.25) / (0.40 + 0.25) = 25 / 0.65 = 38.5
        assert response.overall_score == pytest.approx(38.5, rel=1e-1)


@pytest.mark.asyncio
async def test_orchestrator_prevents_cache_poisoning_on_failure():
    """Verify that degraded or failed reviews are never written to cache."""
    orchestrator = ReviewOrchestrator()
    unique_code = "def unique_func_cache_test_failure(): pass"

    # Compute expected cache key
    cache_key = cache_manager.compute_cache_key(code=unique_code, language="python", agents=["security"])
    # Ensure cache is clean before test
    if cache_key in cache_manager._memory_cache:
        del cache_manager._memory_cache[cache_key]

    with patch.object(orchestrator.registry["security"], "analyze", side_effect=Exception("Crash during analysis")):
        request = CodeReviewRequest(code=unique_code, language="python", agents=["security"])
        response = await orchestrator.execute_review(request)
        assert response.status == "failed"

        # Cache must NOT contain this failed result
        cached = await cache_manager.get(cache_key)
        assert cached is None, "Failed review was erroneously saved to cache!"


@pytest.mark.asyncio
async def test_orchestrator_all_agents_crash():
    """Verify that when all active agents crash, review status is 'failed' and score is 0.0."""
    orchestrator = ReviewOrchestrator()

    with (
        patch.object(orchestrator.registry["security"], "analyze", side_effect=Exception("Fail 1")),
        patch.object(orchestrator.registry["performance"], "analyze", side_effect=Exception("Fail 2")),
    ):
        request = CodeReviewRequest(code="def sample(): pass", language="python", agents=["security", "performance"])
        response = await orchestrator.execute_review(request)

        assert response.status == "failed"
        assert response.overall_score == 0.0


def test_websocket_rejects_unauthenticated_connection():
    """Verify WebSocket endpoint closes connection when token is omitted."""
    client = TestClient(app)
    review_id = "rev_test_ws_auth_fail"

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/review/{review_id}/ws"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_rejects_invalid_token():
    """Verify WebSocket endpoint closes connection when token is invalid."""
    client = TestClient(app)
    review_id = "rev_test_ws_invalid_key"

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/review/{review_id}/ws?token=cvai_fake_invalid_token_999"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_accepts_valid_dev_token():
    """Verify WebSocket endpoint accepts connection with valid token via Authorization header."""
    client = TestClient(app)
    review_id = "rev_test_ws_valid_dev"

    with client.websocket_connect(
        f"/api/v1/review/{review_id}/ws",
        headers={"Authorization": f"Bearer {settings.DEFAULT_DEV_API_KEY}"},
    ) as ws:
        msg = ws.receive_json()
        assert msg["event"] == "connected"
        assert msg["review_id"] == review_id


def test_websocket_connection_cleanup_on_disconnect():
    """Verify that disconnecting clients are properly removed from ws_connections memory store."""
    client = TestClient(app)
    review_id = "rev_test_ws_cleanup"

    # Before connection, review_id not in ws_connections
    assert review_id not in ws_connections

    with client.websocket_connect(
        f"/api/v1/review/{review_id}/ws",
        headers={"Authorization": f"Bearer {settings.DEFAULT_DEV_API_KEY}"},
    ) as ws:
        msg = ws.receive_json()
        assert msg["event"] == "connected"
        # Connection should now be registered
        assert review_id in ws_connections
        assert len(ws_connections[review_id]) == 1

    # After exiting context (disconnect), review_id must be completely cleaned up
    assert review_id not in ws_connections, "WebSocket disconnect leaked connection in ws_connections!"
