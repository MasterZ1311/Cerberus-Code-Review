# MultiAgent-CodeReview

**cerberus</> Autonomous Multi-Agent Code Review & Quality Assurance System**
*(CodeVault AI Architecture Concept)*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/MasterZ1311/MultiAgent-CodeReview/actions/workflows/ci.yml/badge.svg)](https://github.com/MasterZ1311/MultiAgent-CodeReview/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/tests-352%20passed-brightgreen.svg)](tests/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Security Policy](https://img.shields.io/badge/security-policy-red.svg)](SECURITY.md)

**cerberus</>** is an enterprise-grade multi-agent code review platform that inspects source code across five independent, specialized dimensions: **Security**, **Performance**, **Quality**, **Architecture**, and **Regulatory Compliance**. It supports flexible LLM backends including **IBM watsonx (IBM Granite)**, **OpenAI**, **Ollama**, and includes a zero-config deterministic **Heuristic Engine** that runs 100% offline without credentials.

---

## ✨ Key Features

🤖 **5 Specialized Review Agents**
- **Security Agent**: CWE-89 (SQL Injection), CWE-798 (Hardcoded Secrets), CWE-78 (Command Injection), CWE-328 (Weak Cryptography), CWE-502 (Insecure Deserialization), with CVSS 3.1 scoring.
- **Performance Agent**: Algorithmic complexity ($O(n^2)$ nested iterations), database N+1 query patterns, and string concatenation memory churn.
- **Quality Agent**: PEP 257 docstring completeness, cognitive complexity, monolithic functions, bare except clauses, and wildcard import pollution.
- **Architecture Agent**: Structural modularity scoring, deep relative import anti-patterns (`....`), and cyclic dependency risks.
- **Compliance Agent**: Automated auditing against **HIPAA** (ePHI transit encryption), **GDPR** (erasure & minimization), **SOC 2** (secrets & RBAC), **PCI-DSS v4.0** (Luhn card number validation, CVV storage prohibition), and **CCPA**.

⚡ **Dual Execution Engines**
- **Zero-Config Offline Heuristics**: `LLM_PROVIDER=heuristic` works immediately out of the box with zero credentials, zero network latency, and instant deterministic analysis.
- **IBM watsonx Enterprise Integration**: `LLM_PROVIDER=watsonx` leverages IBM Granite foundation models (`ibm/granite-3-8b-instruct`) with automated IAM OAuth token rotation.

🚀 **Developer & Pipeline Ready**
- Full RESTful API with FastAPI and WebSocket real-time progress streaming.
- Typer-powered CLI (`cerberus.cli`) for local reviews, service management, and health checks.
- Prometheus telemetry metrics (`/metrics`) and Redis/in-memory LRU caching.
- Automated dev key auto-seeding (`cvai_dev_key_123`) for frictionless onboarding.

---

## 🚀 Quick Start

### 1. Installation

Clone repository and install pinned dependencies:

```bash
git clone https://github.com/MasterZ1311/MultiAgent-CodeReview.git
cd MultiAgent-CodeReview

# Install dependencies (Python 3.13+)
pip install -r requirements.txt
```

### 2. Configuration & Running Without Credentials

By default, Cerberus runs with the zero-config heuristic engine. No external API keys or cloud accounts are required:

```bash
# Copy example configuration
cp .env.example .env

# Start the API server directly (defaults to LLM_PROVIDER=heuristic)
python -m cerberus.cli serve --host 0.0.0.0 --port 8000
```

Alternatively, launch the containerized stack using Docker Compose:

```bash
docker-compose up -d
```

### 3. Running with IBM watsonx (Granite Models)

To connect Cerberus to IBM Cloud watsonx:

1. Set `LLM_PROVIDER=watsonx` in your `.env` file.
2. Provide your IBM Cloud credentials:
   ```bash
   LLM_PROVIDER=watsonx
   WATSONX_API_KEY=your-ibm-cloud-api-key
   WATSONX_PROJECT_ID=your-watsonx-project-id
   WATSONX_URL=https://us-south.ml.cloud.ibm.com
   WATSONX_MODEL_ID=ibm/granite-3-8b-instruct
   ```
3. Cerberus handles dynamic IAM OAuth bearer token exchange (`https://iam.cloud.ibm.com/identity/token`), token caching, and proactive renewal automatically.
4. See [`WATSONX_INTEGRATION.md`](WATSONX_INTEGRATION.md) for detailed IAM permissions and setup guidance.

---

## 💻 CLI Usage

The Cerberus CLI provides convenient commands for development and automation:

```bash
# Health Check
python -m cerberus.cli health

# Review a code snippet
python -m cerberus.cli review --snippet "import os
API_KEY = 'sk-1234567890'
def get_user(user_id):
    query = f'SELECT * FROM users WHERE id = {user_id}'
    return db.execute(query)"

# Review a local source file
python -m cerberus.cli review --file path/to/source.py

# Create a new API key
python -m cerberus.cli create-api-key --name "ci-token"

# Start the API server
python -m cerberus.cli serve --host 0.0.0.0 --port 8000
```

---

## 📡 API Usage

In development mode (`ENVIRONMENT=development`), the default API key `cvai_dev_key_123` is automatically seeded:

```bash
# Submit code for multi-agent review
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def query_user(user_id):\n    return db.execute(f\"SELECT * FROM users WHERE id = {user_id}\")",
    "language": "python"
  }'
```

```bash
# Liveness health check (no auth required)
curl http://localhost:8000/api/v1/health

# Readiness check (no auth required)
curl http://localhost:8000/api/v1/ready
```

---

## 🧪 Testing & Verification

Execute the full automated test suite (338 tests):

```bash
python -m pytest tests/ -q --tb=short
```

---

## 🏗️ Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                 Clients: CLI, Git Hooks, API                  │
└───────────────────────────────┬───────────────────────────────┘
                                │ HTTP / WebSocket
┌───────────────────────────────▼───────────────────────────────┐
│              FastAPI Gateway (cerberus/api/)                  │
│       Authentication (cvai_*), Rate Limiting, CORS, Cache     │
└───────────────────────────────┬───────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────┐
│     Review Orchestrator (cerberus/agents/orchestrator.py)     │
└───────┬───────────┬───────────┼───────────┬───────────┬───────┘
        │           │           │           │           │
        ▼           ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │Security │ │Perform. │ │ Quality │ │Architect│ │Complian.│
   │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │           │           │
        └───────────┴───────────┼───────────┴───────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │              Provider Layer                  │
         │  HeuristicEngine  │  WatsonxProvider (IAM)   │
         │  OpenAIProvider   │  OllamaProvider          │
         └──────────────────────────────────────────────┘
```

---

## 📚 Documentation Index

- 🏗️ **[Architecture Overview](docs/01-architecture-overview.md)** - Detailed system architecture and data flows
- 🔌 **[API Reference](docs/02-api-reference.md)** - REST and WebSocket endpoint specifications
- 🤖 **[Agent Specifications](docs/03-agent-specifications.md)** - Deep dive into all 5 specialized agents
- 📖 **[Installation & Setup Guide](docs/04-installation-setup.md)** - Production Docker and local setup
- ⚙️ **[Configuration Reference](docs/05-configuration-reference.md)** - Environment variables and options
- 📊 **[Monitoring & Operations](docs/06-monitoring-operations.md)** - Prometheus metrics and Grafana alerts
- 🔵 **[IBM watsonx Integration Guide](WATSONX_INTEGRATION.md)** - IAM credentials, Granite models, and setup

---

## 🤝 Contributing & Community

We welcome contributions of all kinds! Please see our:
- 📖 [Contributing Guide](CONTRIBUTING.md) for local environment setup, testing, and PR conventions.
- 🛡️ [Security Policy](SECURITY.md) for vulnerability disclosure guidelines.
- 📜 [Code of Conduct](CODE_OF_CONDUCT.md) for community expectations.

---

## 📜 License

Distributed under the MIT License. See [LICENSE](LICENSE) for full terms.
