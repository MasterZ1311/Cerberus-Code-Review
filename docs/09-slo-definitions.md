# Cerberus Service Level Objectives (SLOs) & SLA Specification

This document defines formal Service Level Indicators (SLIs), Service Level Objectives (SLOs), and Error Budget burn rate thresholds for the Cerberus Multi-Agent Code Review platform.

---

## 1. Core Service Level Indicators (SLIs)

| SLI Name | Definition | Measurement Metric | Target Window |
|---|---|---|---|
| **Availability** | Ratio of successful review requests (`2xx` or `4xx`) to total review requests | `rate(http_requests_total{status!~"5.."}[5m]) / rate(http_requests_total[5m])` | 30-day rolling |
| **P50 Latency (Cold)** | Median review completion latency without cache hit | `histogram_quantile(0.50, sum(rate(cerberus_review_duration_seconds_bucket[5m])) by (le))` | 1-hour rolling |
| **P50 Latency (Cached)** | Median review response latency on cache hit | `histogram_quantile(0.50, sum(rate(cerberus_review_duration_seconds_bucket{cache_hit="true"}[5m])) by (le))` | 1-hour rolling |
| **P99 Latency** | 99th percentile review processing latency | `histogram_quantile(0.99, sum(rate(cerberus_review_duration_seconds_bucket[5m])) by (le))` | 1-hour rolling |
| **Internal Error Rate** | Percentage of requests terminating in HTTP 500 | `sum(rate(http_requests_total{status="500"}[5m])) / sum(rate(http_requests_total[5m]))` | 5-minute rolling |
| **Webhook Delivery Durability** | Rate of GitHub/GitLab webhook events successfully persisted and processed | `sum(rate(cerberus_webhooks_processed_total{status="success"}[5m])) / sum(rate(cerberus_webhooks_total[5m]))` | 7-day rolling |

---

## 2. Service Level Objectives (SLOs)

```
┌─────────────────────────────────────────────────────────────┐
│                      SLO TARGET SUMMARY                     │
├───────────────────────────────┬─────────────────────────────┤
│ Service Availability          │ ≥ 99.9% (≤ 43.8m down/mo)   │
│ P50 Cold Execution Latency    │ < 50ms (heuristic mode)     │
│ P50 Cached Response Latency   │ < 5ms                       │
│ P99 Overall Review Latency    │ < 500ms (heuristic mode)    │
│ Server Error Rate (5xx)       │ < 0.1% of all traffic       │
│ Webhook Event Loss Rate       │ 0.00% (Strict zero-loss)    │
└───────────────────────────────┴─────────────────────────────┘
```

---

## 3. Error Budget & Burn Rate Alerting Matrix

We employ multi-window multi-burn-rate alerting following the Google SRE handbook:

| Severity | Burn Rate | Budget Consumed | Short Window | Long Window | Notification Channel |
|---|---|---|---|---|---|
| **Critical (P1)** | 14.4x | 2% in 1 hour | 2m (14.4x) | 1h (14.4x) | PagerDuty / On-Call Phone Call |
| **High (P2)** | 6x | 5% in 6 hours | 5m (6x) | 6h (6x) | Slack / Incident Channel |
| **Medium (P3)** | 1x | 10% in 3 days | 30m (1x) | 3d (1x) | Weekly Operations Backlog |

---

## 4. Runbook Response Paths
- **When Error Budget burns > 2% in 1 hour:**
  1. Inspect pod crash loops: `kubectl get pods -n cerberus-system`
  2. Verify database connection pool saturation: `kubectl logs -l app=cerberus --grep="timeout"`
  3. Validate circuit breaker trips: `curl http://localhost:8000/api/v1/health`
  4. Initiate rollback if caused by recent deployment: `python scripts/rollback.py`
