"""
OpenRouter LLM Provider Integration.
Enables access to hundreds of open-source and proprietary models via OpenRouter's unified API.
"""

import logging
import os
from typing import Optional

from cerberus.config import settings
from cerberus.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("cerberus.providers.openrouter")


class OpenRouterProvider(OpenAIProvider):
    """
    OpenRouter unified model provider.
    Inherits from OpenAIProvider with OpenRouter-specific endpoints, default models, and attribution headers.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(
            api_key=api_key or settings.OPENROUTER_API_KEY,
            model=model or settings.OPENROUTER_MODEL,
            base_url=base_url or "https://openrouter.ai/api/v1",
        )

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY")

    @property
    def effective_model(self) -> str:
        model = (
            self.model or settings.OPENROUTER_MODEL or os.getenv("OPENROUTER_MODEL") or "anthropic/claude-3.5-sonnet"
        )
        if model.lower() == "auto":
            return "anthropic/claude-3.5-sonnet"
        return model

    @property
    def effective_base_url(self) -> str:
        return "https://openrouter.ai/api/v1"

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.effective_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/MasterZ1311/MultiAgent-CodeReview",
                "X-Title": "Cerberus Code Review AI",
            }
            payload = {
                "model": self.effective_model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            client = await self.get_client()
            url = f"{self.effective_base_url}/chat/completions"

            async def _req():
                return await client.post(url, json=payload, headers=headers, timeout=25.0)

            res = await self.execute_request_with_retry(_req)
            if res is not None and getattr(res, "status_code", 0) == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    return choices[0].get("message", {}).get("content")
            elif res is not None:
                logger.warning(f"OpenRouter API returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"OpenRouter completion failed: {e}")
        return None
