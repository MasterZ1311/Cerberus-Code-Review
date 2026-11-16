# Monitoring, Observability & Operations Manual

**Platform:** CodeVault AI / Cerberus Enterprise Multi-Agent Code Review System  
**System Architecture:** IBM watsonx Orchestrate + LangGraph + FastAPI + Prometheus + OpenTelemetry + Grafana  
**SLO Commitments:** 99.9% Platform Availability, P95 Review Duration < 15.0s, Error Rate < 0.1%  
**Document Version:** 1.0.0  
**Last Updated:** September 2026  

---

## Table of Contents

1. [Observability Architecture & Design Principles](#1-observability-architecture--design-principles)
2. [Prometheus Metrics Catalog & Python Instrumentation](#2-prometheus-metrics-catalog--python-instrumentation)
   - 2.1 [Prometheus Server Configuration (prometheus.yml)](#21-prometheus-server-configuration-prometheusyml)
   - 2.2 [Python Prometheus Client Instrumentation (cerberus/core/metrics.py)](#22-python-prometheus-client-instrumentation-cerberuscoremetricspy)
3. [Production Grafana Dashboard JSON Specification (24 Panels)](#3-production-grafana-dashboard-json-specification-24-panels)
4. [AlertManager Configuration & 32 Production Alerting Rules](#4-alertmanager-configuration--32-production-alerting-rules)
   - 4.1 [AlertManager Global Configuration (alertmanager.yml)](#41-alertmanager-global-configuration-alertmanageryml)
   - 4.2 [Production Alerting Rules Catalog (k8s/alerts/codevault-alerts.yaml)](#42-production-alerting-rules-catalog-k8salertscodevault-alertsyaml)
5. [Structured JSON Logging Architecture (Loki & ELK)](#5-structured-json-logging-architecture-loki--elk)
   - 5.1 [Structured Log Schema & Correlation Context](#51-structured-log-schema--correlation-context)
   - 5.2 [Python Structured Logging Service (cerberus/core/logging_config.py)](#52-python-structured-logging-service-cerberuscorelogging_configpy)
   - 5.3 [Promtail Configuration for Loki (config/promtail.yml)](#53-promtail-configuration-for-loki-configpromtailyml)
   - 5.4 [Logstash Pipeline Configuration for ELK (config/logstash.conf)](#54-logstash-pipeline-configuration-for-elk-configlogstashconf)
6. [OpenTelemetry APM Tracing & Distributed Context Propagation](#6-opentelemetry-apm-tracing--distributed-context-propagation)
   - 6.1 [OpenTelemetry Initialization & Auto-Instrumentation (cerberus/core/telemetry.py)](#61-opentelemetry-initialization--auto-instrumentation-cerberuscoretelemetrypy)
   - 6.2 [LangGraph Multi-Agent Span Tracer & Decorator](#62-langgraph-multi-agent-span-tracer--decorator)
7. [LLM Cost Tracking, Quota Management & Circuit Breaker](#7-llm-cost-tracking-quota-management--circuit-breaker)
   - 7.1 [LLM Cost Governance Service (cerberus/core/cost_governance.py)](#71-llm-cost-governance-service-cerberuscorecost_governancepy)
8. [10 Comprehensive Production Incident Response Runbooks](#8-10-comprehensive-production-incident-response-runbooks)
   - 8.1 [Runbook 1: High Review Latency / Timeout Spike (P95 > 30s)](#81-runbook-1-high-review-latency--timeout-spike-p95--30s)
   - 8.2 [Runbook 2: Multi-Agent Memory Leak / Worker Pod OOMKilled](#82-runbook-2-multi-agent-memory-leak--worker-pod-oomkilled)
   - 8.3 [Runbook 3: PostgreSQL Connection Pool Starvation & Queue Exhaustion](#83-runbook-3-postgresql-connection-pool-starvation--queue-exhaustion)
   - 8.4 [Runbook 4: IBM watsonx Orchestrate Rate Limiting (HTTP 429) & Degradation](#84-runbook-4-ibm-watsonx-orchestrate-rate-limiting-http-429--degradation)
   - 8.5 [Runbook 5: Redis Cluster Failover & Cache Desynchronization](#85-runbook-5-redis-cluster-failover--cache-desynchronization)
   - 8.6 [Runbook 6: Graph Execution Deadlock / Stuck Review State](#86-runbook-6-graph-execution-deadlock--stuck-review-state)
   - 8.7 [Runbook 7: LLM Token Budget Overrun / Runaway Cost Spike](#87-runbook-7-llm-token-budget-overrun--runaway-cost-spike)
   - 8.8 [Runbook 8: Real-Time WebSocket Disconnect Storm & Buffer Bloat](#88-runbook-8-real-time-websocket-disconnect-storm--buffer-bloat)
   - 8.9 [Runbook 9: HashiCorp Vault Token Expiry & Secret Injection Failure](#89-runbook-9-hashicorp-vault-token-expiry--secret-injection-failure)
   - 8.10 [Runbook 10: Zombie Agent Process Execution & Cache Invalidation Failure](#810-runbook-10-zombie-agent-process-execution--cache-invalidation-failure)
9. [Health Check Probes, SLI/SLO Framework & Error Budget Policies](#9-health-check-probes-slislo-framework--error-budget-policies)
   - 9.1 [Health Check Probe Implementations (/health/live, /health/ready, /health/startup)](#91-health-check-probe-implementations-healthlive-healthready-healthstartup)
   - 9.2 [Service Level Indicators (SLIs) and Objectives (SLOs)](#92-service-level-indicators-slis-and-objectives-slos)
   - 9.3 [Multi-Window Error Budget Burn Rate Policies](#93-multi-window-error-budget-burn-rate-policies)
10. [Summary & Pointer to Next Document](#10-summary--pointer-to-next-document)

---

## 1. Observability Architecture & Design Principles

CodeVault AI implements an enterprise-grade observability fabric built upon the OpenTelemetry standard, unified metrics in Prometheus, high-cardinality distributed tracing in Jaeger/Tempo, structured log ingestion in Grafana Loki/ELK, and proactive anomaly alerting via AlertManager.

```text
# File: docs/diagrams/observability_architecture.txt
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                APPLICATION WORKLOAD (PODS)                             │
│                                                                                        │
│  FastAPI Endpoints ──► LangGraph Orchestrator ──► Multi-Agent Graph ──► watsonx API   │
│         │                         │                        │                │          │
│         ▼                         ▼                        ▼                ▼          │
│  [OpenTelemetry SDK] ───► [structlog JSON Logger] ───► [Prometheus Client Registry]    │
└─────────┬─────────────────────────┬────────────────────────┬───────────────────────────┘
          │ (OTLP / gRPC)           │ (stdout JSON)          │ (/metrics scrape)
          ▼                         ▼                        ▼
┌──────────────────┐      ┌──────────────────┐      ┌────────────────────────────────────┐
│ Jaeger / Tempo   │      │ Promtail / Loki  │      │ Prometheus Server 2.45+            │
│ APM Distributed  │      │ Structured Logs  │      │ TSDB & Metric Evaluator            │
│ Trace Spans      │      │ Query via LogQL  │      └─────────────────┬──────────────────┘
└─────────┬────────┘      └─────────┬────────┘                        │
          │                         │                                 ▼
          └─────────────────┬───────┴───────────────────────► ┌──────────────────────────┐
                            ▼                                 │ AlertManager 0.26+       │
              ┌───────────────────────────┐                   │ PagerDuty / Slack Engine │
              │ Grafana 10 Dashboard      │                   └──────────────────────────┘
              │ Unified Single Pane       │
              └───────────────────────────┘
```

### Core Observability Pillars
1. **Zero-Overhead Metrics:** In-process non-blocking atomic metric updates using Python `prometheus_client`.
2. **Correlation by Design:** Every request injects W3C standard `traceparent` (`trace_id`, `span_id`), `review_id`, and `tenant_id` into all logs, traces, and metrics.
3. **Actionable Alerting:** Alerts are grouped, deduplicated, and mapped 1-to-1 to deterministic incident runbooks with prescriptive remediation steps.
4. **Governance & Cost Controls:** Continuous real-time LLM token metering with proactive circuit-breakers preventing cost overruns.

---

## 2. Prometheus Metrics Catalog & Python Instrumentation

### 2.1 Prometheus Server Configuration (prometheus.yml)

```yaml
# File: config/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s
  external_labels:
    cluster: prod-us-east-1
    environment: production

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - "/etc/prometheus/rules/*.yaml"

scrape_configs:
  - job_name: 'codevault-api'
    metrics_path: '/metrics'
    scheme: 'http'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - codevault
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod
      - source_labels: [__meta_kubernetes_pod_node_name]
        action: replace
        target_label: node

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['pg-exporter.postgres.svc.cluster.local:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter.redis.svc.cluster.local:9121']
```

---

### 2.2 Python Prometheus Client Instrumentation (cerberus/core/metrics.py)

```python
# File: cerberus/core/metrics.py
import time
from typing import Callable, Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    REGISTRY
)

class MetricsCollector:
    """Enterprise Prometheus metrics instrumentation catalog for CodeVault AI."""

    def __init__(self, registry: CollectorRegistry = REGISTRY):
        self.registry = registry

        # ----------------------------------------------------------------------
        # 1. API Gateway & HTTP Traffic Metrics
        # ----------------------------------------------------------------------
        self.api_requests_total = Counter(
            name="codevault_api_requests_total",
            documentation="Total count of inbound HTTP requests handled by the API gateway.",
            labelnames=["endpoint", "method", "status"],
            registry=self.registry
        )

        self.api_request_duration_seconds = Histogram(
            name="codevault_api_request_duration_seconds",
            documentation="Inbound HTTP request latency distribution in seconds.",
            labelnames=["endpoint", "method"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
            registry=self.registry
        )

        self.api_errors_total = Counter(
            name="codevault_api_errors_total",
            documentation="Total count of API errors returned by endpoint and error class.",
            labelnames=["endpoint", "error_type"],
            registry=self.registry
        )

        # ----------------------------------------------------------------------
        # 2. Review Orchestration Metrics
        # ----------------------------------------------------------------------
        self.reviews_total = Counter(
            name="codevault_reviews_total",
            documentation="Total number of code reviews initiated by language and execution status.",
            labelnames=["language", "status"],
            registry=self.registry
        )

        self.review_duration_seconds = Histogram(
            name="codevault_review_duration_seconds",
            documentation="End-to-end review completion duration from submission to final synthesis.",
            buckets=[1.0, 2.5, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 120.0],
            registry=self.registry
        )

        self.reviews_in_progress = Gauge(
            name="codevault_reviews_in_progress",
            documentation="Number of code reviews currently executing in the LangGraph engine.",
            registry=self.registry
        )

        self.review_score = Histogram(
            name="codevault_review_score",
            documentation="Distribution of synthesized code review scores (0.0 to 100.0).",
            buckets=[10.0, 25.0, 50.0, 65.0, 75.0, 85.0, 90.0, 95.0, 100.0],
            registry=self.registry
        )

        self.blocking_reviews_total = Counter(
            name="codevault_blocking_reviews_total",
            documentation="Counter for pull request merge decisions (approved vs blocked).",
            labelnames=["decision"],
            registry=self.registry
        )

        # ----------------------------------------------------------------------
        # 3. Specialized Multi-Agent Metrics
        # ----------------------------------------------------------------------
        self.agent_executions_total = Counter(
            name="codevault_agent_executions_total",
            documentation="Invocations of individual specialized review agents.",
            labelnames=["agent", "status"],
            registry=self.registry
        )

        self.agent_duration_seconds = Histogram(
            name="codevault_agent_duration_seconds",
            documentation="Execution duration of individual specialized agent nodes.",
            labelnames=["agent"],
            buckets=[0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 45.0],
            registry=self.registry
        )

        self.agent_findings_total = Counter(
            name="codevault_agent_findings_total",
            documentation="Total findings discovered categorized by agent, severity, and rule/CWE.",
            labelnames=["agent", "severity", "cwe_id"],
            registry=self.registry
        )

        self.agent_crashes_total = Counter(
            name="codevault_agent_crashes_total",
            documentation="Unhandled exceptions or crashes inside specialized agent execution nodes.",
            labelnames=["agent"],
            registry=self.registry
        )

        # ----------------------------------------------------------------------
        # 4. LLM Foundation Model Metrics
        # ----------------------------------------------------------------------
        self.llm_requests_total = Counter(
            name="codevault_llm_requests_total",
            documentation="Outbound foundation model inference calls by provider, model, and status.",
            labelnames=["provider", "model", "status"],
            registry=self.registry
        )

        self.llm_latency_seconds = Histogram(
            name="codevault_llm_latency_seconds",
            documentation="Inference response latency of upstream foundation model endpoints.",
            labelnames=["provider", "model"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0],
            registry=self.registry
        )

        self.llm_tokens_total = Counter(
            name="codevault_llm_tokens_total",
            documentation="Cumulative token count consumed across prompt and completion phases.",
            labelnames=["provider", "model", "token_type"],
            registry=self.registry
        )

        self.llm_cost_usd_total = Counter(
            name="codevault_llm_cost_usd_total",
            documentation="Cumulative monetary expenditure in USD for foundation model inference.",
            labelnames=["provider", "model"],
            registry=self.registry
        )

        # ----------------------------------------------------------------------
        # 5. Infrastructure, Database & Cache Metrics
        # ----------------------------------------------------------------------
        self.cache_hits_total = Counter(
            name="codevault_cache_hits_total",
            documentation="Cache hit counter across in-memory and Redis caches.",
            registry=self.registry
        )

        self.cache_misses_total = Counter(
            name="codevault_cache_misses_total",
            documentation="Cache miss counter.",
            registry=self.registry
        )

        self.cache_evictions_total = Counter(
            name="codevault_cache_evictions_total",
            documentation="Cache items evicted due to LRU policy or TTL expiry.",
            registry=self.registry
        )

        self.cache_hit_rate = Gauge(
            name="codevault_cache_hit_rate",
            documentation="Instantaneous cache hit ratio (0.0 to 1.0).",
            registry=self.registry
        )

        self.db_pool_size = Gauge(
            name="codevault_db_pool_size",
            documentation="Total configured database connection pool capacity.",
            registry=self.registry
        )

        self.db_pool_checked_out = Gauge(
            name="codevault_db_pool_checked_out",
            documentation="Active database connections currently checked out by worker sessions.",
            registry=self.registry
        )

        self.db_pool_overflow = Gauge(
            name="codevault_db_pool_overflow",
            documentation="Active overflow connections currently allocated beyond base pool size.",
            registry=self.registry
        )

        self.rate_limit_tracked_keys = Gauge(
            name="codevault_rate_limit_tracked_keys",
            documentation="Number of active client identifiers currently tracked in rate limiter memory.",
            registry=self.registry
        )

        self.websocket_active_connections = Gauge(
            name="codevault_websocket_active_connections",
            documentation="Number of active client WebSocket connections streaming review events.",
            registry=self.registry
        )

# Global singleton metrics instance
metrics = MetricsCollector()
```

---

## 3. Production Grafana Dashboard JSON Specification (24 Panels)

Below is the complete, valid, copy-paste ready Grafana 10 dashboard definition encompassing 24 production panels organized into 5 functional rows.

```json
// File: config/grafana/dashboards/codevault-overview.json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Grafana --",
        "enable": true,
        "hide": true,
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 },
      "id": 100,
      "title": "Executive Overview & System Health",
      "type": "row"
    },
    {
      "id": 1,
      "title": "System Availability (30d SLO)",
      "type": "stat",
      "gridPos": { "h": 4, "w": 6, "x": 0, "y": 1 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "(1 - (sum(rate(codevault_api_requests_total{status=~\"5..\"}[30d])) / sum(rate(codevault_api_requests_total[30d])))) * 100",
          "legendFormat": "Uptime %"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "red", "value": null },
              { "color": "yellow", "value": 99.0 },
              { "color": "green", "value": 99.9 }
            ]
          }
        }
      }
    },
    {
      "id": 2,
      "title": "Reviews Completed (Last 24h)",
      "type": "stat",
      "gridPos": { "h": 4, "w": 6, "x": 6, "y": 1 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(increase(codevault_reviews_total{status=\"completed\"}[24h]))",
          "legendFormat": "Reviews"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "color": { "mode": "palette-classic" }
        }
      }
    },
    {
      "id": 3,
      "title": "P95 Review Latency (Target < 15s)",
      "type": "gauge",
      "gridPos": { "h": 4, "w": 6, "x": 12, "y": 1 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(codevault_review_duration_seconds_bucket[5m])) by (le))",
          "legendFormat": "P95 Latency"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "min": 0,
          "max": 30,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 15 },
              { "color": "red", "value": 25 }
            ]
          }
        }
      }
    },
    {
      "id": 4,
      "title": "Active Reviews In Progress",
      "type": "gauge",
      "gridPos": { "h": 4, "w": 6, "x": 18, "y": 1 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_reviews_in_progress",
          "legendFormat": "Active Reviews"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "min": 0,
          "max": 50,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 30 },
              { "color": "red", "value": 45 }
            ]
          }
        }
      }
    },
    {
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 5 },
      "id": 101,
      "title": "API Gateway & Traffic Analytics",
      "type": "row"
    },
    {
      "id": 5,
      "title": "API Request Throughput by Endpoint",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 6 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_api_requests_total[2m])) by (endpoint)",
          "legendFormat": "{{endpoint}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "reqps" } }
    },
    {
      "id": 6,
      "title": "HTTP Status Code Distribution",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 6 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_api_requests_total[2m])) by (status)",
          "legendFormat": "HTTP {{status}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "reqps" } }
    },
    {
      "id": 7,
      "title": "API Request Latency Percentiles (P50, P90, P99)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 6 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "histogram_quantile(0.50, sum(rate(codevault_api_request_duration_seconds_bucket[5m])) by (le))",
          "legendFormat": "P50"
        },
        {
          "expr": "histogram_quantile(0.90, sum(rate(codevault_api_request_duration_seconds_bucket[5m])) by (le))",
          "legendFormat": "P90"
        },
        {
          "expr": "histogram_quantile(0.99, sum(rate(codevault_api_request_duration_seconds_bucket[5m])) by (le))",
          "legendFormat": "P99"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "s" } }
    },
    {
      "id": 8,
      "title": "API Error Rate (%)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 12 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "(sum(rate(codevault_api_requests_total{status=~\"5..\"}[5m])) / sum(rate(codevault_api_requests_total[5m]))) * 100",
          "legendFormat": "5xx Error Rate %"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 0.1 }
            ]
          }
        }
      }
    },
    {
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 18 },
      "id": 102,
      "title": "Multi-Agent Deep Dive & Engine Performance",
      "type": "row"
    },
    {
      "id": 9,
      "title": "Specialized Agent Execution Latency (P95)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 19 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(codevault_agent_duration_seconds_bucket[5m])) by (le, agent))",
          "legendFormat": "{{agent}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "s" } }
    },
    {
      "id": 10,
      "title": "Agent Execution Outcomes (Success vs Degraded vs Failed)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 19 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_agent_executions_total[5m])) by (status)",
          "legendFormat": "{{status}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "ops" } }
    },
    {
      "id": 11,
      "title": "Findings Discovered by Agent & Severity",
      "type": "bargauge",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 19 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(increase(codevault_agent_findings_total[1h])) by (severity)",
          "legendFormat": "{{severity}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 12,
      "title": "Agent Crash Events",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 25 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_agent_crashes_total[5m])) by (agent)",
          "legendFormat": "{{agent}} Crash"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "color": { "fixedColor": "red", "mode": "fixed" }
        }
      }
    },
    {
      "id": 13,
      "title": "Pull Request Approval Decisions (Approved vs Blocked)",
      "type": "piechart",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 25 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(increase(codevault_blocking_reviews_total[24h])) by (decision)",
          "legendFormat": "{{decision}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 14,
      "title": "Review Score Distribution Histogram",
      "type": "histogram",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 25 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_review_score_bucket[1h])) by (le)",
          "legendFormat": "le={{le}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 31 },
      "id": 103,
      "title": "LLM Tokens, Foundation Models & Expenditure",
      "type": "row"
    },
    {
      "id": 15,
      "title": "LLM Token Consumption Rate (Tokens/sec)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 32 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_llm_tokens_total[5m])) by (token_type)",
          "legendFormat": "{{token_type}}"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 16,
      "title": "Cumulative Daily LLM Expenditure ($ USD)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 32 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_llm_cost_usd_total - (codevault_llm_cost_usd_total offset 1d)",
          "legendFormat": "Today Spend ($)"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "currencyUSD",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 400 },
              { "color": "red", "value": 500 }
            ]
          }
        }
      }
    },
    {
      "id": 17,
      "title": "LLM Inference Latency by Model Provider",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 32 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(codevault_llm_latency_seconds_bucket[5m])) by (le, provider))",
          "legendFormat": "{{provider}} P95"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "s" } }
    },
    {
      "id": 18,
      "title": "LLM Provider Rate Limit Events (HTTP 429)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 38 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(codevault_llm_requests_total{status=\"429\"}[5m])) by (provider)",
          "legendFormat": "{{provider}} 429 Throttle"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 44 },
      "id": 104,
      "title": "Infrastructure, Database & Resource Saturation",
      "type": "row"
    },
    {
      "id": 19,
      "title": "PostgreSQL Connection Pool Saturation",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 45 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_db_pool_checked_out",
          "legendFormat": "Checked Out Connections"
        },
        {
          "expr": "codevault_db_pool_size",
          "legendFormat": "Max Pool Capacity"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 20,
      "title": "Redis Cache Hit Ratio & Eviction Rate",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 45 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_cache_hit_rate * 100",
          "legendFormat": "Hit Ratio %"
        },
        {
          "expr": "rate(codevault_cache_evictions_total[5m])",
          "legendFormat": "Evictions/sec"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "percent" } }
    },
    {
      "id": 21,
      "title": "Container CPU & Memory Utilization vs Limits",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 45 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(container_cpu_usage_seconds_total{container=\"codevault-api\"}[5m])) / sum(kube_pod_container_resource_limits{resource=\"cpu\", container=\"codevault-api\"}) * 100",
          "legendFormat": "CPU % of Limit"
        },
        {
          "expr": "sum(container_memory_working_set_bytes{container=\"codevault-api\"}) / sum(kube_pod_container_resource_limits{resource=\"memory\", container=\"codevault-api\"}) * 100",
          "legendFormat": "Memory % of Limit"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "percent" } }
    },
    {
      "id": 22,
      "title": "WebSocket Active Connections & Churn Rate",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 51 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_websocket_active_connections",
          "legendFormat": "Active Client Sockets"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 23,
      "title": "Rate Limiter Tracked Memory Keys (Cap: 25k)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 51 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "codevault_rate_limit_tracked_keys",
          "legendFormat": "Tracked Keys"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 20000 },
              { "color": "red", "value": 24000 }
            ]
          }
        }
      }
    },
    {
      "id": 24,
      "title": "PostgreSQL Slow Query Duration (P95)",
      "type": "timeseries",
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 51 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "rate(codevault_db_query_duration_seconds_sum[5m]) / rate(codevault_db_query_duration_seconds_count[5m])",
          "legendFormat": "Avg Query Duration"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "s" } }
    }
  ],
  "schemaVersion": 38,
  "style": "dark",
  "tags": ["codevault", "production", "sre", "multi-agent"],
  "time": { "from": "now-6h", "to": "now" },
  "timepicker": { "refresh_intervals": ["5s", "10s", "30s", "1m", "5m"] },
  "timezone": "utc",
  "title": "CodeVault AI - Enterprise Production Observability",
  "uid": "codevault-prod-overview",
  "version": 1
}
```

---

## 4. AlertManager Configuration & 32 Production Alerting Rules

### 4.1 AlertManager Global Configuration (alertmanager.yml)

```yaml
# File: config/alertmanager.yml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alertmanager@cerberus.example.com'
  smtp_require_tls: true

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack-default'
  routes:
    # Critical alerts route immediately to PagerDuty Primary On-Call
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true

    # Cost-related alerts route to FinOps channel
    - match:
        category: cost
      receiver: 'slack-finops'

    # Security findings & authentication failures
    - match:
        category: security
      receiver: 'slack-infosec'

inhibit_rules:
  # Silence warning latency alerts if database is completely down
  - source_match:
      alertname: 'DatabaseDown'
    target_match:
      alertname: 'DatabaseHighLatency'
    equal: ['cluster']

receivers:
  - name: 'slack-default'
    slack_configs:
      - channel: '#codevault-sre-alerts'
        api_url: '${SLACK_DEFAULT_WEBHOOK_URL}'
        send_resolved: true
        title: '{{ template "slack.default.title" . }}'
        text: '{{ template "slack.default.text" . }}'

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '${PAGERDUTY_CRITICAL_SERVICE_KEY}'
        severity: 'critical'
        send_resolved: true

  - name: 'slack-finops'
    slack_configs:
      - channel: '#codevault-finops-alerts'
        api_url: '${SLACK_FINOPS_WEBHOOK_URL}'
        send_resolved: true

  - name: 'slack-infosec'
    slack_configs:
      - channel: '#codevault-infosec-alerts'
        api_url: '${SLACK_INFOSEC_WEBHOOK_URL}'
        send_resolved: true
```

---

### 4.2 Production Alerting Rules Catalog (k8s/alerts/codevault-alerts.yaml)

This catalog defines 32 production alerting rules with explicit PromQL queries, thresholds, severity tiers, and runbook links across Infrastructure, Multi-Agent Performance, LLM & Cost, Database, and Security.

```yaml
# File: k8s/alerts/codevault-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: codevault-production-alerts
  namespace: codevault
  labels:
    role: alert-rules
    app.kubernetes.io/name: codevault
spec:
  groups:
    - name: codevault.api.rules
      rules:
        # 1. High API Error Rate
        - alert: HighAPIErrorRate
          expr: sum(rate(codevault_api_requests_total{status=~"5.."}[5m])) / sum(rate(codevault_api_requests_total[5m])) > 0.05
          for: 3m
          labels:
            severity: critical
            category: api
          annotations:
            summary: "API 5xx error rate exceeds 5% in cluster {{ $labels.cluster }}"
            runbook_url: "https://cerberus.example.com/docs/runbooks#81"

        # 2. API Latency Warning
        - alert: APILatencyBreach
          expr: histogram_quantile(0.95, sum(rate(codevault_api_request_duration_seconds_bucket[5m])) by (le)) > 10.0
          for: 5m
          labels:
            severity: warning
            category: api
          annotations:
            summary: "API P95 latency is {{ $value }}s, exceeding 10s warning threshold."

        # 3. API Critical Latency
        - alert: APICriticalLatency
          expr: histogram_quantile(0.99, sum(rate(codevault_api_request_duration_seconds_bucket[5m])) by (le)) > 30.0
          for: 5m
          labels:
            severity: critical
            category: api
          annotations:
            summary: "API P99 latency is {{ $value }}s, exceeding 30s critical threshold."
            runbook_url: "https://cerberus.example.com/docs/runbooks#81"

        # 4. Review Throughput Drop
        - alert: ReviewThroughputDrop
          expr: rate(codevault_reviews_total[15m]) < (rate(codevault_reviews_total[15m] offset 1d) * 0.5)
          for: 15m
          labels:
            severity: warning
            category: traffic
          annotations:
            summary: "Review request rate dropped by over 50% compared to 24h baseline."

        # 5. High Review Failure Rate
        - alert: HighReviewFailureRate
          expr: sum(rate(codevault_reviews_total{status="failed"[5m]})) / sum(rate(codevault_reviews_total[5m])) > 0.10
          for: 5m
          labels:
            severity: critical
            category: multi-agent
          annotations:
            summary: "Over 10% of code reviews are failing completely in LangGraph engine."
            runbook_url: "https://cerberus.example.com/docs/runbooks#86"

        # 6. Agent Crash Detected
        - alert: AgentCrashDetected
          expr: sum(rate(codevault_agent_crashes_total[5m])) > 0
          for: 2m
          labels:
            severity: warning
            category: multi-agent
          annotations:
            summary: "Agent node crash caught in agent {{ $labels.agent }}."

        # 7. Agent Crash Critical Spike
        - alert: AgentCrashCritical
          expr: sum(rate(codevault_agent_executions_total{status="failed"}[5m])) / sum(rate(codevault_agent_executions_total[5m])) > 0.50
          for: 3m
          labels:
            severity: critical
            category: multi-agent
          annotations:
            summary: "Over 50% of executions for agent {{ $labels.agent }} are crashing."
            runbook_url: "https://cerberus.example.com/docs/runbooks#86"

        # 8. Security Agent Down
        - alert: SecurityAgentDown
          expr: rate(codevault_agent_executions_total{agent="security", status="failed"}[5m]) > 0.2
          for: 3m
          labels:
            severity: critical
            category: security
          annotations:
            summary: "Core Security Review Agent is failing; security checks bypassed or failing."
            runbook_url: "https://cerberus.example.com/docs/runbooks#86"

        # 9. Agent Execution Timeout
        - alert: AgentExecutionTimeout
          expr: histogram_quantile(0.95, sum(rate(codevault_agent_duration_seconds_bucket[5m])) by (le, agent)) > 60.0
          for: 5m
          labels:
            severity: warning
            category: multi-agent
          annotations:
            summary: "Agent {{ $labels.agent }} execution duration exceeds 60s timeout."

        # 10. Agent Deadlock Warning
        - alert: AgentDeadlockWarning
          expr: codevault_reviews_in_progress > 20 and rate(codevault_reviews_total[5m]) == 0
          for: 5m
          labels:
            severity: critical
            category: multi-agent
          annotations:
            summary: "Multi-agent graph deadlock: 20+ reviews in progress but zero reviews completing."
            runbook_url: "https://cerberus.example.com/docs/runbooks#86"

    - name: codevault.infrastructure.rules
      rules:
        # 11. PostgreSQL Down
        - alert: DatabaseDown
          expr: up{job="postgres-exporter"} == 0
          for: 1m
          labels:
            severity: critical
            category: database
          annotations:
            summary: "PostgreSQL master database instance is unreachable."
            runbook_url: "https://cerberus.example.com/docs/runbooks#83"

        # 12. PostgreSQL Connection Pool Exhaustion
        - alert: DatabasePoolExhaustion
          expr: codevault_db_pool_checked_out / codevault_db_pool_size > 0.90
          for: 3m
          labels:
            severity: critical
            category: database
          annotations:
            summary: "Database connection pool is > 90% saturated."
            runbook_url: "https://cerberus.example.com/docs/runbooks#83"

        # 13. PostgreSQL High Query Latency
        - alert: DatabaseHighLatency
          expr: rate(codevault_db_query_duration_seconds_sum[5m]) / rate(codevault_db_query_duration_seconds_count[5m]) > 0.5
          for: 5m
          labels:
            severity: warning
            category: database
          annotations:
            summary: "Average database query duration exceeds 500ms."

        # 14. Database Disk Space Low
        - alert: DatabaseDiskSpaceLow
          expr: node_filesystem_free_bytes{mountpoint="/var/lib/postgresql/data"} / node_filesystem_size_bytes < 0.15
          for: 5m
          labels:
            severity: critical
            category: database
          annotations:
            summary: "PostgreSQL storage volume has less than 15% free disk space."

        # 15. Redis Down
        - alert: RedisDown
          expr: up{job="redis-exporter"} == 0
          for: 1m
          labels:
            severity: critical
            category: cache
          annotations:
            summary: "Redis cache master instance is unreachable."
            runbook_url: "https://cerberus.example.com/docs/runbooks#85"

        # 16. Redis Memory High
        - alert: RedisMemoryHigh
          expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.85
          for: 5m
          labels:
            severity: warning
            category: cache
          annotations:
            summary: "Redis memory utilization has exceeded 85% of allocated capacity."

        # 17. Redis Eviction Spike
        - alert: RedisEvictionSpike
          expr: rate(redis_evicted_keys_total[5m]) > 100
          for: 5m
          labels:
            severity: warning
            category: cache
          annotations:
            summary: "Redis is evicting keys at an abnormal rate (>100 keys/sec)."
            runbook_url: "https://cerberus.example.com/docs/runbooks#85"

        # 18. Cache Hit Rate Low
        - alert: CacheHitRateLow
          expr: codevault_cache_hit_rate < 0.40
          for: 15m
          labels:
            severity: warning
            category: cache
          annotations:
            summary: "Cache hit rate dropped below 40% for 15 consecutive minutes."

        # 19. Rate Limiter Capacity Warning
        - alert: RateLimiterCapacityWarning
          expr: codevault_rate_limit_tracked_keys > 20000
          for: 5m
          labels:
            severity: warning
            category: security
          annotations:
            summary: "Rate limiter memory tracking > 20,000 active client tokens."

        # 20. Rate Limiter Memory Exhaustion
        - alert: RateLimiterExhaustion
          expr: codevault_rate_limit_tracked_keys > 24000
          for: 3m
          labels:
            severity: critical
            category: security
          annotations:
            summary: "Rate limiter memory approaching 25,000 key ceiling; LRU eviction imminent."

        # 21. Pod OOMKilled
        - alert: PodOOMKilling
          expr: increase(kube_pod_container_status_restarts_total{reason="OOMKilled"}[5m]) > 0
          for: 1m
          labels:
            severity: critical
            category: compute
          annotations:
            summary: "Pod {{ $labels.pod }} was OOMKilled by the Linux kernel."
            runbook_url: "https://cerberus.example.com/docs/runbooks#82"

        # 22. Pod CrashLooping
        - alert: PodCrashLooping
          expr: rate(kube_pod_container_status_restarts_total[15m]) > 0.2
          for: 5m
          labels:
            severity: critical
            category: compute
          annotations:
            summary: "Pod {{ $labels.pod }} is repeatedly restarting in CrashLoopBackOff."

        # 23. Pod High CPU
        - alert: PodHighCPU
          expr: sum(rate(container_cpu_usage_seconds_total{container="codevault-api"}[5m])) / sum(kube_pod_container_resource_limits{resource="cpu", container="codevault-api"}) > 0.85
          for: 10m
          labels:
            severity: warning
            category: compute
          annotations:
            summary: "API Pods CPU utilization exceeds 85% of limit."

        # 24. Pod High Memory
        - alert: PodHighMemory
          expr: sum(container_memory_working_set_bytes{container="codevault-api"}) / sum(kube_pod_container_resource_limits{resource="memory", container="codevault-api"}) > 0.85
          for: 5m
          labels:
            severity: warning
            category: compute
          annotations:
            summary: "API Pods Working Set memory exceeds 85% of limit."
            runbook_url: "https://cerberus.example.com/docs/runbooks#82"

    - name: codevault.llm.cost.rules
      rules:
        # 25. LLM Rate Limit 429 Throttle
        - alert: LLMRateLimit429
          expr: rate(codevault_llm_requests_total{status="429"}[5m]) > 0.1
          for: 3m
          labels:
            severity: warning
            category: llm
          annotations:
            summary: "Upstream watsonx Orchestrate endpoint returning HTTP 429 rate limit errors."
            runbook_url: "https://cerberus.example.com/docs/runbooks#84"

        # 26. LLM Provider Down
        - alert: LLMProviderDown
          expr: sum(rate(codevault_llm_requests_total{status=~"5.."}[5m])) / sum(rate(codevault_llm_requests_total[5m])) > 0.50
          for: 3m
          labels:
            severity: critical
            category: llm
          annotations:
            summary: "Over 50% of LLM calls failing against upstream provider {{ $labels.provider }}."
            runbook_url: "https://cerberus.example.com/docs/runbooks#84"

        # 27. LLM Latency Spike
        - alert: LLMLatencySpike
          expr: histogram_quantile(0.95, sum(rate(codevault_llm_latency_seconds_bucket[5m])) by (le)) > 20.0
          for: 5m
          labels:
            severity: warning
            category: llm
          annotations:
            summary: "Upstream foundation model inference P95 latency exceeds 20 seconds."

        # 28. Token Budget Exceeded
        - alert: TokenBudgetExceeded
          expr: (codevault_llm_cost_usd_total - (codevault_llm_cost_usd_total offset 1d)) > 500.0
          for: 1m
          labels:
            severity: critical
            category: cost
          annotations:
            summary: "Daily foundation model expenditure has exceeded $500 hard budget cap."
            runbook_url: "https://cerberus.example.com/docs/runbooks#87"

        # 29. Cost Anomaly Spike
        - alert: CostAnomalySpike
          expr: rate(codevault_llm_cost_usd_total[1h]) > (rate(codevault_llm_cost_usd_total[1h] offset 1d) * 3)
          for: 1h
          labels:
            severity: warning
            category: cost
          annotations:
            summary: "LLM spending rate is 3x higher than same period yesterday."

        # 30. WebSocket Connection Leak
        - alert: WebSocketConnectionLeak
          expr: codevault_websocket_active_connections > 1000 and rate(codevault_api_requests_total[10m]) < 1
          for: 15m
          labels:
            severity: warning
            category: websocket
          annotations:
            summary: "Over 1,000 idle WebSocket connections detected without review activity."
            runbook_url: "https://cerberus.example.com/docs/runbooks#88"

        # 31. TLS Certificate Expiring Soon
        - alert: TLSCertificateExpiringSoon
          expr: certmanager_certificate_expiration_timestamp_seconds - time() < 14 * 24 * 3600
          for: 1h
          labels:
            severity: warning
            category: security
          annotations:
            summary: "TLS certificate for {{ $labels.name }} expires in less than 14 days."

        # 32. Ingress Controller Error Rate
        - alert: IngressControllerErrorRate
          expr: sum(rate(nginx_ingress_controller_requests{status=~"5.."}[5m])) / sum(rate(nginx_ingress_controller_requests[5m])) > 0.02
          for: 5m
          labels:
            severity: critical
            category: ingress
          annotations:
            summary: "Ingress controller 5xx error rate is above 2%."
```

---

## 5. Structured JSON Logging Architecture (Loki & ELK)

### 5.1 Structured Log Schema & Correlation Context

Every log entry emitted by CodeVault AI is a single-line JSON string containing distributed context headers and metadata.

```json
// File: config/logging/example-structured-log.json
{
  "timestamp": "2026-09-24T14:30:00.123Z",
  "level": "INFO",
  "service": "codevault-api",
  "component": "langgraph_orchestrator",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "review_id": "78a19bc0-8d4e-4148-812d-9477bcf4d101",
  "tenant_id": "org_ibm_enterprise",
  "caller": "cerberus.agents.orchestrator:execute_review:142",
  "message": "Specialized agent execution finished successfully",
  "duration_ms": 3420,
  "agent": "security",
  "findings_count": 2,
  "score": 88.5,
  "status": "completed"
}
```

---

### 5.2 Python Structured Logging Service (cerberus/core/logging_config.py)

```python
# File: cerberus/core/logging_config.py
import sys
import logging
import structlog
from typing import Dict, Any

def add_open_telemetry_spans(_, __, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Injects active OpenTelemetry trace_id and span_id into structured logs."""
    from opentelemetry import trace
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = f"{ctx.trace_id:032x}"
        event_dict["span_id"] = f"{ctx.span_id:016x}"
    return event_dict

def redact_sensitive_credentials(_, __, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Redacts authorization headers, API keys, and passwords prior to serialization."""
    sensitive_keys = {"authorization", "api_key", "secret_key", "password", "token"}
    for k in list(event_dict.keys()):
        if any(s in k.lower() for s in sensitive_keys):
            event_dict[k] = "[REDACTED]"
    return event_dict

def configure_structured_logging(log_level: str = "INFO"):
    """Configures structlog to output non-blocking, machine-readable JSON logs."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_open_telemetry_spans,
        redact_sensitive_credentials,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=structlog.processors.JSONRenderer(),
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
```

---

### 5.3 Promtail Configuration for Loki (config/promtail.yml)

```yaml
# File: config/promtail.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: kubernetes-pods-codevault
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - codevault
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            service: service
            component: component
            trace_id: trace_id
            review_id: review_id
            tenant_id: tenant_id
      - labels:
          level:
          service:
          component:
      - regex:
          expression: "(?i)(bearer\\s+[a-z0-9_\\-\\.]+)"
          replace: "Bearer [REDACTED]"
      - timestamp:
          source: timestamp
          format: RFC3339Nano
```

---

### 5.4 Logstash Pipeline Configuration for ELK (config/logstash.conf)

```ruby
# File: config/logstash.conf
input {
  beats {
    port => 5044
  }
}

filter {
  json {
    source => "message"
  }

  mutate {
    add_field => {
      "[@metadata][target_index]" => "codevault-logs-%{+YYYY.MM.dd}"
    }
  }

  # Mask sensitive API keys and tokens in string payloads
  mutate {
    gsub => [
      "message", "cvai_[a-zA-Z0-9]{32,}", "[REDACTED_API_KEY]",
      "message", "Bearer [a-zA-Z0-9_\-\.]{20,}", "Bearer [REDACTED_TOKEN]"
    ]
  }
}

output {
  elasticsearch {
    hosts => ["https://elasticsearch.logging.svc.cluster.local:9200"]
    index => "%{[@metadata][target_index]}"
    ssl => true
    cacert => "/etc/logstash/certs/ca.crt"
    user => "logstash_writer"
    password => "${LOGSTASH_PASSWORD}"
  }
}
```

---

## 6. OpenTelemetry APM Tracing & Distributed Context Propagation

### 6.1 OpenTelemetry Initialization & Auto-Instrumentation (cerberus/core/telemetry.py)

```python
# File: cerberus/core/telemetry.py
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

def setup_telemetry(app: FastAPI, engine: Optional[AsyncEngine] = None):
    """Configures OpenTelemetry APM tracer with OTLP HTTP exporter."""
    service_name = os.getenv("OTEL_SERVICE_NAME", "codevault-api")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318/v1/traces")
    environment = os.getenv("ENVIRONMENT", "production")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": environment
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # 1. Instrument FastAPI Request Routing
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    # 2. Instrument Outbound HTTP Requests to watsonx
    HTTPXClientInstrumentor().instrument()

    # 3. Instrument SQLAlchemy Database Queries
    if engine:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

def get_tracer(module_name: str) -> trace.Tracer:
    """Returns an isolated OpenTelemetry tracer for custom span instrumentation."""
    return trace.get_tracer(module_name)
```

---

### 6.2 LangGraph Multi-Agent Span Tracer & Decorator

```python
# File: cerberus/core/tracer_decorator.py
import functools
import time
from typing import Callable, Any
from opentelemetry import trace
from cerberus.core.metrics import metrics

tracer = trace.get_tracer("cerberus.langgraph.agents")

def trace_agent_node(agent_name: str):
    """Decorator creating OpenTelemetry child spans and Prometheus metrics around LangGraph nodes."""
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            with tracer.start_as_current_span(f"AgentNode.{agent_name}") as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("agent.type", "langgraph_node")

                try:
                    result = await func(*args, **kwargs)
                    duration = time.perf_counter() - start_time
                    
                    span.set_attribute("agent.status", "success")
                    span.set_attribute("agent.duration_seconds", duration)
                    metrics.agent_executions_total.labels(agent=agent_name, status="success").inc()
                    metrics.agent_duration_seconds.labels(agent=agent_name).observe(duration)
                    return result
                except Exception as exc:
                    duration = time.perf_counter() - start_time
                    span.set_attribute("agent.status", "failed")
                    span.set_attribute("error.message", str(exc))
                    span.record_exception(exc)
                    
                    metrics.agent_executions_total.labels(agent=agent_name, status="failed").inc()
                    metrics.agent_crashes_total.labels(agent=agent_name).inc()
                    raise exc
        return wrapper
    return decorator
```

---

## 7. LLM Cost Tracking, Quota Management & Circuit Breaker

### 7.1 LLM Cost Governance Service (cerberus/core/cost_governance.py)

```python
# File: cerberus/core/cost_governance.py
import datetime
import redis.asyncio as aioredis
from typing import Tuple
import structlog
from cerberus.core.metrics import metrics

logger = structlog.get_logger(__name__)

class LLMCostGovernanceService:
    """Tracks token consumption and executes automated circuit-breaking on daily budget caps."""

    # Provider Pricing Matrix: (Price per 1,000 Prompt Tokens, Price per 1,000 Completion Tokens) in USD
    MODEL_PRICING = {
        "ibm/granite-13b-chat-v2": (0.0008, 0.0016),
        "ibm/granite-20b-code-instruct": (0.0012, 0.0024),
        "gpt-4o": (0.0050, 0.0150),
        "ollama/granite": (0.0000, 0.0000) # Local free compute
    }

    def __init__(self, redis_client: aioredis.Redis, daily_budget_cap_usd: float = 500.0):
        self.redis = redis_client
        self.daily_budget_cap_usd = daily_budget_cap_usd

    def _get_daily_key(self) -> str:
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        return f"codevault:cost:daily:{today}"

    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculates exact USD expenditure for an inference transaction."""
        prompt_rate, completion_rate = self.MODEL_PRICING.get(model, (0.0010, 0.0020))
        cost = (prompt_tokens / 1000.0 * prompt_rate) + (completion_tokens / 1000.0 * completion_rate)
        return round(cost, 6)

    async def record_usage(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Records token metrics and updates daily spending accumulator in Redis."""
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens)

        # Update Prometheus metrics
        metrics.llm_tokens_total.labels(provider=provider, model=model, token_type="prompt").inc(prompt_tokens)
        metrics.llm_tokens_total.labels(provider=provider, model=model, token_type="completion").inc(completion_tokens)
        metrics.llm_cost_usd_total.labels(provider=provider, model=model).inc(cost)

        # Atomically increment Redis daily budget counter
        key = self._get_daily_key()
        new_total = await self.redis.incrbyfloat(key, cost)
        await self.redis.expire(key, 172800) # 48 hour retention

        if new_total >= (self.daily_budget_cap_usd * 0.8) and new_total < self.daily_budget_cap_usd:
            logger.warn("Daily LLM cost reached 80% threshold", current_spend=new_total, budget_cap=self.daily_budget_cap_usd)
        elif new_total >= self.daily_budget_cap_usd:
            logger.error("Daily LLM cost exceeded 100% budget cap! Circuit breaker active", current_spend=new_total)

        return new_total

    async def check_budget_status(self) -> Tuple[bool, str]:
        """Checks if budget is within bounds or if non-critical workloads must be degraded.
        Returns: (is_allowed, recommended_provider)
        """
        key = self._get_daily_key()
        current_spend_str = await self.redis.get(key)
        current_spend = float(current_spend_str) if current_spend_str else 0.0

        if current_spend >= self.daily_budget_cap_usd:
            # Circuit breaker tripped: Force fallback to local Ollama / heuristic
            return False, "ollama"
        elif current_spend >= (self.daily_budget_cap_usd * 0.9):
            # Degradation threshold: Use small Granite model
            return True, "ibm/granite-13b-chat-v2"

        return True, "standard"
```

---

## 8. 10 Comprehensive Production Incident Response Runbooks

---

### 8.1 Runbook 1: High Review Latency / Timeout Spike (P95 > 30s)

- **Symptoms:**
  - Alert `APICriticalLatency` or `AgentExecutionTimeout` firing in Slack/PagerDuty.
  - Review queue duration increases; developers experience slow PR webhooks.
- **Investigation:**
  1. Inspect the P95 review duration in Grafana dashboard panel 3.
  2. Check whether latency is concentrated in database queries or upstream LLM inference:
     ```bash
     # File: scripts/runbooks/check_llm_latency.sh
     # Check upstream LLM inference latency
     kubectl -n codevault logs -l app.kubernetes.io/name=codevault-api --tail=100 | grep "llm_latency_ms"
     ```
  3. Inspect PostgreSQL active queries:
     ```sql
     -- File: scripts/runbooks/active_pg_queries.sql
     SELECT pid, now() - query_start AS duration, query 
     FROM pg_stat_activity 
     WHERE state != 'idle' ORDER BY duration DESC LIMIT 5;
     ```
- **Mitigation:**
  1. If watsonx is responding slowly, temporarily switch to local Ollama or static AST evaluation:
     ```bash
     # File: scripts/runbooks/switch_llm_heuristic.sh
     kubectl set env deployment/codevault-api -n codevault LLM_PROVIDER=heuristic
     ```
  2. If slow database queries are blocking, kill queries exceeding 60 seconds:
     ```sql
     -- File: scripts/runbooks/terminate_slow_queries.sql
     SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state != 'idle' AND now() - query_start > interval '60 seconds';
     ```
- **Resolution:** Verify P95 review duration drops below 15s in Grafana.
- **Post-Mortem:** Conduct trace analysis in Jaeger to identify unoptimized agent nodes or missing database indexes.

---

### 8.2 Runbook 2: Multi-Agent Memory Leak / Worker Pod OOMKilled

- **Symptoms:**
  - Alert `PodOOMKilling` or `PodHighMemory` firing.
  - Pod restarts with termination reason `OOMKilled` (exit code 137).
- **Investigation:**
  1. Verify which pods were restarted:
     ```bash
     # File: scripts/runbooks/check_oom_pods.sh
     kubectl get pods -n codevault -o wide | grep OOMKilled
     ```
  2. Review memory consumption per container in Grafana panel 21.
  3. Inspect in-memory cache capacity (`CACHE_MAX_ITEMS`) and rate limiter tracked keys (`RATE_LIMIT_MAX_TRACKED`):
     ```bash
     # File: scripts/runbooks/check_cache_evictions.sh
     kubectl -n codevault logs <pod-name> | grep "evicting"
     ```
- **Mitigation:**
  1. Immediately bump Kubernetes memory limit to 6Gi:
     ```bash
     # File: scripts/runbooks/scale_pod_memory.sh
     kubectl set resources deployment/codevault-api -n codevault --limits=memory=6144Mi
     ```
  2. Force garbage collection and purge in-memory cache if leak is in worker process:
     ```bash
     # File: scripts/runbooks/rollout_restart_api.sh
     kubectl rollout restart deployment/codevault-api -n codevault
     ```
- **Resolution:** Observe steady-state memory utilization stabilizing below 70%.
- **Post-Mortem:** Run `tracemalloc` profile during batch review load tests to isolate uncollected AST node objects.

---

### 8.3 Runbook 3: PostgreSQL Connection Pool Starvation & Queue Exhaustion

- **Symptoms:**
  - Alert `DatabasePoolExhaustion` firing.
  - API returns HTTP 503 with error: `TimeoutError: QueuePool limit of size 20 overflow 20 reached`.
- **Investigation:**
  1. Inspect PostgreSQL connection states:
     ```sql
     -- File: scripts/runbooks/pg_stat_activity_count.sql
     SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
     ```
  2. Check for "idle in transaction" connection leaks:
     ```sql
     -- File: scripts/runbooks/pg_idle_transactions.sql
     SELECT pid, client_addr, now() - state_change as idle_duration, query 
     FROM pg_stat_activity 
     WHERE state = 'idle in transaction' AND now() - state_change > interval '2 minutes';
     ```
- **Mitigation:**
  1. Terminate all orphaned idle in transaction sessions:
     ```sql
     -- File: scripts/runbooks/pg_terminate_idle.sql
     SELECT pg_terminate_backend(pid) 
     FROM pg_stat_activity 
     WHERE state = 'idle in transaction' AND now() - state_change > interval '2 minutes';
     ```
  2. Increase pool size and overflow configuration via ConfigMap:
     ```bash
     # File: scripts/runbooks/patch_db_pool.sh
     kubectl patch configmap codevault-config -n codevault --type merge -p '{"data":{"DB_POOL_SIZE":"40","DB_MAX_OVERFLOW":"30"}}'
     kubectl rollout restart deployment/codevault-api -n codevault
     ```
- **Resolution:** Connection pool saturation drops below 50% in Grafana panel 19.
- **Post-Mortem:** Audit async session context managers (`async with get_db_session():`) to guarantee all sessions commit or rollback on exception.

---

### 8.4 Runbook 4: IBM watsonx Orchestrate Rate Limiting (HTTP 429) & Degradation

- **Symptoms:**
  - Alert `LLMRateLimit429` firing.
  - Reviews fail or take excessive time due to backoff retries.
- **Investigation:**
  1. Check rate of HTTP 429 responses in Grafana panel 18.
  2. Check current concurrent batch reviews in Prometheus: `sum(codevault_reviews_in_progress)`.
- **Mitigation:**
  1. Reduce batch concurrency limit immediately:
     ```bash
     # File: scripts/runbooks/patch_batch_concurrency.sh
     kubectl patch configmap codevault-config -n codevault --type merge -p '{"data":{"MAX_CONCURRENT_BATCH_REVIEWS":"3"}}'
     ```
  2. Temporarily route tier-2 agents (documentation, style) to heuristic evaluators to conserve token quota for tier-1 (security).
- **Resolution:** Rate of HTTP 429 errors returns to zero.
- **Post-Mortem:** Request watsonx TPM (Tokens Per Minute) and RPM quota increase from IBM Cloud support.

---

### 8.5 Runbook 5: Redis Cluster Failover & Cache Desynchronization

- **Symptoms:**
  - Alert `RedisDown` or `RedisMemoryHigh` firing.
  - High cache miss rates (`codevault_cache_misses_total` increasing rapidly).
- **Investigation:**
  1. Inspect Redis cluster health:
     ```bash
     # File: scripts/runbooks/redis_cluster_ping.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" ping
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" INFO replication
     ```
  2. Check memory usage and evicted keys:
     ```bash
     # File: scripts/runbooks/redis_check_memory.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" INFO memory
     ```
- **Mitigation:**
  1. If master crashed, initiate manual Sentinel/cluster failover:
     ```bash
     # File: scripts/runbooks/redis_sentinel_failover.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -p 26379 SENTINEL failover mymaster
     ```
  2. Flush corrupted cache keys if desynchronization observed:
     ```bash
     # File: scripts/runbooks/redis_flush_cache.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" FLUSHDB ASYNC
     ```
- **Resolution:** Application seamlessly resumes cache operations with hit rate recovering above 70%.
- **Post-Mortem:** Adjust `maxmemory-policy` to `allkeys-lru` and configure Redis AOF fsync.

---

### 8.6 Runbook 6: Graph Execution Deadlock / Stuck Review State

- **Symptoms:**
  - Alert `AgentDeadlockWarning` firing.
  - Active reviews count high (`reviews_in_progress > 20`) but zero completions.
- **Investigation:**
  1. Identify long-running review jobs in database:
     ```sql
     -- File: scripts/runbooks/find_stuck_reviews.sql
     SELECT id, status, created_at, now() - created_at as duration 
     FROM reviews 
     WHERE status = 'in_progress' AND now() - created_at > interval '10 minutes';
     ```
  2. Inspect pod logs for asyncio deadlocks or circular waiting in LangGraph nodes:
     ```bash
     # File: scripts/runbooks/check_deadlock_logs.sh
     kubectl logs -n codevault -l app.kubernetes.io/name=codevault-api --tail=500 | grep "deadlock"
     ```
- **Mitigation:**
  1. Enforce hard timeout on stuck reviews by updating database status to `failed`:
     ```sql
     -- File: scripts/runbooks/timeout_stuck_reviews.sql
     UPDATE reviews 
     SET status = 'failed', summary = 'Review timed out after 10 minutes (automated watchdog)'
     WHERE status = 'in_progress' AND now() - created_at > interval '10 minutes';
     ```
  2. Rollout restart of API pods to terminate hung asyncio event loop tasks:
     ```bash
     # File: scripts/runbooks/restart_deadlocked_pods.sh
     kubectl rollout restart deployment/codevault-api -n codevault
     ```
- **Resolution:** `codevault_reviews_in_progress` returns to healthy baseline (< 10).
- **Post-Mortem:** Implement strict `asyncio.wait_for(node_execution(), timeout=45.0)` across all LangGraph agent state transitions.

---

### 8.7 Runbook 7: LLM Token Budget Overrun / Runaway Cost Spike

- **Symptoms:**
  - Alert `TokenBudgetExceeded` or `CostAnomalySpike` firing.
  - Cumulative daily cost exceeds $500 threshold.
- **Investigation:**
  1. Inspect Grafana panel 16 for cost trajectory.
  2. Identify top token-consuming tenant or repository:
     ```sql
     -- File: scripts/runbooks/top_token_tenants.sql
     SELECT tenant_id, sum(prompt_tokens + completion_tokens) as total_tokens 
     FROM reviews 
     WHERE created_at > now() - interval '24 hours' 
     GROUP BY tenant_id ORDER BY total_tokens DESC LIMIT 5;
     ```
- **Mitigation:**
  1. Enable automated circuit breaker by forcing fallback model:
     ```bash
     # File: scripts/runbooks/circuit_breaker_ollama.sh
     kubectl patch configmap codevault-config -n codevault --type merge -p '{"data":{"LLM_PROVIDER":"ollama"}}'
     ```
  2. Restrict maximum file size analyzed per PR to 200 lines until daily reset:
     ```bash
     # File: scripts/runbooks/restrict_file_lines.sh
     kubectl patch configmap codevault-config -n codevault --type merge -p '{"data":{"MAX_FILE_LINES":"200"}}'
     ```
- **Resolution:** Hourly spend rate drops to compute-only baseline ($0/hr).
- **Post-Mortem:** Implement per-tenant daily quota tiers and throttle excessive batch reviews.

---

### 8.8 Runbook 8: Real-Time WebSocket Disconnect Storm & Buffer Bloat

- **Symptoms:**
  - Alert `WebSocketConnectionLeak` firing.
  - Pod file descriptor usage spikes (`process_open_fds > 1024`).
- **Investigation:**
  1. Check open socket counts:
     ```bash
     # File: scripts/runbooks/check_socket_descriptors.sh
     kubectl exec -it <pod-name> -n codevault -- ss -s
     ```
  2. Inspect logs for uncleaned WebSocket connections upon client abort:
     ```bash
     # File: scripts/runbooks/check_ws_disconnect_logs.sh
     kubectl logs -n codevault <pod-name> | grep "WebSocketDisconnect"
     ```
- **Mitigation:**
  1. Force restart of leaking pods:
     ```bash
     # File: scripts/runbooks/delete_leaking_ws_pods.sh
     kubectl delete pod -l app.kubernetes.io/name=codevault-api -n codevault
     ```
  2. Ensure server-side ping/pong heartbeat drops dead connections after 30s.
- **Resolution:** Active WebSocket connections drop to match real concurrent browser sessions.
- **Post-Mortem:** Verify that `websocket.close()` is executed in a `finally` block in `cerberus/api/websockets.py`.

---

### 8.9 Runbook 9: HashiCorp Vault Token Expiry & Secret Injection Failure

- **Symptoms:**
  - External Secrets Operator logs error: `SecretStore provider error: permission denied / token expired`.
  - Pods enter `CreateContainerConfigError` when referencing missing secrets.
- **Investigation:**
  1. Inspect ExternalSecret resource status:
     ```bash
     # File: scripts/runbooks/describe_external_secret.sh
     kubectl describe externalsecret codevault-vault-secrets -n codevault
     ```
  2. Check Vault Kubernetes service account token validity:
     ```bash
     # File: scripts/runbooks/lookup_vault_accessor.sh
     vault token lookup -accessor <accessor-id>
     ```
- **Mitigation:**
  1. Re-authenticate Kubernetes Auth role in HashiCorp Vault:
     ```bash
     # File: scripts/runbooks/reapply_vault_config.sh
     bash scripts/configure_vault.sh
     ```
  2. Force immediate refresh of ExternalSecret:
     ```bash
     # File: scripts/runbooks/force_sync_secret.sh
     kubectl annotate externalsecret codevault-vault-secrets -n codevault force-sync=$(date +%s) --overwrite
     ```
- **Resolution:** ExternalSecret status changes to `SecretSynced: True`.
- **Post-Mortem:** Extend Vault token TTL to 24h with periodic background renewal sidecar.

---

### 8.10 Runbook 10: Zombie Agent Process Execution & Cache Invalidation Failure

- **Symptoms:**
  - Old, outdated review findings are repeatedly served to users.
  - Review score contradicts newly committed code changes.
- **Investigation:**
  1. Verify cache key generation logic:
     ```python
     # File: cerberus/core/cache_key_hashing.py
     # Key must be SHA256 of code content + enabled agents
     # Check if cache is returning stale hits for modified code
     ```
  2. Inspect Redis for stale keys:
     ```bash
     # File: scripts/runbooks/check_stale_redis_keys.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" KEYS "codevault:review:*"
     ```
- **Mitigation:**
  1. Purge review cache keys for affected repository:
     ```bash
     # File: scripts/runbooks/purge_stale_cache_keys.sh
     redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" --scan --pattern "codevault:review:*" | xargs -L 100 redis-cli -h redis-cluster.redis.svc.cluster.local -a "$REDIS_PASSWORD" DEL
     ```
- **Resolution:** New review submissions generate fresh analysis with current code diffs.
- **Post-Mortem:** Enforce git commit SHA hashing in cache key generation to guarantee automatic invalidation upon new commits.

---

## 9. Health Check Probes, SLI/SLO Framework & Error Budget Policies

### 9.1 Health Check Probe Implementations (/health/live, /health/ready, /health/startup)

```python
# File: cerberus/api/health.py
from fastapi import APIRouter, status, Response
from pydantic import BaseModel
from typing import Dict, Any
import sqlalchemy as sa
from cerberus.core.database import async_session_factory
from cerberus.core.cache import cache_manager

router = APIRouter(prefix="/api/v1", tags=["Health & Diagnostics"])

class HealthStatusResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    dependencies: Dict[str, str]

@router.get("/health", status_code=status.HTTP_200_OK)
@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes Liveness Probe: Confirms the process is running and event loop is responsive."""
    return {"status": "alive"}

@router.get("/health/ready", response_model=HealthStatusResponse)
async def readiness_probe(response: Response) -> HealthStatusResponse:
    """Kubernetes Readiness Probe: Verifies PostgreSQL and Redis dependencies are operational."""
    dep_status = {"database": "unknown", "cache": "unknown"}
    overall_healthy = True

    # 1. Check PostgreSQL Connection
    try:
        async with async_session_factory() as session:
            await session.execute(sa.text("SELECT 1"))
            dep_status["database"] = "healthy"
    except Exception:
        dep_status["database"] = "unhealthy"
        overall_healthy = False

    # 2. Check Redis / Cache Connection
    try:
        if cache_manager.is_redis_available():
            dep_status["cache"] = "healthy"
        else:
            dep_status["cache"] = "degraded_memory_only"
    except Exception:
        dep_status["cache"] = "unhealthy"
        overall_healthy = False

    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatusResponse(status="unhealthy", dependencies=dep_status)

    return HealthStatusResponse(status="ready", dependencies=dep_status)

@router.get("/health/startup", status_code=status.HTTP_200_OK)
async def startup_probe(response: Response) -> Dict[str, str]:
    """Kubernetes Startup Probe: Confirms database schema migrations and initial config loading."""
    try:
        async with async_session_factory() as session:
            result = await session.execute(sa.text("SELECT count(*) FROM reviews"))
            _ = result.scalar()
        return {"status": "started"}
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "starting", "error": str(exc)}
```

---

### 9.2 Service Level Indicators (SLIs) and Objectives (SLOs)

| Objective Domain | SLI Specification | Target SLO | Measurement Window |
|---|---|---|---|
| **Platform Availability** | Successful HTTP responses (`2xx`, `3xx`, `4xx`) / Total requests | **99.9%** | Rolling 30-Day Window |
| **Review Execution Latency** | Percentage of code reviews (<500 LOC) completing in < 15.0s | **95.0%** | Rolling 7-Day Window |
| **System Error Rate** | Total 5xx server responses / Total API requests | **< 0.1%** | Rolling 24-Hour Window |
| **Agent Execution Integrity** | Specialized agent runs completing without unhandled exceptions | **99.5%** | Rolling 30-Day Window |

---

### 9.3 Multi-Window Error Budget Burn Rate Policies

CodeVault AI implements Google SRE multi-window, multi-burn-rate alerting policies to protect platform reliability:

| Severity | Burn Rate | Budget Consumed | Short Window | Long Window | Operational Action |
|---|---|---|---|---|---|
| **Critical (P1)** | **14.4x** | 2% in 1 hour | 5 minutes | 1 hour | Immediate PagerDuty page to Primary On-Call; freeze all deployments |
| **Critical (P1)** | **6.0x** | 5% in 6 hours | 30 minutes | 6 hours | Page Primary On-Call; investigate upstream dependencies |
| **Warning (P2)** | **1.0x** | 10% in 3 days | 2 hours | 3 days | Dispatch Slack alert to SRE team; create reliability remediation ticket |

#### Error Budget Enforcement Policy
1. **At 50% Budget Consumption (within 7 days):**
   - Non-critical feature deployments paused.
   - Engineering focus directed to reliability bug fixes.
2. **At 100% Budget Consumption:**
   - Production deployment freeze automatically enforced in CI/CD pipeline.
   - Only emergency P1 security and stability patches permitted.

---

## 10. Summary & Pointer to Next Document

This manual established the comprehensive observability, metrics instrumentation, alerting rules, structured logging, distributed tracing, and incident response foundation for CodeVault AI.

To review test framework configurations, unit/integration/E2E test suites, mock fixtures for IBM watsonx Orchestrate, and distributed load testing scripts, proceed to the next document:

👉 **Next Document:** [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
