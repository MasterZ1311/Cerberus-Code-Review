"""
OpenAI & Azure Compatible LLM Provider.
"""

import logging
import os
from typing import Optional
import httpx
from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.openai")


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__()
        self.api_key: Optional[str] = settings.OPENAI_API_KEY
        self.model: str = settings.OPENAI_MODEL

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")

    @property
    def effective_model(self) -> str:
        return self.model or settings.OPENAI_MODEL or os.getenv("OPENAI_MODEL") or "gpt-4o"

    async def is_available(self) -> bool:
        key = self.effective_api_key
        return bool(key and len(key) > 10)

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.effective_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.effective_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            client = await self.get_client()
            res = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=20.0)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    return choices[0].get("message", {}).get("content")
            else:
                logger.warning(f"OpenAI API request returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"OpenAI completion failed: {e}")
        return None
