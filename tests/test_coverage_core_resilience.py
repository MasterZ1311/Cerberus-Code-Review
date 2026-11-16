"""
Comprehensive Test Suite for Core Resilience, Distributed SingleFlight, Tracing,
Circuit Breaker, Background Worker Pool, and Per-Key Rate Limiting.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cerberus.config import settings
from cerberus.core.background import BackgroundTaskManager
from cerberus.core.circuit_breaker import CircuitBreaker, CircuitState, get_circuit_breaker
from cerberus.core.distributed_flight import DistributedSingleFlight
from cerberus.core.exceptions import CircuitBreakerOpenError
from cerberus.core.per_key_rate_limiter import PerKeyRateLimiter, TokenBucket
from cerberus.core.tracing import configure_tracing, get_tracer


@pytest.mark.asyncio
async def test_distributed_single_flight_local_coalescing():
    """Verify local in-process SingleFlight coalesces duplicate concurrent keys."""
    flight = DistributedSingleFlight(ttl_seconds=10)
    compute_count = 0

    async def slow_compute():
        nonlocal compute_count
        compute_count += 1
        await asyncio.sleep(0.05)
        return {"data": 42}

    # Launch two concurrent requests with identical key
    res1, res2 = await asyncio.gather(
        flight.execute("test-key", slow_compute),
        flight.execute("test-key", slow_compute),
    )

    assert res1 == {"data": 42}
    assert res2 == {"data": 42}
    assert compute_count == 1  # Only leader executed computation


@pytest.mark.asyncio
async def test_distributed_single_flight_local_exception():
    """Verify local SingleFlight propagates exceptions to all joined callers."""
    flight = DistributedSingleFlight(ttl_seconds=10)

    async def failing_compute():
        await asyncio.sleep(0.02)
        raise ValueError("Computation failed")

    with pytest.raises(ValueError, match="Computation failed"):
        await flight.execute("err-key", failing_compute)


@pytest.mark.asyncio
async def test_distributed_single_flight_redis_leader_follower():
    """Verify distributed Redis lock acquisition, caching, and follower polling."""
    mock_redis = AsyncMock()
    # Leader acquires lock: returns True
    mock_redis.set.side_effect = [True, True]
    mock_redis.delete.return_value = 1

    flight = DistributedSingleFlight(redis_client=mock_redis, ttl_seconds=10)

    async def compute():
        return {"status": "ok"}

    res = await flight.execute("redis-key", compute)
    assert res == {"status": "ok"}
    mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_distributed_single_flight_redis_follower_polling():
    """Verify follower pod polls Redis and retrieves cached result from leader."""
    mock_redis = AsyncMock()
    # Lock acquisition fails (another pod is leader)
    mock_redis.set.return_value = False
    mock_redis.get.return_value = json.dumps({"leader_result": "done"}).encode("utf-8")

    flight = DistributedSingleFlight(redis_client=mock_redis, ttl_seconds=10)

    async def unused_compute():
        return {"should_not": "run"}

    res = await flight.execute("follower-key", unused_compute, timeout_seconds=2.0)
    assert res == {"leader_result": "done"}


@pytest.mark.asyncio
async def test_distributed_single_flight_redis_failure_fallback():
    """Verify Redis errors gracefully fall back to local computation."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = ConnectionError("Redis unreachable")

    flight = DistributedSingleFlight(redis_client=mock_redis, ttl_seconds=10)

    async def compute():
        return "fallback_result"

    res = await flight.execute("redis-err-key", compute)
    assert res == "fallback_result"


def test_tracing_configuration_disabled():
    """Verify configure_tracing is a no-op when ENABLE_TRACING is False."""
    with patch.object(settings, "ENABLE_TRACING", False):
        configure_tracing()
        assert get_tracer() is None


def test_tracing_configuration_import_error():
    """Verify configure_tracing catches missing OpenTelemetry packages gracefully."""
    with patch.object(settings, "ENABLE_TRACING", True):
        with patch.dict("sys.modules", {"opentelemetry": None}):
            configure_tracing()


def test_tracing_configuration_success():
    """Verify configure_tracing initializes tracer with mocked OpenTelemetry components."""
    mock_trace = MagicMock()
    mock_provider = MagicMock()
    mock_trace.get_tracer.return_value = "mock_tracer"

    with patch.object(settings, "ENABLE_TRACING", True):
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry": mock_trace,
                "opentelemetry.trace": mock_trace,
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(),
                "opentelemetry.instrumentation.fastapi": MagicMock(),
                "opentelemetry.instrumentation.httpx": MagicMock(),
                "opentelemetry.instrumentation.redis": MagicMock(),
                "opentelemetry.instrumentation.sqlalchemy": MagicMock(),
                "opentelemetry.sdk.resources": MagicMock(),
                "opentelemetry.sdk.trace": MagicMock(TracerProvider=MagicMock(return_value=mock_provider)),
                "opentelemetry.sdk.trace.export": MagicMock(),
            },
        ):
            configure_tracing()
            assert get_tracer() is not None


@pytest.mark.asyncio
async def test_circuit_breaker_full_lifecycle():
    """Verify CircuitBreaker states: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    breaker = CircuitBreaker("test_breaker", failure_threshold=2, recovery_timeout=0.1, success_threshold=2)

    # 1. Closed state succeeds
    async def ok_fn():
        return "ok"

    assert await breaker.call(ok_fn) == "ok"
    assert breaker.state == CircuitState.CLOSED

    # 2. Trigger failures to trip to OPEN
    async def fail_fn():
        raise RuntimeError("Service down")

    with pytest.raises(RuntimeError):
        await breaker.call(fail_fn)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    with pytest.raises(RuntimeError):
        await breaker.call(fail_fn)
    assert breaker.state == CircuitState.OPEN
    assert breaker.opened_at is not None

    # 3. Fast failure while OPEN
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(ok_fn)

    # 4. Wait for recovery timeout -> enters HALF_OPEN
    await asyncio.sleep(0.12)
    assert await breaker.call(ok_fn) == "ok"
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.success_count == 1

    # 5. Second success closes the circuit
    assert await breaker.call(ok_fn) == "ok"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

    # 6. Failure during HALF_OPEN trips immediately back to OPEN
    with pytest.raises(RuntimeError):
        await breaker.call(fail_fn)
    with pytest.raises(RuntimeError):
        await breaker.call(fail_fn)
    assert breaker.state == CircuitState.OPEN

    await asyncio.sleep(0.12)
    with pytest.raises(RuntimeError):
        await breaker.call(fail_fn)
    assert breaker.state == CircuitState.OPEN

    # 7. Status inspection
    status = breaker.get_status()
    assert status["name"] == "test_breaker"
    assert status["state"] == "open"
    assert status["is_available"] is False


def test_circuit_breaker_registry():
    """Verify circuit breaker registry retrieves singleton breakers."""
    b1 = get_circuit_breaker("watsonx_api", failure_threshold=3)
    b2 = get_circuit_breaker("watsonx_api", failure_threshold=3)
    assert b1 is b2


@pytest.mark.asyncio
async def test_background_task_manager_error_and_drain():
    """Verify BackgroundTaskManager tracks errors, catches exceptions, and drains."""
    mgr = BackgroundTaskManager()
    caught_errors = []

    def on_error(err):
        caught_errors.append(err)

    async def failing_worker():
        raise ValueError("Worker crash")

    task = mgr.create_task(failing_worker(), name="failing_task", on_error=on_error)
    await asyncio.gather(task, return_exceptions=True)
    # Give done callback a tick to run
    await asyncio.sleep(0.01)
    assert len(caught_errors) == 1
    assert str(caught_errors[0]) == "Worker crash"

    # Test draining
    async def lingering_task():
        await asyncio.sleep(5.0)

    mgr.create_task(lingering_task(), name="lingering")
    await mgr.drain_tasks(timeout=0.1, cancel=True)
    mgr._prune_stale_tasks()
    assert len(mgr._tasks) == 0


@pytest.mark.asyncio
async def test_per_key_rate_limiter_complete():
    """Verify TokenBucket and PerKeyRateLimiter tier quotas, consumption, and cleanup."""
    # TokenBucket basic
    bucket = TokenBucket(capacity=2, refill_rate=10.0)
    assert await bucket.consume(1) is True
    assert await bucket.consume(1) is True
    assert await bucket.consume(1) is False
    assert await bucket.get_remaining() == 0

    # Limiter tiers
    limiter = PerKeyRateLimiter()
    allowed, rem, reset = await limiter.check_limit("key_free", tier="free")
    assert allowed is True
    assert rem > 0
    assert reset > 0

    allowed_pro, _, _ = await limiter.check_limit("key_pro", tier="pro")
    assert allowed_pro is True

    allowed_ent, _, _ = await limiter.check_limit("key_ent", tier="enterprise")
    assert allowed_ent is True

    allowed_admin, _, _ = await limiter.check_limit("key_admin", tier="admin")
    assert allowed_admin is True

    # Test cleanup of inactive limiters
    await limiter._cleanup_old_limiters()


def test_heuristic_multi_language_security_and_compliance():
    """Verify heuristic engine routes and inspects multi-language security patterns."""
    from cerberus.providers.heuristic_engine import HeuristicEngine

    # Java
    f_java, s_java = HeuristicEngine.analyze_multi_language_security(
        'Statement stmt = conn.createStatement(); stmt.executeQuery("SELECT * FROM users WHERE id=" + userId);',
        "java",
    )
    assert len(f_java) >= 1
    assert s_java < 100.0

    # C#
    f_cs, s_cs = HeuristicEngine.analyze_multi_language_security(
        'SqlCommand cmd = new SqlCommand("SELECT * FROM users WHERE id=" + userId);',
        "csharp",
    )
    assert len(f_cs) >= 1
    assert s_cs < 100.0

    # Ruby
    f_rb, s_rb = HeuristicEngine.analyze_multi_language_security("eval(params[:user_input])", "ruby")
    assert len(f_rb) >= 1

    # PHP
    f_php, s_php = HeuristicEngine.analyze_multi_language_security("eval($_POST['code']);", "php")
    assert len(f_php) >= 1

    # Go
    f_go, s_go = HeuristicEngine.analyze_multi_language_security(
        'query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", id)', "go"
    )
    assert len(f_go) >= 1

    # Rust
    f_rs, s_rs = HeuristicEngine.analyze_multi_language_security("unsafe { *ptr = 10; }", "rust")
    assert len(f_rs) >= 1

    # Python route
    f_py, s_py = HeuristicEngine.analyze_multi_language_security("eval(payload)", "python")
    assert len(f_py) >= 1

    # Unsupported language
    f_un, s_un = HeuristicEngine.analyze_multi_language_security("print('hi')", "unknown_lang")
    assert f_un == []
    assert s_un == 100.0

    # Compliance analyzer
    f_comp, s_comp = HeuristicEngine.analyze_compliance(
        "logger.info(f'Processing ssn={ssn} credit_card={card_number} password={pwd}')"
    )
    assert len(f_comp) >= 1
    assert s_comp < 100.0
