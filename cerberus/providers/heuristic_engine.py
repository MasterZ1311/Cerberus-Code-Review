"""
Heuristic and AST-Driven Static Analysis Engine.
Provides high-precision contextual findings out-of-the-box without requiring live cloud LLM keys.
"""

import ast
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple
from cerberus.models.schemas import Finding, SeverityEnum


class HeuristicEngine:
    """Intelligent rule and AST-based evaluator for code reviews."""

    @staticmethod
    def _is_test_or_fixture_context(filename: Optional[str]) -> bool:
        """Determines if the analyzed code is located within a test, fixture, or mock directory."""
        if not filename:
            return False
        normalized = filename.lower().replace("\\", "/")
        test_indicators = (
            "/tests/", "/test/", "/fixtures/", "/mocks/", "/conftest.py",
            "test_", "_test.py", "_spec.py", "/samples/", "/examples/"
        )
        return any(ind in normalized for ind in test_indicators)

    _ast_cache: dict = {}

    @classmethod
    def get_parsed_ast(cls, code: Optional[str]) -> Optional[ast.AST]:
        """Returns cached parsed AST for the provided source code, avoiding redundant parsing passes."""
        if not code or not isinstance(code, (str, bytes)):
            return None
        if len(cls._ast_cache) > 256:
            cls._ast_cache.clear()
        key = hash(code)
        if key in cls._ast_cache:
            return cls._ast_cache[key]
        try:
            tree = ast.parse(code)
            cls._ast_cache[key] = tree
            return tree
        except Exception:
            cls._ast_cache[key] = None
            return None

    @staticmethod
    def _is_comment_or_docstring_line(line: str, docstring_ranges: Set[int], lineno: int) -> bool:
        """Checks if a given line is a comment or inside a docstring block."""
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "<!--")):
            return True
        return lineno in docstring_ranges

    @staticmethod
    def _extract_docstring_lines(code: str) -> Set[int]:
        """Extracts all line numbers belonging to AST docstring literals in Python."""
        docstring_lines: Set[int] = set()
        try:
            tree = HeuristicEngine.get_parsed_ast(code)
            if tree is None:
                return docstring_lines
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        start = getattr(node.body[0], "lineno", None)
                        end = getattr(node.body[0], "end_lineno", start)
                        if start is not None and end is not None:
                            for l in range(start, end + 1):
                                docstring_lines.add(l)
        except Exception:
            pass
        return docstring_lines

    # -------------------------------------------------------------
    # SECURITY FINDINGS
    # -------------------------------------------------------------
    @staticmethod
    def analyze_security(
        code: str,
        language: str = "python",
        filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")
        doc_lines = HeuristicEngine._extract_docstring_lines(code) if language.lower() == "python" else set()
        is_test = HeuristicEngine._is_test_or_fixture_context(filename)

        # 1. SQL Injection Detection
        sql_patterns = [
            (r"""(["'].*SELECT\s+.*FROM\s+.*WHERE\s+.*['"]\s*\+\s*\w+)""", "SQL injection via string concatenation"),
            (r"""f["'].*SELECT\s+.*FROM\s+.*WHERE\s+.*\{.*\}""", "SQL injection via f-string interpolation"),
            (r"""execute\s*\(\s*["'].*SELECT.*WHERE.*%s.*["']\s*%\s*\w+\)""", "SQL injection via string formatting %"),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            for pat, desc in sql_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append(Finding(
                        id=f"SEC-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection Vulnerability",
                        message=f"{desc}. User input is concatenated directly into SQL query.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Untrusted user input injected into dynamic queries allows attackers to bypass authentication or extract sensitive database contents.",
                        recommendation="Use parameterized queries with placeholders (e.g., db.execute('SELECT * FROM users WHERE id = ?', (user_id,)))",
                        suggestion="db.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                        exploitability=0.95
                    ))

        # 2. Hardcoded Credentials & API Keys
        placeholder_indicators = (
            "your_key", "your-key", "your_api_key", "your-token", "<your", "${",
            "dummy", "placeholder", "fake_", "sample_key", "changeme", "0000000",
            "xxxxxx", "sk-your", "sk-placeholder", "insert_key_here"
        )
        cred_patterns = [
            (r"""(?:api[_-]?key|secret|token|password|auth_token)\s*=\s*["'][A-Za-z0-9_\-]{8,}["']""", "Hardcoded API Key or Secret"),
            (r"""sk-[a-zA-Z0-9]{20,}""", "Exposed OpenAI / Service Secret Key"),
            (r"""password\s*=\s*["']admin(?:123)?["']""", "Default / Weak Hardcoded Password"),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue

            line_lower = line.lower()
            if any(ph in line_lower for ph in placeholder_indicators):
                continue
            if is_test and "sk-live-" not in line:
                continue

            for pat, desc in cred_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append(Finding(
                        id=f"SEC-CRED-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="secrets",
                        title="Hardcoded Credentials Detected",
                        message=f"{desc} identified in source code.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Committing secrets directly into version control leads to immediate credential leakage and system compromise.",
                        recommendation="Load secrets from environment variables or a secure key management vault.",
                        suggestion="API_KEY = os.getenv('API_KEY')",
                        cwe_id="CWE-798",
                        cvss_score=8.9,
                        exploitability=0.85
                    ))
                    break

        # 3. Command Injection
        cmd_patterns = [
            (r"""os\.system\s*\(""", "os.system executes shell command without sanitization"),
            (r"""subprocess\.(?:Popen|call|run)\s*\(.*shell\s*=\s*True""", "Subprocess executed with shell=True"),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            for pat, desc in cmd_patterns:
                if re.search(pat, line):
                    findings.append(Finding(
                        id=f"SEC-CMD-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="injection",
                        title="Command Injection Vulnerability",
                        message=desc,
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Passing raw strings to shell execution functions enables remote attackers to execute arbitrary system binaries.",
                        recommendation="Use subprocess.run with argument lists and shell=False.",
                        suggestion='subprocess.run(["ping", "-c", "1", host], check=True)',
                        cwe_id="CWE-78",
                        cvss_score=8.4,
                        exploitability=0.80
                    ))

        # 4. Weak Cryptography & Insecure Hashes
        crypto_patterns = [
            (r"""hashlib\.md5\s*\(""", "Use of MD5 cryptographic hash function"),
            (r"""hashlib\.sha1\s*\(""", "Use of SHA1 cryptographic hash function"),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            for pat, desc in crypto_patterns:
                if re.search(pat, line):
                    findings.append(Finding(
                        id=f"SEC-CRYPTO-{idx}",
                        severity=SeverityEnum.MEDIUM,
                        category="cryptography",
                        title="Weak Hash Algorithm (Collision Vulnerable)",
                        message=f"{desc} detected.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="MD5 and SHA-1 have known collision attacks and are broken for digital signatures and secure hashing.",
                        recommendation="Use SHA-256 for integrity or bcrypt/argon2 for password hashing.",
                        suggestion="hashlib.sha256(data.encode()).hexdigest()",
                        cwe_id="CWE-328",
                        cvss_score=5.3
                    ))

        # 5. Insecure Deserialization
        if "pickle.loads" in code or "yaml.load(" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if "pickle.loads" in line or "yaml.load(" in line:
                    findings.append(Finding(
                        id=f"SEC-DESER-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="deserialization",
                        title="Insecure Object Deserialization",
                        message="Deserializing untrusted data with pickle or unsafe yaml can trigger remote code execution.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Python's pickle module is not secure against erroneous or maliciously constructed data.",
                        recommendation="Use safe serialization formats like JSON or yaml.safe_load.",
                        suggestion="data = json.loads(payload)",
                        cwe_id="CWE-502",
                        cvss_score=8.1
                    ))

        # 6. Code Injection via eval() or exec()
        if "eval(" in code or "exec(" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if re.search(r"""\beval\s*\(.+\)""", line) or re.search(r"""\bexec\s*\(.+\)""", line):
                    findings.append(Finding(
                        id=f"SEC-CODEINJ-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="Code Injection Vulnerability (eval/exec)",
                        message="Dynamic evaluation of raw strings via eval() or exec() allows arbitrary code execution.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Passing untrusted input to eval/exec allows attackers to execute arbitrary system code.",
                        recommendation="Use safe literal parsing (ast.literal_eval) or domain-specific parsers.",
                        suggestion="import ast\nvalue = ast.literal_eval(payload)",
                        cwe_id="CWE-94",
                        cvss_score=9.8,
                        exploitability=0.95
                    ))
                    break

        # 7. Insecure SSL/TLS Verification Disabled
        if "verify=False" in code or "verify = False" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if re.search(r"""verify\s*=\s*False\b""", line):
                    findings.append(Finding(
                        id=f"SEC-TLS-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="transport_security",
                        title="Disabled TLS/SSL Certificate Verification",
                        message="verify=False disables SSL/TLS validation, enabling man-in-the-middle attacks.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Disabling certificate checks allows attackers to intercept and alter secure communications.",
                        recommendation="Enable certificate verification (verify=True or provide path to custom CA bundle).",
                        suggestion="response = requests.get(url, verify=True)",
                        cwe_id="CWE-295",
                        cvss_score=7.4,
                        exploitability=0.70
                    ))
                    break

        # 8. Insecure PRNG for Cryptographic Tokens
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""(?:token|key|secret|password|nonce)\s*=\s*.*random\.(?:random|choice|randint|choices)\(""", line, re.IGNORECASE):
                findings.append(Finding(
                    id=f"SEC-PRNG-{idx}",
                    severity=SeverityEnum.MEDIUM,
                    category="cryptography",
                    title="Insecure PRNG for Security Token Generation",
                    message="Standard 'random' module is pseudo-random and predictable for security contexts.",
                    line=idx,
                    code_snippet=line.strip(),
                    explanation="The standard library random module is not cryptographically secure and tokens can be predicted.",
                    recommendation="Use the secrets module for generating authentication tokens and passwords.",
                    suggestion="token = secrets.token_hex(24)",
                    cwe_id="CWE-330",
                    cvss_score=6.5
                ))
                break

        # Calculate security score (100 minus deductions)
        score = 100.0
        for f in findings:
            if f.severity == SeverityEnum.CRITICAL:
                score -= 30.0
            elif f.severity == SeverityEnum.HIGH:
                score -= 20.0
            elif f.severity == SeverityEnum.MEDIUM:
                score -= 10.0
            else:
                score -= 5.0
        return findings, max(0.0, score)

    # -------------------------------------------------------------
    # PERFORMANCE FINDINGS
    # -------------------------------------------------------------
    @staticmethod
    def analyze_performance(
        code: str,
        language: str = "python",
        filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")
        doc_lines = HeuristicEngine._extract_docstring_lines(code) if language.lower() == "python" else set()

        # 1. AST Analysis for Nested Loops (O(n²) Complexity)
        try:
            tree = HeuristicEngine.get_parsed_ast(code) if language.lower() == "python" else None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.For, ast.While)):
                        for inner in ast.walk(node):
                            if inner is not node and isinstance(inner, (ast.For, ast.While)):
                                line_no = getattr(node, "lineno", 1)
                                findings.append(Finding(
                                    id=f"PERF-NESTED-{line_no}",
                                    severity=SeverityEnum.MEDIUM,
                                    category="algorithmic_complexity",
                                    title="Quadratic Time Complexity O(n²)",
                                    message="Nested loop detected. Execution time will grow quadratically with input size.",
                                    line=line_no,
                                    code_snippet=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                                    explanation="Nested iterations over collections lead to high CPU latency as datasets grow to thousands of items.",
                                    recommendation="Consider using hash maps, sets, or list comprehensions to reduce complexity to O(n) or O(n log n).",
                                    suggestion="# Build a lookup dictionary beforehand for O(1) lookups:\nlookup = {item.id: item for item in items}",
                                ))
                                break
        except Exception:
            pass

        # 2. Inefficient string concatenation in loops
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""\b\w+\s*\+=\s*["'].*["']""", line) or re.search(r"""\b\w+\s*=\s*\w+\s*\+\s*str\(.+""", line):
                findings.append(Finding(
                    id=f"PERF-STRCAT-{idx}",
                    severity=SeverityEnum.LOW,
                    category="memory_efficiency",
                    title="Repeated In-Place String Concatenation",
                    message="String concatenation in loops creates intermediate immutable string copies.",
                    line=idx,
                    code_snippet=line.strip(),
                    explanation="Strings are immutable in Python; repeated concatenation generates O(n²) allocations.",
                    recommendation="Accumulate items in a list and call ''.join(items).",
                    suggestion="''.join(chunk_list)",
                ))

        # 3. Database query inside loop (N+1 Query Pattern)
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""(?:db|session|cursor|repository|User|Product)\.(?:execute|query|find|get)\(""", line):
                for prev in range(max(0, idx - 5), idx):
                    if "for " in lines[prev] or "while " in lines[prev]:
                        findings.append(Finding(
                            id=f"PERF-NPLUS1-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="database",
                            title="N+1 Query Pattern Detected",
                            message="Database operation detected inside iterative loop.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Executing queries inside loops leads to high roundtrip network latency and database connection saturation.",
                            recommendation="Batch fetch records using SQL IN clauses or join queries before the loop.",
                            suggestion="items = db.query(Item).filter(Item.id.in_(ids)).all()",
                        ))
                        break

        # Calculate performance score
        score = 100.0
        for f in findings:
            if f.severity == SeverityEnum.HIGH:
                score -= 25.0
            elif f.severity == SeverityEnum.MEDIUM:
                score -= 15.0
            else:
                score -= 5.0
        return findings, max(0.0, score)

    # -------------------------------------------------------------
    # CODE QUALITY FINDINGS
    # -------------------------------------------------------------
    @staticmethod
    def analyze_quality(
        code: str,
        language: str = "python",
        filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")
        doc_lines = HeuristicEngine._extract_docstring_lines(code) if language.lower() == "python" else set()

        # 1. Missing Docstrings on Functions & Classes
        try:
            tree = HeuristicEngine.get_parsed_ast(code) if language.lower() == "python" else None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        docstring = ast.get_docstring(node)
                        if not docstring and not node.name.startswith("_"):
                            line_no = node.lineno
                            findings.append(Finding(
                                id=f"QUAL-DOC-{line_no}",
                                severity=SeverityEnum.INFO,
                                category="documentation",
                                title=f"Missing Docstring on '{node.name}'",
                                message=f"Public function/class '{node.name}' lacks documentation docstring.",
                                line=line_no,
                                code_snippet=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                                explanation="Clear docstrings communicate expected arguments, return types, and side effects to other engineers.",
                                recommendation="Add a descriptive triple-quoted docstring explaining the component.",
                                suggestion=f'def {node.name}():\n    """Brief description of {node.name}."""\n    pass',
                            ))

                    # 2. Long Functions (> 40 lines)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end_lineno = getattr(node, "end_lineno", node.lineno)
                        if (end_lineno - node.lineno) > 40:
                            findings.append(Finding(
                                id=f"QUAL-LEN-{node.lineno}",
                                severity=SeverityEnum.LOW,
                                category="maintainability",
                                title=f"Function '{node.name}' is Excessively Long ({end_lineno - node.lineno} lines)",
                                message="Long functions reduce readability and testability.",
                                line=node.lineno,
                                code_snippet=lines[node.lineno - 1].strip(),
                                explanation="Large functions often violate the Single Responsibility Principle and are harder to unit test.",
                                recommendation="Refactor into smaller, focused helper methods.",
                            ))
        except Exception:
            pass

        # 3. Bare Except Clauses
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""^\s*except\s*:""", line):
                findings.append(Finding(
                    id=f"QUAL-EXCEPT-{idx}",
                    severity=SeverityEnum.MEDIUM,
                    category="error_handling",
                    title="Bare 'except:' Clause",
                    message="Catching all exceptions without specifying exception type hides critical errors.",
                    line=idx,
                    code_snippet=line.strip(),
                    explanation="Bare exceptions inadvertently suppress KeyboardInterrupt, SystemExit, and memory errors.",
                    recommendation="Catch specific exceptions such as except ValueError: or at least except Exception:.",
                    suggestion="except Exception as e:",
                ))

        # 4. Wildcard Imports
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""^\s*from\s+[\w\.]+\s+import\s+\*""", line):
                findings.append(Finding(
                    id=f"QUAL-IMPORT-{idx}",
                    severity=SeverityEnum.LOW,
                    category="style",
                    title="Wildcard Import Detected (from module import *)",
                    message="Wildcard imports pollute the local namespace and obscure symbol origins.",
                    line=idx,
                    code_snippet=line.strip(),
                    explanation="Explicit imports prevent unintended variable shadowing and make static linters faster.",
                    recommendation="Import explicitly required symbols or the module name.",
                ))

        # Calculate quality score
        score = 100.0
        for f in findings:
            if f.severity == SeverityEnum.MEDIUM:
                score -= 15.0
            elif f.severity == SeverityEnum.LOW:
                score -= 8.0
            else:
                score -= 3.0
        return findings, max(0.0, score)

    # -------------------------------------------------------------
    # ARCHITECTURE FINDINGS
    # -------------------------------------------------------------
    @staticmethod
    def analyze_architecture(
        code: str,
        language: str = "python",
        filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Deep Relative Parent Import Detection
        for idx, line in enumerate(lines, 1):
            if "import " in line and "from .." in line:
                findings.append(Finding(
                    id=f"ARCH-COUPLE-{idx}",
                    severity=SeverityEnum.LOW,
                    category="architecture",
                    title="Deep Relative Parent Import",
                    message="Importing from deep parent packages indicates potential architectural coupling.",
                    line=idx,
                    code_snippet=line.strip(),
                    explanation="Deep relative imports make components difficult to extract into separate packages or microservices.",
                    recommendation="Use absolute package imports or inversion of control.",
                ))

        # 2. Advanced AST-Driven Structural & Coupling Analysis
        if language.lower() == "python":
            try:
                tree = HeuristicEngine.get_parsed_ast(code)
                if tree is not None:
                    imported_modules: Set[str] = set()
                    current_module = Path(filename).stem.lower() if filename else None

                    for node in ast.walk(tree):
                        # Track imported module names for Fan-Out and Circular Self-Import
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                base_mod = alias.name.split(".")[0]
                                imported_modules.add(base_mod)
                                if current_module and alias.name.lower() == current_module:
                                    findings.append(Finding(
                                        id=f"ARCH-CYCLIC-{node.lineno}",
                                        severity=SeverityEnum.HIGH,
                                        category="dependency",
                                        title=f"Circular Self-Import Detected: '{alias.name}'",
                                        message=f"Module appears to import itself ('{alias.name}'), risking circular import recursion.",
                                        line=node.lineno,
                                        code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                        explanation="Circular imports trigger ImportError during module loading and indicate tightly tangled dependencies.",
                                        recommendation="Refactor common symbols into a shared leaf module or use dependency injection.",
                                    ))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                base_mod = node.module.split(".")[0]
                                imported_modules.add(base_mod)
                                if current_module and node.module.lower() == current_module:
                                    findings.append(Finding(
                                        id=f"ARCH-CYCLIC-{node.lineno}",
                                        severity=SeverityEnum.HIGH,
                                        category="dependency",
                                        title=f"Circular Self-Import Detected: '{node.module}'",
                                        message=f"Module appears to import from itself ('{node.module}'), risking circular import recursion.",
                                        line=node.lineno,
                                        code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                        explanation="Circular imports trigger module resolution cycles and runtime deadlocks.",
                                        recommendation="Extract shared abstractions into an independent interface or helper module.",
                                    ))

                        # God Object / Monolithic Class Detection
                        if isinstance(node, ast.ClassDef):
                            method_count = sum(1 for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
                            class_lines = (getattr(node, "end_lineno", node.lineno) - node.lineno) + 1
                            if method_count > 15 or class_lines > 250:
                                findings.append(Finding(
                                    id=f"ARCH-GOD-CLASS-{node.lineno}",
                                    severity=SeverityEnum.MEDIUM,
                                    category="modularity",
                                    title=f"God Object Anti-Pattern in Class '{node.name}'",
                                    message=f"Class '{node.name}' defines {method_count} methods across {class_lines} lines, indicating low cohesion.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="God Classes aggregate too many responsibilities, violating Single Responsibility Principle (SRP).",
                                    recommendation="Decompose class into cohesive sub-components, services, or strategy delegates.",
                                ))

                        # Tramp Data / Excessive Function Parameters
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            total_args = len(node.args.args) + len(node.args.kwonlyargs)
                            if node.args.args and node.args.args[0].arg in ("self", "cls"):
                                total_args -= 1
                            if total_args >= 7:
                                findings.append(Finding(
                                    id=f"ARCH-TRAMP-{node.lineno}",
                                    severity=SeverityEnum.LOW,
                                    category="architecture",
                                    title=f"Excessive Function Parameters ({total_args} params) in '{node.name}'",
                                    message=f"Function '{node.name}' takes {total_args} arguments, suggesting parameter grouping or a config object is needed.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                    explanation="Functions with numerous parameters increase cognitive load and indicate improper abstraction boundaries.",
                                    recommendation="Encapsulate parameters into a typed dataclass, Pydantic model, or parameter object.",
                                ))

                    # Excessive External Fan-Out (High Coupling)
                    std_libs = {
                        "sys", "os", "re", "math", "time", "typing", "collections", "datetime",
                        "pathlib", "json", "logging", "asyncio", "hashlib", "secrets", "uuid", "abc", "io"
                    }
                    external_deps = {m for m in imported_modules if m not in std_libs}
                    if len(external_deps) > 12:
                        findings.append(Finding(
                            id="ARCH-COUPLING-FANOUT",
                            severity=SeverityEnum.MEDIUM,
                            category="coupling",
                            title=f"High Coupling / Excessive Fan-Out ({len(external_deps)} external dependencies)",
                            message=f"Module exhibits high fan-out coupling by directly importing {len(external_deps)} distinct external packages.",
                            line=1,
                            code_snippet=lines[0].strip() if lines else "",
                            explanation="Modules with excessive outgoing dependencies are fragile and sensitive to changes in any dependent library.",
                            recommendation="Introduce facade or adapter layers to consolidate external subsystem integrations.",
                        ))

            except Exception:
                pass

        # Calculate architectural modularity score
        score = 100.0
        for f in findings:
            if f.severity == SeverityEnum.CRITICAL:
                score -= 30.0
            elif f.severity == SeverityEnum.HIGH:
                score -= 20.0
            elif f.severity == SeverityEnum.MEDIUM:
                score -= 10.0
            else:
                score -= 5.0
        return findings, max(0.0, score)

    # -------------------------------------------------------------
    # COMPLIANCE FINDINGS (HIPAA / GDPR / SOC 2 / PCI-DSS)
    # -------------------------------------------------------------
    @staticmethod
    def analyze_compliance(
        code: str,
        language: str = "python",
        filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")
        doc_lines = HeuristicEngine._extract_docstring_lines(code) if language.lower() == "python" else set()
        is_test = HeuristicEngine._is_test_or_fixture_context(filename)

        pii_patterns = [
            (r"""\b(?:ssn|social_security|credit_card|card_number|cvv|dob|date_of_birth)\b""", "PII / PCI-DSS Sensitive Data Exposure"),
            (r"""(?:logger|logging)\.(?:debug|info|warning|warn|error|critical)\s*\(.*(?:password|token|secret|ssn)""", "Sensitive Data Emitted in Logs (HIPAA / SOC 2 violation)"),
            (r"""print\s*\(.*(?:password|token|secret|ssn)""", "Sensitive Data Emitted via print() (HIPAA / SOC 2 violation)"),
        ]

        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if is_test and "test" in line.lower() and not any(p in line.lower() for p in ("ssn", "password", "token")):
                continue

            for pat, desc in pii_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append(Finding(
                        id=f"COMP-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="compliance",
                        title=desc,
                        message="Potential regulatory compliance violation regarding personal or cardholder data.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="HIPAA, GDPR, and PCI-DSS require that unencrypted identifiers and credentials are never stored or logged in plain text.",
                        recommendation="Mask or redact sensitive fields before processing or logging.",
                        suggestion="# Sanitize sensitive fields:\nlogger.info(f'User login: {sanitize_user(user)}')",
                    ))

        score = 100.0 - (len(findings) * 20.0)
        return findings, max(0.0, score)
