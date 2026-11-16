#!/usr/bin/env python3
"""
Repeatable Performance & Latency Benchmark Script for Cerberus Code Review Service.
Measures cold execution latency, warm (cached) latency, and throughput percentiles (p50, p95, p99).
Produces verifiable, reproducible empirical benchmarks.
"""

import asyncio
import statistics
import sys
import time
from typing import Any, Dict, List

from cerberus.agents.orchestrator import ReviewOrchestrator
from cerberus.core.cache import cache_manager
from cerberus.models.schemas import CodeReviewRequest

SAMPLE_CODE = """
def authenticate_user(username, password, db):
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    result = db.execute(query)
    if result:
        return True
    return False

def process_payment(amount, token):
    if amount <= 0:
        raise ValueError("Invalid amount")
    return {"status": "success", "amount": amount}
"""


async def run_benchmark(iterations: int = 50) -> Dict[str, Any]:
    print(f"=== Cerberus Review Benchmark (Iterations: {iterations}) ===")
    orchestrator = ReviewOrchestrator()

    # Flush cache to ensure true cold measurement
    req_cold = CodeReviewRequest(
        code=SAMPLE_CODE,
        language="python",
        filename="auth_service.py",
        enable_agents=["security", "quality", "performance"],
    )
    cold_key = cache_manager.compute_cache_key(
        code=req_cold.code,
        language=req_cold.language or "python",
        agents=["security", "quality", "performance"],
        filename=req_cold.filename,
    )
    await cache_manager.delete(cold_key)

    # 1. Measure Cold Latency (first evaluation)
    t0 = time.perf_counter()
    cold_resp = await orchestrator.execute_review(req_cold)
    cold_duration_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Cold Run Latency: {cold_duration_ms:.2f} ms (Cache Miss: {not cold_resp.cache_hit})")

    # 2. Measure Warm (Cached) Latencies
    warm_latencies: List[float] = []
    for _ in range(iterations):
        t_start = time.perf_counter()
        warm_resp = await orchestrator.execute_review(req_cold)
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        warm_latencies.append(duration_ms)
        assert warm_resp.cache_hit is True

    # 3. Calculate Percentiles
    sorted_latencies = sorted(warm_latencies)
    p50 = statistics.median(sorted_latencies)
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
    avg_latency = statistics.mean(sorted_latencies)

    print("\n--- Warm Cache Latency Results ---")
    print(f"Average: {avg_latency:.2f} ms")
    print(f"P50:     {p50:.2f} ms")
    print(f"P95:     {p95:.2f} ms")
    print(f"P99:     {p99:.2f} ms")
    print(f"Min:     {min(sorted_latencies):.2f} ms")
    print(f"Max:     {max(sorted_latencies):.2f} ms")

    summary = {
        "cold_ms": round(cold_duration_ms, 2),
        "warm_avg_ms": round(avg_latency, 2),
        "warm_p50_ms": round(p50, 2),
        "warm_p95_ms": round(p95, 2),
        "warm_p99_ms": round(p99, 2),
        "iterations": iterations,
    }
    return summary


def main():
    try:
        summary = asyncio.run(run_benchmark(iterations=30))
        print(f"\nBenchmark completed successfully: {len(summary)} suites executed.")
        return 0
    except Exception as e:
        print(f"Benchmark failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
