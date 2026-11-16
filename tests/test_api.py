"""
Integration Tests for FastAPI REST Endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "active_agents" in data


@pytest.mark.asyncio
async def test_list_agents_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/agents", headers={"Authorization": "Bearer cvai_dev_key_123"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 3
        agent_names = [a["name"] for a in data]
        assert "security" in agent_names
        assert "performance" in agent_names
        assert "quality" in agent_names


@pytest.mark.asyncio
async def test_submit_review_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"code": "def hello():\n    print('Hello World')", "language": "python"}
        res = await client.post("/api/v1/review", json=payload, headers={"Authorization": "Bearer cvai_dev_key_123"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert "review_id" in data
        assert data["overall_score"] is not None

        # Verify retrieval
        rev_id = data["review_id"]
        res_get = await client.get(f"/api/v1/review/{rev_id}", headers={"Authorization": "Bearer cvai_dev_key_123"})
        assert res_get.status_code == 200
        assert res_get.json()["review_id"] == rev_id
