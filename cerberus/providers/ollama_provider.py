"""
Local Ollama LLM Provider for Air-Gapped & Privacy-Preserving Deployments.
"""

import logging
import os
from typing import Optional
import httpx
from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.ollama")


class OllamaProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__()
        self.base_url: str = settings.OLLAMA_BASE_URL
        self.model: str = settings.OLLAMA_MODEL

    @property
    def effective_base_url(self) -> str:
        return self.base_url or settings.OLLAMA_BASE_URL or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"

    @property
    def effective_model(self) -> str:
        return self.model or settings.OLLAMA_MODEL or os.getenv("OLLAMA_MODEL") or "codellama"

    async def is_available(self) -> bool:
        try:
            client = await self.get_client()
            res = await client.get(f"{self.effective_base_url}/api/tags", timeout=1.0)
            return res.status_code == 200
        except Exception:
            return False

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        try:
            payload = {
                "model": self.effective_model,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False
            }
            client = await self.get_client()
            res = await client.post(f"{self.effective_base_url}/api/generate", json=payload, timeout=30.0)
            if res.status_code == 200:
                return res.json().get("response")
            else:
                logger.warning(f"Ollama generation request returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Ollama generation failed: {e}")
        return None
