# Cerberus - Agent Specifications

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## Table of Contents

- [Agent Architecture Overview](#agent-architecture-overview)
  - [Agent Lifecycle](#agent-lifecycle)
  - [Base Agent Interface](#base-agent-interface)
  - [Unified Finding Schema](#unified-finding-schema)
- [Security Agent](#security-agent)
- [Performance Agent](#performance-agent)
- [Code Quality Agent](#code-quality-agent)
- [Architecture Agent](#architecture-agent)
- [Compliance Agent](#compliance-agent)
- [Agent Customization](#agent-customization)
- [Creating Custom Agents](#creating-custom-agents)
- [Agent Orchestration](#agent-orchestration)

---

## Agent Architecture Overview

Cerberus uses a multi-agent orchestration architecture where each agent is an autonomous, specialized module focused on a specific quality, security, architectural, or regulatory dimension.

### Agent Lifecycle

```
┌─────────────┐
│ Initialize  │ ← Load config & providers (Watsonx, OpenAI, Heuristic)
└──────┬──────┘
       │
┌──────▼──────┐
│  Prepare    │ ← Extract AST, imports, functions, context
└──────┬──────┘
       │
┌──────▼──────┐
│  Analyze    │ ← Run static heuristics or query LLM provider
└──────┬──────┘
       │
┌──────▼──────┐
│  Normalize  │ ← Structure findings into unified Finding schema
└──────┬──────┘
       │
┌──────▼──────┐
│  Aggregate  │ ← Calculate agent score and return AgentResult
└─────────────┘
```

### Base Agent Interface

All agents in Cerberus inherit from `BaseAgent` (`cerberus/agents/base.py`):

```python
class BaseAgent(ABC):
    """Abstract Base Class for all specialized review agents."""

    name: str = "base_agent"
    version: str = "1.0.0"
    purpose: str = "Base code review agent"

    @abstractmethod
    async def analyze(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """Analyze code snippet and return structured findings and score."""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of specific checks and capabilities provided by this agent."""
        pass

    async def health_check(self) -> bool:
        """Verify that agent is operational and ready to receive review tasks."""
        return True
```

### Unified Finding Schema

All agents return issues modeled by the Pydantic `Finding` schema (`cerberus/models/schemas.py`):

```python
class Finding(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique finding ID, e.g. SEC-001")
    severity: SeverityEnum = Field(description="Severity classification: critical, high, medium, low, info")
    category: str = Field(description="Finding category, e.g. injection, complexity, architecture, compliance")
    title: str = Field(description="Short human-readable summary of the issue")
    message: str = Field(description="Detailed explanation of what was found")
    line: Optional[int] = Field(default=None, description="Line number in source code")
    column: Optional[int] = Field(default=None, description="Column offset in source code")
    code_snippet: Optional[str] = Field(default=None, description="Offending code line or block")
    explanation: Optional[str] = Field(default=None, description="Why this finding matters")
    recommendation: Optional[str] = Field(default=None, description="Actionable guidance to resolve the issue")
    suggestion: Optional[str] = Field(default=None, description="Concrete replacement snippet or diff")
    cwe_id: Optional[str] = Field(default=None, description="Common Weakness Enumeration ID (e.g. CWE-89)")
    cvss_score: Optional[float] = Field(default=None, description="CVSS 3.1 score between 0.0 and 10.0")
    exploitability: Optional[float] = Field(default=None, description="Estimated exploitability probability")
    false_positive_probability: Optional[float] = Field(default=0.02, description="Calculated FP probability")
```

---

## Security Agent

**ID:** `security`  
**Version:** 1.2.0  
**Purpose:** Identify security vulnerabilities and compliance issues

### Capabilities

The Security Agent detects the following types of issues:

#### 1. Injection Vulnerabilities

**SQL Injection:**
```python
# ❌ Vulnerable
query = f"SELECT * FROM users WHERE id = {user_id}"
db.execute(query)

# ❌ Vulnerable
query = "SELECT * FROM users WHERE name = '" + username + "'"
db.execute(query)

# ✅ Secure
query = "SELECT * FROM users WHERE id = ?"
db.execute(query, (user_id,))
```

**Command Injection:**
```python
# ❌ Vulnerable
os.system(f"ping {user_input}")

# ✅ Secure
subprocess.run(["ping", user_input], check=True)
```

**XSS (Cross-Site Scripting):**
```javascript
// ❌ Vulnerable
element.innerHTML = userInput;

// ❌ Vulnerable
document.write("<div>" + userInput + "</div>");

// ✅ Secure
element.textContent = userInput;
// Or use a sanitization library
element.innerHTML = DOMPurify.sanitize(userInput);
```

#### 2. Authentication & Authorization

**Hardcoded Credentials:**
```python
# ❌ Insecure
API_KEY = "sk-1234567890abcdef"
PASSWORD = "admin123"

# ✅ Secure
API_KEY = os.getenv("API_KEY")
PASSWORD = os.getenv("PASSWORD")
```

**Weak Authentication:**
```python
# ❌ Weak
def login(username, password):
    if username == "admin" and password == "admin":
        return True
    return False

# ✅ Strong
def login(username, password):
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        return create_session(user)
    return None
```

**Missing Authorization Checks:**
```python
# ❌ Missing auth
@app.route('/api/user/<user_id>')
def get_user(user_id):
    return User.query.get(user_id).to_json()

# ✅ With auth
@app.route('/api/user/<user_id>')
@require_auth
def get_user(user_id):
    if current_user.id != user_id and not current_user.is_admin:
        abort(403)
    return User.query.get(user_id).to_json()
```

#### 3. Cryptography Issues

**Weak Hashing:**
```python
# ❌ Weak (MD5)
import hashlib
hash = hashlib.md5(password.encode()).hexdigest()

# ✅ Strong (bcrypt)
import bcrypt
hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
```

**Insecure Random:**
```python
# ❌ Insecure
import random
token = ''.join(random.choices(string.ascii_letters, k=32))

# ✅ Secure
import secrets
token = secrets.token_urlsafe(32)
```

#### 4. Data Exposure

**Sensitive Data in Logs:**
```python
# ❌ Exposes data
logger.info(f"User login: {username}, password: {password}")

# ✅ Safe logging
logger.info(f"User login: {username}")
```

**PII Leakage:**
```python
# ❌ Exposes PII
return {"user": user.to_dict()}  # Includes SSN, credit card, etc.

# ✅ Sanitized
return {"user": user.to_public_dict()}  # Only public fields
```

#### 5. Dependency Vulnerabilities

The Security Agent checks for known vulnerabilities in imported packages:

```python
# ❌ Vulnerable versions detected
import requests  # Using requests 2.25.0 (CVE-2023-xxxxx)

# ✅ Agent recommends
# Update to requests >= 2.31.0 to fix security vulnerabilities
```

#### 6. Insecure Configurations

```python
# ❌ Insecure
app.config['SECRET_KEY'] = 'dev'
app.config['DEBUG'] = True  # In production

# ✅ Secure
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['DEBUG'] = os.getenv('FLASK_ENV') == 'development'
```

### Analysis Methodology

The Security Agent uses a multi-layered approach:

1. **Pattern Matching**: Regex patterns for common vulnerabilities
2. **Contextual Analysis**: LLM understands code context and intent
3. **Data Flow Tracking**: Traces user input through the code
4. **Best Practices**: Compares against security frameworks (OWASP, CWE)

### Severity Classification

| Severity | Criteria | Example |
|----------|----------|---------|
| **Critical** | Immediate exploit possible, high impact | SQL injection, hardcoded credentials |
| **High** | Exploit likely, significant impact | Weak authentication, XSS |
| **Medium** | Exploit possible with conditions | Missing input validation, weak crypto |
| **Low** | Potential security improvement | Verbose error messages, missing HTTPS |
| **Info** | Best practice recommendation | Add security headers, enable CSP |

### Configuration

```yaml
agents:
  security:
    enabled: true
    llm_model: "gpt-4-turbo-preview"  # Best model for security
    
    # Rule sets to enable
    rule_sets:
      - owasp_top_10
      - cwe_top_25
      - sans_top_25
    
    # Secret scanning
    secret_scanning:
      enabled: true
      patterns:
        - api_keys
        - passwords
        - private_keys
        - tokens
      custom_patterns:
        - regex: "API_KEY_[A-Za-z0-9]{32}"
          name: "Custom API Key"
    
    # Severity thresholds
    severity:
      block_on: ["critical", "high"]
      warn_on: ["medium"]
      report_all: true
    
    # Timeouts
    timeout_seconds: 30
    max_retries: 2
```

### Example Output

```json
{
  "agent": "security",
  "version": "1.2.0",
  "status": "completed",
  "execution_time_ms": 3450,
  "score": 45,
  "findings": [
    {
      "id": "SEC-001",
      "severity": "critical",
      "category": "sql_injection",
      "title": "SQL Injection vulnerability detected",
      "message": "User input is directly concatenated into SQL query without sanitization",
      "line": 42,
      "column": 12,
      "code_snippet": "query = f\"SELECT * FROM users WHERE id = {user_id}\"",
      "explanation": "This code constructs an SQL query by directly embedding user input, allowing attackers to inject malicious SQL code. For example, if user_id is \"1 OR 1=1\", it would return all users.",
      "impact": "Attackers can read, modify, or delete database contents, potentially compromising all data.",
      "cwe_id": "CWE-89",
      "owasp_category": "A03:2021 – Injection",
      "references": [
        "https://owasp.org/www-community/attacks/SQL_Injection",
        "https://cwe.mitre.org/data/definitions/89.html"
      ],
      "recommendation": "Use parameterized queries or an ORM to safely handle user input",
      "suggested_fix": "query = \"SELECT * FROM users WHERE id = ?\"\ndb.execute(query, (user_id,))",
      "confidence": 0.95
    }
  ],
  "token_usage": {
    "prompt_tokens": 1250,
    "completion_tokens": 380,
    "total_tokens": 1630,
    "estimated_cost_usd": 0.0326
  }
}
```

---

## Performance Agent

**ID:** `performance`  
**Version:** 1.1.0  
**Purpose:** Detect performance bottlenecks and optimization opportunities

### Capabilities

#### 1. Algorithmic Complexity

**Nested Loops:**
```python
# ❌ O(n²) complexity
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates

# ✅ O(n) complexity
def find_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
```

**Inefficient Searching:**
```python
# ❌ O(n) lookup in list
def is_valid_user(user_id, valid_users):
    return user_id in valid_users  # valid_users is a list

# ✅ O(1) lookup in set
def is_valid_user(user_id, valid_users):
    return user_id in valid_users  # valid_users is a set
```

#### 2. Database Query Optimization

**N+1 Query Problem:**
```python
# ❌ N+1 queries
users = User.query.all()
for user in users:
    print(user.posts)  # Separate query for each user

# ✅ Single query with join
users = User.query.options(joinedload(User.posts)).all()
for user in users:
    print(user.posts)  # Already loaded
```

**Missing Indexes:**
```python
# ❌ Slow query without index
# Agent detects: SELECT * FROM users WHERE email = ?
# Recommendation: Add index on 'email' column

# ✅ With index
# CREATE INDEX idx_users_email ON users(email);
```

**Large Result Sets:**
```python
# ❌ Loading all records
users = User.query.all()  # Could be millions

# ✅ Pagination
users = User.query.paginate(page=page, per_page=100)
```

#### 3. Memory Management

**Memory Leaks:**
```python
# ❌ Potential memory leak
cache = {}
def get_data(key):
    if key not in cache:
        cache[key] = expensive_operation(key)  # Unbounded growth
    return cache[key]

# ✅ Bounded cache
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_data(key):
    return expensive_operation(key)
```

**Large Data Structures:**
```python
# ❌ Loading entire file into memory
data = open('large_file.csv').read()  # Could be GBs

# ✅ Streaming
for line in open('large_file.csv'):
    process(line)
```

#### 4. Caching Opportunities

**Redundant Computations:**
```python
# ❌ Recomputing expensive operations
def get_user_data(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    permissions = calculate_permissions(user)  # Expensive
    return user, permissions

# ✅ Cache expensive computations
@cache(ttl=300)
def calculate_permissions(user):
    # Expensive computation
    return permissions
```

#### 5. I/O Optimization

**Synchronous I/O in Loops:**
```python
# ❌ Sequential API calls
results = []
for user_id in user_ids:
    result = requests.get(f"https://api.example.com/users/{user_id}")
    results.append(result.json())

# ✅ Parallel API calls
import asyncio
import aiohttp

async def fetch_all(user_ids):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_user(session, uid) for uid in user_ids]
        return await asyncio.gather(*tasks)
```

#### 6. Resource-Intensive Operations

```python
# ❌ Heavy computation in request handler
@app.route('/report')
def generate_report():
    report = complex_calculation()  # Takes 30 seconds
    return report

# ✅ Background processing
@app.route('/report')
def generate_report():
    task_id = queue.enqueue(complex_calculation)
    return {"task_id": task_id, "status": "processing"}
```

### Performance Scoring

The agent calculates a performance score (0-100) based on:

- **Algorithmic Efficiency** (40%): Complexity analysis
- **Database Queries** (30%): Query efficiency
- **Memory Usage** (15%): Memory patterns
- **I/O Operations** (15%): I/O efficiency

### Configuration

```yaml
agents:
  performance:
    enabled: true
    llm_model: "gpt-4-turbo-preview"
    
    # Complexity thresholds
    complexity:
      warn_at: "O(n²)"
      error_at: "O(n³)"
    
    # Memory thresholds
    memory:
      warn_at_mb: 100
      error_at_mb: 500
    
    # Database analysis
    database:
      detect_n_plus_1: true
      suggest_indexes: true
      max_result_size: 1000
    
    # Caching
    caching:
      suggest_opportunities: true
      min_computation_time_ms: 100
```

### Example Output

```json
{
  "agent": "performance",
  "status": "completed",
  "score": 68,
  "findings": [
    {
      "id": "PERF-001",
      "severity": "high",
      "category": "algorithmic_complexity",
      "title": "Nested loop creates O(n²) complexity",
      "line": 15,
      "explanation": "The nested loop iterates over the same list twice, resulting in quadratic time complexity. For a list of 1000 items, this means 1,000,000 operations.",
      "performance_impact": "For n=1000: ~1M operations. For n=10000: ~100M operations",
      "recommendation": "Use a set or dictionary for O(1) lookups",
      "suggested_fix": "seen = set(items)\nfor item in items:\n    if item in seen:\n        # O(1) lookup",
      "estimated_improvement": "1000x faster for large inputs"
    }
  ]
}
```

---

## Code Quality Agent

**ID:** `quality`  
**Version:** 1.3.0  
**Purpose:** Review maintainability, readability, and best practices

### Capabilities

#### 1. Naming Conventions

```python
# ❌ Poor naming
def f(x, y):
    z = x + y
    return z

# ✅ Clear naming
def calculate_total_price(base_price, tax_amount):
    total_price = base_price + tax_amount
    return total_price
```

#### 2. Code Structure

```python
# ❌ Long function
def process_order(order):
    # 200 lines of code...
    pass

# ✅ Decomposed
def process_order(order):
    validate_order(order)
    calculate_total(order)
    charge_payment(order)
    send_confirmation(order)
```

#### 3. Design Patterns

```python
# ❌ Tight coupling
class OrderProcessor:
    def __init__(self):
        self.payment = PayPalPayment()  # Hardcoded dependency
    
    def process(self, order):
        self.payment.charge(order.total)

# ✅ Dependency injection
class OrderProcessor:
    def __init__(self, payment_provider):
        self.payment = payment_provider
    
    def process(self, order):
        self.payment.charge(order.total)
```

#### 4. Documentation

```python
# ❌ Missing documentation
def calculate(a, b, c):
    return (a + b) * c

# ✅ Well documented
def calculate_order_total(subtotal, tax_rate, quantity):
    """
    Calculate the total order amount including tax.
    
    Args:
        subtotal: Base price before tax
        tax_rate: Tax rate as a decimal (e.g., 0.08 for 8%)
        quantity: Number of items ordered
    
    Returns:
        Total amount including tax
    
    Example:
        >>> calculate_order_total(100, 0.08, 2)
        216.0
    """
    return (subtotal + subtotal * tax_rate) * quantity
```

#### 5. Code Duplication

```python
# ❌ Duplicated logic
def get_active_users():
    return User.query.filter(User.active == True).all()

def get_active_admins():
    return User.query.filter(User.active == True, User.is_admin == True).all()

# ✅ DRY principle
def get_users(active=None, is_admin=None):
    query = User.query
    if active is not None:
        query = query.filter(User.active == active)
    if is_admin is not None:
        query = query.filter(User.is_admin == is_admin)
    return query.all()
```

#### 6. Error Handling

```python
# ❌ Bare except
try:
    risky_operation()
except:
    pass

# ✅ Specific error handling
try:
    risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
    return default_value
```

#### 7. SOLID Principles

**Single Responsibility:**
```python
# ❌ Multiple responsibilities
class User:
    def save_to_database(self):
        pass
    
    def send_welcome_email(self):
        pass
    
    def generate_report(self):
        pass

# ✅ Single responsibility
class User:
    pass

class UserRepository:
    def save(self, user):
        pass

class EmailService:
    def send_welcome_email(self, user):
        pass

class ReportGenerator:
    def generate_user_report(self, user):
        pass
```

### Quality Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Cyclomatic Complexity** | Number of independent paths | < 10 per function |
| **Function Length** | Lines of code per function | < 50 lines |
| **Class Size** | Number of methods | < 20 methods |
| **Documentation Coverage** | % of functions with docstrings | > 80% |
| **Naming Clarity** | Descriptive variable names | Subjective, LLM evaluates |

### Configuration

```yaml
agents:
  quality:
    enabled: true
    llm_model: "gpt-3.5-turbo"  # Good enough for quality checks
    
    # Style guide
    style_guide: "pep8"  # Or: "google", "airbnb", etc.
    
    # Complexity limits
    max_function_length: 50
    max_cyclomatic_complexity: 10
    max_class_size: 20
    
    # Documentation
    require_docstrings: true
    require_type_hints: true
    
    # Patterns to detect
    detect_code_smells: true
    detect_duplication: true
    suggest_refactoring: true
```

### Example Output

```json
{
  "agent": "quality",
  "status": "completed",
  "score": 78,
  "findings": [
    {
      "id": "QUAL-001",
      "severity": "medium",
      "category": "naming",
      "title": "Non-descriptive variable name",
      "line": 10,
      "code_snippet": "x = calculate_value()",
      "explanation": "Variable 'x' doesn't convey meaning. Use descriptive names.",
      "recommendation": "Rename to indicate what the variable represents",
      "suggested_fix": "total_price = calculate_value()"
    },
    {
      "id": "QUAL-002",
      "severity": "low",
      "category": "documentation",
      "title": "Missing docstring",
      "line": 5,
      "explanation": "Function lacks documentation explaining its purpose",
      "suggested_fix": "def calculate_value():\n    \"\"\"\n    Calculate the total value including tax.\n    \n    Returns:\n        float: Total value\n    \"\"\""
    }
  ]
}
```

---

## Architecture Agent

**ID:** `architecture`  
**Version:** `1.0.0`  
**Purpose:** Validate system architecture, module coupling, and structural anti-patterns

### Capabilities

The Architecture Agent analyzes module organization, dependency direction, and coupling anti-patterns:

#### 1. Deep Coupling & Relative Import Detection

Excessive relative import depth indicates tight architectural coupling between disparate package layers:

```python
# ❌ Anti-pattern: Deep relative import crossing architectural boundaries
from ....services.billing.internal.ledger import LedgerProcessor

# ✅ Clean: Absolute import or decoupled interface injection
from cerberus.services.billing import LedgerProcessor
```

#### 2. Cyclic Dependency Risk Analysis

Detects mutual dependencies where module A imports B and B imports A, leading to initialization deadlocks:

```python
# ❌ Anti-pattern: Direct mutual module import
# In auth.py:
from cerberus.core.users import get_user_profile

# In users.py:
from cerberus.core.auth import verify_session_token

# ✅ Decoupled: Domain events, dependency injection, or shared protocol
```

#### 3. Single Responsibility Principle (SRP) Verification

Identifies bloated classes and monolithic modules that combine database access, business logic, network communication, and presentation:

```python
# ❌ Anti-pattern: God class handling storage, business logic, and notifications
class UserManager:
    def connect_database(self): ...
    def hash_password(self): ...
    def send_smtp_email(self): ...
    def generate_html_invoice(self): ...

# ✅ Decomposed: Modular single-purpose services
class UserRepository: ...
class PasswordHasher: ...
class NotificationService: ...
```

#### 4. Architectural Modularity Scoring

Computes a structural modularity index (0.0 to 100.0) based on cohesion, import graph depth, and component boundaries.

### Architecture Agent Finding Format

```json
{
  "name": "architecture",
  "status": "completed",
  "score": 70.0,
  "execution_time_ms": 12,
  "findings": [
    {
      "id": "ARCH-001",
      "severity": "medium",
      "category": "architecture",
      "title": "Deep Relative Import Violates Layer Separation",
      "message": "Module uses 4 levels of relative import traversal, creating brittle coupling.",
      "line": 4,
      "code_snippet": "from ....services.internal import core_db",
      "explanation": "Deep relative imports bypass architectural layers and complicate module refactoring.",
      "recommendation": "Use absolute package imports or dependency injection.",
      "suggestion": "from myapp.services.internal import core_db",
      "cwe_id": "CWE-1061",
      "cvss_score": 3.2,
      "exploitability": 0.05,
      "false_positive_probability": 0.02
    }
  ]
}
```

---

## Compliance Agent

**ID:** `compliance`  
**Version:** `2.0.0`  
**Purpose:** Audit code against HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA regulatory mandates

### Supported Regulatory Frameworks

The Compliance Agent (`ComprehensiveComplianceAgent`) continuously evaluates code against 5 regulatory standards:

#### 1. HIPAA Security Rule (45 CFR §164.312)
- **ePHI In-Transit Encryption:** Enforces TLS 1.2+ for electronic Protected Health Information; flags plaintext HTTP transmission.
- **Audit Controls & Logging:** Requires audit logging for medical record access; forbids plaintext ePHI (SSN, medical records) in application logs.

```python
# ❌ Non-compliant: Transmitting ePHI over plaintext HTTP
response = requests.post("http://health-api.local/patients/records", json=patient_ephi)

# ✅ Compliant: Mandatory TLS and audit trail
response = requests.post("https://health-api.secure.internal/patients/records", json=patient_ephi)
```

#### 2. GDPR Data Protection (Articles 5, 6, 17, 25, 32)
- **Data Minimization (Art. 5):** Flags unnecessary personal data collection or long-term caching without retention bounds.
- **Right to Erasure (Art. 17):** Verifies that user data processing pipelines support cascade deletion / forgetting mechanisms.
- **Lawful Processing & Consent (Art. 6):** Validates explicit consent checks before personal telemetry tracking.

#### 3. SOC 2 Trust Services Criteria (CC6.1, CC6.6, CC7.1, CC7.2)
- **Hardcoded Secrets & Plaintext Credentials:** Flags passwords, API keys, and connection strings embedded directly in source code.
- **Role-Based Access Control (RBAC):** Verifies authentication and authorization checks on sensitive administrative handlers.
- **Log Masking:** Flags unmasked authentication tokens or PII written to standard output or logging pipelines.

#### 4. PCI-DSS v4.0 (Req 3.2, 3.4, 3.5)
- **Prohibited Sensitive Authentication Data (Req 3.2):** Forbids permanent storage of Card Verification Values (CVV / CVC) post-authorization.
- **Primary Account Number (PAN) Protection (Req 3.4):** Employs Luhn checksum validation to identify real 13–19 digit credit card numbers in code, ensuring they are hashed or masked.

```python
# ❌ Non-compliant: Storing CVV and plaintext card PAN
db.execute(f"INSERT INTO transactions (pan, cvv) VALUES ('{card_num}', '{cvv}')")

# ✅ Compliant: Tokenized payment processor reference
db.execute("INSERT INTO transactions (token) VALUES (%s)", (payment_token,))
```

#### 5. CCPA / CPRA (§1798.105, §1798.120)
- **Do Not Sell My Personal Information:** Audits data broker endpoints and analytics handlers for opt-out honoring.
- **Consumer Request Verification:** Ensures Data Subject Access Request (DSAR) validation before data exports.

### Compliance Agent Finding Format

```json
{
  "name": "compliance",
  "status": "completed",
  "score": 45.0,
  "execution_time_ms": 28,
  "findings": [
    {
      "id": "COMP-PCI-001",
      "severity": "critical",
      "category": "compliance",
      "title": "PCI-DSS Prohibited CVV Storage Detected",
      "message": "Storage of card security code (CVV/CVC) post-authorization violates PCI-DSS Requirement 3.2.",
      "line": 42,
      "code_snippet": "card_cvv = request.json['cvv']; db.save(cvv=card_cvv)",
      "explanation": "Card verification codes must never be stored after transaction authorization under any circumstances.",
      "recommendation": "Purge CVV from storage and memory immediately following bank authorization.",
      "suggestion": "# Do not persist CVV\npass",
      "cwe_id": "CWE-312",
      "cvss_score": 9.1,
      "exploitability": 0.9,
      "false_positive_probability": 0.01
    },
    {
      "id": "COMP-HIPAA-002",
      "severity": "high",
      "category": "compliance",
      "title": "HIPAA ePHI Transmission Without TLS",
      "message": "Protected health information transmitted over unencrypted HTTP endpoint (45 CFR §164.312(e)(1)).",
      "line": 88,
      "code_snippet": "requests.post('http://internal-records/phi', json=phi_payload)",
      "recommendation": "Enforce HTTPS with TLS 1.2 or TLS 1.3 encryption for all health data transit.",
      "suggestion": "requests.post('https://internal-records/phi', json=phi_payload)",
      "cwe_id": "CWE-319",
      "cvss_score": 7.5,
      "exploitability": 0.7,
      "false_positive_probability": 0.01
    }
  ]
}
```

---

## Agent Customization

### Per-Review Configuration

Override agent behavior for specific reviews:

```python
client.review(
    code="...",
    config={
        "agents": {
            "security": {
                "severity_threshold": "critical",  # Only critical issues
                "rule_sets": ["owasp_top_10"]       # Limited rule set
            },
            "performance": {
                "enabled": False  # Skip performance analysis
            }
        }
    }
)
```

### Project-Level Configuration

Create `.cerberus.yml` in your project root:

```yaml
version: 1

agents:
  security:
    enabled: true
    severity_threshold: high
    secret_scanning:
      enabled: true
      ignore_patterns:
        - "test_api_key_*"
        - "*_EXAMPLE_*"
  
  performance:
    enabled: true
    complexity:
      warn_at: "O(n²)"
  
  quality:
    enabled: true
    style_guide: pep8
    max_function_length: 30

ignore:
  - "**/*_test.py"
  - "migrations/**"
  - "vendor/**"
```

---

## Creating Custom Agents

### Agent Development SDK

```python
from cerberus.agents import BaseAgent, AgentResult, Finding

class TypeScriptLinterAgent(BaseAgent):
    """Custom agent for TypeScript-specific linting."""
    
    def __init__(self, config, llm_provider):
        super().__init__(config, llm_provider)
        self.name = "typescript_linter"
        self.version = "1.0.0"
    
    async def analyze(self, code: str, context: CodeContext) -> AgentResult:
        # Only analyze TypeScript files
        if context.language not in ["typescript", "tsx"]:
            return AgentResult(status="skipped")
        
        # Build prompt
        prompt = self._build_prompt(code, context)
        
        # Call LLM
        response = await self.llm.complete(prompt)
        
        # Parse response into findings
        findings = self._parse_findings(response)
        
        # Calculate score
        score = self._calculate_score(findings)
        
        return AgentResult(
            agent_name=self.name,
            status="completed",
            score=score,
            findings=findings
        )
    
    def _build_prompt(self, code: str, context: CodeContext) -> str:
        return f"""
        You are a TypeScript expert. Review this code for TypeScript-specific issues:
        
        {code}
        
        Focus on:
        - Type safety
        - Interface usage
        - Async/await patterns
        - TypeScript best practices
        
        Return findings in JSON format.
        """
    
    def _parse_findings(self, llm_response: str) -> List[Finding]:
        # Parse LLM response into structured findings
        pass
    
    def _calculate_score(self, findings: List[Finding]) -> int:
        # Calculate overall score based on findings
        pass
    
    def get_capabilities(self) -> List[str]:
        return [
            "typescript_type_checking",
            "interface_review",
            "async_patterns"
        ]
```

### Registering Custom Agents

```python
from cerberus import Cerberus
from my_agents import TypeScriptLinterAgent

client = Cerberus(api_key="...")

# Register custom agent
client.register_agent(TypeScriptLinterAgent)

# Use in reviews
result = client.review(
    code="...",
    language="typescript",
    agents=["security", "typescript_linter"]
)
```

---

## Agent Orchestration

### Execution Modes

**Parallel (Default):**
```yaml
execution:
  mode: parallel
  timeout_seconds: 30
```

All agents run simultaneously. Fastest but uses more resources.

**Sequential:**
```yaml
execution:
  mode: sequential
  order: ["security", "performance", "quality"]
```

Agents run one after another. Slower but uses less resources.

**Priority-Based:**
```yaml
execution:
  mode: priority
  priorities:
    security: 1    # Run first
    performance: 2  # Run second
    quality: 3      # Run last
  parallel_within_priority: true
```

### Consensus Logic

When agents have overlapping findings:

```yaml
consensus:
  enabled: true
  strategy: "highest_severity"  # Or: "majority_vote", "all_agree"
  deduplication: true
```

**Example:**
- Security Agent: "Potential SQL injection (HIGH)"
- Quality Agent: "Unsafe string concatenation (MEDIUM)"
- Result: Single finding with HIGH severity and combined context

---

**Next Steps:**
- [Configuration Reference](05-configuration-reference.md) - Configure agents
- [Developer Guide](08-developer-guide.md) - Create custom agents

---

*Cerberus Agent Specifications - v0.1.0*
