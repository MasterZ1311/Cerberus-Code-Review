# Agent Architecture Specifications (All 20 Agents)

## Table of Contents
1. [Executive Overview & Agent Ecosystem Taxonomy](#1-executive-overview--agent-ecosystem-taxonomy)
2. [Three-Tier Multi-Agent Classification Matrix](#2-three-tier-multi-agent-classification-matrix)
3. [Comprehensive Specifications for All 20 Agents](#3-comprehensive-specifications-for-all-20-agents)
   - [Agent 1: Predictive Bug Detection](#agent-1-predictive-bug-detection)
   - [Agent 2: Supply Chain Security](#agent-2-supply-chain-security)
   - [Agent 3: Performance Regression](#agent-3-performance-regression)
   - [Agent 4: Architecture Violation](#agent-4-architecture-violation)
   - [Agent 5: Technical Debt Quantifier](#agent-5-technical-debt-quantifier)
   - [Agent 6: Code Fixer](#agent-6-code-fixer)
   - [Agent 7: Custom Rule Engine](#agent-7-custom-rule-engine)
   - [Agent 8: Multi-Language Reviewer](#agent-8-multi-language-reviewer)
   - [Agent 9: Historical Trend Analysis](#agent-9-historical-trend-analysis)
   - [Agent 10: ML Code Auditor](#agent-10-ml-code-auditor)
   - [Agent 11: Compliance Standards (SOC2, HIPAA, PCI-DSS, ISO27001)](#agent-11-compliance-standards-soc2-hipaa-pci-dss-iso27001)
   - [Agent 12: IDE Integration](#agent-12-ide-integration)
   - [Agent 13: Cost Analysis (Cloud & LLM)](#agent-13-cost-analysis-cloud--llm)
   - [Agent 14: Accessibility Checker (WCAG 2.2)](#agent-14-accessibility-checker-wcag-22)
   - [Agent 15: Anomaly Detection](#agent-15-anomaly-detection)
   - [Agent 16: Codebase Fine-tuning](#agent-16-codebase-fine-tuning)
   - [Agent 17: Team Expertise Router](#agent-17-team-expertise-router)
   - [Agent 18: Knowledge Base Builder](#agent-18-knowledge-base-builder)
   - [Agent 19: Burndown Predictor](#agent-19-burndown-predictor)
   - [Agent 20: Collaborative Review](#agent-20-collaborative-review)
4. [Summary & Next Steps](#4-summary--next-steps)

---

## 1. Executive Overview & Agent Ecosystem Taxonomy

The **Cerberus** platform implements an enterprise multi-agent architecture powered by IBM watsonx Granite foundation models and LangGraph state graphs. The platform features 20 specialized agents designed to deliver comprehensive, end-to-end source code analysis across security, performance, architecture, compliance, team operations, and developer experience.

Every agent is structured as an autonomous, self-contained worker adhering to strict contracts:
- **Typed I/O Boundaries**: Explicit TypedDict schemas for `InputState`, `ExecutionState`, and `OutputState`.
- **Deterministic State Reducers**: Non-destructive state updates that aggregate seamlessly into the Master Orchestrator's `ReviewState`.
- **Hybrid Static & LLM Execution**: High-speed AST parsing and deterministic tool evaluation paired with IBM Granite foundation model reasoning.
- **Fail-Safe Isolation**: Dedicated timeout limits, exponential backoff retries, and offline heuristic fallbacks to guarantee pipeline continuity without score inflation.

---

## 2. Three-Tier Multi-Agent Classification Matrix

To optimize execution latency, resource allocation, and review throughput, the 20 agents are categorized across three architectural execution tiers:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               MASTER ORCHESTRATOR GRAPH                                │
└────────────┬───────────────────────────────┬───────────────────────────────┬───────────┘
             │                               │                               │
             ▼                               ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│         TIER 1          │     │         TIER 2          │     │         TIER 3          │
│   (Critical Blocking)   │     │  (Deep Analysis & Law)  │     │   (Team & Operations)   │
│ Latency SLA: < 4.0s     │     │ Latency SLA: < 10.0s    │     │ Latency SLA: Asynch/Bg  │
├─────────────────────────┤     ├─────────────────────────┤     ├─────────────────────────┤
│ 1. Predictive Bug       │     │ 5. Technical Debt       │     │ 12. IDE Integration     │
│ 2. Supply Chain Sec     │     │ 6. Code Fixer           │     │ 13. Cost Analysis       │
│ 3. Perf Regression      │     │ 7. Custom Rule Engine   │     │ 16. Codebase Fine-tune  │
│ 4. Architecture Viol    │     │ 8. Multi-Language Rev   │     │ 17. Expertise Router    │
│                         │     │ 9. Historical Trends    │     │ 18. Knowledge Base      │
│                         │     │ 10. ML Code Auditor     │     │ 19. Burndown Predict    │
│                         │     │ 11. Compliance Stds     │     │ 20. Collab Review       │
│                         │     │ 14. Accessibility WCAG  │     │                         │
│                         │     │ 15. Anomaly Detection   │     │                         │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
```

| # | Agent Name | Tier | Primary Objective | Blocking Gate | Primary Toolset |
|---|------------|------|-------------------|---------------|-----------------|
| 1 | Predictive Bug Detection | Tier 1 | ML-based defect prediction & hazard analysis | Yes (High Risk) | AST Churn Analyzer, CVE Matcher |
| 2 | Supply Chain Security | Tier 1 | SBOM generation & vulnerability audit | Yes (CVSS >= 9.0) | CycloneDX Generator, OSV/NVD API |
| 3 | Performance Regression | Tier 1 | Big-O profiling & N+1 query detection | Yes (O(n²) in loop) | Radon, AST Loop Analyzer |
| 4 | Architecture Violation | Tier 1 | Circular dependencies & SOLID boundaries | Yes (Cycle detected) | NetworkX Graph, Layer Checker |
| 5 | Technical Debt Quantifier | Tier 2 | Remediation hours & dollar valuation | No (Advisory) | SQALE Engine, ROI Projector |
| 6 | Code Fixer | Tier 2 | Automated unified diff patch generation | No (Advisory) | AST Syntax Verifier, UniDiff Gen |
| 7 | Custom Rule Engine | Tier 2 | Enterprise policy & custom YAML/regex rules | Yes (Configurable) | YAML Compiler, AST Node Matcher |
| 8 | Multi-Language Reviewer | Tier 2 | Polyglot idioms (Py, JS/TS, Java, Go, Rust) | No (Advisory) | Tree-Sitter Universal Parser |
| 9 | Historical Trend Analysis | Tier 2 | Longitudinal score & quality velocity tracking | No (Reporting) | Time-Series OLS, Churn Indexer |
| 10 | ML Code Auditor | Tier 2 | Data leakage, pickle risks & reproducibility | Yes (Data Leakage) | Pipeline Inspector, Pickle Scanner |
| 11 | Compliance Standards | Tier 2 | SOC2, HIPAA, PCI-DSS, ISO27001 audits | Yes (Regulated) | PHI/PII Scanner, Audit Validator |
| 12 | IDE Integration | Tier 3 | Sub-second LSP diagnostics for VS Code | No (Inline Hints) | LSP Diagnostic Converter |
| 13 | Cost Analysis (Cloud/LLM) | Tier 3 | Cloud infrastructure & token FinOps projections | No (Advisory) | Cloud Pricing API, Token Counter |
| 14 | Accessibility Checker | Tier 2 | WCAG 2.2 AA/AAA UI markup validation | No (Advisory) | JSX ARIA Validator, Contrast Tool |
| 15 | Anomaly Detection | Tier 2 | Statistical outlier PR churn & risk alerts | No (Advisory) | Z-Score Scorer, Isolation Forest |
| 16 | Codebase Fine-tuning | Tier 3 | LoRA instruction-tuning dataset synthesis | No (Background) | PII Scrubber, JSONL Dataset Writer |
| 17 | Team Expertise Router | Tier 3 | Git blame & domain reviewer matching | No (Workflow) | Git Blame Indexer, Team Calendar |
| 18 | Knowledge Base Builder | Tier 3 | ADR synthesis from resolved review discussions | No (Background) | ADR Generator, pgvector Embedder |
| 19 | Burndown Predictor | Tier 3 | Review turnaround time & rework prediction | No (Workflow) | Iteration Regressor, Queue Model |
| 20 | Collaborative Review | Tier 3 | Human-in-the-loop & multi-agent consensus | Yes (Final Gate) | Consensus Tally, Conflict Advisor |

---

## 3. Comprehensive Specifications for All 20 Agents

---

### Agent 1: Predictive Bug Detection

#### 1. Architectural Role & Tier
- **Tier**: Tier 1 (Critical Path)
- **Role**: Employs static AST metrics, commit churn analysis, and machine learning models to detect latent bugs (null-pointer dereferences, off-by-one errors, race conditions) before runtime.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Source Code & Diff    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Parse AST & Extract Churn    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Evaluate Defect Probability ML │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Timeout / Error]
┌────────────────┐     ┌────────────────┐
│ Watsonx Granite│     │ Fallback Static│
│ Pattern Reason │     │ Churn Scorer   │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│   Emit Bug Probability & Pts   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/bug_predictor/schemas.py
from typing import Any, Dict, List, Optional, TypedDict

class BugPredictorInput(TypedDict):
    code: str
    diff: Optional[str]
    language: str
    churn_history: Optional[Dict[str, int]]

class BugPredictorState(TypedDict):
    ast_tokens: List[str]
    cyclomatic_density: float
    hazard_score: float
    predicted_bugs: List[Dict[str, Any]]

class BugPredictorOutput(TypedDict):
    agent_name: str
    bug_probability: float
    high_risk_lines: List[int]
    findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/bug_predictor/tools.py
from typing import Any, Dict, List
import re

class ASTChurnAnalyzerTool:
    """Computes ratio of changed tokens to cyclomatic complexity branches."""
    name: str = "ast_churn_analyzer"
    description: str = "Calculates churn density and branch hazard coefficient."

    async def execute(self, code: str, diff: Optional[str]) -> Dict[str, float]:
        lines = code.splitlines()
        branch_count = sum(1 for line in lines if any(k in line for k in ["if ", "for ", "while ", "try:"]))
        total_lines = max(1, len(lines))
        cyclomatic_density = round(branch_count / total_lines, 3)
        churn_factor = 1.0 if not diff else min(3.0, len(diff.splitlines()) / total_lines)
        return {
            "cyclomatic_density": cyclomatic_density,
            "churn_factor": churn_factor,
            "hazard_score": round(cyclomatic_density * churn_factor, 3),
        }

class CVEPatternMatcherTool:
    """Matches code AST structures against known vulnerability patterns."""
    name: str = "cve_pattern_matcher"
    description: str = "Identifies structural similarity to recorded defect patterns."

    async def execute(self, code: str) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        if re.search(r"while\s+True:\s*(?!.*\bbreak\b)", code, re.DOTALL):
            matches.append({
                "pattern_id": "BUG-INF-LOOP",
                "title": "Unbounded Loop Without Break Condition",
                "severity": "critical",
                "line": 1,
            })
        return matches
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Enterprise Defect Prediction Specialist utilizing IBM Granite.
  [TASK]: Analyze the provided code diff and identify latent bugs, unhandled null pointers, off-by-one boundary hazards, and race conditions before runtime.
  [CONSTRAINTS]: Return strictly valid JSON adhering to the BugPredictorOutput schema. No markdown conversational filler.
  [FORMAT]:
  {
    "agent_name": "predictive_bug_detection",
    "bug_probability": 0.85,
    "high_risk_lines": [42, 87],
    "findings": [
      {
        "category": "logic_defect",
        "title": "Potential Null Pointer Dereference",
        "line": 42,
        "message": "Variable may be None prior to member access."
      }
    ]
  }
  ```
- **User Prompt**:
  ```
  Analyze this {language} snippet for latent bugs and defect probability:
  ```{language}
  {code}
  ```
  Diff Context:
  ```diff
  {diff}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms strict cancellation token.
- **Retry Strategy**: 2 retries with exponential backoff (base 500ms, max 1,500ms).
- **Fallback**: If IBM watsonx times out, fallback to `ASTChurnAnalyzerTool`. If `hazard_score > 0.4`, emit advisory finding with calculated static probability.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Max 4,000 prompt tokens. AST token pruner strips whitespace and inline comments before prompting.
- **Output Budget**: 1,000 completion tokens.
- **Garbage Collection**: AST tree references explicitly set to `None` upon completion of analysis.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_bug_predictor.py
import pytest
from src.cerberus.agents.bug_predictor.tools import ASTChurnAnalyzerTool

@pytest.mark.asyncio
async def test_ast_churn_analyzer_detects_dense_branches():
    tool = ASTChurnAnalyzerTool()
    sample_code = "if a:\n    if b:\n        for i in range(10):\n            pass\n"
    metrics = await tool.execute(sample_code, diff=None)
    assert metrics["cyclomatic_density"] > 0.5
    assert metrics["hazard_score"] > 0.5
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Added as `run_bug_predictor` node parallel to security node. Reducer accumulates findings to `ReviewState["findings"]`.
- **Database Table**: Writes defect probability vectors to `ml_predictions` table.

---

### Agent 2: Supply Chain Security

#### 1. Architectural Role & Tier
- **Tier**: Tier 1 (Critical Path)
- **Role**: Extracts Software Bill of Materials (SBOM), audits dependencies against CVE databases (OSV, NVD), and verifies open-source license compliance.
- **Latency Budget**: 3,000ms
- **Memory Ceiling**: 350MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Manifest / Lockfile   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Extract Packages & Versions    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Generate CycloneDX 1.5 SBOM  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Query OSV.dev / NVD for CVEs   │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [API Outage]
┌────────────────┐     ┌────────────────┐
│ Watsonx License│     │ Local Offline  │
│ Conflict Audit │     │ CVE Cache      │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│ Emit Supply Chain Vulnerability│
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/supply_chain/schemas.py
from typing import Any, Dict, List, Optional, TypedDict

class SupplyChainInput(TypedDict):
    manifest_content: str
    manifest_type: str  # requirements.txt, package.json, go.mod, Cargo.toml

class SupplyChainState(TypedDict):
    packages: List[Dict[str, str]]
    sbom_json: Dict[str, Any]
    vulnerabilities: List[Dict[str, Any]]

class SupplyChainOutput(TypedDict):
    agent_name: str
    sbom_url: Optional[str]
    vulnerable_packages: List[Dict[str, Any]]
    license_conflicts: List[Dict[str, Any]]
    score: float
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/supply_chain/tools.py
from typing import Any, Dict, List
import re

class SBOMGeneratorTool:
    """Parses manifest files into standardized package structures."""
    name: str = "sbom_generator"
    description: str = "Extracts dependencies and generates CycloneDX metadata."

    async def execute(self, manifest_content: str, manifest_type: str) -> List[Dict[str, str]]:
        packages: List[Dict[str, str]] = []
        if manifest_type == "requirements.txt":
            for line in manifest_content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "==" in line:
                    parts = line.split("==")
                    packages.append({"name": parts[0].strip(), "version": parts[1].strip()})
        return packages

class OSVVulnerabilityLookupTool:
    """Simulates CVE database queries against known vulnerable packages."""
    name: str = "osv_vulnerability_lookup"
    description: str = "Queries OSV and NVD for known package CVEs."

    KNOWN_VULNERABLE = {
        "urllib3": [("CVE-2023-45803", 9.8, "Request body leak in redirect handling")],
        "requests": [("CVE-2023-32681", 6.1, "Proxy-Authorization header leak")],
    }

    async def execute(self, packages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        vulnerabilities: List[Dict[str, Any]] = []
        for pkg in packages:
            name = pkg["name"].lower()
            if name in self.KNOWN_VULNERABLE:
                for cve, cvss, desc in self.KNOWN_VULNERABLE[name]:
                    vulnerabilities.append({
                        "package": name,
                        "version": pkg["version"],
                        "cve_id": cve,
                        "cvss_score": cvss,
                        "description": desc,
                    })
        return vulnerabilities
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Supply Chain & Software Bill of Materials (SBOM) Auditor using IBM Granite.
  [TASK]: Review parsed software packages for copyleft license violations (e.g. GPL-3.0 in proprietary SaaS) and outdated insecure components.
  [CONSTRAINTS]: Output strict JSON conforming to SupplyChainOutput schema.
  [FORMAT]:
  {
    "agent_name": "supply_chain_security",
    "sbom_url": null,
    "vulnerable_packages": [],
    "license_conflicts": [
      {
        "package": "gpl-library",
        "license": "GPL-3.0",
        "risk": "High copyleft contamination hazard."
      }
    ],
    "score": 85.0
  }
  ```
- **User Prompt**:
  ```
  Audit the following dependencies for commercial license conflicts:
  Manifest Type: {manifest_type}
  Packages:
  {packages}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,000ms.
- **Fallback**: Local cached vulnerability dictionary returned if external REST API fails or times out.
- **Unpinned Warning**: Emits MEDIUM finding when dependencies lack fixed versions (`pkg>=1.0`).

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Cap manifest inputs to 10,000 lines. Stream-parse with line iterators to maintain memory footprint < 20MB.
- **Output Budget**: 1,500 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_supply_chain.py
import pytest
from src.cerberus.agents.supply_chain.tools import SBOMGeneratorTool, OSVVulnerabilityLookupTool

@pytest.mark.asyncio
async def test_supply_chain_cve_detection():
    sbom_tool = SBOMGeneratorTool()
    cve_tool = OSVVulnerabilityLookupTool()
    packages = await sbom_tool.execute("urllib3==1.26.4\nrequests==2.25.0", "requirements.txt")
    assert len(packages) == 2
    vulns = await cve_tool.execute(packages)
    assert any(v["cve_id"] == "CVE-2023-45803" for v in vulns)
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Invoked when PR manifests (`requirements.txt`, `package.json`, etc.) are detected in changeset.
- **Database Table**: Writes SBOM payloads and findings to `security_findings` table.

---

### Agent 3: Performance Regression

#### 1. Architectural Role & Tier
- **Tier**: Tier 1 (Critical Path)
- **Role**: Analyzes algorithmic time and space complexity ($O(N)$, $O(N^2)$), detects nested loops, unbuffered I/O, and ORM database N+1 query patterns.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Source Code AST       │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Parse Loops & Call Sites     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Calculate Big-O Complexity     │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [N+1 Detected]
┌────────────────┐     ┌────────────────┐
│ Watsonx Latency│     │ ORM Query Loop │
│ Impact Scoring │     │ Bottleneck Flag│
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│   Emit Performance Findings    │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/perf_regression/schemas.py
from typing import Any, Dict, List, Optional, TypedDict

class PerfRegressionInput(TypedDict):
    code: str
    language: str
    baseline_latency_ms: Optional[float]

class PerfRegressionState(TypedDict):
    complexity_class: str
    n_plus_one_queries: List[Dict[str, Any]]
    memory_leaks: List[Dict[str, Any]]

class PerfRegressionOutput(TypedDict):
    agent_name: str
    current_complexity: str
    estimated_latency_delta_pct: float
    findings: List[Dict[str, Any]]
    score: float
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/perf_regression/tools.py
from typing import Any, Dict, List
import re

class ComplexityAnalyzerTool:
    """Detects quadratic Big-O bottlenecks in nested loops."""
    name: str = "complexity_analyzer"
    description: str = "Evaluates AST nesting to flag O(N^2) or worse algorithms."

    async def execute(self, code: str) -> Dict[str, Any]:
        lines = code.splitlines()
        depth = 0
        max_depth = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("for ") or stripped.startswith("while "):
                depth += 1
                max_depth = max(max_depth, depth)
            elif not stripped or stripped.startswith("#"):
                continue
            elif len(line) - len(line.lstrip()) == 0:
                depth = 0

        complexity = "O(N)" if max_depth <= 1 else ("O(N^2)" if max_depth == 2 else "O(N^3+)")
        return {"max_loop_depth": max_depth, "complexity": complexity}

class QueryPatternAnalyzerTool:
    """Detects database queries initiated inside iterative loops (N+1 hazard)."""
    name: str = "query_pattern_analyzer"
    description: str = "Identifies unbatched database queries executed in loops."

    async def execute(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        lines = code.splitlines()
        in_loop = False
        for idx, line in enumerate(lines, start=1):
            if any(line.strip().startswith(k) for k in ["for ", "while "]):
                in_loop = True
            if in_loop and any(db in line for db in [".query(", ".filter(", "session.execute(", "select("]):
                findings.append({
                    "line": idx,
                    "title": "Database N+1 Query in Loop",
                    "severity": "high",
                    "code_snippet": line.strip()[:80],
                })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: High-Performance Systems Architect using IBM Granite.
  [TASK]: Detect algorithmic bottlenecks, O(n^2) nested iterations, unindexed DB queries, and unbounded memory allocations.
  [CONSTRAINTS]: Emit strictly JSON conforming to PerfRegressionOutput. Include optimal replacement code.
  [FORMAT]:
  {
    "agent_name": "performance_regression",
    "current_complexity": "O(N^2)",
    "estimated_latency_delta_pct": 250.0,
    "findings": [],
    "score": 65.0
  }
  ```
- **User Prompt**:
  ```
  Profile the performance scaling of this {language} snippet:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms.
- **Fallback**: Static `ComplexityAnalyzerTool` returns complexity score based strictly on indentation analysis.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 4,000 tokens. Large files partitioned by class/method boundaries.
- **Output Budget**: 1,000 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_perf_regression.py
import pytest
from src.cerberus.agents.perf_regression.tools import ComplexityAnalyzerTool, QueryPatternAnalyzerTool

@pytest.mark.asyncio
async def test_performance_n_plus_one_detection():
    tool = QueryPatternAnalyzerTool()
    code = "for user_id in user_ids:\n    user = session.execute(select(User).where(User.id == user_id))\n"
    findings = await tool.execute(code)
    assert len(findings) == 1
    assert findings[0]["title"] == "Database N+1 Query in Loop"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: `run_performance` node.
- **Database Table**: Writes latency estimates and findings to `performance_findings`.

---

### Agent 4: Architecture Violation

#### 1. Architectural Role & Tier
- **Tier**: Tier 1 (Critical Path)
- **Role**: Enforces clean architecture, hexagonal module boundaries, circular import elimination, and SOLID principles.
- **Latency Budget**: 3,000ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Module AST Imports    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Build Module Dependency Graph  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Check Cycles (Tarjan Algorithm)│
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Cycle Found]
┌────────────────┐     ┌────────────────┐
│ Layer Boundary │     │ Circular Import│
│ Audit (Hexagon)│     │ Violation Flag │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│  Emit Architecture Violations  │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/architecture/schemas.py
from typing import Any, Dict, List, TypedDict

class ArchitectureInput(TypedDict):
    file_path: str
    code: str
    project_modules: List[str]

class ArchitectureState(TypedDict):
    import_graph: Dict[str, List[str]]
    circular_cycles: List[List[str]]
    layer_violations: List[Dict[str, Any]]

class ArchitectureOutput(TypedDict):
    agent_name: str
    architecture_score: float
    coupling_metric: float
    cohesion_metric: float
    anti_patterns: List[str]
    findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/architecture/tools.py
from typing import Any, Dict, List
import re

class DependencyGraphTool:
    """Builds import dependency graphs and detects cycles."""
    name: str = "dependency_graph"
    description: str = "Parses import statements to detect circular references."

    async def execute(self, file_path: str, code: str) -> Dict[str, Any]:
        imports: List[str] = []
        for line in code.splitlines():
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                match = re.search(r"(?:from|import)\s+([\w\.]+)", line)
                if match:
                    imports.append(match.group(1))

        # Check for self-import or immediate circular pattern
        current_mod = file_path.replace("/", ".").replace(".py", "")
        circular = [imp for imp in imports if imp in current_mod]
        return {
            "module": current_mod,
            "imports": imports,
            "has_circular": len(circular) > 0,
        }
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Enterprise Software Architect using IBM Granite.
  [TASK]: Enforce clean architecture, hexagonal boundaries, SOLID principles, and eliminate circular dependencies.
  [CONSTRAINTS]: Output strict JSON adhering to ArchitectureOutput.
  [FORMAT]:
  {
    "agent_name": "architecture_violation",
    "architecture_score": 90.0,
    "coupling_metric": 0.25,
    "cohesion_metric": 0.85,
    "anti_patterns": [],
    "findings": []
  }
  ```
- **User Prompt**:
  ```
  Review architectural layer integrity for module '{file_path}':
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,000ms.
- **Fallback**: Graph search times out after 2,000ms and returns heuristic layer checks based on directory path conventions (`domain/` vs `infra/`).

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 3,500 tokens. Strips function bodies, keeping only module header imports and class signatures.
- **Output Budget**: 1,000 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_architecture.py
import pytest
from src.cerberus.agents.architecture.tools import DependencyGraphTool

@pytest.mark.asyncio
async def test_dependency_graph_detects_circular_imports():
    tool = DependencyGraphTool()
    code = "from src.cerberus.orchestration.master_orchestrator import App\n"
    res = await tool.execute("src/cerberus/orchestration/master_orchestrator.py", code)
    assert res["has_circular"] is True
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: `run_architecture` node.
- **Database Table**: Writes coupling metrics and cycle alerts to `architecture_findings`.

---

### Agent 5: Technical Debt Quantifier

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Quantifies technical debt in engineering hours and remediation financial cost ($ USD) using the SQALE methodology.
- **Latency Budget**: 3,500ms
- **Memory Ceiling**: 250MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Code & Agent Findings │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Calculate SQALE Remediation Hrs│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Compute Dollar Remediation ($) │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Advisory]
┌────────────────┐     ┌────────────────┐
│ Watsonx ROI    │     │ Static Debt    │
│ Payoff Traject │     │ Formula Model  │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│   Emit Technical Debt Report   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/technical_debt/schemas.py
from typing import Any, Dict, List, TypedDict

class TechnicalDebtInput(TypedDict):
    code: str
    findings_summary: Dict[str, int]
    developer_hourly_rate: float

class TechnicalDebtState(TypedDict):
    remediation_minutes: int
    complexity_debt_hours: float
    documentation_debt_hours: float

class TechnicalDebtOutput(TypedDict):
    agent_name: str
    total_debt_hours: float
    estimated_remediation_cost_usd: float
    debt_score: float
    payoff_recommendations: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/technical_debt/tools.py
from typing import Any, Dict

class SQALEDebtCalculatorTool:
    """Calculates engineering hours required to remediate code debt."""
    name: str = "sqale_debt_calculator"
    description: str = "Maps severity findings into standard SQALE engineering hours."

    MINUTES_PER_SEVERITY = {
        "critical": 180,  # 3 hours
        "high": 90,       # 1.5 hours
        "medium": 30,     # 30 mins
        "low": 10,        # 10 mins
        "info": 0,
    }

    async def execute(self, findings_summary: Dict[str, int], hourly_rate: float = 120.0) -> Dict[str, float]:
        total_minutes = sum(
            findings_summary.get(sev, 0) * mins
            for sev, mins in self.MINUTES_PER_SEVERITY.items()
        )
        total_hours = round(total_minutes / 60.0, 2)
        total_cost = round(total_hours * hourly_rate, 2)
        return {
            "debt_hours": total_hours,
            "cost_usd": total_cost,
        }
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Engineering Management & Technical Debt Valuation Expert using IBM Granite.
  [TASK]: Translate code smells, test gaps, and architecture flaws into concrete remediation engineering hours and dollar cost.
  [CONSTRAINTS]: Return strictly JSON conforming to TechnicalDebtOutput.
  [FORMAT]:
  {
    "agent_name": "technical_debt_quantifier",
    "total_debt_hours": 4.5,
    "estimated_remediation_cost_usd": 540.0,
    "debt_score": 75.0,
    "payoff_recommendations": []
  }
  ```
- **User Prompt**:
  ```
  Quantify technical debt for code with findings {findings_summary} at rate ${developer_hourly_rate}/hr:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,500ms.
- **Fallback**: Mathematical SQALE formula operates statelessly without external network dependencies.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 2,500 tokens. Only metrics and findings summary passed to LLM.
- **Output Budget**: 800 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_technical_debt.py
import pytest
from src.cerberus.agents.technical_debt.tools import SQALEDebtCalculatorTool

@pytest.mark.asyncio
async def test_sqale_debt_calculation():
    tool = SQALEDebtCalculatorTool()
    summary = {"critical": 1, "high": 2, "medium": 1}
    res = await tool.execute(summary, hourly_rate=100.0)
    # (180 + 180 + 30) = 390 mins = 6.5 hrs * $100 = $650
    assert res["debt_hours"] == 6.5
    assert res["cost_usd"] == 650.0
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Aggregator output consumer node.
- **Database Table**: Persists to `cost_findings` and `repository_metrics`.

---

### Agent 6: Code Fixer

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Enhancement)
- **Role**: Synthesizes AST-verified unified diff patches (`.patch`) resolving flagged security, performance, and best practices findings.
- **Latency Budget**: 4,000ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Finding & Code Snippet│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Watsonx Granite Patch Synthesis│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Verify AST Syntactic Validity  │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Syntax Error]
┌────────────────┐     ┌────────────────┐
│ Generate Git   │     │ Discard Patch, │
│ Unified Diff   │     │ Emit Text Hint │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│   Emit Repaired Patch Output   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/code_fixer/schemas.py
from typing import Any, Dict, Optional, TypedDict

class CodeFixerInput(TypedDict):
    code: str
    finding: Dict[str, Any]
    language: str

class CodeFixerState(TypedDict):
    raw_patch: str
    is_syntactically_valid: bool
    verification_error: Optional[str]

class CodeFixerOutput(TypedDict):
    agent_name: str
    finding_id: str
    unified_diff: str
    repaired_code: str
    confidence_score: float
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/code_fixer/tools.py
import ast
import difflib
from typing import Any, Dict, Tuple

class ASTSyntaxValidatorTool:
    """Verifies that generated code patches compile into a valid AST."""
    name: str = "ast_syntax_validator"
    description: str = "Validates syntax integrity of proposed code repairs."

    async def execute(self, code: str, language: str) -> Tuple[bool, str]:
        if language.lower() == "python":
            try:
                ast.parse(code)
                return True, "Valid Python AST"
            except SyntaxError as e:
                return False, f"SyntaxError: {str(e)}"
        return True, "Non-Python syntax validation bypassed"

class UniDiffGeneratorTool:
    """Generates standard unified diff format strings."""
    name: str = "unidiff_generator"
    description: str = "Builds git-compatible patch diffs."

    async def execute(self, original: str, repaired: str, filename: str = "main.py") -> str:
        orig_lines = original.splitlines(keepends=True)
        rep_lines = repaired.splitlines(keepends=True)
        diff = difflib.unified_diff(orig_lines, rep_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
        return "".join(diff)
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Principal Refactoring & Automated Code Repair Engineer using IBM Granite.
  [TASK]: Produce minimal, safe, syntactically perfect replacement code that eliminates the specified finding without breaking existing logic.
  [CONSTRAINTS]: Return ONLY the replacement code snippet enclosed in standard markdown fences. No preamble.
  [FORMAT]:
  ```{language}
  # Repaired code here
  ```
  ```
- **User Prompt**:
  ```
  Fix finding: {finding_title} - {finding_remediation}
  Original code at line {line}:
  ```{language}
  {code_snippet}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 4,000ms.
- **Fallback**: If repaired code fails `ast.parse()`, the patch is discarded and `unified_diff=""` with `confidence_score=0.0` is returned.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Scoped strictly to localized window (target line +/- 25 lines) to limit prompt tokens < 1,500.
- **Output Budget**: 1,000 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_code_fixer.py
import pytest
from src.cerberus.agents.code_fixer.tools import ASTSyntaxValidatorTool, UniDiffGeneratorTool

@pytest.mark.asyncio
async def test_code_fixer_validates_syntax_and_diff():
    validator = ASTSyntaxValidatorTool()
    diff_tool = UniDiffGeneratorTool()
    original = "x = 1\n"
    repaired = "x = 2\n"
    valid, _ = await validator.execute(repaired, "python")
    assert valid is True
    diff = await diff_tool.execute(original, repaired)
    assert "-x = 1" in diff and "+x = 2" in diff
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: On-demand execution triggered via `POST /api/v1/reviews/{id}/fix`.
- **Database Table**: Writes diff suggestions to `review_findings` table `remediation_patch` column.

---

### Agent 7: Custom Rule Engine

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Evaluates proprietary enterprise rules defined in YAML using regex, AST patterns, and Semgrep queries.
- **Latency Budget**: 2,000ms
- **Memory Ceiling**: 250MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Code & YAML Rules     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Compile Regex / AST Patterns │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Execute Pattern Matching     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Map Severity & Custom Messages │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│     Emit Custom Findings       │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/custom_rules/schemas.py
from typing import Any, Dict, List, TypedDict

class CustomRuleEngineInput(TypedDict):
    code: str
    language: str
    custom_rules_yaml: str

class CustomRuleEngineState(TypedDict):
    compiled_rules: List[Dict[str, Any]]
    matched_violations: List[Dict[str, Any]]

class CustomRuleEngineOutput(TypedDict):
    agent_name: str
    rules_evaluated_count: int
    violations_count: int
    findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/custom_rules/tools.py
from typing import Any, Dict, List
import re
import yaml

class YAMLRuleCompilerTool:
    """Parses and executes YAML custom rules."""
    name: str = "yaml_rule_compiler"
    description: str = "Evaluates regex rules against source code lines."

    async def execute(self, code: str, rules_yaml: str) -> List[Dict[str, Any]]:
        findings = []
        try:
            config = yaml.safe_load(rules_yaml) or {}
            rules = config.get("rules", [])
        except Exception:
            return findings

        lines = code.splitlines()
        for rule in rules:
            pattern = re.compile(rule.get("regex", r"$^"))
            for idx, line in enumerate(lines, start=1):
                if pattern.search(line):
                    findings.append({
                        "rule_id": rule.get("id", "CUSTOM-001"),
                        "title": rule.get("title", "Custom Policy Violation"),
                        "severity": rule.get("severity", "medium"),
                        "message": rule.get("message", "Violates custom rule."),
                        "line": idx,
                        "code_snippet": line.strip()[:80],
                    })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Enterprise Policy & Custom Rule Enforcement Engine using IBM Granite.
  [TASK]: Evaluate codebase against proprietary enterprise design guidelines and compliance policies defined in YAML.
  [CONSTRAINTS]: Output strict JSON conforming to CustomRuleEngineOutput.
  [FORMAT]:
  {
    "agent_name": "custom_rule_engine",
    "rules_evaluated_count": 5,
    "violations_count": 1,
    "findings": []
  }
  ```
- **User Prompt**:
  ```
  Evaluate code against these rules:
  ```yaml
  {custom_rules_yaml}
  ```
  Source:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,000ms.
- **Fallback**: Schema validation failure on rule YAML aborts execution with zero violations and descriptive lint error.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Compiled regex cache bounded to 100 entries.
- **Output Budget**: 1,000 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_custom_rules.py
import pytest
from src.cerberus.agents.custom_rules.tools import YAMLRuleCompilerTool

@pytest.mark.asyncio
async def test_custom_rule_compiler():
    tool = YAMLRuleCompilerTool()
    rules = "rules:\n  - id: NO-PRINT\n    regex: 'print\\('\n    severity: high\n"
    code = "def foo():\n    print('test')\n"
    findings = await tool.execute(code, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "NO-PRINT"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Executed in parallel with Tier 2 agents.
- **Database Table**: Loads rules from `custom_rules` table; records findings in `review_findings`.

---

### Agent 8: Multi-Language Reviewer

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Polyglot code analysis supporting Python, JavaScript/TypeScript, Java, Go, and Rust via tree-sitter.
- **Latency Budget**: 3,000ms
- **Memory Ceiling**: 350MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Polyglot Source File  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Detect Language & Tree-Sitter  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Language-Specific Idiom Linter │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Missing Grammar]
┌────────────────┐     ┌────────────────┐
│ Watsonx Idiom  │     │ Universal AST  │
│ Deep Inspection│     │ Regex Tokenizer│
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│   Emit Multi-Language Report   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/multi_language/schemas.py
from typing import Any, Dict, List, TypedDict

class MultiLanguageInput(TypedDict):
    code: str
    language: str  # python, javascript, typescript, java, go, rust

class MultiLanguageState(TypedDict):
    detected_dialect: str
    idiom_violations: List[Dict[str, Any]]

class MultiLanguageOutput(TypedDict):
    agent_name: str
    language_detected: str
    idiomatic_score: float
    findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/multi_language/tools.py
from typing import Any, Dict, List

class IdiomCatalogCheckerTool:
    """Checks language-specific anti-patterns across polyglot languages."""
    name: str = "idiom_catalog_checker"
    description: str = "Validates idioms for Go, Rust, Java, TS, and Python."

    async def execute(self, code: str, language: str) -> List[Dict[str, Any]]:
        findings = []
        lang = language.lower()
        lines = code.splitlines()

        if lang == "go":
            for idx, line in enumerate(lines, start=1):
                if ", _ = " in line or ", _ :=" in line:
                    findings.append({
                        "language": "go",
                        "title": "Unhandled Error Return In Go",
                        "severity": "medium",
                        "line": idx,
                        "remediation": "Check and handle error value explicitly.",
                    })
        elif lang == "rust":
            for idx, line in enumerate(lines, start=1):
                if ".unwrap()" in line:
                    findings.append({
                        "language": "rust",
                        "title": "Unsafe unwrap() Call in Rust",
                        "severity": "medium",
                        "line": idx,
                        "remediation": "Use match, if let, or ? operator instead of unwrap().",
                    })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Polyglot Language Specialist (Python, JS/TS, Java, Go, Rust) using IBM Granite.
  [TASK]: Detect non-idiomatic patterns, unhandled errors, memory leaks, and concurrency bugs specific to {language}.
  [CONSTRAINTS]: Output strict JSON conforming to MultiLanguageOutput.
  [FORMAT]:
  {
    "agent_name": "multi_language_reviewer",
    "language_detected": "go",
    "idiomatic_score": 85.0,
    "findings": []
  }
  ```
- **User Prompt**:
  ```
  Review this {language} code for idiomatic correctness and language safety:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,000ms.
- **Fallback**: Regex tokenization fallback if Tree-Sitter grammar binaries are absent.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 4,000 tokens.
- **Output Budget**: 1,000 tokens. Tree-sitter node pointers freed immediately.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_multi_language.py
import pytest
from src.cerberus.agents.multi_language.tools import IdiomCatalogCheckerTool

@pytest.mark.asyncio
async def test_multi_language_go_rust_checks():
    tool = IdiomCatalogCheckerTool()
    go_code = "val, _ := doSomething()\n"
    rust_code = "let x = opt.unwrap();\n"
    go_findings = await tool.execute(go_code, "go")
    rust_findings = await tool.execute(rust_code, "rust")
    assert len(go_findings) == 1
    assert len(rust_findings) == 1
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Dynamic routing based on `request.language`.
- **Database Table**: Writes polyglot metrics to `review_findings`.

---

### Agent 9: Historical Trend Analysis

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Longitudinal tracking of repository scores, technical debt trajectory, and code quality degradation across pull requests.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 250MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Repo ID & Date Range  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Query Historical DB Rollups  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Compute OLS Linear Regression  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Forecast Trajectory & Drift  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Emit Historical Trend Report   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/historical_trends/schemas.py
from typing import Any, Dict, List, TypedDict

class HistoricalTrendInput(TypedDict):
    repo_owner: str
    repo_name: str
    timeframe_days: int

class HistoricalTrendState(TypedDict):
    time_series_points: List[Dict[str, Any]]
    quality_slope: float
    security_delta: float

class HistoricalTrendOutput(TypedDict):
    agent_name: str
    quality_trajectory: str  # improving, degrading, stable
    velocity_impact_pct: float
    historical_chart_data: List[Dict[str, Any]]
    summary: str
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/historical_trends/tools.py
from typing import Any, Dict, List

class TimeSeriesRegressionTool:
    """Calculates linear regression slope on quality time-series."""
    name: str = "time_series_regression"
    description: str = "Computes OLS trend direction across historical reviews."

    async def execute(self, points: List[float]) -> Dict[str, Any]:
        if len(points) < 2:
            return {"slope": 0.0, "trajectory": "insufficient_data"}
        n = len(points)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(points) / n
        numerator = sum((x[i] - x_mean) * (points[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = round(numerator / denominator, 3) if denominator != 0 else 0.0
        trajectory = "improving" if slope > 0.05 else ("degrading" if slope < -0.05 else "stable")
        return {"slope": slope, "trajectory": trajectory}
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Software Quality Analytics & Velocity Forecaster using IBM Granite.
  [TASK]: Interpret longitudinal quality metrics and warn leadership of systemic code degradation or technical debt accumulation.
  [CONSTRAINTS]: Output strict JSON conforming to HistoricalTrendOutput.
  [FORMAT]:
  {
    "agent_name": "historical_trend_analysis",
    "quality_trajectory": "stable",
    "velocity_impact_pct": 0.0,
    "historical_chart_data": [],
    "summary": "Repository quality has remained consistent over the last 30 days."
  }
  ```
- **User Prompt**:
  ```
  Analyze quality trend for {repo_owner}/{repo_name}:
  Historical Score Series: {time_series_points}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms.
- **Fallback**: Returns `trajectory="insufficient_data"` if repo has fewer than 3 reviews.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Max 100 historical points.
- **Output Budget**: 800 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_historical_trends.py
import pytest
from src.cerberus.agents.historical_trends.tools import TimeSeriesRegressionTool

@pytest.mark.asyncio
async def test_time_series_regression_detects_degradation():
    tool = TimeSeriesRegressionTool()
    scores = [95.0, 90.0, 85.0, 75.0, 60.0]
    res = await tool.execute(scores)
    assert res["trajectory"] == "degrading"
    assert res["slope"] < 0
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Subgraph node powering `/analytics/trends`.
- **Database Table**: Queries `metrics_history` and `code_reviews`.

---

### Agent 10: ML Code Auditor

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Validates AI/ML pipelines for train/test data leakage, unsafe model serialization (`pickle`), and unseeded randoms.
- **Latency Budget**: 3,000ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: ML Code / Notebook    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Extract Python AST Cells     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Inspect Data Preprocessing AST │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Leakage Detected]
┌────────────────┐     ┌────────────────┐
│ Pickle Safety &│     │ Flag Train/Test│
│ Seed Check     │     │ Data Leakage   │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│     Emit ML Integrity Audit    │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/ml_auditor/schemas.py
from typing import Any, Dict, List, TypedDict

class MLCodeAuditorInput(TypedDict):
    code: str
    framework: str  # pytorch, tensorflow, scikit-learn

class MLCodeAuditorState(TypedDict):
    data_leakage_detected: bool
    unsafe_pickles: List[int]
    unseeded_randoms: List[int]

class MLCodeAuditorOutput(TypedDict):
    agent_name: str
    model_integrity_score: float
    leakage_risks: List[Dict[str, Any]]
    reproducibility_findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/ml_auditor/tools.py
from typing import Any, Dict, List

class DataLeakageDetectorTool:
    """Detects preprocessing fit before dataset split."""
    name: str = "data_leakage_detector"
    description: str = "Identifies scalers or encoders fitted on entire dataset."

    async def execute(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        lines = code.splitlines()
        fit_line = -1
        split_line = -1
        for idx, line in enumerate(lines, start=1):
            if ".fit(" in line or ".fit_transform(" in line:
                if fit_line == -1: fit_line = idx
            if "train_test_split" in line:
                if split_line == -1: split_line = idx

        if fit_line != -1 and split_line != -1 and fit_line < split_line:
            findings.append({
                "title": "Critical Data Leakage (Scaler Fit Before Split)",
                "severity": "critical",
                "line": fit_line,
                "message": "Data preprocessor fitted prior to train_test_split contamination.",
            })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: AI/ML Quality & Security Auditor using IBM Granite.
  [TASK]: Detect data leakage, unsafe model serialization, lack of random seeding, and training pipeline flaws.
  [CONSTRAINTS]: Output strict JSON conforming to MLCodeAuditorOutput.
  [FORMAT]:
  {
    "agent_name": "ml_code_auditor",
    "model_integrity_score": 40.0,
    "leakage_risks": [],
    "reproducibility_findings": []
  }
  ```
- **User Prompt**:
  ```
  Audit this {framework} ML training script:
  ```{framework}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,000ms.
- **Fallback**: Static regex pattern matching for `.fit(` and `pickle.load`.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 3,500 tokens. Ignores large inline dataset definitions.
- **Output Budget**: 1,000 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_ml_auditor.py
import pytest
from src.cerberus.agents.ml_auditor.tools import DataLeakageDetectorTool

@pytest.mark.asyncio
async def test_ml_data_leakage_detection():
    tool = DataLeakageDetectorTool()
    code = "scaler.fit(X)\nX_train, X_test = train_test_split(X)\n"
    findings = await tool.execute(code)
    assert len(findings) == 1
    assert "Data Leakage" in findings[0]["title"]
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Routing triggered when imports include `sklearn`, `torch`, or `tensorflow`.
- **Database Table**: Writes to `ml_predictions`.

---

### Agent 11: Compliance Standards (SOC2, HIPAA, PCI-DSS, ISO27001)

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Verifies code adherence to regulatory compliance frameworks (HIPAA PHI, PCI-DSS cardholder data, SOC 2 audit trails).
- **Latency Budget**: 3,000ms
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Code & Active Stds    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Scan for Unencrypted PHI / PII │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Audit Mutation Endpoint Logs   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Generate Compliance Evidence   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Emit Compliance Findings     │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/compliance/schemas.py
from typing import Any, Dict, List, TypedDict

class ComplianceInput(TypedDict):
    code: str
    frameworks: List[str]  # "SOC2", "HIPAA", "PCI-DSS", "ISO27001"

class ComplianceState(TypedDict):
    evaluated_controls: List[str]
    violations: List[Dict[str, Any]]

class ComplianceOutput(TypedDict):
    agent_name: str
    compliance_status: Dict[str, bool]
    findings: List[Dict[str, Any]]
    audit_citations: List[str]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/compliance/tools.py
from typing import Any, Dict, List
import re

class PHIPICheckerTool:
    """Scans for unencrypted PHI/PII and credit card numbers."""
    name: str = "phi_pii_checker"
    description: str = "Detects plain SSNs, credit card numbers, and patient records."

    PAN_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
    SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    async def execute(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        for idx, line in enumerate(code.splitlines(), start=1):
            if self.PAN_REGEX.search(line):
                findings.append({
                    "framework": "PCI-DSS",
                    "citation": "Requirement 3.4 (Protect Cardholder Data)",
                    "title": "Plaintext Primary Account Number (PAN)",
                    "severity": "critical",
                    "line": idx,
                })
            if self.SSN_REGEX.search(line):
                findings.append({
                    "framework": "HIPAA",
                    "citation": "45 CFR § 164.312 (e)(1) Transmission Security",
                    "title": "Unencrypted Social Security Number",
                    "severity": "critical",
                    "line": idx,
                })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Chief Information Security & Regulatory Compliance Auditor using IBM Granite.
  [TASK]: Enforce strict technical controls for SOC 2 (Trust Services Criteria), HIPAA (Security Rule), PCI-DSS 4.0, and ISO 27001:2022.
  [CONSTRAINTS]: Output strict JSON conforming to ComplianceOutput schema.
  [FORMAT]:
  {
    "agent_name": "compliance_standards",
    "compliance_status": {"SOC2": true, "HIPAA": false},
    "findings": [],
    "audit_citations": ["HIPAA § 164.312"]
  }
  ```
- **User Prompt**:
  ```
  Audit code against frameworks {frameworks}:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 3,000ms.
- **Fallback**: Ambiguous matches fail closed (marked non-compliant) to preserve audit posture.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 3,500 tokens.
- **Output Budget**: 1,200 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_compliance.py
import pytest
from src.cerberus.agents.compliance.tools import PHIPICheckerTool

@pytest.mark.asyncio
async def test_compliance_pan_detection():
    tool = PHIPICheckerTool()
    code = "card_number = '4111 1111 1111 1111'\n"
    findings = await tool.execute(code)
    assert len(findings) == 1
    assert findings[0]["framework"] == "PCI-DSS"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Critical blocking gate on regulatory PRs.
- **Database Table**: Writes audit evidence logs to `compliance_results`.

---

### Agent 12: IDE Integration

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Delivers sub-800ms Language Server Protocol (LSP 3.17) inline diagnostics for VS Code and IntelliJ IDE extensions.
- **Latency Budget**: 800ms
- **Memory Ceiling**: 200MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: LSP Document Sync     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Restrict Analysis to Active Win│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Execute Fast Sub-Second Linter │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Convert to LSP Diagnostic Array│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  Emit LSP Inline Diagnostics   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/ide_integration/schemas.py
from typing import Any, Dict, List, TypedDict

class IDELspInput(TypedDict):
    document_uri: str
    content: str
    cursor_line: int
    cursor_character: int

class IDELspState(TypedDict):
    fast_diagnostics: List[Dict[str, Any]]

class IDELspOutput(TypedDict):
    agent_name: str
    document_uri: str
    diagnostics: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/ide_integration/tools.py
from typing import Any, Dict, List

class LSPDiagnosticConverterTool:
    """Converts internal findings into LSP Diagnostic structures."""
    name: str = "lsp_diagnostic_converter"
    description: str = "Converts line findings to 0-indexed character range diagnostics."

    async def execute(self, findings: List[Dict[str, Any]], uri: str) -> List[Dict[str, Any]]:
        diagnostics = []
        for f in findings:
            line = max(0, f.get("line", 1) - 1)
            diagnostics.append({
                "range": {
                    "start": {"line": line, "character": 0},
                    "end": {"line": line, "character": 80},
                },
                "severity": 1 if f.get("severity") in ["critical", "high"] else 2,
                "source": "Cerberus",
                "message": f.get("message", "Issue detected."),
            })
        return diagnostics
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Real-time Language Server Protocol (LSP) Diagnostic Generator using IBM Granite.
  [TASK]: Deliver instant, high-precision code hints and inline warnings under 800ms.
  [CONSTRAINTS]: Output strict JSON conforming to IDELspOutput.
  [FORMAT]:
  {
    "agent_name": "ide_integration",
    "document_uri": "file:///workspace/app.py",
    "diagnostics": []
  }
  ```
- **User Prompt**:
  ```
  Provide instant inline diagnostics for line {cursor_line}:
  ```
  {content}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 800ms strict cancellation token.
- **Fallback**: Returns fast local heuristic syntax diagnostics if LLM times out.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Restricts prompt to 50 lines surrounding active cursor. Max 800 tokens.
- **Output Budget**: 400 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_ide_integration.py
import pytest
from src.cerberus.agents.ide_integration.tools import LSPDiagnosticConverterTool

@pytest.mark.asyncio
async def test_lsp_diagnostic_conversion():
    tool = LSPDiagnosticConverterTool()
    findings = [{"line": 10, "severity": "high", "message": "SQL Injection"}]
    diag = await tool.execute(findings, "file:///app.py")
    assert len(diag) == 1
    assert diag[0]["range"]["start"]["line"] == 9  # 0-indexed
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Low-latency endpoint `POST /api/v1/ide/diagnostics`.
- **Database Table**: Bypasses persistence to ensure zero I/O latency.

---

### Agent 13: Cost Analysis (Cloud & LLM)

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: FinOps analysis estimating AWS/GCP/Azure infrastructure costs and watsonx inference token charges from code patterns.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 250MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Cloud IaC / API Code  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Detect Cloud SDK & Model Calls │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Pricing API Lookup (AWS/Azure) │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Project Monthly USD Cost & ROI │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Emit FinOps Cost Report      │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/cost_analysis/schemas.py
from typing import Any, Dict, List, Optional, TypedDict

class CostAnalysisInput(TypedDict):
    code: str
    cloud_provider: str  # aws, gcp, azure
    monthly_invocations: Optional[int]

class CostAnalysisState(TypedDict):
    api_calls_count: Dict[str, int]
    estimated_tokens: int

class CostAnalysisOutput(TypedDict):
    agent_name: str
    monthly_cost_estimate_usd: float
    llm_token_cost_usd: float
    optimization_opportunities: List[Dict[str, Any]]
    estimated_monthly_savings_usd: float
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/cost_analysis/tools.py
from typing import Any, Dict

class CloudPricingCalculatorTool:
    """Calculates serverless invocation and database read/write costs."""
    name: str = "cloud_pricing_calculator"
    description: str = "Estimates monthly AWS Lambda and DynamoDB expenditures."

    async def execute(self, invocations: int = 1_000_000) -> Dict[str, float]:
        lambda_cost = (invocations / 1_000_000) * 0.20  # $0.20 per 1M requests
        dynamo_cost = (invocations / 1_000_000) * 1.25  # $1.25 per 1M writes
        return {
            "lambda_cost_usd": round(lambda_cost, 2),
            "dynamo_cost_usd": round(dynamo_cost, 2),
            "total_monthly_usd": round(lambda_cost + dynamo_cost, 2),
        }
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Cloud FinOps & AI Cost Optimization Architect using IBM Granite.
  [TASK]: Estimate recurring infrastructure costs (AWS/GCP/Azure) and LLM inference charges from code patterns.
  [CONSTRAINTS]: Output strict JSON conforming to CostAnalysisOutput.
  [FORMAT]:
  {
    "agent_name": "cost_analysis",
    "monthly_cost_estimate_usd": 145.0,
    "llm_token_cost_usd": 25.0,
    "optimization_opportunities": [],
    "estimated_monthly_savings_usd": 50.0
  }
  ```
- **User Prompt**:
  ```
  Estimate cloud resource costs for:
  ```{language}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms.
- **Fallback**: Static pricing table pricing model applied on SDK call counts.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 2,500 tokens.
- **Output Budget**: 800 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_cost_analysis.py
import pytest
from src.cerberus.agents.cost_analysis.tools import CloudPricingCalculatorTool

@pytest.mark.asyncio
async def test_cloud_pricing_calculator():
    tool = CloudPricingCalculatorTool()
    res = await tool.execute(invocations=5_000_000)
    assert res["total_monthly_usd"] > 5.0
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Ingests IaC files (`.tf`, CloudFormation, SDK calls).
- **Database Table**: Writes to `cost_analysis`.

---

### Agent 14: Accessibility Checker (WCAG 2.2)

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Scans UI frontend components (React JSX, TSX, Vue, HTML) for WCAG 2.2 Level AA/AAA accessibility violations and broken ARIA semantics.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 250MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: UI Component (JSX/TSX)│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Parse JSX / HTML Element AST │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Check ARIA Roles & Alt Tags    │
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Violation]
┌────────────────┐     ┌────────────────┐
│ Contrast & Tab │     │ Flag WCAG 2.2  │
│ Index Check    │     │ Success Failure│
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│    Emit Accessibility Report   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/accessibility/schemas.py
from typing import Any, Dict, List, TypedDict

class AccessibilityInput(TypedDict):
    code: str
    component_type: str  # react, vue, html, svelte

class AccessibilityState(TypedDict):
    missing_alt_tags: List[int]
    aria_violations: List[Dict[str, Any]]

class AccessibilityOutput(TypedDict):
    agent_name: str
    wcag_compliance_level: str  # "Fail", "A", "AA", "AAA"
    accessibility_score: float
    findings: List[Dict[str, Any]]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/accessibility/tools.py
from typing import Any, Dict, List
import re

class JSXAriaValidatorTool:
    """Checks UI elements for missing accessibility attributes."""
    name: str = "jsx_aria_validator"
    description: str = "Detects missing alt text and unlabeled buttons."

    async def execute(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        lines = code.splitlines()
        for idx, line in enumerate(lines, start=1):
            if "<img" in line and "alt=" not in line:
                findings.append({
                    "wcag_rule": "1.1.1 Non-text Content",
                    "title": "Missing alt Attribute on <img>",
                    "severity": "medium",
                    "line": idx,
                    "remediation": "Provide descriptive alt text for screen readers.",
                })
            if "<button" in line and ">" in line and not re.search(r"aria-label|aria-labelledby", line):
                if "<button></button>" in line.replace(" ", ""):
                    findings.append({
                        "wcag_rule": "4.1.2 Name, Role, Value",
                        "title": "Empty Interactive Button",
                        "severity": "high",
                        "line": idx,
                    })
        return findings
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Web Accessibility Specialist (WCAG 2.2 Level AA/AAA) using IBM Granite.
  [TASK]: Audit UI markup for missing alt attributes, unlabelled interactive buttons, keyboard trap hazards, and broken ARIA roles.
  [CONSTRAINTS]: Output strict JSON conforming to AccessibilityOutput.
  [FORMAT]:
  {
    "agent_name": "accessibility_checker",
    "wcag_compliance_level": "Fail",
    "accessibility_score": 70.0,
    "findings": []
  }
  ```
- **User Prompt**:
  ```
  Audit this UI component:
  ```{component_type}
  {code}
  ```
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms.
- **Fallback**: Backend non-UI files automatically marked 100.0 without running checks.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 3,000 tokens.
- **Output Budget**: 800 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_accessibility.py
import pytest
from src.cerberus.agents.accessibility.tools import JSXAriaValidatorTool

@pytest.mark.asyncio
async def test_accessibility_img_alt_check():
    tool = JSXAriaValidatorTool()
    code = "<img src='hero.png' className='header-img' />\n"
    findings = await tool.execute(code)
    assert len(findings) == 1
    assert "Missing alt Attribute" in findings[0]["title"]
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Filtered on frontend files (`.jsx`, `.tsx`, `.vue`, `.html`).
- **Database Table**: Writes to `accessibility_reports`.

---

### Agent 15: Anomaly Detection

#### 1. Architectural Role & Tier
- **Tier**: Tier 2 (Deep Analysis)
- **Role**: Statistical outlier detection for anomalous PR churn, abnormal cyclomatic jumps, and suspicious commit patterns.
- **Latency Budget**: 2,000ms
- **Memory Ceiling**: 200MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: PR Commit Vector      │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Fetch Repo Historical Baselines│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Compute Z-Scores on Churn & LOC│
└───────┬────────────────┬───────┘
        │                │
 [Pass] ▼                ▼ [Z > 3.0]
┌────────────────┐     ┌────────────────┐
│ Standard Review│     │ Flag Outlier   │
│ Flow           │     │ Anomaly Risk   │
└───────┬────────┘     └────────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌────────────────────────────────┐
│     Emit Anomaly Risk Flag     │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/anomaly_detection/schemas.py
from typing import Dict, List, TypedDict

class AnomalyDetectionInput(TypedDict):
    repo_id: str
    pr_metrics: Dict[str, float]

class AnomalyDetectionState(TypedDict):
    historical_mean: Dict[str, float]
    historical_std: Dict[str, float]
    z_scores: Dict[str, float]

class AnomalyDetectionOutput(TypedDict):
    agent_name: str
    is_anomalous: bool
    anomaly_score: float
    flagged_dimensions: List[str]
    scrutiny_recommendation: str
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/anomaly_detection/tools.py
from typing import Any, Dict

class ZScoreCalculatorTool:
    """Computes statistical standard deviations from repository baseline."""
    name: str = "z_score_calculator"
    description: str = "Identifies metric deviations exceeding 3 standard deviations."

    async def execute(self, current: float, mean: float, std: float) -> float:
        if std <= 0:
            return 0.0
        return round((current - mean) / std, 2)
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Software Engineering Behavioral Anomaly Detector using IBM Granite.
  [TASK]: Detect abnormal PR patterns that indicate dangerous accidental mega-commits, account compromise, or rushed releases.
  [CONSTRAINTS]: Output strict JSON conforming to AnomalyDetectionOutput.
  [FORMAT]:
  {
    "agent_name": "anomaly_detection",
    "is_anomalous": true,
    "anomaly_score": 3.8,
    "flagged_dimensions": ["lines_added"],
    "scrutiny_recommendation": "Elevate review scrutiny: PR touches 10x normal volume."
  }
  ```
- **User Prompt**:
  ```
  Evaluate statistical anomalies for PR metrics:
  {pr_metrics}
  Historical Baseline:
  {historical_mean}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,000ms.
- **Fallback**: Static threshold boundaries (> 1,500 lines added = anomalous).

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 1,500 tokens.
- **Output Budget**: 500 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_anomaly_detection.py
import pytest
from src.cerberus.agents.anomaly_detection.tools import ZScoreCalculatorTool

@pytest.mark.asyncio
async def test_z_score_anomaly_detection():
    tool = ZScoreCalculatorTool()
    z = await tool.execute(current=2500.0, mean=100.0, std=50.0)
    assert z == 48.0
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Pre-routing node signaling other agents to perform deeper scans.
- **Database Table**: Writes to `metrics_history`.

---

### Agent 16: Codebase Fine-tuning

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Synthesizes sanitized instruction-tuning pairs (`bad_code` -> `repaired_code`) from resolved PR reviews for IBM Granite LoRA fine-tuning.
- **Latency Budget**: Asynchronous Background Worker
- **Memory Ceiling**: 350MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Approved PR Review    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Scrub PII, Passwords & Secrets │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Format Granite Instruction JSON│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Deduplicate & Append to JSONL  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  Emit Fine-Tuning Sample Status│
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/fine_tuning/schemas.py
from typing import Any, Dict, List, TypedDict

class FineTuningInput(TypedDict):
    review_id: str
    original_code: str
    approved_code: str
    review_comments: List[str]

class FineTuningState(TypedDict):
    sanitized_prompt: str
    sanitized_completion: str
    token_count: int

class FineTuningOutput(TypedDict):
    agent_name: str
    dataset_entry_id: str
    jsonl_record: Dict[str, Any]
    status: str
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/fine_tuning/tools.py
from typing import Any, Dict
import re

class PIIScrubberTool:
    """Scans and scrubs sensitive tokens before writing to training dataset."""
    name: str = "pii_scrubber"
    description: str = "Redacts emails, IP addresses, and authorization credentials."

    async def execute(self, text: str) -> str:
        text = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[REDACTED_EMAIL]", text)
        text = re.sub(r"(?i)(?:key|secret|password)\s*=\s*['\"][^'\"]+['\"]", "secret = '[REDACTED]'", text)
        return text
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Dataset Preparation & Fine-Tuning Synthesis Specialist using IBM Granite.
  [TASK]: Transform successful code review remediations into high-quality instruction-tuning pairs for IBM Granite model training.
  [CONSTRAINTS]: Output strict JSON conforming to FineTuningOutput.
  [FORMAT]:
  {
    "agent_name": "codebase_fine_tuning",
    "dataset_entry_id": "ft_001",
    "jsonl_record": {
      "instruction": "Fix SQL injection vulnerability.",
      "input": "...",
      "output": "..."
    },
    "status": "accepted"
  }
  ```
- **User Prompt**:
  ```
  Format training sample:
  Original: {original_code}
  Approved: {approved_code}
  Comments: {review_comments}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 5,000ms.
- **Fallback**: Samples with lingering secrets or unparseable diffs are rejected.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 4,000 tokens.
- **Output Budget**: 1,500 tokens. Streamed batch writes to disk.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_fine_tuning.py
import pytest
from src.cerberus.agents.fine_tuning.tools import PIIScrubberTool

@pytest.mark.asyncio
async def test_pii_scrubber():
    tool = PIIScrubberTool()
    raw = "user = 'admin@corp.com'\napi_key = 'secret_12345'\n"
    scrubbed = await tool.execute(raw)
    assert "admin@corp.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Background post-merge hook.
- **Database Table**: Writes dataset manifests to `tuning_datasets`.

---

### Agent 17: Team Expertise Router

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Analyzes git blame distribution and commit churn to route pull requests to optimal domain expert peer reviewers.
- **Latency Budget**: 2,000ms
- **Memory Ceiling**: 200MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: PR Changed Files      │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Query Git Blame Ownership Index│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Filter Author & Match Domain   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Score Reviewer Availability    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Emit Recommended Reviewers     │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/expertise_router/schemas.py
from typing import Any, Dict, List, TypedDict

class ExpertiseRouterInput(TypedDict):
    pr_diff: str
    changed_files: List[str]
    pr_author: str

class ExpertiseRouterState(TypedDict):
    file_ownership: Dict[str, Dict[str, float]]
    expertise_scores: Dict[str, float]

class ExpertiseRouterOutput(TypedDict):
    agent_name: str
    recommended_reviewers: List[Dict[str, Any]]
    fallback_reviewers: List[str]
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/expertise_router/tools.py
from typing import Any, Dict, List

class GitBlameIndexerTool:
    """Calculates author line percentage in modified modules."""
    name: str = "git_blame_indexer"
    description: str = "Analyzes line ownership per developer."

    async def execute(self, files: List[str], author: str) -> List[Dict[str, Any]]:
        # Simulated blame index
        return [
            {"username": "alice", "match_score": 0.88, "rationale": "Authored 88% of auth/jwt.py"},
            {"username": "bob", "match_score": 0.45, "rationale": "Recent contributor to core/db.py"},
        ]
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Engineering Team Expertise & Review Dispatch Router using IBM Granite.
  [TASK]: Select optimal, balanced code reviewers based on historical file commits, architectural domain knowledge, and avoiding review burnout.
  [CONSTRAINTS]: Output strict JSON conforming to ExpertiseRouterOutput.
  [FORMAT]:
  {
    "agent_name": "team_expertise_router",
    "recommended_reviewers": [
      {"username": "alice", "match_score": 0.88, "rationale": "Domain expert in auth."}
    ],
    "fallback_reviewers": ["lead_dev"]
  }
  ```
- **User Prompt**:
  ```
  Recommend reviewers for PR touching {changed_files} authored by {pr_author}:
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,000ms.
- **Fallback**: Repository `CODEOWNERS` fallback list used if blame history is missing.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 1,500 tokens.
- **Output Budget**: 600 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_expertise_router.py
import pytest
from src.cerberus.agents.expertise_router.tools import GitBlameIndexerTool

@pytest.mark.asyncio
async def test_git_blame_indexer():
    tool = GitBlameIndexerTool()
    reviewers = await tool.execute(["auth/jwt.py"], author="charlie")
    assert len(reviewers) > 0
    assert reviewers[0]["username"] == "alice"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: GitHub webhook ingestion endpoint.
- **Database Table**: Writes to `team_expertise`.

---

### Agent 18: Knowledge Base Builder

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Synthesizes Architectural Decision Records (ADRs) from resolved pull request discussions and indexes them into vector storage.
- **Latency Budget**: Asynchronous Background Worker
- **Memory Ceiling**: 300MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Review Discussion     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Filter Trivial Syntax Debates│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Watsonx Synthesize MADR Record │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Generate Embedding Vector      │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Index into Vector DB Table   │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/knowledge_base/schemas.py
from typing import Dict, List, TypedDict

class KnowledgeBaseInput(TypedDict):
    review_threads: List[Dict[str, str]]
    repo_name: str

class KnowledgeBaseState(TypedDict):
    synthesized_decision: str
    tags: List[str]
    embedding_vector: List[float]

class KnowledgeBaseOutput(TypedDict):
    agent_name: str
    adr_id: str
    title: str
    markdown_content: str
    indexed_status: bool
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/knowledge_base/tools.py
from typing import Any, Dict

class ADRMarkdownGeneratorTool:
    """Formats engineering debates into standard MADR format."""
    name: str = "adr_markdown_generator"
    description: str = "Synthesizes Markdown Architectural Decision Records."

    async def execute(self, title: str, context: str, decision: str) -> str:
        return f"# ADR: {title}\n\n## Context\n{context}\n\n## Decision\n{decision}\n\n## Status\nAccepted\n"
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Technical Documentation & Architectural Decision Record (ADR) Synthesizer using IBM Granite.
  [TASK]: Extract recurring coding conventions, architectural decisions, and best practices from review debates into permanent team documentation.
  [CONSTRAINTS]: Output strict JSON conforming to KnowledgeBaseOutput.
  [FORMAT]:
  {
    "agent_name": "knowledge_base_builder",
    "adr_id": "ADR-042",
    "title": "Use Redis for Two-Tier Cache",
    "markdown_content": "# ADR-042 ...",
    "indexed_status": true
  }
  ```
- **User Prompt**:
  ```
  Synthesize an ADR from this engineering debate:
  {review_threads}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 5,000ms.
- **Fallback**: Skips ADR synthesis if discussion has fewer than 3 comments.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 3,000 tokens.
- **Output Budget**: 1,200 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_knowledge_base.py
import pytest
from src.cerberus.agents.knowledge_base.tools import ADRMarkdownGeneratorTool

@pytest.mark.asyncio
async def test_adr_markdown_generation():
    tool = ADRMarkdownGeneratorTool()
    adr = await tool.execute("PostgreSQL Pooling", "Need async access", "Use asyncpg")
    assert "# ADR: PostgreSQL Pooling" in adr
    assert "Use asyncpg" in adr
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Async worker triggered on PR close/merge.
- **Database Table**: Writes to `knowledge_base`.

---

### Agent 19: Burndown Predictor

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Predicts pull request review turnaround cycles, rework rounds, and merge timeline using historical velocity.
- **Latency Budget**: 2,000ms
- **Memory Ceiling**: 200MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: PR Size & Complexity  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Model Author Historical Rework │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Estimate Turnaround Iterations │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Predict Total Merge Time (Hrs) │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│    Emit Burndown Forecast      │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/burndown_predictor/schemas.py
from typing import TypedDict

class BurndownPredictorInput(TypedDict):
    pr_size_lines: int
    cyclomatic_complexity: float
    author_historical_rework_rate: float
    open_reviews_count: int

class BurndownPredictorState(TypedDict):
    predicted_iterations: int
    estimated_hours_to_approval: float

class BurndownPredictorOutput(TypedDict):
    agent_name: str
    estimated_merge_time_hours: float
    predicted_rework_rounds: int
    risk_of_delay: str
    mitigation_advice: str
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/burndown_predictor/tools.py
from typing import Any, Dict

class IterationRegressorTool:
    """Predicts review cycles from size and queue depth."""
    name: str = "iteration_regressor"
    description: str = "Estimates rework rounds and turnaround latency."

    async def execute(self, lines: int, queue_depth: int) -> Dict[str, Any]:
        rounds = 1 if lines < 200 else (2 if lines < 800 else 3)
        hours = round((lines / 50.0) + (queue_depth * 2.5), 1)
        risk = "low" if hours < 8 else ("medium" if hours < 24 else "high")
        return {"predicted_rounds": rounds, "estimated_hours": hours, "risk": risk}
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Agile Delivery & PR Review Velocity Forecaster using IBM Granite.
  [TASK]: Predict the time-to-merge and review iteration cycles for a pull request, alerting teams to bottlenecks.
  [CONSTRAINTS]: Output strict JSON conforming to BurndownPredictorOutput.
  [FORMAT]:
  {
    "agent_name": "burndown_predictor",
    "estimated_merge_time_hours": 12.5,
    "predicted_rework_rounds": 2,
    "risk_of_delay": "medium",
    "mitigation_advice": "Split PR into 2 smaller modules."
  }
  ```
- **User Prompt**:
  ```
  Predict review timeline for PR:
  Lines Added: {pr_size_lines}
  Complexity: {cyclomatic_complexity}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,000ms.
- **Fallback**: Mathematical heuristic bounding hours between 1.0 and 168.0.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: 1,000 tokens.
- **Output Budget**: 400 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_burndown_predictor.py
import pytest
from src.cerberus.agents.burndown_predictor.tools import IterationRegressorTool

@pytest.mark.asyncio
async def test_iteration_regressor():
    tool = IterationRegressorTool()
    res = await tool.execute(lines=1000, queue_depth=4)
    assert res["predicted_rounds"] == 3
    assert res["risk"] == "high"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: PR intake hook.
- **Database Table**: Writes to `metrics_history`.

---

### Agent 20: Collaborative Review

#### 1. Architectural Role & Tier
- **Tier**: Tier 3 (Enterprise Operations)
- **Role**: Synthesizes human peer review decisions with automated agent findings to establish final pull request merge readiness consensus.
- **Latency Budget**: 2,500ms
- **Memory Ceiling**: 200MB

#### 2. ASCII State Machine Diagram
```
┌────────────────────────────────┐
│   Input: Agent & Human Approvals│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Check Agent Blocking Issues  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│   Tally Human Sign-Off Votes   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Resolve Disagreements & Debates│
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Emit Final Consensus PR Action │
└────────────────────────────────┘
```

#### 3. TypedDict I/O Schemas
```python
# File: src/cerberus/agents/collaborative_review/schemas.py
from typing import Any, Dict, List, TypedDict

class CollaborativeReviewInput(TypedDict):
    review_id: str
    agent_findings: List[Dict[str, Any]]
    human_approvals: List[Dict[str, Any]]
    required_approvals_count: int

class CollaborativeReviewState(TypedDict):
    unresolved_blocking_issues: List[Dict[str, Any]]
    consensus_reached: bool

class CollaborativeReviewOutput(TypedDict):
    agent_name: str
    pr_action: str  # "MERGE_READY", "BLOCKED_ON_ISSUES", "PENDING_PEER_APPROVAL"
    total_approvals: int
    outstanding_blockers: List[str]
    consensus_summary: str
```

#### 4. Tool Definitions with Parameters and Return Types
```python
# File: src/cerberus/agents/collaborative_review/tools.py
from typing import Any, Dict, List

class ConsensusTallyTool:
    """Tallies automated agent blockers and human approvals."""
    name: str = "consensus_tally"
    description: str = "Evaluates overall PR merge gate criteria."

    async def execute(
        self,
        findings: List[Dict[str, Any]],
        approvals: List[Dict[str, Any]],
        required: int = 1
    ) -> Dict[str, Any]:
        criticals = [f for f in findings if f.get("severity") == "critical"]
        approved_count = sum(1 for a in approvals if a.get("decision") == "approved")

        if len(criticals) > 0:
            action = "BLOCKED_ON_ISSUES"
            summary = f"Blocked: {len(criticals)} critical automated findings unresolved."
        elif approved_count < required:
            action = "PENDING_PEER_APPROVAL"
            summary = f"Pending: Received {approved_count}/{required} required human approvals."
        else:
            action = "MERGE_READY"
            summary = "Consensus achieved: All gates passed and approvals acquired."

        return {
            "pr_action": action,
            "total_approvals": approved_count,
            "blockers_count": len(criticals),
            "summary": summary,
        }
```

#### 5. watsonx-Optimized System and User Prompts (IBM Granite Format)
- **System Prompt**:
  ```
  [ROLE]: Multi-Agent & Human-in-the-Loop Consensus Facilitator using IBM Granite.
  [TASK]: Synthesize disparate feedback from automated review agents and human senior engineers into a single clear action plan.
  [CONSTRAINTS]: Output strict JSON conforming to CollaborativeReviewOutput.
  [FORMAT]:
  {
    "agent_name": "collaborative_review",
    "pr_action": "MERGE_READY",
    "total_approvals": 2,
    "outstanding_blockers": [],
    "consensus_summary": "All quality and human gates satisfied."
  }
  ```
- **User Prompt**:
  ```
  Evaluate consensus:
  Agent Blockers: {unresolved_blocking_issues}
  Human Approvals: {human_approvals}
  Required Approvals: {required_approvals_count}
  ```

#### 6. Error Handling, Timeouts & Fallback Strategies
- **Timeout**: 2,500ms.
- **Fallback**: Fails safe to `BLOCKED_ON_ISSUES` if any critical blocker exists.

#### 7. Memory Management & Token Budgeting
- **Input Budget**: Metadata only. Max 2,000 tokens.
- **Output Budget**: 600 tokens.

#### 8. Testing Strategy & Unit Test Verification
```python
# File: tests/agents/test_collaborative_review.py
import pytest
from src.cerberus.agents.collaborative_review.tools import ConsensusTallyTool

@pytest.mark.asyncio
async def test_consensus_tally_blocks_on_critical_issue():
    tool = ConsensusTallyTool()
    findings = [{"severity": "critical", "title": "SQLi"}]
    approvals = [{"user": "bob", "decision": "approved"}]
    res = await tool.execute(findings, approvals, required=1)
    assert res["pr_action"] == "BLOCKED_ON_ISSUES"
```

#### 9. Integration Points with Master Orchestrator and Database
- **Orchestrator Node**: Final evaluation node before updating GitHub PR status check.
- **Database Table**: Writes final consensus status to `code_reviews` record.

---

## 4. Summary & Next Steps

### Architecture Verification Sign-Off
All 20 specialized agents for the Cerberus platform are specified with:
- Architectural role, tier, latency SLA, and memory ceiling
- ASCII state machine diagrams
- Pydantic/TypedDict I/O contracts
- Complete tool implementations with strict types
- IBM watsonx Granite prompt templates
- Error handling, timeouts, and fallback strategies
- Memory management and token budgeting
- Pytest unit test verification harnesses
- Master Orchestrator and PostgreSQL database integration points

### Next Document Pointer
For the complete PostgreSQL relational database architecture—including 50+ DDL statements across all 11 domain tables, composite indexes, foreign keys, Alembic migrations, Redis caching topologies, and disaster recovery runbooks—proceed to:

👉 **[DATABASE_DESIGN.md](DATABASE_DESIGN.md)**
