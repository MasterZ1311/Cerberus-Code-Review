"""
Google Gemini Foundation Model Provider.
Supports Gemini 1.5 Flash, Gemini 1.5 Pro, and Gemini 2.0 Flash via Google Generative Language API.
"""

import logging
import os
from typing import Optional

from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.gemini")


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__()
        self.api_key: Optional[str] = api_key or settings.GEMINI_API_KEY
        self.model: str = model or settings.GEMINI_MODEL

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")

    @property
    def effective_model(self) -> str:
        return self.model or settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"

    async def is_available(self) -> bool:
        key = self.effective_api_key
        return bool(key and len(key) > 5)

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            return None

        try:
            model = self.effective_model
            client = await self.get_client()
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\nUser Request:\n{user_prompt}"}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048,
                },
            }

            # Try v1 first, then v1beta
            for api_version in ("v1", "v1beta"):
                url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={self.effective_api_key}"

                async def _req(target_url=url):
                    return await client.post(target_url, json=payload, headers=headers, timeout=25.0)

                res = await self.execute_request_with_retry(_req)
                if res is not None and getattr(res, "status_code", 0) == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and len(candidates) > 0:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and len(parts) > 0:
                            return parts[0].get("text")
                elif res is not None and getattr(res, "status_code", 0) != 404:
                    logger.warning(f"Gemini API request ({api_version}) returned HTTP {res.status_code}: {res.text}")
                    break
        except Exception as e:
            logger.warning(f"Gemini generation failed: {e}")
        return None
