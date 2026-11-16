"""
Benchmark script for measuring review performance.
Generates performance SLO report with actual measurements.
"""

import asyncio
import statistics
import time

from cerberus.agents.orchestrator import orchestrator
from cerberus.models.schemas import CodeReviewRequest


async def benchmark_review_latency(samples: int = 100) -> dict:
    """
    Benchmark review latency with and without caching.

    Args:
        samples: Number of samples to collect

    Returns:
        Dictionary with benchmark results
    """
    print(f"Running performance benchmarks ({samples} samples)...\n")

    # Test code snippets of varying sizes
    test_cases = {
        "tiny": 'def hello(): return "world"',
        "small": "\n".join([f"def func_{i}(): pass" for i in range(10)]),
        "medium": "\n".join([f"def func_{i}():\n    # TODO\n    pass\n" for i in range(50)]),
        "large": "\n".join([f"class Class_{i}:\n    def method(self): pass\n" for i in range(100)]),
    }

    results = {}

    for size_name, code in test_cases.items():
        print(f"Benchmarking {size_name} snippet ({len(code)} bytes)...")

        # Cold cache measurements
        cold_latencies = []
        for _ in range(min(10, samples)):
            request = CodeReviewRequest(code=code, language="python", context={"benchmark": f"cold_{_}"})
            start = time.perf_counter()
            await orchestrator.execute_review(request)
            duration = (time.perf_counter() - start) * 1000  # Convert to ms
            cold_latencies.append(duration)

        # Warm cache measurements (same code)
        warm_latencies = []
        request = CodeReviewRequest(code=code, language="python")
        for _ in range(samples):
            start = time.perf_counter()
            await orchestrator.execute_review(request)
            duration = (time.perf_counter() - start) * 1000
            warm_latencies.append(duration)

        results[size_name] = {
            "size_bytes": len(code),
            "cold_p50": statistics.median(cold_latencies),
            "cold_p95": statistics.quantiles(cold_latencies, n=20)[18] if len(cold_latencies) >= 20 else max(cold_latencies),
            "cold_p99": statistics.quantiles(cold_latencies, n=100)[98] if len(cold_latencies) >= 100 else max(cold_latencies),
            "warm_p50": statistics.median(warm_latencies),
            "warm_p95": statistics.quantiles(warm_latencies, n=20)[18],
            "warm_p99": statistics.quantiles(warm_latencies, n=100)[98],
            "speedup": statistics.median(cold_latencies) / statistics.median(warm_latencies),
        }

    return results


def print_slo_report(results: dict):
    """Print SLO compliance report."""
    print("\n" + "=" * 80)
    print("PERFORMANCE SERVICE LEVEL OBJECTIVES (SLO) REPORT")
    print("=" * 80)
    print()
    print("| Metric                          | Target    | Measured  | Status |")
    print("|--------------------------------|-----------|-----------|--------|")

    # Extract key metrics
    tiny_warm = results["tiny"]["warm_p50"]
    medium_cold = results["medium"]["cold_p50"]
    medium_warm = results["medium"]["warm_p95"]

    # Define SLOs
    slos = [
        ("P50 Review Latency (cached)", "< 5ms", f"{tiny_warm:.2f}ms", tiny_warm < 5),
        ("P50 Review Latency (cold)", "< 50ms", f"{medium_cold:.2f}ms", medium_cold < 50),
        ("P95 Review Latency (warm)", "< 100ms", f"{medium_warm:.2f}ms", medium_warm < 100),
        ("Cache Speedup", "> 5x", f"{results['medium']['speedup']:.1f}x", results["medium"]["speedup"] > 5),
    ]

    for metric, target, measured, passed in slos:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"| {metric:<30} | {target:<9} | {measured:<9} | {status:<6} |")

    print()
    print("Detailed Breakdown by Code Size:")
    print()
    print("| Size   | Bytes | Cold P50 | Cold P99 | Warm P50 | Warm P99 | Speedup |")
    print("|--------|-------|----------|----------|----------|----------|---------|")

    for size_name, metrics in results.items():
        print(
            f"| {size_name:<6} | {metrics['size_bytes']:<5} | "
            f"{metrics['cold_p50']:>7.2f}ms | {metrics['cold_p99']:>7.2f}ms | "
            f"{metrics['warm_p50']:>7.2f}ms | {metrics['warm_p99']:>7.2f}ms | "
            f"{metrics['speedup']:>6.1f}x |"
        )

    print("\n" + "=" * 80)


async def main():
    """Run benchmarks and generate report."""
    results = await benchmark_review_latency(samples=100)
    print_slo_report(results)


if __name__ == "__main__":
    asyncio.run(main())
