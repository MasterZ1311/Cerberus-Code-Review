# Cerberus - System Architecture & Overview

**Version:** 0.1.0  
**Last Updated:** September 21, 2026  
**Document Status:** Draft

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [What is Cerberus?](#what-is-cerberus-ai)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Technology Stack](#technology-stack)
- [Deployment Architecture](#deployment-architecture)
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)
- [Quick Reference](#quick-reference)
- [Next Steps](#next-steps)

---

## Executive Summary

**Cerberus** is an intelligent, multi-agent code review system designed specifically for solo developers and small teams who want enterprise-grade code analysis without the complexity of enterprise tools.

Unlike traditional static analysis tools that apply rigid rules, Cerberus uses multiple specialized AI agents that understand context, provide intelligent suggestions, and explain their reasoning—just like having expert reviewers on your team.

**Key Benefits:**
- **Automated Expert Review**: Get security, performance, and quality insights automatically
- **Zero Configuration Start**: Docker Compose setup in under 5 minutes
- **Seamless Integration**: Works directly in your Git workflow via hooks
- **Privacy-Focused**: Support for local LLM models—your code never leaves your infrastructure
- **Cost-Effective**: Optimized for small teams with intelligent caching and batch processing

---

## What is cerberus</>?

cerberus</> (project codename: Cerberus) is an autonomous **enterprise multi-agent code review orchestration platform** that analyzes source code across 5 specialized perspectives simultaneously:

1. **Security Agent** — Detects injection flaws (CWE-89, CWE-78), hardcoded secrets (CWE-798), weak cryptography, and computes CVSS 3.1 severity scores.
2. **Performance Agent** — Identifies quadratic O(n²) loops, database N+1 queries, string concatenation memory churn, and calculates latency savings.
3. **Code Quality Agent** — Evaluates cyclomatic complexity, missing docstrings, long functions, bare except clauses, and maintainability.
4. **Architecture Agent** — Analyzes component coupling, deep relative imports, modularity, and architectural boundary violations.
5. **Compliance Agent** — Audits regulatory mandates for HIPAA (ePHI logging, TLS), GDPR (data minimization, erasure), SOC 2, and PCI-DSS (Luhn credit card validation).

Each agent operates independently in parallel via the `ReviewOrchestrator`, providing synthesized and prioritized findings.

### The Problem We Solve

Solo developers and engineering teams face a challenge:
- **Manual code review** is time-consuming and inconsistent
- **Traditional static analysis** tools produce high false positives and lack context
- **Enterprise solutions** are too complex and expensive
- **AI coding assistants** help generate code but don't review it comprehensively

cerberus</> bridges this gap by providing intelligent, contextual code review that is:
- Easy to set up with zero cloud credentials (`LLM_PROVIDER=heuristic`)
- Scalable with IBM watsonx foundation models (`ibm/granite-3-8b-instruct`)
- Privacy-respecting with local offline support
- Integrated into existing workflows with Git hooks and real-time WebSockets

---

## Key Features

### 🤖 Multi-Agent Intelligence
- Five specialized AI agents working in parallel via `ReviewOrchestrator`
- Real-time review streaming via WebSockets (`/api/v1/review/{review_id}/ws`)
- Context-aware analysis that understands language, imports, and AST structure
- Natural language explanations and concrete fix suggestions for every finding

### 🚀 Developer-Friendly Integration
- Git pre-commit and pre-push hooks
- CLI for on-demand reviews
- RESTful API for custom integrations
- IDE plugins (coming soon)

### 🔒 Privacy & Flexibility
- Support for local LLM models (Ollama, LM Studio)
- OpenAI, Anthropic, Azure OpenAI integration
- Configurable data retention policies
- Air-gapped deployment support

### ⚡ Performance & Efficiency
- Intelligent caching to minimize redundant analysis
- Incremental reviews (analyze only changed code)
- Parallel agent execution
- Batch processing for multiple files

### 📊 Actionable Insights
- Severity-based prioritization
- Code snippets with specific recommendations
- Trend analysis across commits
- Export to JSON, Markdown, HTML, SARIF formats

### 🔧 Extensible Architecture
- Custom agent development SDK
- Plugin system for formatters and integrations
- Webhook support for external tools
- Open configuration format

---

## System Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        A[Git Hooks]
        B[CLI Tool]
        C[REST API Client]
        D[CI/CD Pipeline]
    end
    
    subgraph "API Gateway Layer"
        E[FastAPI Server]
        F[Authentication]
        G[Rate Limiting]
    end
    
    subgraph "Orchestration Layer"
        H[Review Coordinator]
        I[Agent Scheduler]
        J[Result Aggregator]
    end
    
    subgraph "Agent Layer"
        K[Security Agent]
        L[Performance Agent]
        M[Code Quality Agent]
    end
    
    subgraph "LLM Provider Layer"
        N[OpenAI]
        O[Anthropic Claude]
        P[Ollama Local]
        Q[Azure OpenAI]
    end
    
    subgraph "Storage Layer"
        R[(SQLite/PostgreSQL)]
        S[(Redis Cache)]
        T[File Storage]
    end
    
    subgraph "Monitoring Layer"
        U[Prometheus Metrics]
        V[Structured Logs]
        W[Health Checks]
    end
    
    A --> E
    B --> E
    C --> E
    D --> E
    
    E --> F
    F --> G
    G --> H
    
    H --> I
    I --> K
    I --> L
    I --> M
    
    K --> N
    K --> O
    K --> P
    K --> Q
    
    L --> N
    L --> O
    L --> P
    L --> Q
    
    M --> N
    M --> O
    M --> P
    M --> Q
    
    I --> J
    J --> H
    
    H --> R
    H --> S
    H --> T
    
    E --> U
    E --> V
    E --> W
```

### Component Interaction Flow

```
┌─────────────┐
│   Client    │
│  (Git Hook) │
└──────┬──────┘
       │ 1. Submit Review Request
       ▼
┌─────────────────────────────────┐
│      API Gateway (FastAPI)      │
│  - Authenticate                 │
│  - Validate Request             │
│  - Rate Limit Check             │
└──────┬──────────────────────────┘
       │ 2. Forward to Coordinator
       ▼
┌─────────────────────────────────┐
│     Review Coordinator          │
│  - Check cache for results      │
│  - Parse code & extract context │
│  - Schedule agent tasks         │
└──────┬──────────────────────────┘
       │ 3. Dispatch to Agents (Parallel)
       ├──────────┬──────────┬────────────┐
       ▼          ▼          ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Security │ │Performance│ │  Quality │
│  Agent   │ │  Agent    │ │  Agent   │
└────┬─────┘ └────┬──────┘ └────┬─────┘
     │            │             │
     │ 4. Analyze with LLM     │
     ├────────────┼─────────────┤
     ▼            ▼             ▼
┌─────────────────────────────────┐
│      LLM Provider               │
│  (OpenAI / Ollama / Claude)     │
└──────┬──────────────────────────┘
       │ 5. Return Analysis
       ▼
┌─────────────────────────────────┐
│     Result Aggregator           │
│  - Combine agent results        │
│  - Deduplicate findings         │
│  - Calculate aggregate score    │
│  - Format output                │
└──────┬──────────────────────────┘
       │ 6. Store & Return
       ├─────────────────┬──────────────┐
       ▼                 ▼              ▼
┌────────────┐    ┌───────────┐  ┌──────────┐
│  Database  │    │   Cache   │  │  Client  │
│  (persist) │    │  (speed)  │  │ (display)│
└────────────┘    └───────────┘  └──────────┘
```

---

## Core Components

### 1. API Gateway (FastAPI Server)

**Purpose**: Entry point for all client requests, handles authentication, validation, and routing.

**Responsibilities:**
- Request authentication and authorization
- Input validation and sanitization
- Rate limiting and quota enforcement
- Request routing to appropriate handlers
- Response formatting and error handling
- Metrics collection

**Technology**: FastAPI (Python) - chosen for:
- Async/await support for high concurrency
- Automatic OpenAPI documentation
- Type safety with Pydantic
- High performance (comparable to Node.js)

**Key Endpoints:**
- `/api/v1/review` - Submit code for review
- `/api/v1/review/{id}` - Get review status/results
- `/api/v1/agents` - List and configure agents
- `/api/v1/health` - Health check endpoint

### 2. Review Coordinator

**Purpose**: Orchestrates the entire review process from request to response.

**Responsibilities:**
- Parse incoming code and extract metadata
- Check cache for existing review results
- Determine which agents to invoke based on configuration
- Schedule agent execution (parallel or sequential)
- Manage timeouts and retries
- Aggregate results from multiple agents
- Store final review in database and cache

**Key Algorithms:**
- **Cache Key Generation**: Hash of (code content + agent versions + configuration)
- **Agent Selection**: Rule-based selection based on file types and user config
- **Parallel Execution**: asyncio task groups for concurrent agent runs
- **Consensus Building**: Weighted scoring when agents have conflicting opinions

### 3. Agent Scheduler

**Purpose**: Manages agent lifecycle and execution.

**Responsibilities:**
- Initialize agent instances with proper configuration
- Distribute work to agents based on availability
- Monitor agent execution time and resource usage
- Handle agent failures and retries
- Collect agent metrics (execution time, token usage, error rates)

**Execution Modes:**
- **Parallel**: All agents run simultaneously (default, fastest)
- **Sequential**: Agents run one after another (lower resource usage)
- **Priority**: High-priority agents run first, others conditionally

### 4. Individual Agents

Each agent is an independent module that analyzes code from a specific perspective.

#### Security Agent

**Focus**: Identifies security vulnerabilities and compliance issues

**Key Capabilities:**
- SQL injection detection
- XSS vulnerability identification
- Hardcoded secrets scanning
- Insecure cryptography detection
- Authentication/authorization flaws
- Dependency vulnerability checking

**LLM Prompting Strategy:**
- System prompt defines security expertise persona
- Code provided with surrounding context
- Structured output format (JSON schema enforcement)
- Few-shot examples of vulnerabilities

#### Performance Agent

**Focus**: Detects performance bottlenecks and inefficiencies

**Key Capabilities:**
- Algorithmic complexity analysis (O(n²) loops, etc.)
- Memory leak detection
- Inefficient database queries (N+1 problems)
- Unnecessary computations in loops
- Resource-intensive operations
- Caching opportunities

**LLM Prompting Strategy:**
- System prompt emphasizes performance optimization
- Request complexity analysis and concrete metrics
- Ask for specific optimization suggestions with code examples

#### Code Quality Agent

**Focus**: Reviews maintainability, readability, and best practices

**Key Capabilities:**
- Naming convention review
- Code structure and organization
- Design pattern appropriateness
- Code duplication detection
- Documentation completeness
- Test coverage gaps
- SOLID principle violations

**LLM Prompting Strategy:**
- System prompt defines senior developer perspective
- Emphasize maintainability and team collaboration
- Request practical refactoring suggestions

### 5. LLM Provider Abstraction

**Purpose**: Unified interface for multiple LLM backends

**Supported Providers:**
- **OpenAI**: GPT-4, GPT-4-turbo, GPT-3.5-turbo
- **Anthropic**: Claude 3 Opus, Sonnet, Haiku
- **Azure OpenAI**: Enterprise OpenAI deployment
- **Ollama**: Local models (CodeLlama, Mistral, etc.)
- **Custom**: Extensible for other providers

**Abstraction Layer Benefits:**
- Switch providers without changing agent code
- Fallback to alternative providers on failure
- Cost optimization (route to cheaper models when appropriate)
- Privacy control (use local models for sensitive code)

**Implementation Pattern:**
```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, config: dict) -> str:
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        pass
```

### 6. Storage Layer

#### Database (SQLite/PostgreSQL)

**Purpose**: Persistent storage for review history, configurations, and metadata

**Schema Overview:**
- `reviews` - Review requests and overall results
- `agent_findings` - Individual findings from each agent
- `code_snapshots` - Code content and metadata (optional retention)
- `configurations` - User and project configurations
- `audit_logs` - Audit trail for compliance

**Why SQLite for POC?**
- Zero configuration
- Single file database
- Perfect for solo developers
- Easy backup and portability

**When to use PostgreSQL?**
- Multiple concurrent users
- Need for advanced querying
- Replication and high availability
- Team collaboration features

#### Cache (Redis)

**Purpose**: High-speed cache for review results and LLM responses

**Cached Data:**
- Recent review results (keyed by code hash)
- LLM responses (for identical prompts)
- Agent execution results
- Frequently accessed configurations

**Cache Strategy:**
- TTL: 7 days for review results
- LRU eviction when memory limit reached
- Cache invalidation on configuration changes

**Performance Impact:**
- Cache hit: <50ms response time
- Cache miss: 5-30s (depends on LLM)
- Cache hit rate target: >70%

### 7. Monitoring & Observability

#### Prometheus Metrics

**Key Metrics Collected:**
- `cerberus_review_total` - Total reviews processed
- `cerberus_review_duration_seconds` - Review latency
- `cerberus_agent_execution_seconds` - Per-agent execution time
- `cerberus_llm_tokens_total` - Token usage by provider
- `cerberus_cache_hit_rate` - Cache effectiveness
- `cerberus_errors_total` - Error rate by type

#### Structured Logging

**Log Levels:**
- DEBUG: Detailed execution flow
- INFO: Key events (review started, completed)
- WARNING: Recoverable issues (cache miss, retry)
- ERROR: Failures requiring attention

**Log Format**: JSON for machine parsing
```json
{
  "timestamp": "2026-09-21T10:30:00Z",
  "level": "INFO",
  "component": "security_agent",
  "review_id": "rev_abc123",
  "message": "Security analysis completed",
  "duration_ms": 3450,
  "findings_count": 2
}
```

---

## Data Flow

### Review Request Lifecycle

**Phase 1: Submission** (0-100ms)
```
Developer commits code
        ↓
Git pre-commit hook triggered
        ↓
Hook invokes Cerberus CLI
        ↓
CLI sends HTTP POST to /api/v1/review
        ↓
API Gateway authenticates & validates
        ↓
Request queued in Review Coordinator
```

**Phase 2: Analysis & Parallel Execution** (10ms - 2s)
```
ReviewOrchestrator computes deterministic cache key (cvai:cache:<sha256>)
        ↓
Check Redis cache ─── HIT → Return cached CodeReviewResponse (fast path)
        ↓ MISS
Check in-memory LRU cache fallback
        ↓ MISS
Identify active agents: Security, Performance, Quality, Architecture, Compliance
        ↓
ReviewOrchestrator executes all active agents in parallel (asyncio.gather):
  │
  ├─→ Security Agent      → Heuristic/AST + LLM → Vulnerability findings & CVSS
  ├─→ Performance Agent   → Heuristic/AST + LLM → Algorithmic & N+1 findings
  ├─→ Quality Agent       → Heuristic/AST + LLM → Complexity & style findings
  ├─→ Architecture Agent  → Heuristic/AST + LLM → Coupling & boundary findings
  └─→ Compliance Agent    → Regulatory audit    → HIPAA, GDPR, SOC 2, PCI-DSS
        ↓
All agents report AgentResult (crashed agents score 0.0 with status "failed")
```

**Phase 3: Synthesis, Scoring & Status Determination** (10-50ms)
```
ReviewOrchestrator aggregates all findings
        ↓
Calculate weighted overall score (0.0 - 100.0):
  - Security (40%)
  - Performance (25%)
  - Quality (25%)
  - Architecture (5%)
  - Compliance (5%)
        ↓
Determine status:
  - "completed" (all agents succeeded)
  - "degraded"  (one or more agents failed)
  - "failed"    (all agents failed)
        ↓
Assess blocking threshold (critical/high severity issues trigger block)
```

**Phase 4: Persistence, WebSocket Broadcast & Response** (20-100ms)
```
Persist review and findings to database asynchronously (_persist_review_record)
        ↓
If status == "completed": Cache response in Redis & In-Memory LRU (prevents cache poisoning)
        ↓
Broadcast completion event to active WebSockets (/api/v1/review/{review_id}/ws)
        ↓
Update Prometheus telemetry metrics (review counts, durations, finding counters)
        ↓
Return CodeReviewResponse to client / CLI
```

### Caching Strategy Details

**Cache Key Calculation (`cerberus.core.cache.CacheManager`):**
```python
def compute_cache_key(self, code: str, language: str = "python", agents: Optional[List[str]] = None) -> str:
    normalized_code = code.strip().replace("\r\n", "\n")
    agents_str = ",".join(sorted(agents or []))
    payload = f"{language.lower()}:{agents_str}:{normalized_code}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"cvai:cache:{digest}"
```

**Cache Eviction & Invalidation:**
- Redis TTL: 7 days (`CACHE_TTL_SECONDS = 604800`)
- In-Memory LRU: Strictly bounded by `CACHE_MAX_ITEMS` (default 1000) using `OrderedDict.popitem(last=False)`
- Degraded or failed reviews are never saved to cache

---

## Technology Stack

### Backend Core

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **API Framework** | FastAPI 0.141+ | Async ASGI framework, OpenAPI docs, dependency injection |
| **Language Runtime** | Python 3.13 / 3.11+ | Modern typing, asyncio improvements, rich AI ecosystem |
| **ASGI Server** | Uvicorn 0.40+ | High-throughput production ASGI web server |
| **Agent Orchestration** | LangChain 1.3+ & LangGraph 1.2+ | Agent workflow modeling, state management |
| **Data Validation** | Pydantic 2.12+ & pydantic-settings 2.14+ | High-performance Rust-backed schema validation |
| **CLI & Terminal** | Typer 0.24+ & Rich 14.3+ | Expressive command line interface and colored tables |

### Storage, Caching & Security

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **ORM / Data Access** | SQLAlchemy 2.0+ | Modern async ORM supporting SQLite and PostgreSQL |
| **Local Database** | aiosqlite 0.22+ | Zero-configuration async SQLite for development |
| **Production Database**| PostgreSQL 15+ (asyncpg) | Enterprise relational persistence with ACID compliance |
| **Cache Tier** | Redis 8.1+ & In-Memory LRU | Two-tier caching with SHA-256 fingerprinting |
| **Security & Auth** | python-jose 3.5+ & hashlib | SHA-256 API key hashing, token verification |

### LLM Foundation Model Integrations

| Provider | Model / Engine | Characteristics |
|----------|----------------|-----------------|
| **Heuristic Engine** | Python AST & Regex Evaluator | **Default zero-config**, offline, deterministic, sub-15ms |
| **IBM watsonx.ai** | `ibm/granite-3-8b-instruct` | **Primary enterprise LLM**, IAM OAuth authentication |
| **OpenAI** | `gpt-4o` | Cloud reasoning via pooled persistent HTTP client sessions |
| **Ollama** | `codellama`, `llama3` | On-premise local weights execution |

### Deployment & Operations

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Containerization** | Docker 24+ | Builds `cerberus` package from root `Dockerfile` |
| **Local Orchestration**| Docker Compose | Multi-container setup (`cerberus-api`, `cerberus-postgres`, `cerberus-redis`) |
| **Metrics** | Prometheus Client 0.26+ | Standard metrics exposed at `/metrics` |
| **Test Framework** | pytest 9.1+, pytest-asyncio, httpx2 | Automated test suite (338+ passing tests) |

---

## Deployment Architecture

### Local Development (Docker Compose)

```
┌────────────────────────────────────────────────────────┐
│                   Host Machine                         │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │               Docker Compose                     │ │
│  │                                                  │ │
│  │  ┌─────────────────────────┐                     │ │
│  │  │  cerberus-api           │                     │ │
│  │  │  (FastAPI on Port 8000) │                     │ │
│  │  └───────────┬─────────────┘                     │ │
│  │              │                                   │ │
│  │     ┌────────┴────────┐                          │ │
│  │     ▼                 ▼                          │ │
│  │  ┌──────────────┐  ┌──────────────────────────┐  │ │
│  │  │cerberus-redis│  │    cerberus-postgres     │  │ │
│  │  │(Port 6379)   │  │    (Port 5432)           │  │ │
│  │  └──────────────┘  └──────────────────────────┘  │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```
| **Orchestration (Cloud)** | Kubernetes 1.28+ | Scalable, cloud-agnostic, production-ready |
| **Monitoring** | Prometheus + Grafana | Industry standard, rich ecosystem |
| **Logging** | Python logging + Loki | Structured logs, Grafana integration |

### Development & Testing

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Testing** | pytest + pytest-asyncio | De-facto standard for Python testing |
| **Mocking** | pytest-mock, responses | LLM mocking, HTTP mocking |
| **Linting** | ruff, mypy | Fast linting, type checking |
| **Formatting** | black, isort | Consistent code style |
| **CI/CD** | GitHub Actions | Free for open source, excellent integration |

---

## Deployment Architecture

### Local Development (Docker Compose)

```
┌────────────────────────────────────────┐
│          Developer Laptop              │
│                                        │
│  ┌──────────────────────────────┐    │
│  │     Docker Compose           │    │
│  │                              │    │
│  │  ┌─────────────────────┐    │    │
│  │  │  cerberus-api      │    │    │
│  │  │  (FastAPI)          │    │    │
│  │  │  Port: 8000         │    │    │
│  │  └──────────┬──────────┘    │    │
│  │             │                │    │
│  │  ┌──────────┴──────────┐    │    │
│  │  │  cerberus-redis    │    │    │
│  │  │  Port: 6379         │    │    │
│  │  └─────────────────────┘    │    │
│  │             │                │    │
│  │  ┌──────────┴──────────┐    │    │
│  │  │  cerberus-db       │    │    │
│  │  │  (PostgreSQL)       │    │    │
│  │  │  Port: 5432         │    │    │
│  │  └─────────────────────┘    │    │
│  │             │                │    │
│  │  ┌──────────┴──────────┐    │    │
│  │  │  prometheus         │    │    │
│  │  │  Port: 9090         │    │    │
│  │  └─────────────────────┘    │    │
│  │             │                │    │
│  │  ┌──────────┴──────────┐    │    │
│  │  │  grafana            │    │    │
│  │  │  Port: 3000         │    │    │
│  │  └─────────────────────┘    │    │
│  └──────────────────────────────┘    │
│                                        │
│  ┌──────────────────────────────┐    │
│  │  Git Hooks (pre-commit)      │    │
│  │  → curl localhost:8000       │    │
│  └──────────────────────────────┘    │
└────────────────────────────────────────┘
```

**Characteristics:**
- Single command setup: `docker-compose up`
- All services on localhost
- Persistent volumes for data
- Hot reload for development
- Zero cloud costs

### Cloud Deployment (AWS Example)

```
┌─────────────────────────────────────────────────────┐
│                    AWS Cloud                        │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │          Application Load Balancer         │   │
│  │          (TLS termination)                 │   │
│  └───────────────────┬────────────────────────┘   │
│                      │                             │
│  ┌───────────────────┴────────────────────────┐   │
│  │         ECS Fargate Cluster                │   │
│  │                                            │   │
│  │  ┌──────────────────────────────────┐    │   │
│  │  │  Cerberus API (3 tasks)         │    │   │
│  │  │  - Auto-scaling 1-10 tasks       │    │   │
│  │  │  - CPU/Memory limits             │    │   │
│  │  └──────────────┬───────────────────┘    │   │
│  └─────────────────┼────────────────────────┘   │
│                    │                             │
│  ┌─────────────────┴────────────────────────┐   │
│  │         ElastiCache Redis                │   │
│  │         (Multi-AZ, Replication)          │   │
│  └──────────────────────────────────────────┘   │
│                    │                             │
│  ┌─────────────────┴────────────────────────┐   │
│  │         RDS PostgreSQL                   │   │
│  │         (Multi-AZ, Auto-backup)          │   │
│  └──────────────────────────────────────────┘   │
│                    │                             │
│  ┌─────────────────┴────────────────────────┐   │
│  │         CloudWatch                       │   │
│  │         (Logs + Metrics)                 │   │
│  └──────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────────────────────────────────┐   │
│  │         Secrets Manager                  │   │
│  │         (API Keys, Credentials)          │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Characteristics:**
- Managed services (less operational overhead)
- Auto-scaling based on load
- High availability (Multi-AZ)
- Secure secrets management
- Monitoring and alerting built-in

### Kubernetes Deployment (Any Cloud)

```
┌─────────────────────────────────────────────────────┐
│            Kubernetes Cluster                       │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │          Ingress Controller                │   │
│  │          (nginx/traefik)                   │   │
│  └───────────────────┬────────────────────────┘   │
│                      │                             │
│  ┌───────────────────┴────────────────────────┐   │
│  │     Namespace: cerberus                   │   │
│  │                                            │   │
│  │  ┌──────────────────────────────────┐    │   │
│  │  │  Deployment: api (3 replicas)    │    │   │
│  │  │  - HPA: 1-10 replicas            │    │   │
│  │  │  - Resource limits               │    │   │
│  │  │  - Liveness/Readiness probes     │    │   │
│  │  └──────────────┬───────────────────┘    │   │
│  │                 │                         │   │
│  │  ┌──────────────┴───────────────────┐    │   │
│  │  │  Service: cerberus-api          │    │   │
│  │  │  Type: ClusterIP                 │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │                 │                         │   │
│  │  ┌──────────────┴───────────────────┐    │   │
│  │  │  StatefulSet: redis              │    │   │
│  │  │  - Persistent volumes            │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │                 │                         │   │
│  │  ┌──────────────┴───────────────────┐    │   │
│  │  │  StatefulSet: postgresql         │    │   │
│  │  │  - Persistent volumes            │    │   │
│  │  │  - Automated backups             │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │                 │                         │   │
│  │  ┌──────────────┴───────────────────┐    │   │
│  │  │  ConfigMap: app-config           │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │                 │                         │   │
│  │  ┌──────────────┴───────────────────┐    │   │
│  │  │  Secret: api-keys                │    │   │
│  │  └──────────────────────────────────┘    │   │
│  └────────────────────────────────────────┘   │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │     Namespace: monitoring                  │   │
│  │                                            │   │
│  │  ┌──────────────────────────────────┐    │   │
│  │  │  Prometheus                      │    │   │
│  │  └──────────────────────────────────┘    │   │
│  │  ┌──────────────────────────────────┐    │   │
│  │  │  Grafana                         │    │   │
│  │  └──────────────────────────────────┘    │   │
│  └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Characteristics:**
- Cloud-agnostic (works on any K8s)
- Advanced orchestration features
- Rolling updates, rollbacks
- Resource management and quotas
- Service mesh ready (future)

---

## Design Decisions & Trade-offs

### 1. Multi-Agent Architecture vs. Single LLM Call

**Decision**: Use multiple specialized agents instead of one general-purpose call

**Rationale:**
- **Better Quality**: Each agent has focused expertise and optimized prompts
- **Parallel Execution**: Faster than sequential analysis
- **Configurability**: Enable/disable specific agents based on needs
- **Cost Optimization**: Use different models per agent (GPT-4 for security, GPT-3.5 for style)

**Trade-off**: More complex orchestration, higher cost if all agents use expensive models

**Mitigation**: Intelligent caching, configurable agent selection, support for cheaper local models

### 2. FastAPI (Python) vs. Node.js/Go

**Decision**: Python with FastAPI

**Rationale:**
- **LLM Ecosystem**: Python has best AI/ML library support
- **Developer Experience**: Type hints, async/await, excellent tooling
- **Performance**: FastAPI is comparable to Node.js for I/O-bound workloads
- **Community**: Large Python community in AI/ML space

**Trade-off**: Slower than Go for CPU-intensive tasks, higher memory usage than Node.js

**Mitigation**: Use async patterns, containerization for resource limits, offload heavy computation

### 3. SQLite vs. PostgreSQL Default

**Decision**: SQLite for POC/MVP, PostgreSQL for production

**Rationale:**
- **Zero Config**: SQLite requires no setup for solo developers
- **Portability**: Single file database, easy backup
- **Sufficient**: Handles solo dev/small team workload
- **Migration Path**: Easy to migrate to PostgreSQL later

**Trade-off**: SQLite has limited concurrency, no replication

**Mitigation**: Clear documentation on when to upgrade, automated migration scripts

### 4. Synchronous vs. Asynchronous Agent Execution

**Decision**: Asynchronous (parallel) by default, configurable

**Rationale:**
- **Speed**: 3 agents in parallel = 3x faster than sequential
- **User Experience**: Faster feedback in Git hooks
- **Resource Efficiency**: Better utilization of I/O wait time

**Trade-off**: Higher resource usage (memory, CPU) during execution

**Mitigation**: Configurable execution mode, resource limits, queue-based processing option

### 5. Caching Strategy

**Decision**: Aggressive caching with Redis, 7-day TTL

**Rationale:**
- **Cost**: LLM calls are expensive (time and money)
- **Speed**: Cache hits are 100x faster than LLM calls
- **Repeatability**: Same code = same results (within version constraints)

**Trade-off**: Stale results if agent improvements aren't reflected

**Mitigation**: Cache invalidation on agent version changes, configurable TTL

### 6. Git Hooks vs. CI/CD Only

**Decision**: Primary integration via Git hooks, CI/CD as alternative

**Rationale:**
- **Fast Feedback**: Developers get immediate feedback before commit
- **Prevent Bad Commits**: Block issues before they enter history
- **Workflow Integration**: Seamless, no separate step needed

**Trade-off**: Adds latency to git operations, requires local setup

**Mitigation**: 
- Async mode (commit proceeds, results sent later)
- Cache for fast repeated reviews
- Advisory mode (don't block, just warn)
- CI/CD option for teams that prefer server-side only

### 7. Multi-Provider LLM Support vs. OpenAI Only

**Decision**: Support multiple LLM providers from day one

**Rationale:**
- **Privacy**: Local models for sensitive code
- **Cost**: Flexibility to use cheaper models
- **Availability**: Fallback if one provider has issues
- **Future-Proofing**: LLM landscape is evolving rapidly

**Trade-off**: More complex abstraction layer, testing burden

**Mitigation**: Well-defined provider interface, comprehensive test mocks

### 8. Language-Agnostic vs. Language-Specific Agents

**Decision**: Language-agnostic agents using LLM context

**Rationale:**
- **Simplicity**: One set of agents works for all languages
- **LLM Capability**: Modern LLMs understand many languages
- **Maintenance**: No need for language-specific rules

**Trade-off**: May miss language-specific patterns that AST analysis would catch

**Mitigation**: 
- Provide language context to LLM
- Future: Optional language-specific pre-processors
- Combine with traditional linters (ESLint, Pylint, etc.)

---

## Quick Reference

### System Components at a Glance

| Component | Purpose | Technology | Port |
|-----------|---------|-----------|------|
| API Gateway | Request handling | FastAPI | 8000 |
| Review Coordinator | Orchestration | Python | - |
| Security Agent | Security analysis | LangChain + LLM | - |
| Performance Agent | Performance analysis | LangChain + LLM | - |
| Code Quality Agent | Quality analysis | LangChain + LLM | - |
| Database | Persistent storage | SQLite/PostgreSQL | 5432 |
| Cache | Result caching | Redis | 6379 |
| Metrics | Monitoring | Prometheus | 9090 |
| Dashboards | Visualization | Grafana | 3000 |

### Key Metrics

| Metric | Target | Purpose |
|--------|--------|---------|
| Review Latency (cached) | <50ms | Fast feedback for cached results |
| Review Latency (uncached) | 5-30s | Acceptable for LLM analysis |
| Cache Hit Rate | >70% | Cost and speed optimization |
| Agent Success Rate | >99% | Reliability |
| API Availability | >99.9% | System reliability |

### File Structure Overview

```
cerberus-ai/
├── api/                    # FastAPI application
│   ├── routes/            # API endpoints
│   ├── middleware/        # Auth, rate limiting, etc.
│   └── models/            # Pydantic models
├── agents/                # Agent implementations
│   ├── base.py           # Base agent class
│   ├── security.py       # Security agent
│   ├── performance.py    # Performance agent
│   └── quality.py        # Code quality agent
├── orchestration/         # Coordinator and scheduler
│   ├── coordinator.py
│   └── scheduler.py
├── llm/                   # LLM provider abstractions
│   ├── base.py
│   ├── openai.py
│   ├── anthropic.py
│   └── ollama.py
├── storage/               # Database and cache
│   ├── database.py
│   └── cache.py
├── cli/                   # Command-line interface
├── hooks/                 # Git hook scripts
├── config/                # Configuration management
├── tests/                 # Test suite
└── docs/                  # Documentation (you are here!)
```

---

## Next Steps

Now that you understand the high-level architecture of Cerberus, here's where to go next:

### For Developers Getting Started
👉 **[Installation & Setup Guide](04-installation-setup.md)** - Get Cerberus running in 5 minutes

### For Understanding the API
👉 **[API Reference](02-api-reference.md)** - Complete REST API documentation with examples

### For Customizing Behavior
👉 **[Agent Specifications](03-agent-specifications.md)** - Learn how each agent works and how to configure them

👉 **[Configuration Reference](05-configuration-reference.md)** - All configuration options explained

### For Operations Teams
👉 **[Monitoring & Operations Guide](06-monitoring-operations.md)** - Running in production, troubleshooting, optimization

👉 **[Security & Compliance Guide](07-security-compliance.md)** - Security best practices and data handling

### For Contributors
👉 **[Developer Guide](08-developer-guide.md)** - Contributing code, creating custom agents, extending functionality

---

## Document Information

**Version**: 0.1.0  
**Last Updated**: September 21, 2026  
**Maintained By**: Cerberus Team
**License**: MIT  

**Related Documents**:
- [API Reference](02-api-reference.md)
- [Installation Guide](04-installation-setup.md)
- [FAQ](FAQ.md)

**Feedback**: Found an error or have suggestions? [Open an issue](https://github.com/cerberus-ai/cerberus/issues) or contribute to the docs!

---

*Cerberus - Intelligent Code Review for Modern Developers*
