# Cerberus - Installation & Setup Guide

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (5 Minutes)](#quick-start-5-minutes)
- [Local Development Setup](#local-development-setup)
- [Cloud Deployment](#cloud-deployment)
- [Git Hooks Integration](#git-hooks-integration)
- [Verification & Testing](#verification--testing)
- [Troubleshooting](#troubleshooting)
- [Upgrade & Migration](#upgrade--migration)

---

## Prerequisites

### Required Software

| Software | Minimum Version | Purpose |
|----------|----------------|---------|
| **Docker** | 24.0+ | Container runtime |
| **Docker Compose** | 2.20+ | Multi-container orchestration |
| **Git** | 2.30+ | Version control (for hooks) |
| **Python** | 3.11+ | CLI tool (optional) |

### LLM Provider Requirements

Cerberus supports multiple LLM providers as well as a zero-credential heuristic fallback:

**Option 1: Heuristic Engine (Default, Zero-Config)**
- **No external API key or internet access required**
- 100% deterministic, instant execution, zero cloud cost
- Uses AST parsing, regex vulnerability patterns, and heuristic analyzers
- `LLM_PROVIDER=heuristic` (the built-in default)

**Option 2: IBM watsonx (Recommended for Enterprise)**
- Powered by IBM Granite models (default: `ibm/granite-3-8b-instruct`)
- Automated IBM Cloud IAM OAuth token exchange
- Requires `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, and `WATSONX_URL`
- Refer to [`WATSONX_INTEGRATION.md`](../WATSONX_INTEGRATION.md) for full setup instructions

**Option 3: OpenAI**
- Requires API key from [platform.openai.com](https://platform.openai.com)
- Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=sk-...`

**Option 4: Ollama (Local LLM)**
- Free local execution using Ollama
- Set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL=http://localhost:11434`

### System Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4GB
- Disk: 10GB free

**Recommended:**
- CPU: 4+ cores
- RAM: 8GB+
- Disk: 20GB+ free
- SSD storage

---

## Quick Start (5 Minutes)

Get Cerberus running locally in under 5 minutes.

### Step 1: Clone and Configure

```bash
# Clone repository
git clone https://github.com/cerberus-ai/MultiAgent-CodeReview.git
cd MultiAgent-CodeReview

# Copy example environment file
cp .env.example .env

# By default, LLM_PROVIDER=heuristic works out of the box with zero external configuration!
# To use IBM watsonx, add:
# echo "LLM_PROVIDER=watsonx" >> .env
# echo "WATSONX_API_KEY=your-ibm-cloud-key" >> .env
# echo "WATSONX_PROJECT_ID=your-project-id" >> .env
```

### Step 2: Start Services

**Option A: Running with Docker Compose**
```bash
# Start all containerized services
docker-compose up -d

# Check container status
docker-compose ps
```

**Expected Container Output:**
```
NAME                STATUS              PORTS
cerberus-api        Up 30 seconds       0.0.0.0:8000->8000/tcp
cerberus-redis      Up 30 seconds       6379/tcp
cerberus-postgres   Up 30 seconds       5432/tcp
```

**Option B: Running Locally with Python**
```bash
# Install dependencies
pip install -r requirements.txt

# Start API server directly via the Cerberus CLI
python -m cerberus.cli serve --host 0.0.0.0 --port 8000
```

### Step 3: Verify Installation

```bash
# Health check (no authentication required)
curl http://localhost:8000/api/v1/health

# Response:
# {"status":"healthy","version":"0.1.0","database":"connected","cache":"in_memory_lru","active_agents":["security","performance","quality","architecture","compliance"],"uptime_seconds":1.2}
```

### Step 4: Authentication & API Keys

In development mode (`ENVIRONMENT=development`), the default API key `cvai_dev_key_123` is automatically pre-seeded.

You can also create a new API key at any time using the CLI:
```bash
python -m cerberus.cli create-api-key --name "my-dev-key"

# Output:
# API Key created successfully!
# Key: cvai_1234567890abcdefghijklmnop
# Name: my-dev-key
```

### Step 5: Run First Review

```bash
# Test review with pre-seeded dev key
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def hello():\n    print(\"Hello, World!\")",
    "language": "python"
  }'
```

**Success!** You now have Cerberus running locally. 🎉

---

## Local Development Setup

### Docker Compose Configuration

**Production docker-compose.yml:**

```yaml
version: '3.8'

services:
  api:
    build: .
    container_name: cerberus-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - HOST=0.0.0.0
      - PORT=8000
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql+asyncpg://cerberus:${DB_PASSWORD:-dev_password}@db:5432/cerberus_db
      - REDIS_URL=redis://redis:6379/0
      - CACHE_ENABLED=true
      - LLM_PROVIDER=${LLM_PROVIDER:-heuristic}
      - WATSONX_API_KEY=${WATSONX_API_KEY:-}
      - WATSONX_PROJECT_ID=${WATSONX_PROJECT_ID:-}
      - WATSONX_URL=${WATSONX_URL:-https://us-south.ml.cloud.ibm.com}
      - WATSONX_MODEL_ID=${WATSONX_MODEL_ID:-ibm/granite-3-8b-instruct}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://ollama:11434}
      - ENABLED_AGENTS=security,performance,quality,architecture,compliance
      - SECRET_KEY=${SECRET_KEY:-cerberus_production_secret_key_change_me_now_1234}
    depends_on:
      - db
      - redis
    networks:
      - cerberus-network

  db:
    image: postgres:15-alpine
    container_name: cerberus-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: cerberus
      POSTGRES_PASSWORD: ${DB_PASSWORD:-dev_password}
      POSTGRES_DB: cerberus_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - cerberus-network

  redis:
    image: redis:7-alpine
    container_name: cerberus-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - cerberus-network

networks:
  cerberus-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

### Environment Configuration

**Complete .env file:**

```bash
# ============================================
# Cerberus Multi-Agent System Configuration
# ============================================

# --- Core Server Settings ---
ENVIRONMENT=development
HOST=0.0.0.0
PORT=8000
SECRET_KEY=e4c198518244d0ef6fdbb8c907c3072465c91ccc44bf2092136c4de6c7382a7d
ALLOWED_HOSTS=*
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# --- Database & Cache ---
DATABASE_URL=sqlite+aiosqlite:///./cerberus.db
DB_PASSWORD=dev_password
REDIS_URL=redis://localhost:6379/0
CACHE_ENABLED=true
CACHE_TTL_SECONDS=86400
CACHE_MAX_ITEMS=1000

# --- LLM Provider Selection ---
# Options: heuristic (default), watsonx, openai, ollama
LLM_PROVIDER=heuristic

# --- IBM watsonx Configuration ---
WATSONX_API_KEY=
WATSONX_PROJECT_ID=
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-3-8b-instruct

# --- OpenAI Configuration ---
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# --- Ollama Configuration (Local) ---
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=codellama

# --- Active Agents ---
ENABLED_AGENTS=security,performance,quality,architecture,compliance

# --- Operational Thresholds ---
SEVERITY_THRESHOLD=medium
BLOCKING_MODE=false
MAX_CONCURRENT_BATCH_REVIEWS=5
MAX_BATCH_SIZE=100
RATE_LIMIT_PER_HOUR=100
```

### Connecting to Different LLM Backends

#### IBM watsonx Setup (Enterprise)

IBM watsonx is the enterprise model backbone featuring IBM Granite models:

```bash
# Set provider
export LLM_PROVIDER=watsonx

# Configure IBM Cloud credentials
export WATSONX_API_KEY="${WATSONX_API_KEY}"
export WATSONX_PROJECT_ID="${WATSONX_PROJECT_ID}"
export WATSONX_URL="https://us-south.ml.cloud.ibm.com"
export WATSONX_MODEL_ID="ibm/granite-3-8b-instruct"
```

> **Note:** Cerberus automatically exchanges `WATSONX_API_KEY` for temporary IAM OAuth bearer tokens via `https://iam.cloud.ibm.com/identity/token`, caches the bearer token, and handles token expiry refresh seamlessly. See [`WATSONX_INTEGRATION.md`](../WATSONX_INTEGRATION.md) for full IAM permissions and setup guidance.

#### Heuristic Engine (Default, Zero-Config)

```bash
# Enabled out-of-the-box:
export LLM_PROVIDER=heuristic
```
No external API keys or network connection required. Full static security analysis, AST inspection, and compliance checking run locally.

#### OpenAI Setup

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o"
```

#### Ollama Setup (Local)

```bash
# Pull model
ollama pull codellama

# Point Cerberus to Ollama instance
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="codellama"
```

### Volume Mounting for Development

For local development with hot reload:

```yaml
# docker-compose.dev.yml
services:
  api:
    volumes:
      - ./cerberus:/app/cerberus
    environment:
      - ENVIRONMENT=development
```

```bash
# Run in development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

---

## Cloud Deployment

### AWS Deployment (ECS Fargate)

**Step 1: Build and Push Docker Image**

```bash
# Build image
docker build -t cerberus/api:latest .

# Tag for ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker tag cerberus/api:latest <account>.dkr.ecr.us-east-1.amazonaws.com/cerberus:latest

# Push to ECR
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/cerberus:latest
```

**Step 2: Create ECS Task Definition**

```json
{
  "family": "cerberus-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "cerberus-api",
      "image": "<account>.dkr.ecr.us-east-1.amazonaws.com/cerberus:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "DATABASE_URL", "value": "postgresql://..."},
        {"name": "REDIS_URL", "value": "redis://..."}
      ],
      "secrets": [
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:...:secret:cerberus/openai-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/cerberus",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api"
        }
      }
    }
  ]
}
```

**Step 3: Create ECS Service**

```bash
aws ecs create-service \
  --cluster cerberus-cluster \
  --service-name cerberus-api \
  --task-definition cerberus-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=cerberus-api,containerPort=8000"
```

### GCP Deployment (Cloud Run)

```bash
# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/PROJECT-ID/cerberus

# Deploy to Cloud Run
gcloud run deploy cerberus \
  --image gcr.io/PROJECT-ID/cerberus \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=postgresql://...,REDIS_URL=redis://..." \
  --set-secrets="OPENAI_API_KEY=cerberus-openai-key:latest" \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10
```

### Azure Deployment (Container Apps)

```bash
# Create Container App
az containerapp create \
  --name cerberus \
  --resource-group cerberus-rg \
  --environment cerberus-env \
  --image cerberus/api:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 \
  --memory 2.0 \
  --env-vars \
    DATABASE_URL=postgresql://... \
    REDIS_URL=redis://... \
  --secrets \
    openai-key=sk-... \
  --min-replicas 1 \
  --max-replicas 10
```

### Kubernetes Deployment

**deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cerberus-api
  namespace: cerberus
spec:
  replicas: 3
  selector:
    matchLabels:
      app: cerberus-api
  template:
    metadata:
      labels:
        app: cerberus-api
    spec:
      containers:
      - name: api
        image: cerberus/api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: cerberus-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: cerberus-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: cerberus-api
  namespace: cerberus
spec:
  selector:
    app: cerberus-api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

**Deploy:**

```bash
# Create namespace
kubectl create namespace cerberus

# Create secrets
kubectl create secret generic cerberus-secrets \
  --from-literal=openai-api-key=sk-... \
  --from-literal=database-url=postgresql://... \
  -n cerberus

# Deploy
kubectl apply -f deployment.yaml

# Check status
kubectl get pods -n cerberus
kubectl logs -f deployment/cerberus-api -n cerberus
```

---

## Git Hooks Integration

### Installing Pre-commit Hook

**Automatic Installation:**

```bash
# Install Cerberus CLI
pip install cerberus-cli

# Initialize in your project
cd /path/to/your/project
cerberus init

# This creates:
# - .git/hooks/pre-commit
# - .cerberus.yml (config file)
```

**Manual Installation:**

```bash
# Create pre-commit hook
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash

CERBERUS_API_URL="${CERBERUS_API_URL:-http://localhost:8000}"
CERBERUS_API_KEY="${CERBERUS_API_KEY}"

if [ -z "$CERBERUS_API_KEY" ]; then
  echo "⚠️  CERBERUS_API_KEY not set. Skipping review."
  exit 0
fi

# Get staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|js|ts|java|go|rb|php|cpp|c|cs)$')

if [ -z "$STAGED_FILES" ]; then
  echo "No code files to review."
  exit 0
fi

echo "🔍 Running Cerberus review..."

FAILED=0

for FILE in $STAGED_FILES; do
  if [ ! -f "$FILE" ]; then
    continue
  fi
  
  echo "  Reviewing $FILE..."
  
  CODE=$(cat "$FILE" | jq -Rs .)
  RESPONSE=$(curl -s -X POST "$CERBERUS_API_URL/api/v1/review" \
    -H "Authorization: Bearer $CERBERUS_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"code\": $CODE, \"filename\": \"$FILE\", \"config\": {\"blocking_mode\": true}}")
  
  SHOULD_BLOCK=$(echo "$RESPONSE" | jq -r '.should_block // false')
  
  if [ "$SHOULD_BLOCK" = "true" ]; then
    echo "  ❌ Review failed for $FILE"
    echo "$RESPONSE" | jq -r '.results.agents[].findings[] | "    [\(.severity)] \(.title)"'
    FAILED=1
  else
    echo "  ✅ $FILE passed"
  fi
done

if [ $FAILED -eq 1 ]; then
  echo ""
  echo "❌ Commit blocked due to critical issues."
  echo "   Fix the issues or use 'git commit --no-verify' to bypass."
  exit 1
fi

echo "✅ All files passed review!"
exit 0
EOF

# Make executable
chmod +x .git/hooks/pre-commit
```

### Installing Pre-push Hook

```bash
cat > .git/hooks/pre-push << 'EOF'
#!/bin/bash

CERBERUS_API_URL="${CERBERUS_API_URL:-http://localhost:8000}"
CERBERUS_API_KEY="${CERBERUS_API_KEY}"

echo "🔍 Running comprehensive Cerberus review before push..."

# Get all changed files in commits being pushed
CHANGED_FILES=$(git diff --name-only HEAD@{u}..HEAD | grep -E '\.(py|js|ts|java|go|rb|php|cpp|c|cs)$')

# Submit batch review
# (implementation similar to pre-commit but with batch endpoint)

echo "✅ Push review complete!"
exit 0
EOF

chmod +x .git/hooks/pre-push
```

### Hook Configuration

**.cerberus.yml:**

```yaml
version: 1

# Git hook configuration
hooks:
  pre_commit:
    enabled: true
    blocking: true  # Fail commit on critical issues
    agents: ["security", "quality"]
    severity_threshold: "high"
  
  pre_push:
    enabled: true
    blocking: true
    agents: ["security", "performance", "quality"]
    severity_threshold: "medium"

# File patterns to review
include:
  - "**/*.py"
  - "**/*.js"
  - "**/*.ts"
  - "**/*.java"

# File patterns to ignore
exclude:
  - "**/*_test.py"
  - "**/*.min.js"
  - "migrations/**"
  - "vendor/**"
  - "node_modules/**"

# Agent-specific configuration
agents:
  security:
    enabled: true
    severity_threshold: "high"
  performance:
    enabled: true
    complexity_threshold: "O(n²)"
  quality:
    enabled: true
    max_function_length: 50
```

### Bypass Mechanisms

```bash
# Bypass pre-commit hook
git commit --no-verify -m "Emergency fix"

# Bypass specific review (environment variable)
CERBERUS_SKIP=1 git commit -m "Skip review"

# Advisory mode (warning only, don't block)
export CERBERUS_ADVISORY_MODE=1
git commit -m "Warn but don't block"
```

---

## Verification & Testing

### Health Check Commands

```bash
# Basic health check
curl http://localhost:8000/api/v1/health

# CLI health check command
python -m cerberus.cli health

# Readiness check probe
curl http://localhost:8000/api/v1/ready
```

### Running Test Reviews

**Test with sample code via CLI:**

```bash
python -m cerberus.cli review --snippet "import os
API_KEY = 'sk-1234567890'
def get_user(user_id):
    query = f'SELECT * FROM users WHERE id = {user_id}'
    return db.execute(query)"
```

**Test via HTTP API:**

```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "import os\nAPI_KEY = \"sk-1234567890\"\ndef get_user(user_id):\n    return db.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
    "language": "python"
  }'
```

**Expected to detect:**
- Critical: Hardcoded API key (CWE-798)
- Critical: SQL injection vulnerability (CWE-89)
- Warnings / Suggestions: Quality docstrings, compliance checks

---

## Troubleshooting

### Common Issues

**Issue: "Connection refused" when calling API**

```bash
# Check if services are running
docker-compose ps

# Check logs
docker-compose logs api

# Or run API server directly in current shell
python -m cerberus.cli serve --host 0.0.0.0 --port 8000
```

**Issue: "Invalid API key"**

```bash
# In local development mode, use pre-seeded key: cvai_dev_key_123
# Or create a new key via CLI:
python -m cerberus.cli create-api-key --name "new-key"
```

**Issue: "LLM provider unavailable"**

```bash
# If using IBM watsonx, verify IAM credentials & project ID:
python -c "
import os
from cerberus.config import settings
print('Provider:', settings.LLM_PROVIDER)
print('WatsonX Model:', settings.WATSONX_MODEL_ID)
print('WatsonX Key Configured:', bool(settings.WATSONX_API_KEY))
"

# Fallback to zero-config heuristic engine:
export LLM_PROVIDER=heuristic
```

**Issue: "Database connection failed"**

```bash
# Check container status
docker-compose ps db

# Test PostgreSQL connectivity
docker-compose exec db psql -U cerberus -d cerberus_db -c "SELECT 1"

# Or switch to zero-config local SQLite:
# Set DATABASE_URL=sqlite+aiosqlite:///./cerberus.db in .env
```

**Issue: Slow reviews**

```bash
# Check cache status
curl http://localhost:8000/api/v1/health | jq '.cache'

# Clear Redis cache if applicable
docker-compose exec redis redis-cli FLUSHALL
```

---

## Upgrade & Maintenance

### Upgrading Cerberus

```bash
# Pull latest code
git pull origin main

# Install/update pinned dependencies
pip install -r requirements.txt

# Verify test suite
python -m pytest tests/ -q --tb=short
```

---

**Next Steps:**
- [Configuration Reference](05-configuration-reference.md) - Fine-tune settings
- [Monitoring & Operations](06-monitoring-operations.md) - Production operations

---

*Cerberus Installation Guide - v0.1.0*
