"""
IBM watsonx Foundation Model Provider.
Integrates with IBM watsonx Orchestrate / watsonx.ai foundation models via IBM Cloud IAM OAuth.
"""

import logging
import os
import time
from typing import Optional
import httpx
from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider

logger = logging.getLogger("cerberus.providers.watsonx")


class WatsonxProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__()
        self.api_key: Optional[str] = settings.WATSONX_API_KEY
        self.project_id: Optional[str] = settings.WATSONX_PROJECT_ID
        self.endpoint: str = settings.WATSONX_URL
        self.model_id: str = settings.WATSONX_MODEL_ID
        self._iam_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def effective_api_key(self) -> Optional[str]:
        return self.api_key or settings.WATSONX_API_KEY or os.getenv("WATSONX_API_KEY")

    @property
    def effective_project_id(self) -> Optional[str]:
        return self.project_id or settings.WATSONX_PROJECT_ID or os.getenv("WATSONX_PROJECT_ID")

    @property
    def effective_endpoint(self) -> str:
        return self.endpoint or settings.WATSONX_URL or os.getenv("WATSONX_URL") or "https://us-south.ml.cloud.ibm.com"

    @property
    def effective_model_id(self) -> str:
        return self.model_id or settings.WATSONX_MODEL_ID or os.getenv("WATSONX_MODEL_ID") or "ibm/granite-3-8b-instruct"

    async def is_available(self) -> bool:
        return bool(self.effective_api_key and self.effective_project_id)

    async def _get_iam_token(self) -> Optional[str]:
        """
        Exchanges IBM Cloud API key for IAM OAuth bearer token and caches it.
        Refreshes when within 60 seconds of expiry.
        """
        api_key = self.effective_api_key
        if not api_key:
            return None

        # Return cached token if valid for at least another 60 seconds
        if self._iam_token and time.time() < (self._token_expires_at - 60):
            return self._iam_token

        try:
            client = await self.get_client()
            url = "https://iam.cloud.ibm.com/identity/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
            data = {
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": api_key,
            }
            res = await client.post(url, data=data, headers=headers, timeout=15.0)
            if res.status_code == 200:
                payload = res.json()
                token = payload.get("access_token")
                expires_in = payload.get("expires_in", 3600)
                if token:
                    self._iam_token = token
                    self._token_expires_at = time.time() + float(expires_in)
                    return self._iam_token
            logger.warning(f"Failed to obtain IBM IAM token: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.warning(f"Error fetching IBM IAM token: {e}")
        return None

    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not await self.is_available():
            logger.debug("IBM watsonx credentials not configured; deferring to heuristic evaluator.")
            return None

        token = await self._get_iam_token()
        if not token:
            logger.warning("IBM watsonx IAM token exchange failed; falling back to heuristic evaluator.")
            return None

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = {
                "model_id": self.effective_model_id,
                "project_id": self.effective_project_id,
                "input": f"{system_prompt}\n\n{user_prompt}",
                "parameters": {
                    "decoding_method": "greedy",
                    "max_new_tokens": 2048,
                    "repetition_penalty": 1.05,
                },
            }
            client = await self.get_client()
            endpoint_base = self.effective_endpoint.rstrip("/")
            url = f"{endpoint_base}/ml/v1/text/generation?version=2023-05-29"
            res = await client.post(url, json=payload, headers=headers, timeout=20.0)
            if res.status_code == 200:
                data = res.json()
                results = data.get("results")
                if results and len(results) > 0:
                    return results[0].get("generated_text")
            else:
                logger.warning(f"watsonx API request returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"watsonx API request failed: {e}")
        return None
