"""
DeepSeek Foundation Model Provider.
Supports DeepSeek-Chat and DeepSeek-Coder via DeepSeek API.
"""

import logging
import os
from typing import Optional

from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.deepseek")


class DeepSeekProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__()
        self.api_key: Optional[str] = api_key or settings.DEEPSEEK_API_KEY
        self.model: str = model or settings.DEEPSEEK_MODEL

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY")

    @property
    def effective_model(self) -> str:
        return self.model or settings.DEEPSEEK_MODEL or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

    async def is_available(self) -> bool:
        key = self.effective_api_key
        return bool(key and len(key) > 10)

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.effective_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.effective_model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            client = await self.get_client()
            url = "https://api.deepseek.com/chat/completions"

            async def _req():
                return await client.post(url, json=payload, headers=headers, timeout=25.0)

            res = await self.execute_request_with_retry(_req)
            if res is not None and getattr(res, "status_code", 0) == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    return choices[0].get("message", {}).get("content")
            elif res is not None:
                logger.warning(f"DeepSeek API request returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"DeepSeek generation failed: {e}")
        return None
