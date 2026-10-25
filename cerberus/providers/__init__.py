"""
LLM and Analysis Providers Package.
Includes multi-provider support: OpenAI, Anthropic Claude, Google Gemini, Groq, DeepSeek,
Ollama, IBM watsonx (optional), and the offline Heuristic AST engine.
Supports auto-detection of configured keys and per-agent provider routing.
"""

import logging
import os
from typing import Dict, Optional
from cerberus.config import settings
from cerberus.providers.anthropic_provider import AnthropicProvider
from cerberus.providers.base import BaseLLMProvider
from cerberus.providers.deepseek_provider import DeepSeekProvider
from cerberus.providers.gemini_provider import GeminiProvider
from cerberus.providers.groq_provider import GroqProvider
from cerberus.providers.heuristic_engine import HeuristicEngine
from cerberus.providers.ollama_provider import OllamaProvider
from cerberus.providers.openai_provider import OpenAIProvider
from cerberus.providers.watsonx_provider import WatsonxProvider

logger = logging.getLogger("cerberus.providers")

_provider_registry: Dict[str, BaseLLMProvider] = {}


def resolve_auto_provider() -> str:
    """
    Auto-detects the active provider by checking which API key is present in environment/settings.
    Prioritizes fast & modern providers: Groq > OpenAI > Anthropic > Gemini > DeepSeek > Watsonx.
    Falls back to 'heuristic' if no credentials are configured.
    """
    if os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", None):
        return "groq"
    if os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None):
        return "gemini"
    if os.getenv("DEEPSEEK_API_KEY") or getattr(settings, "DEEPSEEK_API_KEY", None):
        return "deepseek"
    if os.getenv("WATSONX_API_KEY") or getattr(settings, "WATSONX_API_KEY", None):
        return "watsonx"
    return "heuristic"


def get_llm_provider(
    provider_type: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Optional[BaseLLMProvider]:
    """
    Returns the active singleton LLM provider instance.
    Supports per-agent overrides (e.g. SECURITY_AGENT_PROVIDER=anthropic, PERFORMANCE_AGENT_PROVIDER=groq).
    If provider_type is 'auto', automatically detects configured credentials.
    Returns None if provider resolves to 'heuristic' (zero-config local AST engine).
    """
    # 1. Check for per-agent provider override if agent_name is given
    target_type = provider_type
    if agent_name:
        agent_override = getattr(settings, f"{agent_name.upper()}_AGENT_PROVIDER", None) or os.getenv(f"{agent_name.upper()}_AGENT_PROVIDER") or os.getenv(f"{agent_name.upper()}_PROVIDER")
        if agent_override:
            target_type = agent_override

    # 2. Default to global settings.LLM_PROVIDER
    if not target_type:
        target_type = settings.LLM_PROVIDER or "auto"

    ptype = str(target_type).strip().lower()

    # 3. Resolve auto-detection
    if ptype in ("auto", "detect", ""):
        ptype = resolve_auto_provider()

    # 4. Handle heuristic / offline
    if ptype in ("heuristic", "offline", "none", "local_ast"):
        return None

    # 5. Instantiate or retrieve cached provider
    if ptype not in _provider_registry:
        if ptype == "openai":
            _provider_registry[ptype] = OpenAIProvider()
        elif ptype == "anthropic":
            _provider_registry[ptype] = AnthropicProvider()
        elif ptype == "gemini":
            _provider_registry[ptype] = GeminiProvider()
        elif ptype == "groq":
            _provider_registry[ptype] = GroqProvider()
        elif ptype == "deepseek":
            _provider_registry[ptype] = DeepSeekProvider()
        elif ptype == "ollama":
            _provider_registry[ptype] = OllamaProvider()
        elif ptype == "watsonx":
            _provider_registry[ptype] = WatsonxProvider()
        else:
            logger.warning(f"Unrecognized LLM provider '{ptype}'; falling back to heuristic engine.")
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
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "GroqProvider",
    "DeepSeekProvider",
    "OllamaProvider",
    "WatsonxProvider",
    "get_llm_provider",
    "resolve_auto_provider",
    "close_all_providers",
]
