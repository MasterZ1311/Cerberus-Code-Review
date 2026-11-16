"""
Load Testing Suite for Cerberus using Locust.

Run with:
    locust -f tests/performance/load_test.py --host=http://localhost:8000

Or headless:
    locust -f tests/performance/load_test.py --host=http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 60s --headless

Requirements:
    pip install locust
"""

import random

try:
    from locust import HttpUser, between, task
except ImportError:
    # Graceful dummy classes so pytest doesn't fail on collection if locust isn't installed
    HttpUser = object  # type: ignore
    between = lambda a, b: None  # type: ignore # noqa: E731
    task = lambda weight=1: lambda f: f  # type: ignore # noqa: E731

from cerberus.config import settings


class CerberusUser(HttpUser):
    """Simulated user performing code reviews."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Called when a simulated user starts."""
        # Use configured API key or default dev key
        api_key = settings.DEFAULT_DEV_API_KEY or "cvai_dev_key_123"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @task(5)
    def review_small_snippet(self):
        """Most common use case: review a small code snippet."""
        snippets = [
            'def hello(): return "world"',
            "import os; os.system('ls')",
            "def add(a, b): return a + b",
            "SELECT * FROM users WHERE id = 1",
            "eval(user_input)",
        ]
        code = random.choice(snippets)
        self.client.post(
            "/api/v1/review",
            json={"code": code, "language": "python"},
            headers=self.headers,
            name="/api/v1/review (small)",
        )

    @task(2)
    def review_medium_file(self):
        """Review a medium-sized file (~100 lines)."""
        code = "\n".join([f"def function_{i}():\n    pass\n" for i in range(50)])
        self.client.post(
            "/api/v1/review",
            json={"code": code, "language": "python"},
            headers=self.headers,
            name="/api/v1/review (medium)",
        )

    @task(1)
    def review_large_file(self):
        """Review a larger file (~500 lines)."""
        code = "\n".join([f"def function_{i}():\n    # TODO: implement\n    pass\n" for i in range(200)])
        self.client.post(
            "/api/v1/review",
            json={"code": code, "language": "python"},
            headers=self.headers,
            name="/api/v1/review (large)",
        )

    @task(1)
    def check_health(self):
        """Health check endpoint."""
        self.client.get("/api/v1/health", name="/api/v1/health")

    @task(1)
    def list_agents(self):
        """List available agents."""
        self.client.get("/api/v1/agents", headers=self.headers, name="/api/v1/agents")


class AdminUser(HttpUser):
    """Simulated admin user accessing analytics and config."""

    wait_time = between(2, 5)

    def on_start(self):
        api_key = settings.DEFAULT_DEV_API_KEY or "cvai_dev_key_123"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    @task(2)
    def view_analytics(self):
        """View analytics dashboard."""
        self.client.get("/api/v1/analytics/summary", headers=self.headers)

    @task(1)
    def check_system_health(self):
        """Check detailed system health."""
        self.client.get("/api/v1/health", headers=self.headers)


class BurstTrafficUser(HttpUser):
    """Simulates burst traffic patterns."""

    wait_time = between(0.1, 0.5)  # Very short wait times

    def on_start(self):
        api_key = settings.DEFAULT_DEV_API_KEY or "cvai_dev_key_123"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    @task
    def burst_requests(self):
        """Rapid-fire requests to test caching and rate limiting."""
        # Same code to test cache hits
        code = 'def test(): return "cached"'
        for _ in range(5):
            self.client.post(
                "/api/v1/review", json={"code": code, "language": "python"}, headers=self.headers, catch_response=True
            )
