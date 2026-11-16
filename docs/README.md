# cerberus</> Documentation

Welcome to the **cerberus</>** documentation! cerberus</> (project codename: Cerberus) is an autonomous enterprise multi-agent code review and automated quality assurance platform built with FastAPI, SQLAlchemy, Redis, and specialized static and LLM analysis agents.

---

## 📚 Documentation Structure

### Core Documentation

1. **[System Architecture & Overview](01-architecture-overview.md)**
   - Executive summary and multi-agent coordination model
   - 5 specialized review agents (Security, Performance, Quality, Architecture, Compliance)
   - Real-time WebSocket streaming and two-tier LRU caching
   - Technology stack overview (FastAPI, SQLAlchemy 2.0, LangGraph, Redis)

2. **[API Reference](02-api-reference.md)**
   - Complete REST API documentation (`/api/v1/review`, `/api/v1/agents`, `/api/v1/analytics`, `/api/v1/health`, etc.)
   - Real-time WebSocket review streaming: `ws://localhost:8000/api/v1/review/{review_id}/ws?token=cvai_dev_key_123`
   - Authentication via Bearer tokens (`Authorization: Bearer cvai_dev_key_123`)
   - Sliding-window rate limiting and error response schemas

3. **[Agent Specifications](03-agent-specifications.md)**
   - Security Agent (OWASP Top 10, CWE-89, CWE-798, CVSS 3.1)
   - Performance Agent (Big-O analysis, O(n²) detection, N+1 query patterns)
   - Code Quality Agent (maintainability, docstrings, cyclomatic complexity)
   - Architecture Agent (coupling metrics, circular dependencies, modularity)
   - Compliance Agent (HIPAA, GDPR, SOC 2, PCI-DSS with Luhn validation)

4. **[Installation & Setup Guide](04-installation-setup.md)**
   - Quick start with `python -m cerberus.cli serve`
   - Local zero-config development using `LLM_PROVIDER=heuristic`
   - Docker Compose deployment (`cerberus-api`, `cerberus-postgres`, `cerberus-redis`)
   - Automated git pre-commit and pre-push hooks

5. **[Configuration Reference](05-configuration-reference.md)**
   - Comprehensive environment variable reference (`.env`)
   - LLM provider configuration (`watsonx`, `openai`, `ollama`, `heuristic`)
   - IBM watsonx Granite model configuration (`WATSONX_MODEL_ID`)
   - Two-tier cache (`CACHE_MAX_ITEMS`) and rate limiter bounds (`RATE_LIMIT_MAX_TRACKED`)

6. **[Monitoring & Operations](06-monitoring-operations.md)**
   - Real Prometheus metrics (`cerberus_review_requests_total`, `cerberus_review_duration_seconds`, etc.)
   - Grafana dashboard guidelines and log aggregation
   - Operational troubleshooting and maintenance routines

7. **[Security & Compliance](07-security-compliance.md)**
   - Cryptographic API key hashing and database authentication
   - Regulatory checks (HIPAA ePHI, GDPR Article 17, PCI-DSS cardholder data)
   - Production secrets validation and CORS safeguards

8. **[Developer Guide](08-developer-guide.md)**
   - Local development environment and project layout
   - Extending agent rules and evaluators
   - Test suite execution (`python -m pytest tests/ -q`)

---

## 💡 Key Architectural Concepts

### 5 Specialized Review Agents

cerberus</> executes 5 specialized review agents in parallel coordinated by `ReviewOrchestrator`:

1. **Security Agent**: Threat modeling, SQL injection (CWE-89), hardcoded secrets (CWE-798), and CVSS risk scoring.
2. **Performance Agent**: Algorithmic complexity, nested O(n²) iterations, and database N+1 antipatterns.
3. **Code Quality Agent**: Documentation completeness, cyclomatic complexity, and code duplication.
4. **Architecture Agent**: Component coupling, deep relative imports, and module boundaries.
5. **Compliance Agent**: Regulatory standards auditing for HIPAA, GDPR, SOC 2, and PCI-DSS (including Luhn credit card validation).

### LLM Provider Flexibility & Zero-Config Default

- **Heuristic & AST Engine (`LLM_PROVIDER=heuristic`)**: **Default zero-config mode**. Operates 100% offline with zero cloud API keys, executing Python AST analysis and regex rules in sub-15ms.
- **IBM watsonx.ai (`LLM_PROVIDER=watsonx`)**: **Primary enterprise cloud integration**. Uses IBM Cloud IAM OAuth exchange and IBM Granite models (default: `ibm/granite-3-8b-instruct`) for contextual reasoning.
- **OpenAI (`LLM_PROVIDER=openai`)**: Connects to OpenAI GPT-4o models via persistent HTTP client session pooling.
- **Ollama (`LLM_PROVIDER=ollama`)**: Local open-weights model runner (`codellama`, `llama3`) for private on-premise execution.

### Two-Tier Resilient Caching

1. **Redis Tier**: Distributed cache shared across instances with configurable TTL (`CACHE_TTL_SECONDS`).
2. **In-Memory Tier**: Local bounded LRU cache (`OrderedDict`) capped at `CACHE_MAX_ITEMS` with automatic eviction.

---

## 🔍 Quick Commands Reference

| Task | Command |
|------|---------|
| Start API Server | `python -m cerberus.cli serve` |
| Health Check | `python -m cerberus.cli health` |
| Review Code File | `python -m cerberus.cli review path/to/file.py` |
| Review Code Snippet | `python -m cerberus.cli review --snippet "def query(): pass"` |
| Run in Blocking Mode | `python -m cerberus.cli review path/to/file.py --blocking` |
| Create API Key | `python -m cerberus.cli keys create --name my-key` |
| Run Test Suite | `python -m pytest tests/ -q` |
| Docker Deployment | `docker-compose up -d` |

---

## 🆘 Troubleshooting & Support

- Check server logs: stdout structured logging formatted as `[TIMESTAMP] [LEVEL] [LOGGER]: MESSAGE`
- Verify system status: `GET http://localhost:8000/api/v1/health`
- See [Monitoring & Operations Guide](06-monitoring-operations.md) for Prometheus metrics and troubleshooting steps.
