"""
Cerberus Custom Exception Hierarchy.
Provides typed, structured, and granular exceptions for all subsystem operations.
"""

from typing import Any, Dict, Optional


class CerberusError(Exception):
    """Base exception for all Cerberus domain errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(CerberusError):
    """Raised when configuration values, environment variables, or secrets are invalid."""


class ValidationError(CerberusError):
    """Raised when request payload or code input fails domain validation."""


class SecurityError(CerberusError):
    """Base exception for authentication, authorization, or request integrity failures."""


class AuthenticationError(SecurityError):
    """Raised when API key, token, or webhook signature is missing, invalid, or expired."""


class AuthorizationError(SecurityError):
    """Raised when an authenticated actor lacks required scopes for an operation."""


class RateLimitExceededError(SecurityError):
    """Raised when an API key or client IP exceeds their allocated quota."""

    def __init__(self, message: str, retry_after: int = 60, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class AnalysisError(CerberusError):
    """Base exception for analysis, agent coordination, and lint failures."""


class SyntaxParsingError(AnalysisError):
    """Raised when source code cannot be parsed by AST or tree-sitter parsers."""


class ProviderError(CerberusError):
    """Base exception for LLM and heuristic inference provider operations."""

    def __init__(self, message: str, provider_name: str = "unknown", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.provider_name = provider_name


class ProviderTimeoutError(ProviderError):
    """Raised when a remote LLM provider times out."""


class ProviderRateLimitError(ProviderError):
    """Raised when an external LLM provider responds with HTTP 429 Too Many Requests."""


class ProviderAuthError(ProviderError):
    """Raised when an external LLM provider rejects authentication (HTTP 401/403)."""


class ProviderUnavailableError(ProviderError):
    """Raised when an external LLM provider is down or returns HTTP 5xx."""


class CircuitBreakerOpenError(ProviderError):
    """Raised when a call to an LLM provider is rejected because the circuit breaker is OPEN."""

    def __init__(self, provider_name: str, recovery_timeout: float):
        message = f"Circuit breaker is OPEN for provider '{provider_name}'. Calls will be rejected for {recovery_timeout:.1f}s."
        super().__init__(message, provider_name=provider_name, details={"recovery_timeout": recovery_timeout})
        self.recovery_timeout = recovery_timeout


class DatabaseError(CerberusError):
    """Raised when persistent storage operations fail."""


class CacheError(CerberusError):
    """Raised when Redis or cache operations encounter errors."""
