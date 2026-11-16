# Cerberus - Developer & Contributing Guide

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## Table of Contents

- [Project Overview](#project-overview)
- [Development Setup](#development-setup)
- [Architecture Deep Dive](#architecture-deep-dive)
- [Creating Custom Agents](#creating-custom-agents)
- [Extending Functionality](#extending-functionality)
- [Testing](#testing)
- [Contributing Guidelines](#contributing-guidelines)
- [API for Extensions](#api-for-extensions)
- [Example Projects](#example-projects)

---

## Project Overview

### Repository Structure

```
cerberus-ai/
├── api/                        # FastAPI application
│   ├── routes/                # API endpoint handlers
│   │   ├── review.py         # Review endpoints
│   │   ├── agents.py         # Agent management
│   │   ├── config.py         # Configuration endpoints
│   │   └── health.py         # Health check
│   ├── middleware/            # Middleware components
│   │   ├── auth.py           # Authentication
│   │   ├── rate_limit.py     # Rate limiting
│   │   └── logging.py        # Request logging
│   ├── models/                # Pydantic models
│   │   ├── review.py         # Review models
│   │   ├── agent.py          # Agent models
│   │   └── config.py         # Config models
│   └── main.py                # FastAPI app initialization
├── agents/                     # Agent implementations
│   ├── base.py                # Base agent class
│   ├── security.py            # Security agent
│   ├── performance.py         # Performance agent
│   └── quality.py             # Code quality agent
├── orchestration/              # Review orchestration
│   ├── coordinator.py         # Review coordinator
│   ├── scheduler.py           # Agent scheduler
│   └── aggregator.py          # Result aggregation
├── llm/                        # LLM provider abstractions
│   ├── base.py                # Base provider interface
│   ├── openai.py              # OpenAI integration
│   ├── anthropic.py           # Anthropic integration
│   ├── ollama.py              # Ollama integration
│   └── azure_openai.py        # Azure OpenAI
├── storage/                    # Data persistence
│   ├── database.py            # Database operations
│   ├── cache.py               # Redis cache
│   └── models.py              # SQLAlchemy models
├── cli/                        # Command-line interface
│   ├── main.py                # CLI entry point
│   ├── commands/              # CLI commands
│   └── utils.py               # CLI utilities
├── hooks/                      # Git hook templates
│   ├── pre-commit.sh
│   └── pre-push.sh
├── config/                     # Configuration files
│   ├── default.yml            # Default config
│   └── prometheus.yml         # Prometheus config
├── tests/                      # Test suite
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── e2e/                   # End-to-end tests
├── docs/                       # Documentation
├── docker/                     # Docker files
│   ├── Dockerfile.api
│   └── Dockerfile.cli
├── scripts/                    # Utility scripts
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # Docker Compose config
└── README.md                   # Project README
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API Framework** | FastAPI 0.104+ | REST API server |
| **Language** | Python 3.11+ | Application code |
| **ORM** | SQLAlchemy 2.0+ | Database abstraction |
| **Migration** | Alembic | Schema migrations |
| **Caching** | Redis 7+ | Result caching |
| **LLM Framework** | LangChain 0.1+ | LLM abstractions |
| **Testing** | pytest, pytest-asyncio | Test framework |
| **Linting** | ruff, mypy | Code quality |
| **Formatting** | black, isort | Code formatting |

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git
- Make (optional)

### Local Development Environment

**1. Clone Repository:**

```bash
git clone https://github.com/cerberus-ai/cerberus.git
cd cerberus
```

**2. Create Virtual Environment:**

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

**3. Install Dependencies:**

```bash
# Install in development mode
pip install -e ".[dev]"

# Or using requirements
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**4. Set Up Environment:**

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings
nano .env
```

**5. Start Development Services:**

```bash
# Start PostgreSQL and Redis
docker-compose up -d db redis

# Run database migrations
alembic upgrade head

# Start API in development mode (with hot reload)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**6. Verify Setup:**

```bash
# Check health
curl http://localhost:8000/api/v1/health

# Run tests
pytest
```

### Development Tools

**Code Formatting:**

```bash
# Format code
black .
isort .

# Check formatting
black --check .
isort --check .
```

**Linting:**

```bash
# Run linters
ruff check .
mypy .

# Auto-fix issues
ruff check --fix .
```

**Pre-commit Hooks:**

```bash
# Install pre-commit
pip install pre-commit

# Set up git hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## Architecture Deep Dive

### Request Flow

```python
# api/routes/review.py
@router.post("/review")
async def submit_review(
    review_request: ReviewRequest,
    api_key: str = Depends(get_api_key)
) -> ReviewResponse:
    """
    1. Validate request
    2. Check cache
    3. If cache miss, submit to coordinator
    4. Return review ID or cached result
    """
    # Validate
    validator.validate(review_request)
    
    # Generate cache key
    cache_key = generate_cache_key(review_request)
    
    # Check cache
    cached_result = await cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Submit to coordinator
    review_id = await coordinator.submit(review_request)
    
    return ReviewResponse(review_id=review_id, status="processing")
```

### Agent Base Class

```python
# agents/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class Finding:
    """Represents a single code issue found by an agent."""
    id: str
    severity: str  # critical, high, medium, low, info
    category: str
    title: str
    message: str
    line: int
    column: int = 0
    code_snippet: str = ""
    explanation: str = ""
    recommendation: str = ""
    suggested_fix: str = ""
    confidence: float = 1.0
    references: List[str] = None

@dataclass
class AgentResult:
    """Result from an agent execution."""
    agent_name: str
    status: str  # completed, failed, skipped
    score: int  # 0-100
    findings: List[Finding]
    execution_time_ms: int
    token_usage: Dict[str, int] = None
    error: str = None

class BaseAgent(ABC):
    """Base class for all code review agents."""
    
    def __init__(self, config: Dict[str, Any], llm_provider):
        self.config = config
        self.llm = llm_provider
        self.name = self.__class__.__name__
        self.version = "1.0.0"
    
    @abstractmethod
    async def analyze(
        self,
        code: str,
        context: Dict[str, Any]
    ) -> AgentResult:
        """
        Analyze code and return findings.
        
        Args:
            code: Source code to analyze
            context: Additional context (language, filename, etc.)
        
        Returns:
            AgentResult with findings
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of agent capabilities."""
        pass
    
    async def health_check(self) -> bool:
        """Check if agent is healthy."""
        try:
            await self.llm.health_check()
            return True
        except Exception:
            return False
    
    def _build_prompt(self, code: str, context: Dict[str, Any]) -> str:
        """Build LLM prompt for code analysis."""
        return f"""
        You are a {self.name} expert.
        Analyze the following {context.get('language', 'code')}:
        
        ```
        {code}
        ```
        
        Provide findings in JSON format.
        """
    
    def _parse_llm_response(self, response: str) -> List[Finding]:
        """Parse LLM response into structured findings."""
        # Implementation specific to response format
        pass
    
    def _calculate_score(self, findings: List[Finding]) -> int:
        """Calculate overall score based on findings."""
        if not findings:
            return 100
        
        # Deduct points based on severity
        score = 100
        for finding in findings:
            if finding.severity == "critical":
                score -= 20
            elif finding.severity == "high":
                score -= 10
            elif finding.severity == "medium":
                score -= 5
            elif finding.severity == "low":
                score -= 2
        
        return max(0, score)
```

---

## Creating Custom Agents

### Step 1: Create Agent Class

```python
# agents/typescript_linter.py
from agents.base import BaseAgent, AgentResult, Finding
from typing import List, Dict, Any
import json

class TypeScriptLinterAgent(BaseAgent):
    """Custom agent for TypeScript-specific linting."""
    
    def __init__(self, config: Dict[str, Any], llm_provider):
        super().__init__(config, llm_provider)
        self.name = "typescript_linter"
        self.version = "1.0.0"
    
    async def analyze(
        self,
        code: str,
        context: Dict[str, Any]
    ) -> AgentResult:
        """Analyze TypeScript code."""
        start_time = time.time()
        
        # Skip if not TypeScript
        if context.get('language') not in ['typescript', 'tsx']:
            return AgentResult(
                agent_name=self.name,
                status="skipped",
                score=100,
                findings=[],
                execution_time_ms=0
            )
        
        try:
            # Build prompt
            prompt = self._build_typescript_prompt(code, context)
            
            # Call LLM
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.2,
                max_tokens=2000
            )
            
            # Parse findings
            findings = self._parse_findings(response)
            
            # Calculate score
            score = self._calculate_score(findings)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return AgentResult(
                agent_name=self.name,
                status="completed",
                score=score,
                findings=findings,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status="failed",
                score=0,
                findings=[],
                execution_time_ms=0,
                error=str(e)
            )
    
    def _build_typescript_prompt(
        self,
        code: str,
        context: Dict[str, Any]
    ) -> str:
        """Build TypeScript-specific prompt."""
        return f"""
        You are a TypeScript expert. Analyze this code for TypeScript-specific issues:
        
        ```typescript
        {code}
        ```
        
        Focus on:
        1. Type safety - Missing or incorrect types
        2. Interface usage - Proper interface definitions
        3. Async/await patterns - Correct async handling
        4. TypeScript best practices
        
        Return findings in this JSON format:
        {{
          "findings": [
            {{
              "severity": "high",
              "category": "type_safety",
              "title": "Missing return type",
              "message": "Function is missing explicit return type",
              "line": 5,
              "recommendation": "Add explicit return type annotation",
              "suggested_fix": "function getName(): string {{"
            }}
          ]
        }}
        """
    
    def _parse_findings(self, llm_response: str) -> List[Finding]:
        """Parse LLM JSON response into Finding objects."""
        try:
            data = json.loads(llm_response)
            findings = []
            
            for item in data.get('findings', []):
                finding = Finding(
                    id=f"TS-{len(findings)+1:03d}",
                    severity=item.get('severity', 'medium'),
                    category=item.get('category', 'typescript'),
                    title=item.get('title', ''),
                    message=item.get('message', ''),
                    line=item.get('line', 0),
                    recommendation=item.get('recommendation', ''),
                    suggested_fix=item.get('suggested_fix', '')
                )
                findings.append(finding)
            
            return findings
            
        except json.JSONDecodeError:
            # Fallback parsing logic
            return []
    
    def get_capabilities(self) -> List[str]:
        """Return agent capabilities."""
        return [
            "typescript_type_checking",
            "interface_review",
            "async_patterns",
            "generics_usage",
            "decorator_patterns"
        ]
```

### Step 2: Register Agent

```python
# orchestration/agent_registry.py
from agents.typescript_linter import TypeScriptLinterAgent

AGENT_REGISTRY = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "quality": CodeQualityAgent,
    "typescript_linter": TypeScriptLinterAgent,  # Add custom agent
}

def get_agent(agent_name: str, config: Dict, llm_provider):
    """Get agent instance by name."""
    agent_class = AGENT_REGISTRY.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}")
    return agent_class(config, llm_provider)
```

### Step 3: Configure Agent

```yaml
# config/agents.yml
agents:
  typescript_linter:
    enabled: true
    llm_model: "gpt-4-turbo-preview"
    severity_threshold: "medium"
    
    # Custom configuration
    checks:
      - strict_null_checks
      - no_implicit_any
      - prefer_const
      - no_unused_vars
```

### Step 4: Test Agent

```python
# tests/unit/agents/test_typescript_linter.py
import pytest
from agents.typescript_linter import TypeScriptLinterAgent
from llm.mock import MockLLMProvider

@pytest.mark.asyncio
async def test_typescript_linter_detects_missing_types():
    """Test that agent detects missing type annotations."""
    
    # Arrange
    code = """
    function getName(user) {
        return user.name;
    }
    """
    
    config = {"severity_threshold": "medium"}
    llm_provider = MockLLMProvider()
    agent = TypeScriptLinterAgent(config, llm_provider)
    
    # Act
    result = await agent.analyze(code, {"language": "typescript"})
    
    # Assert
    assert result.status == "completed"
    assert len(result.findings) > 0
    assert any(f.category == "type_safety" for f in result.findings)

@pytest.mark.asyncio
async def test_typescript_linter_skips_non_typescript():
    """Test that agent skips non-TypeScript files."""
    
    code = "print('hello')"
    config = {}
    llm_provider = MockLLMProvider()
    agent = TypeScriptLinterAgent(config, llm_provider)
    
    result = await agent.analyze(code, {"language": "python"})
    
    assert result.status == "skipped"
```

---

## Extending Functionality

### Adding New LLM Providers

```python
# llm/custom_provider.py
from llm.base import BaseLLMProvider

class CustomLLMProvider(BaseLLMProvider):
    """Custom LLM provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get('api_key')
        self.base_url = config.get('base_url')
        self.model = config.get('model', 'default-model')
    
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """Send completion request to custom LLM."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            ) as response:
                data = await response.json()
                return data['choices'][0]['text']
    
    async def health_check(self) -> bool:
        """Check if provider is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as response:
                    return response.status == 200
        except Exception:
            return False
```

### Creating Custom Output Formatters

```python
# formatters/slack_formatter.py
from formatters.base import BaseFormatter

class SlackFormatter(BaseFormatter):
    """Format review results for Slack notifications."""
    
    def format(self, review_result: AgentResult) -> Dict[str, Any]:
        """Format as Slack message."""
        
        # Determine color based on score
        if review_result.score >= 80:
            color = "good"  # Green
        elif review_result.score >= 60:
            color = "warning"  # Yellow
        else:
            color = "danger"  # Red
        
        # Build Slack message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Code Review Complete - Score: {review_result.score}/100"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Critical:* {self._count_by_severity(review_result, 'critical')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*High:* {self._count_by_severity(review_result, 'high')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Medium:* {self._count_by_severity(review_result, 'medium')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Low:* {self._count_by_severity(review_result, 'low')}"
                    }
                ]
            }
        ]
        
        # Add top findings
        top_findings = sorted(
            review_result.findings,
            key=lambda x: self._severity_weight(x.severity),
            reverse=True
        )[:3]
        
        for finding in top_findings:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{finding.severity.upper()}:* {finding.title}\n{finding.message}"
                }
            })
        
        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks
                }
            ]
        }
```

---

## Testing

### Unit Tests

```python
# tests/unit/agents/test_security_agent.py
import pytest
from agents.security import SecurityAgent
from llm.mock import MockLLMProvider

class TestSecurityAgent:
    
    @pytest.mark.asyncio
    async def test_detects_sql_injection(self):
        """Test SQL injection detection."""
        code = 'query = f"SELECT * FROM users WHERE id = {user_id}"'
        
        agent = SecurityAgent({}, MockLLMProvider())
        result = await agent.analyze(code, {"language": "python"})
        
        assert result.status == "completed"
        assert any("sql injection" in f.title.lower() for f in result.findings)
    
    @pytest.mark.asyncio
    async def test_detects_hardcoded_secrets(self):
        """Test hardcoded secret detection."""
        code = 'API_KEY = "sk-1234567890abcdef"'
        
        agent = SecurityAgent({}, MockLLMProvider())
        result = await agent.analyze(code, {"language": "python"})
        
        assert any("secret" in f.title.lower() or "credential" in f.title.lower() 
                   for f in result.findings)
```

### Integration Tests

```python
# tests/integration/test_review_flow.py
import pytest
from fastapi.testclient import TestClient
from api.main import app

class TestReviewFlow:
    
    def test_complete_review_flow(self):
        """Test end-to-end review flow."""
        client = TestClient(app)
        
        # Submit review
        response = client.post(
            "/api/v1/review",
            headers={"Authorization": "Bearer test_key"},
            json={
                "code": "def test(): pass",
                "language": "python"
            }
        )
        
        assert response.status_code == 201
        review_id = response.json()["review_id"]
        
        # Poll for completion
        # ... (polling logic)
        
        # Get results
        response = client.get(
            f"/api/v1/review/{review_id}",
            headers={"Authorization": "Bearer test_key"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
```

### Mocking LLM Responses

```python
# llm/mock.py
class MockLLMProvider:
    """Mock LLM provider for testing."""
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Return pre-defined response based on prompt content."""
        
        if "sql injection" in prompt.lower():
            return json.dumps({
                "findings": [
                    {
                        "severity": "critical",
                        "category": "sql_injection",
                        "title": "SQL Injection vulnerability",
                        "message": "User input directly in SQL query",
                        "line": 1
                    }
                ]
            })
        
        return json.dumps({"findings": []})
    
    async def health_check(self) -> bool:
        return True
```

---

## Contributing Guidelines

### Code Style

- Follow PEP 8 for Python code
- Use type hints for all functions
- Maximum line length: 100 characters
- Use descriptive variable names

### Commit Conventions

```
type(scope): subject

body

footer
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

**Example:**
```
feat(agents): add TypeScript linter agent

Implements custom agent for TypeScript-specific code review.
Includes type checking, interface validation, and async patterns.

Closes #123
```

### Pull Request Process

1. Fork repository
2. Create feature branch: `git checkout -b feat/my-feature`
3. Make changes with tests
4. Run linters: `ruff check . && mypy .`
5. Run tests: `pytest`
6. Commit with conventional commits
7. Push and create PR
8. Address review feedback

### Documentation Requirements

- Add docstrings to all public functions/classes
- Update relevant documentation files
- Include examples for new features
- Update CHANGELOG.md

---

## API for Extensions

### Webhook System

```python
# Register webhook handler
@app.post("/webhooks/cerberus")
async def handle_webhook(event: WebhookEvent):
    if event.event_type == "review.completed":
        # Process completed review
        review_id = event.data["review_id"]
        score = event.data["overall_score"]
        
        # Custom logic
        if score < 50:
            send_alert(review_id)
    
    return {"status": "received"}
```

### Database Schema for Extensions

```python
# Custom tables for extensions
from sqlalchemy import Column, String, Integer, JSON

class CustomReviewMetadata(Base):
    __tablename__ = "custom_review_metadata"
    
    id = Column(Integer, primary_key=True)
    review_id = Column(String, ForeignKey("reviews.id"))
    metadata_key = Column(String)
    metadata_value = Column(JSON)
```

---

## Example Projects

### 1. Slack Notification Bot

Sends Slack notifications on review completion.

```python
# examples/slack-bot/bot.py
from slack_sdk.webhook import WebhookClient

async def on_review_complete(review_result):
    """Send Slack notification."""
    webhook = WebhookClient(SLACK_WEBHOOK_URL)
    
    message = format_slack_message(review_result)
    webhook.send(message)
```

### 2. VS Code Extension

IDE integration for Cerberus.

```typescript
// examples/vscode-extension/extension.ts
export function activate(context: vscode.ExtensionContext) {
    let disposable = vscode.commands.registerCommand(
        'cerberus.reviewFile',
        async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            
            const code = editor.document.getText();
            const result = await cerberusClient.review(code);
            
            showResults(result);
        }
    );
}
```

### 3. CI/CD Integration

GitHub Actions integration.

```yaml
# examples/github-action/action.yml
name: 'Cerberus Review'
runs:
  using: 'node16'
  main: 'index.js'
inputs:
  api_key:
    required: true
  severity_threshold:
    default: 'medium'
```

---

**Next Steps:**
- Review [Architecture Overview](01-architecture-overview.md)
- Check [API Reference](02-api-reference.md) for integration
- Join our community on GitHub

---

*Cerberus Developer Guide - v0.1.0*
