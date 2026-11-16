"""
Team Style Conventions Plugin for cerberus</>.
Enforces organization coding standards via pre/post review lifecycle hooks.
"""

from typing import Any, Dict, List

from cerberus.core.plugins import BasePlugin
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse


class TeamStyleConventionsPlugin(BasePlugin):
    name: str = "team_conventions"
    version: str = "1.0.0"
    description: str = "Corporate team coding standards and production logging enforcement"
    author: str = "Cerberus Quality Engineering"
    is_enabled: bool = True

    def get_custom_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "python": [
                {
                    "id": "QUAL-PRINT-STMT",
                    "pattern": r"(?<!\w)print\s*\(",
                    "severity": "LOW",
                    "category": "code_quality",
                    "title": "Raw 'print()' Statement in Production Code",
                    "message": "Use structured logging (logger.info/error) instead of stdout print statements.",
                    "recommendation": "Replace print() with structured logger.",
                    "suggestion": 'logger.info("Message")',
                    "cwe_id": "CWE-1077",
                }
            ]
        }

    async def pre_review_hook(self, request: CodeReviewRequest) -> CodeReviewRequest:
        """Injects team-specific metadata into review context."""
        if request.context is None:
            from cerberus.models.schemas import ReviewContext

            request.context = ReviewContext(custom={"team_convention_enforced": True})
        elif request.context.custom is None:
            request.context.custom = {"team_convention_enforced": True}
        else:
            request.context.custom["team_convention_enforced"] = True
        return request

    async def post_review_hook(self, response: CodeReviewResponse) -> CodeReviewResponse:
        """Appends team convention audit badge into results summary."""
        if response.results and isinstance(response.results, dict):
            response.results["team_conventions_verified"] = True
        return response


# Alias for backward compatibility & testing
TeamStylePlugin = TeamStyleConventionsPlugin
