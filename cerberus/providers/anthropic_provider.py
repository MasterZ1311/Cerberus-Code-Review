"""
Anthropic Claude Foundation Model Provider.
Supports Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus via standard Anthropic Messages API.
"""

import logging
import os
from typing import Optional

from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.anthropic")


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__()
        self.api_key: Optional[str] = api_key or settings.ANTHROPIC_API_KEY
        self.model: str = model or settings.ANTHROPIC_MODEL

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")

    @property
    def effective_model(self) -> str:
        return self.model or settings.ANTHROPIC_MODEL or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-20241022"

    async def is_available(self) -> bool:
        key = self.effective_api_key
        return bool(key and len(key) > 10)

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            return None

        try:
            headers = {
                "x-api-key": self.effective_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self.effective_model,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.1,
            }
            client = await self.get_client()
            url = "https://api.anthropic.com/v1/messages"

            async def _req():
                return await client.post(url, json=payload, headers=headers, timeout=25.0)

            res = await self.execute_request_with_retry(_req)
            if res is not None and getattr(res, "status_code", 0) == 200:
                data = res.json()
                content = data.get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text")
            elif res is not None:
                logger.warning(f"Anthropic API request returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Anthropic completion failed: {e}")
        return None
