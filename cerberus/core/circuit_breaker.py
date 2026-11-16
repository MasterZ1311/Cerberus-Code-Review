"""
Circuit Breaker Pattern for External LLM Providers and Remote Services.
Prevents cascading failures, reduces wasted network latency, and allows self-healing.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from cerberus.core.exceptions import CircuitBreakerOpenError

logger = logging.getLogger("cerberus.circuit_breaker")


class CircuitState(str, Enum):
    """Possible states of the circuit breaker."""

    CLOSED = "closed"  # Normal: calls are passed through
    OPEN = "open"  # Failing: calls fail fast immediately
    HALF_OPEN = "half_open"  # Recovery trial: allowing limited probe requests


class CircuitBreaker:
    """
    Asynchronous stateful circuit breaker.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """
        Execute an asynchronous callable protected by the circuit breaker.
        """
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.OPEN:
                if self.opened_at is not None and (now - self.opened_at) >= self.recovery_timeout:
                    logger.info(
                        "Circuit breaker for '%s' transitioned from OPEN to HALF_OPEN (trial probe enabled)",
                        self.name,
                    )
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    remaining = (
                        self.recovery_timeout - (now - self.opened_at)
                        if self.opened_at is not None
                        else self.recovery_timeout
                    )
                    logger.warning(
                        "Circuit breaker for '%s' is OPEN. Rejecting call fast (remaining timeout: %.1fs)",
                        self.name,
                        remaining,
                    )
                    raise CircuitBreakerOpenError(provider_name=self.name, recovery_timeout=max(0.0, remaining))

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            await self._on_failure(exc)
            raise

    async def _on_success(self) -> None:
        """Handle successful execution."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.debug(
                    "Circuit breaker '%s' trial success %d/%d",
                    self.name,
                    self.success_count,
                    self.success_threshold,
                )
                if self.success_count >= self.success_threshold:
                    logger.info("Circuit breaker for '%s' recovered and transitioned to CLOSED", self.name)
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.opened_at = None
            else:
                self.failure_count = 0

    async def _on_failure(self, exc: Exception) -> None:
        """Handle failed execution."""
        async with self._lock:
            self.failure_count += 1
            logger.warning(
                "Circuit breaker '%s' recorded failure (%s). Count: %d/%d (state: %s)",
                self.name,
                type(exc).__name__,
                self.failure_count,
                self.failure_threshold,
                self.state.value,
            )
            if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                logger.error(
                    "Circuit breaker for '%s' tripped and transitioned to OPEN for %.1fs due to failures",
                    self.name,
                    self.recovery_timeout,
                )

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic state dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "is_available": self.state != CircuitState.OPEN,
        }


# Registry for managing breakers across providers
_registry: Dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 2,
) -> CircuitBreaker:
    """Retrieve or register a circuit breaker by provider name."""
    if name not in _registry:
        _registry[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
        )
    return _registry[name]
