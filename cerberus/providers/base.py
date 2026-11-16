"""
Base Abstract Interface for LLM Providers with Built-in Circuit Breaker & Retry Resilience.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger("cerberus.providers.base")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Fail-fast Circuit Breaker preventing cascading timeouts during cloud provider outages.
    Automatically trips after consecutive errors and recovers gracefully.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering HALF_OPEN state; probing endpoint.")
                return True
            return False
        # HALF_OPEN allows single probe attempt
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker tripped to OPEN state after %s consecutive failures. Fast-failing cloud calls for %ss to fallback to Heuristic Engine.",
                self.failure_count,
                self.recovery_timeout,
            )


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM foundation model integrations."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.circuit_breaker = CircuitBreaker()

    async def get_client(self) -> httpx.AsyncClient:
        """Lazily instantiate or return persistent AsyncClient with connection pooling."""
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
            self._client = httpx.AsyncClient(limits=limits)
        return self._client

    async def close(self) -> None:
        """Gracefully close the persistent client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def execute_request_with_retry(
        self,
        request_fn: Callable[[], Any],
        max_retries: int = 2,
        initial_backoff: float = 0.5,
    ) -> Optional[Any]:
        """
        Executes an HTTP request function with Circuit Breaker inspection and exponential backoff retry.
        Catches transient 429/503 network errors.
        """
        if not self.circuit_breaker.can_execute():
            logger.debug("Circuit breaker is OPEN. Skipping remote LLM call to favor instant heuristic fallback.")
            return None

        delay = initial_backoff
        for attempt in range(max_retries + 1):
            try:
                res = await request_fn()
                if hasattr(res, "status_code"):
                    if res.status_code == 200:
                        self.circuit_breaker.record_success()
                        return res
                    elif res.status_code in (429, 502, 503, 504) and attempt < max_retries:
                        logger.warning(
                            "Provider returned HTTP %s on attempt %s. Retrying in %ss...",
                            res.status_code,
                            attempt + 1,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        delay *= 2.0
                        continue
                    else:
                        self.circuit_breaker.record_failure()
                        return res
                self.circuit_breaker.record_success()
                return res
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < max_retries:
                    logger.warning(
                        "Transient network error (%s) on attempt %s. Retrying in %ss...", exc, attempt + 1, delay
                    )
                    await asyncio.sleep(delay)
                    delay *= 2.0
                else:
                    self.circuit_breaker.record_failure()
                    logger.warning("Remote LLM request failed after %s attempts: %s", max_retries + 1, exc)
                    return None
            except Exception as e:
                self.circuit_breaker.record_failure()
                logger.warning("Unexpected provider error: %s", e)
                return None
        return None

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider credentials and network endpoints are accessible."""
        pass

    @abstractmethod
    async def generate_response(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Generate a raw text response from the model."""
        pass
