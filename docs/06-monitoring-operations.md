# Cerberus - Monitoring & Operations Guide

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## Table of Contents

- [Monitoring Setup](#monitoring-setup)
- [Key Metrics](#key-metrics)
- [Logging](#logging)
- [Health Checks](#health-checks)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Maintenance Tasks](#maintenance-tasks)
- [Performance Optimization](#performance-optimization)
- [Alerting](#alerting)

---

## Monitoring Setup

### Prometheus Configuration

**prometheus.yml:**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'cerberus-api'
    static_configs:
      - targets: ['cerberus-api:8000']
    metrics_path: '/metrics'
    
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
  
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### Grafana Dashboard Setup

**Dashboard JSON:**

```json
{
  "dashboard": {
    "title": "Cerberus Multi-Agent AI Overview",
    "panels": [
      {
        "title": "Review Request Rate",
        "targets": [
          {
            "expr": "rate(cerberus_review_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Average Review Duration",
        "targets": [
          {
            "expr": "rate(cerberus_review_duration_seconds_sum[5m]) / rate(cerberus_review_duration_seconds_count[5m])"
          }
        ]
      },
      {
        "title": "Cache Hit Rate",
        "targets": [
          {
            "expr": "rate(cerberus_cache_hits_total[5m]) / (rate(cerberus_cache_hits_total[5m]) + rate(cerberus_cache_misses_total[5m]))"
          }
        ]
      },
      {
        "title": "Findings Rate by Severity",
        "targets": [
          {
            "expr": "sum by (severity) (rate(cerberus_findings_detected_total[5m]))"
          }
        ]
      }
    ]
  }
}
```

---

## Key Metrics

### Application Metrics

Cerberus exposes production metrics generated via `cerberus/core/telemetry.py`:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cerberus_review_requests_total` | Counter | `status`, `language` | Total number of code review requests processed |
| `cerberus_review_duration_seconds` | Histogram | None | Total time spent analyzing code reviews (buckets: 0.1 to 30.0s) |
| `cerberus_agent_execution_seconds` | Histogram | `agent_name` | Individual execution duration per agent |
| `cerberus_findings_detected_total` | Counter | `agent_name`, `severity` | Count of findings discovered by agents |
| `cerberus_cache_hits_total` | Counter | None | Number of review requests served directly from cache |
| `cerberus_cache_misses_total` | Counter | None | Number of review requests requiring fresh agent analysis |

### System Metrics

| Metric | Description |
|--------|-------------|
| `process_cpu_usage` | CPU usage percentage |
| `process_memory_bytes` | Memory usage |
| `database_connections_active` | Active DB connections |
| `redis_connections_active` | Active Redis connections |

### Example Queries

**Review requests per minute:**
```promql
rate(cerberus_review_requests_total[1m]) * 60
```

**Average review duration (last hour):**
```promql
rate(cerberus_review_duration_seconds_sum[1h]) / rate(cerberus_review_duration_seconds_count[1h])
```

**Average per-agent execution time:**
```promql
rate(cerberus_agent_execution_seconds_sum[5m]) / rate(cerberus_agent_execution_seconds_count[5m])
```

**Cache hit rate percentage:**
```promql
(rate(cerberus_cache_hits_total[5m]) / (rate(cerberus_cache_hits_total[5m]) + rate(cerberus_cache_misses_total[5m]))) * 100
```

**P95 review latency:**
```promql
histogram_quantile(0.95, rate(cerberus_review_duration_seconds_bucket[5m]))
```

**Findings detected per minute by severity:**
```promql
sum by (severity) (rate(cerberus_findings_detected_total[1m])) * 60
```

---

## Logging

### Log Structure

**JSON Format:**
```json
{
  "timestamp": "2026-09-21T10:30:00.123Z",
  "level": "INFO",
  "component": "security_agent",
  "review_id": "rev_abc123",
  "message": "Security analysis completed",
  "duration_ms": 3450,
  "findings_count": 2,
  "request_id": "req_xyz789",
  "user_id": "user_123",
  "metadata": {
    "language": "python",
    "file_size_bytes": 1024,
    "cache_hit": false
  }
}
```

### Log Levels

| Level | Usage | Example |
|-------|-------|---------|
| **DEBUG** | Detailed flow | "Calling LLM with prompt..." |
| **INFO** | Key events | "Review started", "Agent completed" |
| **WARNING** | Recoverable issues | "Cache miss", "Retry attempt" |
| **ERROR** | Failures | "LLM timeout", "Database error" |
| **CRITICAL** | System failures | "Cannot connect to database" |

### Key Log Messages

**Review Lifecycle:**
```
INFO  Review created: review_id=rev_abc123
INFO  Agents scheduled: agents=['security', 'performance', 'quality']
INFO  Security agent started: review_id=rev_abc123
INFO  Security agent completed: duration_ms=3200, findings=2
INFO  All agents completed: review_id=rev_abc123, total_duration_ms=8450
INFO  Review completed: review_id=rev_abc123, score=85
```

**Errors:**
```
ERROR LLM provider timeout: provider=openai, timeout=30s
ERROR Database connection failed: error="connection refused"
WARNING Agent retry attempt: agent=security, attempt=2/3
```

### Log Aggregation

**Using Grafana Loki:**

```yaml
# promtail.yml
clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: cerberus
    static_configs:
      - targets:
          - localhost
        labels:
          job: cerberus
          __path__: /var/log/cerberus/*.log
```

---

## Health Checks

### Endpoint Health

```bash
# Basic health check
curl http://localhost:8000/api/v1/health

# Expected response (healthy):
{
  "status": "healthy",
  "version": "0.1.0",
  "components": {
    "api": {"status": "healthy"},
    "database": {"status": "healthy"},
    "cache": {"status": "healthy"},
    "llm_providers": {
      "openai": {"status": "healthy"}
    }
  }
}
```

### Component Health Scripts

**check_database.sh:**
```bash
#!/bin/bash
docker-compose exec db pg_isready -U cerberus
if [ $? -eq 0 ]; then
  echo "✅ Database is healthy"
else
  echo "❌ Database is unhealthy"
  exit 1
fi
```

**check_redis.sh:**
```bash
#!/bin/bash
docker-compose exec redis redis-cli ping
if [ $? -eq 0 ]; then
  echo "✅ Redis is healthy"
else
  echo "❌ Redis is unhealthy"
  exit 1
fi
```

**check_llm.sh:**
```bash
#!/bin/bash
HEALTH=$(curl -s http://localhost:8000/api/v1/health | jq -r '.components.llm_providers.openai.status')
if [ "$HEALTH" = "healthy" ]; then
  echo "✅ LLM provider is healthy"
else
  echo "❌ LLM provider is unhealthy: $HEALTH"
  exit 1
fi
```

### Automated Health Monitoring

**healthcheck-cron.sh:**
```bash
#!/bin/bash
# Run every 5 minutes via cron: */5 * * * * /path/to/healthcheck-cron.sh

WEBHOOK_URL="https://your-monitoring-service.com/webhook"

# Check all components
API_HEALTH=$(curl -s http://localhost:8000/api/v1/health | jq -r '.status')
DB_HEALTH=$(docker-compose exec -T db pg_isready -U cerberus > /dev/null 2>&1 && echo "healthy" || echo "unhealthy")
REDIS_HEALTH=$(docker-compose exec -T redis redis-cli ping > /dev/null 2>&1 && echo "healthy" || echo "unhealthy")

if [ "$API_HEALTH" != "healthy" ] || [ "$DB_HEALTH" != "healthy" ] || [ "$REDIS_HEALTH" != "healthy" ]; then
  # Send alert
  curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{
      \"alert\": \"Cerberus unhealthy\",
      \"api\": \"$API_HEALTH\",
      \"database\": \"$DB_HEALTH\",
      \"redis\": \"$REDIS_HEALTH\"
    }"
fi
```

---

## Troubleshooting Guide

### 1. High Review Latency

**Symptoms:**
- Reviews taking > 30 seconds
- User complaints about slow responses

**Diagnosis:**
```bash
# Check metrics
curl -s "http://localhost:9090/api/v1/query?query=rate(cerberus_review_duration_seconds_sum[5m])/rate(cerberus_review_duration_seconds_count[5m])"

# Check LLM provider latency
curl -s http://localhost:8000/api/v1/health?detailed=true | jq '.components.llm_providers'

# Check database performance
docker-compose exec db psql -U cerberus -c "SELECT * FROM pg_stat_activity;"
```

**Resolution:**
1. Check LLM provider status and response times
2. Increase cache TTL to improve hit rate
3. Consider switching to faster LLM model (gpt-3.5-turbo)
4. Scale up workers: `CERBERUS_WORKERS=8`
5. Add database indexes if slow queries detected

### 2. LLM Connection Failures

**Symptoms:**
- `llm_provider_error` in logs
- Reviews failing with provider errors

**Diagnosis:**
```bash
# Test OpenAI connection
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Check provider config
docker-compose exec api python -c "
import os
print('Provider:', os.getenv('LLM_PROVIDER'))
print('API Key set:', bool(os.getenv('OPENAI_API_KEY')))
"
```

**Resolution:**
1. Verify API key is valid and has credit
2. Check rate limits: `curl -I https://api.openai.com/v1/models -H "Authorization: Bearer $KEY"`
3. Enable fallback provider in config
4. Switch to local Ollama if persistent issues

### 3. Database Connection Pool Exhausted

**Symptoms:**
- `TimeoutError: QueuePool limit exceeded`
- Slow review processing

**Diagnosis:**
```bash
# Check active connections
docker-compose exec db psql -U cerberus -c "
SELECT count(*) as connections, state
FROM pg_stat_activity
WHERE datname='cerberus'
GROUP BY state;
"
```

**Resolution:**
```yaml
# Increase pool size in config
database:
  pool_size: 20        # Was 10
  max_overflow: 40     # Was 20
```

### 4. Cache Memory Issues

**Symptoms:**
- Redis evicting keys frequently
- Low cache hit rate

**Diagnosis:**
```bash
# Check Redis memory
docker-compose exec redis redis-cli INFO memory

# Check evictions
docker-compose exec redis redis-cli INFO stats | grep evicted
```

**Resolution:**
```bash
# Increase Redis memory
# In docker-compose.yml:
redis:
  command: redis-server --maxmemory 1gb  # Was 512mb
```

### 5. High Error Rate

**Symptoms:**
- `cerberus_review_requests_total{status="failed"}` increasing
- Failed reviews

**Diagnosis:**
```bash
# Check failed review counts
curl -s "http://localhost:9090/api/v1/query?query=cerberus_review_requests_total{status='failed'}" | jq

# Check logs for errors
docker-compose logs api | grep ERROR | tail -50
```

**Resolution:**
1. Identify error pattern from logs
2. Fix configuration if config-related
3. Restart services if transient: `docker-compose restart`
4. Roll back if related to recent deployment

### 6. Git Hook Not Triggering

**Symptoms:**
- Hook not running on commit
- No review feedback

**Diagnosis:**
```bash
# Check hook exists and is executable
ls -la .git/hooks/pre-commit

# Test hook manually
.git/hooks/pre-commit

# Check API connectivity from hook
curl http://localhost:8000/api/v1/health
```

**Resolution:**
1. Ensure hook is executable: `chmod +x .git/hooks/pre-commit`
2. Verify `CERBERUS_API_KEY` environment variable set
3. Check API URL in hook matches running instance
4. Test with `--no-verify` to isolate issue

### 7. Out of Memory

**Symptoms:**
- Container crashes
- `OOMKilled` in Docker logs

**Diagnosis:**
```bash
# Check container memory usage
docker stats cerberus-api

# Check system memory
free -h
```

**Resolution:**
```yaml
# Increase container memory limits
api:
  deploy:
    resources:
      limits:
        memory: 4G  # Was 2G
```

### 8. Slow Database Queries

**Symptoms:**
- High database latency
- Slow review retrieval

**Diagnosis:**
```sql
-- Check slow queries
SELECT * FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Check missing indexes
SELECT * FROM pg_stat_user_tables 
WHERE seq_scan > 100 AND idx_scan = 0;
```

**Resolution:**
```sql
-- Add indexes for common queries
CREATE INDEX idx_reviews_created_at ON reviews(created_at);
CREATE INDEX idx_reviews_user_id ON reviews(user_id);
CREATE INDEX idx_agent_findings_review_id ON agent_findings(review_id);
```

---

## Maintenance Tasks

### Daily Tasks

**1. Check System Health:**
```bash
#!/bin/bash
# daily-health-check.sh

echo "=== Daily Health Check ==="
echo "Date: $(date)"

# API health
curl -s http://localhost:8000/api/v1/health | jq '.status'

# Check disk space
df -h | grep -E '(Filesystem|/var/lib/docker)'

# Check logs for errors
ERROR_COUNT=$(docker-compose logs api --since 24h | grep ERROR | wc -l)
echo "Errors in last 24h: $ERROR_COUNT"

# Check metrics
echo "Reviews last 24h:"
curl -s "http://localhost:9090/api/v1/query?query=increase(cerberus_review_requests_total[24h])" | jq '.data.result[0].value[1]'
```

**2. Review Metrics:**
```bash
# Check cache hit rate
curl -s "http://localhost:9090/api/v1/query?query=rate(cerberus_cache_hits_total[5m])/(rate(cerberus_cache_hits_total[5m])+rate(cerberus_cache_misses_total[5m]))" | jq '.data.result[0].value[1]'
```

### Weekly Tasks

**1. Database Cleanup:**
```sql
-- Delete old reviews (optional, based on retention policy)
DELETE FROM reviews 
WHERE created_at < NOW() - INTERVAL '90 days';

-- Vacuum database
VACUUM ANALYZE;
```

**2. Cache Cleanup:**
```bash
# Clear stale cache entries
docker-compose exec redis redis-cli --scan --pattern "cerberus:review:*" | \
  xargs -L 1 docker-compose exec -T redis redis-cli TTL | \
  awk '$1 == -1 {print $0}' | \
  xargs -L 1 docker-compose exec -T redis redis-cli DEL
```

**3. Log Rotation:**
```bash
# Rotate logs
docker-compose exec api python -m cerberus.cli rotate-logs --keep 30
```

### Monthly Tasks

**1. Database Backup:**
```bash
#!/bin/bash
# monthly-backup.sh

BACKUP_DIR="/backups/cerberus"
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"

# Backup database
docker-compose exec -T db pg_dump -U cerberus cerberus | gzip > "$BACKUP_DIR/cerberus-$DATE.sql.gz"

# Backup configuration
cp -r config "$BACKUP_DIR/config-$DATE"

# Keep only last 3 months
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +90 -delete
```

**2. Update Dependencies:**
```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose up -d
```

**3. Review and Optimize:**
```bash
# Analyze performance trends
# Review Grafana dashboards
# Identify optimization opportunities
# Update configuration as needed
```

---

## Performance Optimization

### 1. Optimize Cache Hit Rate

**Target:** > 70% cache hit rate

**Actions:**
```yaml
# Increase cache TTL
cache:
  ttl_seconds: 1209600  # 14 days instead of 7

# Use aggressive caching
performance:
  caching:
    aggressive: true
```

### 2. Reduce LLM Costs

**Actions:**
- Use GPT-3.5-turbo for quality agent (cheaper)
- Increase cache hit rate
- Use batch processing for multiple files
- Consider local Ollama for non-sensitive code

```yaml
agents:
  quality:
    llm_model: "gpt-3.5-turbo"  # Instead of gpt-4
  performance:
    llm_model: "gpt-3.5-turbo"
```

**Cost Savings:**
- GPT-4: ~$0.03/review
- GPT-3.5: ~$0.001/review
- Ollama: $0/review

### 3. Scale Horizontally

**Add more workers:**
```yaml
# docker-compose.yml
api:
  deploy:
    replicas: 3
```

**Use load balancer:**
```yaml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
```

---

## Alerting

### Prometheus Alert Rules

**alerts.yml:**
```yaml
groups:
  - name: cerberus
    interval: 30s
    rules:
      - alert: HighReviewFailureRate
        expr: rate(cerberus_review_requests_total{status="failed"}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High review failure rate detected"
          description: "Review failure rate is {{ $value }} errors/sec"
      
      - alert: SlowReviews
        expr: rate(cerberus_review_duration_seconds_sum[5m]) / rate(cerberus_review_duration_seconds_count[5m]) > 30
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Reviews are slow"
          description: "Average review time is {{ $value }}s"
      
      - alert: LowCacheHitRate
        expr: rate(cerberus_cache_hits_total[15m]) / (rate(cerberus_cache_hits_total[15m]) + rate(cerberus_cache_misses_total[15m])) < 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Low cache hit rate"
          description: "Cache hit rate is {{ $value }}"
      
      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database is down"
      
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis is down"
```

### Notification Channels

**Slack:**
```yaml
# alertmanager.yml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#cerberus-alerts'
```

**Email:**
```yaml
receivers:
  - name: 'email'
    email_configs:
      - to: 'ops@example.com'
        from: 'alertmanager@example.com'
        smarthost: 'smtp.gmail.com:587'
```

**PagerDuty:**
```yaml
receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

---

**Next Steps:**
- [Security & Compliance](07-security-compliance.md) - Secure your deployment
- [Developer Guide](08-developer-guide.md) - Extend functionality

---

*Cerberus Monitoring & Operations Guide - v0.1.0*
