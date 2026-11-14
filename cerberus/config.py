"""
cerberus</> Configuration Management using Pydantic Settings.
Supports loading from environment variables and .env files.
"""

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


INSECURE_DEFAULT_SECRETS = {
    "cerberus_dev_secret_key_change_in_production_32chars",
    "cerberus_production_secret_key_change_me_now_1234",
    "change_me_in_production",
    "secret",
    "changeme",
    "password",
    "admin",
}

INSECURE_DEFAULT_DEV_KEYS = {
    "cvai_dev_key_123",
    "dev_key",
    "test_key",
    "default",
}

_ENV_FALLBACK = str(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", _ENV_FALLBACK),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 5173
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Security Settings
    SECRET_KEY: str = "cerberus_dev_secret_key_change_in_production_32chars"
    API_KEY_PREFIX: str = "cvai_"
    RATE_LIMIT_PER_HOUR: int = 100
    RATE_LIMIT_MAX_TRACKED: int = 10000
    DEFAULT_DEV_API_KEY: Optional[str] = "cvai_dev_key_123"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./cerberus.db"

    # Cache Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 604800  # 7 days
    CACHE_MAX_ITEMS: int = 1000

    # LLM Provider Configuration (Supports multi-provider, auto-detection, and per-agent routing)
    LLM_PROVIDER: str = "auto"  # Options: auto, openai, anthropic, gemini, groq, deepseek, openrouter, ollama, heuristic, watsonx

    # Provider Credentials & Model Settings
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_BASE_URL: Optional[str] = None

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-chat"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "auto"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "codellama"

    # Optional / Legacy IBM watsonx (optional backwards compatibility)
    WATSONX_API_KEY: Optional[str] = None
    WATSONX_PROJECT_ID: Optional[str] = None
    WATSONX_URL: str = "https://us-south.ml.cloud.ibm.com"
    WATSONX_MODEL_ID: str = "ibm/granite-3-8b-instruct"

    # Per-Agent Provider Overrides (assign different providers/keys to different agents)
    SECURITY_AGENT_PROVIDER: Optional[str] = None
    PERFORMANCE_AGENT_PROVIDER: Optional[str] = None
    QUALITY_AGENT_PROVIDER: Optional[str] = None
    ARCHITECTURE_AGENT_PROVIDER: Optional[str] = None
    COMPLIANCE_AGENT_PROVIDER: Optional[str] = None
    FIXER_AGENT_PROVIDER: Optional[str] = None
    CONSENSUS_AGENT_PROVIDER: Optional[str] = None

    # Multi-Agent Collaboration Settings
    COLLABORATIVE_MODE: bool = True
    AUTO_GENERATE_FIXES: bool = True

    # Active Agents
    ENABLED_AGENTS: str = "security,performance,quality,architecture,compliance"

    # Review Tuning
    SEVERITY_THRESHOLD: str = "medium"
    BLOCKING_MODE: bool = False
    PROMETHEUS_ENABLED: bool = True
    MAX_CONCURRENT_BATCH_REVIEWS: int = 5
    MAX_BATCH_SIZE: int = 100

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def enabled_agents_list(self) -> List[str]:
        return [a.strip().lower() for a in self.ENABLED_AGENTS.split(",") if a.strip()]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT.lower() in ("production", "prod"):
            if not self.SECRET_KEY or self.SECRET_KEY in INSECURE_DEFAULT_SECRETS:
                raise ValueError(
                    "Production configuration error: Insecure default SECRET_KEY is not permitted in production. "
                    "Set a unique, high-entropy SECRET_KEY via environment variable."
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "Production configuration error: SECRET_KEY must be at least 32 characters long in production."
                )
            # In production, automatically nullify default dev key to ensure dev fallback is disabled
            if self.DEFAULT_DEV_API_KEY and (
                self.DEFAULT_DEV_API_KEY in INSECURE_DEFAULT_DEV_KEYS
                or "dev_key" in self.DEFAULT_DEV_API_KEY.lower()
            ):
                self.DEFAULT_DEV_API_KEY = None
        return self


# Global singleton settings instance
settings = Settings()
