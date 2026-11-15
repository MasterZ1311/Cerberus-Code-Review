"""
Agents Metadata Endpoint: Lists available specialized review agents and capabilities.
"""

from typing import List

from fastapi import APIRouter, Depends

from cerberus.agents.orchestrator import orchestrator
from cerberus.api.dependencies import verify_api_key
from cerberus.models.schemas import AgentInfo

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.get("", response_model=List[AgentInfo])
async def list_agents(api_key: str = Depends(verify_api_key)):
    """Retrieve all available code review agents, current status, and operational capabilities."""
    return orchestrator.list_agents()
