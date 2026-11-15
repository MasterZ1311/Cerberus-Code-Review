"""
Base Class Interface for all Cerberus Code Review Agents.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from cerberus.models.schemas import AgentResult


class BaseAgent(ABC):
    """Abstract Base Class for all specialized review agents."""

    name: str = "base_agent"
    version: str = "1.0.0"
    purpose: str = "Base code review agent"

    @abstractmethod
    async def analyze(
        self, code: str, language: str = "python", context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze code snippet and return structured findings and score.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of specific checks and capabilities provided by this agent."""
        pass

    async def health_check(self) -> bool:
        """Verify that agent is operational and ready to receive review tasks."""
        return True
