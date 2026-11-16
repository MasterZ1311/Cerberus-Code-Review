import asyncio
import logging

import pytest

from cerberus.core.background import background_tasks
from cerberus.core.security import rate_limiter


@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    """Ensure database schema is initialized and migrations applied prior to running test suite."""
    from cerberus.core.database import init_db

    try:
        asyncio.run(init_db())
    except Exception as e:
        logging.getLogger("cerberus.test").warning("Database session initialization note: %s", e)
    yield


@pytest.fixture(autouse=True)
def cleanup_test_database_connections():
    """Ensure database engine connection handles are cleanly disposed after each test."""
    yield
    from cerberus.core.database import engine

    try:
        engine.sync_engine.dispose()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_test_rate_limiter():
    """Ensure test runs do not inadvertently exhaust production sliding-window rate limits."""
    rate_limiter.requests.clear()
    orig_limit = rate_limiter.limit
    rate_limiter.limit = 100000
    yield
    rate_limiter.limit = orig_limit
    rate_limiter.requests.clear()


@pytest.fixture(autouse=True)
def drain_test_background_tasks():
    """Cancel and clear any pending background tasks to avoid cross-loop leaks and closed-loop warnings."""
    yield
    if getattr(background_tasks, "_tasks", None):
        for task in list(background_tasks._tasks):
            if not task.done():
                task.cancel()
        background_tasks._tasks.clear()
