# Glossary

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## A

**Agent**
A specialized module in Cerberus that analyzes code from a specific perspective (security, performance, or quality). Each agent uses an LLM to provide intelligent, contextual analysis.

**Agent Coordinator**
The orchestration component that manages agent execution, schedules tasks, and aggregates results from multiple agents.

**Agent Result**
The structured output from an agent containing findings, score, execution time, and metadata.

**API Gateway**
The FastAPI-based entry point that handles authentication, validation, rate limiting, and routes requests to the Review Coordinator.

**API Key**
An authentication token used to access the Cerberus API. Format: `cvai_{random_string}`.

**Async Mode**
A git hook execution mode where the review runs asynchronously and the commit proceeds immediately without waiting for results.

---

## B

**Base Agent**
The abstract class that all agents inherit from, defining the standard interface for code analysis.

**Batch Review**
Reviewing multiple files in a single API request, processed in parallel for efficiency.

**Blocking Mode**
A configuration setting where commits or pushes are prevented if critical or high-severity issues are found.

---

## C

**Cache Hit**
When a review request finds existing results in the cache, avoiding the need for LLM processing.

**Cache Key**
A unique identifier for cached results, generated from code hash, agent versions, configuration, and LLM model.

**Cache Miss**
When a review request doesn't find existing results in cache, requiring new LLM processing.

**Cache TTL (Time To Live)**
The duration cached results are kept before expiration. Default: 7 days (604,800 seconds).

**CLI (Command-Line Interface)**
The `cerberus-cli` tool for interacting with Cerberus from the terminal.

**Code Context**
Additional metadata about code being reviewed (language, filename, project name, git commit) that helps agents provide better analysis.

**Code Quality Agent**
An agent that reviews code maintainability, readability, naming conventions, documentation, and adherence to best practices.

---

## D

**Deployment**
The process of installing and configuring Cerberus in a specific environment (local, cloud, Kubernetes).

**Docker Compose**
A tool for defining and running multi-container Docker applications. Cerberus uses this for local deployment.

---

## E

**Execution Mode**
How agents are run: `parallel` (all at once), `sequential` (one after another), or `priority` (by priority order).

---

## F

**Fallback Provider**
An alternative LLM provider that's used if the primary provider fails or is unavailable.

**FastAPI**
The Python web framework used to build Cerberus's REST API.

**Finding**
A single issue identified by an agent (e.g., SQL injection vulnerability, O(n²) loop, missing docstring).

---

## G

**Git Hook**
A script that runs automatically at specific points in the git workflow (pre-commit, pre-push). Cerberus uses these for automatic code review.

**Grafana**
An open-source platform for monitoring and observability, used to visualize Cerberus metrics.

---

## H

**Health Check**
An API endpoint (`/api/v1/health`) that returns the status of Cerberus and its dependencies.

**Hook Configuration**
Settings that control when and how git hooks execute reviews.

---

## I

**Incremental Review**
Reviewing only changed files rather than the entire codebase, improving speed and reducing costs.

---

## L

**LangChain**
A framework for building applications with LLMs, used by Cerberus for agent implementation.

**LLM (Large Language Model)**
An AI model trained on vast amounts of text (e.g., GPT-4, Claude) that can understand and generate human-like text. Cerberus uses LLMs to analyze code.

**LLM Provider**
A service that provides access to LLMs (OpenAI, Anthropic, Ollama, Azure OpenAI).

**LRU (Least Recently Used)**
A cache eviction policy that removes the least recently used items when the cache is full.

---

## M

**Mermaid**
A markdown-based diagramming language used in Cerberus documentation for architecture diagrams.

**Multi-Agent Architecture**
The design pattern where multiple specialized agents work together to provide comprehensive code analysis.

---

## N

**N+1 Query Problem**
A database performance issue where N additional queries are executed for each item in a collection. The Performance Agent detects this pattern.

---

## O

**Ollama**
A tool for running large language models locally on your machine. Provides free, private LLM inference.

**Orchestration**
The coordination of multiple agents and their execution, handled by the Agent Coordinator.

**OWASP Top 10**
A list of the 10 most critical web application security risks. The Security Agent checks for these vulnerabilities.

---

## P

**Performance Agent**
An agent that analyzes code for performance bottlenecks, algorithmic complexity, memory issues, and optimization opportunities.

**Pre-commit Hook**
A git hook that runs before a commit is finalized. Used by Cerberus to review staged changes.

**Pre-push Hook**
A git hook that runs before code is pushed to a remote repository. Used for comprehensive reviews.

**Prometheus**
An open-source monitoring system that collects and stores metrics as time series data. Used to monitor Cerberus.

---

## R

**Rate Limiting**
Restricting the number of API requests a client can make in a time period to prevent abuse.

**Redis**
An in-memory data structure store used by Cerberus for caching review results.

**REST API**
The HTTP-based interface for interacting with Cerberus programmatically.

**Review**
The process of analyzing code with multiple agents and returning findings and recommendations.

**Review Coordinator**
The component that orchestrates the entire review process from request to response.

**Review ID**
A unique identifier for a review request (e.g., `rev_abc123`).

---

## S

**SARIF (Static Analysis Results Interchange Format)**
A standard JSON format for representing static analysis results. Cerberus can export to SARIF for integration with other tools.

**Score**
A numerical rating (0-100) indicating code quality. Higher scores indicate fewer and less severe issues.

**Security Agent**
An agent that identifies security vulnerabilities, including injection attacks, authentication issues, cryptographic weaknesses, and hardcoded secrets.

**Severity**
The importance level of a finding: `critical`, `high`, `medium`, `low`, or `info`.

**SQLAlchemy**
A Python SQL toolkit and ORM (Object-Relational Mapping) library used by Cerberus for database operations.

**SQLite**
A lightweight, file-based database. Used by Cerberus for development and small deployments.

---

## T

**Token**
The unit of text processing for LLMs. Roughly 4 characters = 1 token. LLM costs are based on token usage.

**Token Usage**
The number of tokens consumed by an LLM request, including both input (prompt) and output (completion).

**TTL (Time To Live)**
The duration data is kept before automatic deletion or expiration.

---

## U

**Uvicorn**
An ASGI server used to run FastAPI applications in production.

---

## V

**Vulnerability**
A security weakness in code that could be exploited by attackers (e.g., SQL injection, XSS).

---

## W

**Webhook**
An HTTP callback that notifies external systems when a review completes. Used for integrations with Slack, Teams, etc.

---

## X

**XSS (Cross-Site Scripting)**
A security vulnerability where malicious scripts are injected into web pages. Detected by the Security Agent.

---

## Z

**Zero-Retention Policy**
An LLM provider policy where data is not stored after processing. Available with OpenAI Enterprise.

---

## Acronyms

| Acronym | Full Term | Description |
|---------|-----------|-------------|
| **AI** | Artificial Intelligence | Computer systems that perform tasks requiring human intelligence |
| **API** | Application Programming Interface | Interface for software communication |
| **ASGI** | Asynchronous Server Gateway Interface | Python standard for async web servers |
| **CCPA** | California Consumer Privacy Act | California privacy regulation |
| **CI/CD** | Continuous Integration/Continuous Deployment | Automated software delivery |
| **CLI** | Command-Line Interface | Text-based user interface |
| **CRUD** | Create, Read, Update, Delete | Basic database operations |
| **CSV** | Comma-Separated Values | Tabular data format |
| **CWE** | Common Weakness Enumeration | List of software security weaknesses |
| **DRY** | Don't Repeat Yourself | Programming principle avoiding duplication |
| **ECS** | Elastic Container Service | AWS container orchestration |
| **GCP** | Google Cloud Platform | Google's cloud computing services |
| **GDPR** | General Data Protection Regulation | EU privacy regulation |
| **HTTP** | Hypertext Transfer Protocol | Web communication protocol |
| **HTTPS** | HTTP Secure | Encrypted web communication |
| **IDE** | Integrated Development Environment | Software development application |
| **JSON** | JavaScript Object Notation | Data interchange format |
| **JWT** | JSON Web Token | Compact authentication token |
| **K8s** | Kubernetes | Container orchestration platform |
| **LLM** | Large Language Model | AI model for text understanding |
| **LRU** | Least Recently Used | Cache eviction strategy |
| **MFA** | Multi-Factor Authentication | Security using multiple verification |
| **MVP** | Minimum Viable Product | Basic version with core features |
| **ORM** | Object-Relational Mapping | Database abstraction technique |
| **OWASP** | Open Web Application Security Project | Security standards organization |
| **PII** | Personally Identifiable Information | Data that identifies individuals |
| **POC** | Proof of Concept | Demonstration of feasibility |
| **PR** | Pull Request | Code review request |
| **RBAC** | Role-Based Access Control | Access control based on roles |
| **REST** | Representational State Transfer | API architectural style |
| **SARIF** | Static Analysis Results Interchange Format | Analysis results format |
| **SDK** | Software Development Kit | Tools for developers |
| **SOC 2** | Service Organization Control 2 | Security compliance standard |
| **SOLID** | (S)ingle Responsibility, (O)pen/Closed, (L)iskov Substitution, (I)nterface Segregation, (D)ependency Inversion | Object-oriented design principles |
| **SQL** | Structured Query Language | Database query language |
| **SSD** | Solid State Drive | Fast storage device |
| **SSH** | Secure Shell | Encrypted network protocol |
| **SSRF** | Server-Side Request Forgery | Security vulnerability |
| **TLS** | Transport Layer Security | Encryption protocol |
| **TTL** | Time To Live | Data expiration time |
| **URL** | Uniform Resource Locator | Web address |
| **UUID** | Universally Unique Identifier | Unique identifier |
| **YAML** | YAML Ain't Markup Language | Human-readable data format |
| **XSS** | Cross-Site Scripting | Security vulnerability |

---

## Common Terms in Code Review

**Code Smell**: A surface indication of a deeper problem in code (long functions, duplicated code, etc.)

**Cyclomatic Complexity**: A measure of code complexity based on the number of independent paths through code.

**Dead Code**: Code that's never executed or has no effect.

**Magic Number**: Unexplained numeric constant in code that should be a named constant.

**Refactoring**: Restructuring code to improve design without changing behavior.

**Technical Debt**: The implied cost of future rework caused by choosing an easy solution now instead of a better approach that would take longer.

---

**For more information, see the [main documentation](README.md).**

**Last Updated**: September 21, 2026  
**Version**: 0.1.0
