# MultiAgent-CodeReview

**cerberus</> Autonomous Multi-Agent Code Review & Collaborative Quality Assurance System**
*(CodeVault AI Architecture Concept)*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/MasterZ1311/MultiAgent-CodeReview/actions/workflows/ci.yml/badge.svg)](https://github.com/MasterZ1311/MultiAgent-CodeReview/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/tests-363%20passed-brightgreen.svg)](tests/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Security Policy](https://img.shields.io/badge/security-policy-red.svg)](SECURITY.md)

**cerberus</>** is an enterprise-grade multi-agent code review platform where specialized AI agents inspect source code across independent dimensions (**Security**, **Performance**, **Quality**, **Architecture**, **Regulatory Compliance**), collaboratively deliberate to reach a unified merge consensus (**Consensus Agent**), and automatically synthesize verified Git unified diff patches (**Code Fixer Agent**).

Cerberus is LLM-agnostic: plug in **any key you have** — **Groq**, **OpenAI**, **Anthropic Claude**, **Google Gemini**, **DeepSeek**, **Ollama** (100% free local), or **IBM watsonx** — or run completely offline with the deterministic **Heuristic Engine** with zero credentials.

---

## ✨ Key Features

🤖 **Specialized Multi-Agent Panel & Collaborative Engine**
- **Security Agent**: CWE-89 (SQL Injection), CWE-798 (Hardcoded Secrets), CWE-78 (Command Injection), CWE-328 (Weak Cryptography), CWE-502 (Insecure Deserialization), with CVSS 3.1 scoring.
- **Performance Agent**: Algorithmic complexity ($O(n^2)$ nested iterations), database N+1 query patterns, and string concatenation memory churn.
- **Quality Agent**: PEP 257 docstring completeness, cognitive complexity, monolithic functions, bare except clauses, and wildcard import pollution.
- **Architecture Agent**: Structural modularity scoring, deep relative import anti-patterns (`....`), and cyclic dependency risks.
- **Compliance Agent**: Automated auditing against **HIPAA** (ePHI transit encryption), **GDPR** (erasure & minimization), **SOC 2** (secrets & RBAC), **PCI-DSS v4.0** (Luhn card number validation, CVV storage prohibition), and **CCPA**.
- **Consensus Agent (Collaborative Moderator)**: Correlates cross-domain findings, resolves multi-agent conflicts, evaluates PR merge-readiness (`MERGE_READY`, `NEEDS_REVISION`, `BLOCKED_ON_ISSUES`), and issues an actionable consensus brief.
- **Code Fixer Agent (Automated Patch Synthesis)**: Automatically generates an AST-verified Git unified diff patch (`.patch`) resolving all flagged issues simultaneously.

🔑 **Flexible Multi-Provider & Per-Agent Key Routing**
- **Auto-Detection (`LLM_PROVIDER=auto`)**: Add any key to `.env` (Groq, OpenAI, Anthropic, Gemini, DeepSeek, Ollama) and Cerberus configures itself automatically.
- **Mix & Match Different Keys**: Assign different providers and keys to different agents (e.g. `SECURITY_AGENT_PROVIDER=anthropic`, `PERFORMANCE_AGENT_PROVIDER=groq`, `QUALITY_AGENT_PROVIDER=openai`).
- **Zero-Config Offline Heuristics**: Runs 100% offline without credentials, zero latency, and zero cloud dependencies.

🚀 **Developer & Pipeline Ready**
- Full RESTful API with FastAPI and WebSocket real-time progress streaming.
- Typer-powered CLI (`cerberus.cli`) for local reviews, service management, and health checks.
- Prometheus telemetry metrics (`/metrics`) and Redis/in-memory LRU caching.
- Modern Web Dashboard with real-time score rings, consensus verdicts, and one-click Git patch copying.

---

## 🚀 Quick Start

### 1. Installation

Clone repository and install dependencies:

```bash
git clone https://github.com/MasterZ1311/MultiAgent-CodeReview.git
cd MultiAgent-CodeReview

# Install dependencies (Python 3.11+)
pip install -r requirements.txt
```

### 2. Configure Your API Keys

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Set any API key you have (or leave empty to run offline heuristics):

```bash
# Provider selection (auto-detects configured keys)
LLM_PROVIDER=auto

# Groq (Ultra-fast, generous free tier: https://console.groq.com)
GROQ_API_KEY=gsk_your_key_here

# OpenAI (https://platform.openai.com)
OPENAI_API_KEY=sk-your_key_here

# Anthropic Claude (https://console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-your_key_here

# Google Gemini (Free tier available: https://aistudio.google.com)
GEMINI_API_KEY=your_gemini_key_here

# DeepSeek (https://platform.deepseek.com)
DEEPSEEK_API_KEY=sk-your_deepseek_key_here

# Ollama (100% Free, Local, Offline: https://ollama.ai)
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. Run Different Agents on Different Providers (Optional)

You can assign distinct providers/keys to individual agents:

```bash
SECURITY_AGENT_PROVIDER=anthropic
PERFORMANCE_AGENT_PROVIDER=groq
QUALITY_AGENT_PROVIDER=openai
ARCHITECTURE_AGENT_PROVIDER=gemini
COMPLIANCE_AGENT_PROVIDER=deepseek
```

### 4. Launch Web Dashboard or CLI

```bash
# Launch Web Dashboard on http://localhost:8000
python -m cerberus.cli serve

# Health check
python -m cerberus.cli health

# Run multi-agent review via CLI
python -m cerberus.cli review --snippet "import os; os.system('ls')"
```

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
