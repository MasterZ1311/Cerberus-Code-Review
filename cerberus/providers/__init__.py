"""
LLM and Analysis Providers Package.
Includes IBM watsonx, OpenAI, Ollama, and offline Heuristic AST engine.
"""

import logging
from typing import Dict, Optional
from cerberus.config import settings
from cerberus.providers.base import BaseLLMProvider
from cerberus.providers.heuristic_engine import HeuristicEngine
from cerberus.providers.watsonx_provider import WatsonxProvider
from cerberus.providers.openai_provider import OpenAIProvider
from cerberus.providers.ollama_provider import OllamaProvider

logger = logging.getLogger("cerberus.providers")

_provider_registry: Dict[str, BaseLLMProvider] = {}


def get_llm_provider(provider_type: Optional[str] = None) -> Optional[BaseLLMProvider]:
    """
    Returns the active singleton LLM provider instance for the configured provider type.
    Options: 'watsonx', 'openai', 'ollama', 'heuristic'
    Returns None if provider is 'heuristic' (zero-config local analysis).
    """
    ptype = (provider_type or settings.LLM_PROVIDER or "heuristic").strip().lower()
    if ptype in ("heuristic", "offline", "none", ""):
        return None

    if ptype not in _provider_registry:
        if ptype == "watsonx":
            _provider_registry[ptype] = WatsonxProvider()
        elif ptype == "openai":
            _provider_registry[ptype] = OpenAIProvider()
        elif ptype == "ollama":
            _provider_registry[ptype] = OllamaProvider()
        else:
            logger.warning(f"Unrecognized LLM_PROVIDER '{ptype}'; falling back to heuristic engine.")
            return None

    return _provider_registry[ptype]


async def close_all_providers() -> None:
    """Gracefully close all active provider client sessions."""
    for p in list(_provider_registry.values()):
        try:
            await p.close()
        except Exception as e:
            logger.warning(f"Error closing provider session: {e}")
    _provider_registry.clear()


__all__ = [
    "BaseLLMProvider",
    "HeuristicEngine",
    "WatsonxProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "get_llm_provider",
    "close_all_providers",
]
