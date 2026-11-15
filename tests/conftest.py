import pytest
from cerberus.core.security import rate_limiter


@pytest.fixture(autouse=True)
def reset_test_rate_limiter():
    """Ensure test runs do not inadvertently exhaust production sliding-window rate limits."""
    rate_limiter.requests.clear()
    orig_limit = rate_limiter.limit
    rate_limiter.limit = 100000
    yield
    rate_limiter.limit = orig_limit
    rate_limiter.requests.clear()
