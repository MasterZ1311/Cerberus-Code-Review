"""
Heuristic and AST-Driven Static Analysis Engine.
Provides high-precision contextual findings out-of-the-box without requiring live cloud LLM keys.
"""

import ast
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
            "/tests/",
            "/test/",
            "/fixtures/",
            "/mocks/",
            "/conftest.py",
            "test_",
            "_test.py",
            "_spec.py",
            "/samples/",
            "/examples/",
        )
        return any(ind in normalized for ind in test_indicators)

    _ast_cache: dict = {}
    _custom_rules: dict = {}

    @classmethod
    def register_custom_rules(cls, language: str, rules: List[dict]) -> None:
        """Registers custom analysis rules for a specific language."""
        lang = language.lower()
        if lang not in cls._custom_rules:
            cls._custom_rules[lang] = []
        cls._custom_rules[lang].extend(rules)

    @classmethod
    def clear_custom_rules(cls, language: Optional[str] = None) -> None:
        """Clears custom rules for one or all languages."""
        if language:
            cls._custom_rules.pop(language.lower(), None)
        else:
            cls._custom_rules.clear()

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
    def _safe_scan_line(line: str, max_chars: int = 10000) -> str:
        """Mitigates ReDoS by bounding line evaluation width for regular expressions."""
        return line[:max_chars] if line else ""

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
                    if node.body:
                        first_stmt = node.body[0]
                        if isinstance(first_stmt, ast.Expr):
                            expr_val = getattr(first_stmt, "value", None)
                            if isinstance(expr_val, ast.Constant) and isinstance(expr_val.value, str):
                                start = getattr(first_stmt, "lineno", None)
                                end = getattr(first_stmt, "end_lineno", start)
                                if start is not None and end is not None:
                                    for line_idx in range(start, end + 1):
                                        docstring_lines.add(line_idx)
        except Exception:
            pass
        return docstring_lines

    # -------------------------------------------------------------
    # SECURITY FINDINGS
    # -------------------------------------------------------------
    @staticmethod
    def analyze_security(
        code: str, language: str = "python", filename: Optional[str] = None
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
                    findings.append(
                        Finding(
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
                            exploitability=0.95,
                        )
                    )

        # 2. Hardcoded Credentials & API Keys
        placeholder_indicators = (
            "your_key",
            "your-key",
            "your_api_key",
            "your-token",
            "<your",
            "${",
            "dummy",
            "placeholder",
            "fake_",
            "sample_key",
            "changeme",
            "0000000",
            "xxxxxx",
            "sk-your",
            "sk-placeholder",
            "insert_key_here",
        )
        cred_patterns = [
            (
                r"""(?:api[_-]?key|secret|token|password|auth_token)\s*=\s*["'][A-Za-z0-9_\-]{8,}["']""",
                "Hardcoded API Key or Secret",
            ),
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
                    findings.append(
                        Finding(
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
                            exploitability=0.85,
                        )
                    )
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
                    findings.append(
                        Finding(
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
                            exploitability=0.80,
                        )
                    )

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
                    findings.append(
                        Finding(
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
                            cvss_score=5.3,
                        )
                    )

        # 5. Insecure Deserialization
        if "pickle.loads" in code or "yaml.load(" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if "pickle.loads" in line or "yaml.load(" in line:
                    findings.append(
                        Finding(
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
                            cvss_score=8.1,
                        )
                    )

        # 6. Code Injection via eval() or exec()
        if "eval(" in code or "exec(" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if re.search(r"""\beval\s*\(.+\)""", line) or re.search(r"""\bexec\s*\(.+\)""", line):
                    findings.append(
                        Finding(
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
                            exploitability=0.95,
                        )
                    )
                    break

        # 7. Insecure SSL/TLS Verification Disabled
        if "verify=False" in code or "verify = False" in code:
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                if re.search(r"""verify\s*=\s*False\b""", line):
                    findings.append(
                        Finding(
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
                            exploitability=0.70,
                        )
                    )
                    break

        # 8. Insecure PRNG for Cryptographic Tokens
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(
                r"""(?:token|key|secret|password|nonce)\s*=\s*.*random\.(?:random|choice|randint|choices)\(""",
                line,
                re.IGNORECASE,
            ):
                findings.append(
                    Finding(
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
                        cvss_score=6.5,
                    )
                )
                break

        # 9. Server-Side Request Forgery (SSRF - CWE-918)
        ssrf_patterns = [
            (
                r"""(?:requests|httpx)\.(?:get|post|put|delete|head)\s*\(\s*(?:url|user_url|target|dest|endpoint|req_url|request\.)""",
                "HTTP client request to unvalidated dynamic URL",
            ),
            (
                r"""urllib\.request\.urlopen\s*\(\s*(?:url|user_url|target|endpoint|request\.)""",
                "urllib.request.urlopen with unvalidated destination URL",
            ),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            for pat, desc in ssrf_patterns:
                if re.search(pat, line):
                    findings.append(
                        Finding(
                            id=f"SEC-SSRF-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="ssrf",
                            title="Server-Side Request Forgery (SSRF)",
                            message=f"{desc}. Unchecked outbound network requests can access internal services and cloud metadata.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Untrusted URLs passed to HTTP clients can allow attackers to probe localhost, 127.0.0.1, or cloud metadata endpoints (169.254.169.254).",
                            recommendation="Validate URL schema (whitelist http/https), resolve DNS, and block loopback/private/link-local IP addresses.",
                            suggestion="# Validate URL against allowlist:\nif is_allowed_domain(target_url):\n    resp = requests.get(target_url)",
                            cwe_id="CWE-918",
                            cvss_score=8.6,
                            exploitability=0.85,
                        )
                    )
                    break

        # 10. Path Traversal & Unrestricted File Access (CWE-22)
        traversal_patterns = [
            (
                r"""open\s*\(\s*(?:user_path|file_path|filename|path|user_input|request\.)""",
                "File open with untrusted path",
            ),
            (
                r"""os\.path\.join\s*\([^,]+,\s*(?:user_path|file_path|filename|path|request\.)""",
                "Path join with unvalidated user input",
            ),
        ]
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            for pat, desc in traversal_patterns:
                if re.search(pat, line):
                    findings.append(
                        Finding(
                            id=f"SEC-TRAV-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="path_traversal",
                            title="Path Traversal / Arbitrary File Access",
                            message=f"{desc}. Path manipulation can allow reading or writing outside intended directories.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Without path boundary validation, attackers can use '../' sequences or absolute paths to escape storage sandboxes.",
                            recommendation="Canonicalize paths with os.path.realpath/resolve() and verify the result starts with the safe base directory.",
                            suggestion="safe_path = Path(base_dir).resolve() / filename\nif not safe_path.resolve().is_relative_to(base_dir):\n    raise ValueError('Path traversal detected')",
                            cwe_id="CWE-22",
                            cvss_score=8.2,
                            exploitability=0.80,
                        )
                    )
                    break

        # 11. Multi-Language: JavaScript / TypeScript Security Findings
        js_langs = ("javascript", "js", "typescript", "ts", "tsx", "jsx")
        if language.lower() in js_langs or (
            filename and any(filename.endswith(ext) for ext in (".js", ".ts", ".tsx", ".jsx"))
        ):
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                # DOM XSS
                if (
                    re.search(r"""(?:innerHTML|outerHTML)\s*=""", line)
                    or "document.write(" in line
                    or "dangerouslySetInnerHTML" in line
                ):
                    findings.append(
                        Finding(
                            id=f"SEC-XSS-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="xss",
                            title="DOM-based Cross-Site Scripting (XSS)",
                            message="Direct HTML assignment or document.write introduces DOM-based XSS vulnerabilities.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Assigning untrusted data directly to innerHTML bypasses HTML escaping, executing attacker scripts.",
                            recommendation="Use textContent or a sanitizer like DOMPurify before inserting HTML.",
                            suggestion="element.textContent = sanitize(userInput);",
                            cwe_id="CWE-79",
                            cvss_score=8.3,
                            exploitability=0.85,
                        )
                    )
                # Command execution in Node.js
                if re.search(r"""child_process\.(?:exec|execSync)\s*\(""", line):
                    findings.append(
                        Finding(
                            id=f"SEC-NODE-CMD-{idx}",
                            severity=SeverityEnum.CRITICAL,
                            category="injection",
                            title="Node.js Command Injection",
                            message="child_process.exec invokes system shell without argument escaping.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Passing concatenated commands to exec allows shell metacharacters to execute arbitrary binaries.",
                            recommendation="Use child_process.execFile or spawn with argument arrays.",
                            suggestion="execFile('node', [scriptPath], callback);",
                            cwe_id="CWE-78",
                            cvss_score=9.5,
                            exploitability=0.90,
                        )
                    )
                # Prototype Pollution
                if "__proto__" in line or "constructor.prototype" in line:
                    findings.append(
                        Finding(
                            id=f"SEC-PROTO-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="prototype_pollution",
                            title="Prototype Pollution Vulnerability",
                            message="Direct property manipulation on __proto__ can pollute global Object prototypes.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Polluting Object.prototype alters properties across all JavaScript objects, often causing RCE or DoS.",
                            recommendation="Use Object.create(null) for maps or freeze Object.prototype.",
                            suggestion="const safeMap = Object.create(null);",
                            cwe_id="CWE-1321",
                            cvss_score=8.5,
                            exploitability=0.75,
                        )
                    )

        # 12. Multi-Language: Go Findings
        go_langs = ("go", "golang")
        if language.lower() in go_langs or (filename and filename.endswith(".go")):
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                # SQL Injection via fmt.Sprintf or concatenation
                if re.search(r"""db\.(?:Query|QueryRow|Exec)\s*\(\s*fmt\.Sprintf\(""", line) or re.search(
                    r"""db\.(?:Query|QueryRow|Exec)\s*\(\s*["'].*["']\s*\+""", line
                ):
                    findings.append(
                        Finding(
                            id=f"SEC-GO-SQLI-{idx}",
                            severity=SeverityEnum.CRITICAL,
                            category="injection",
                            title="Go SQL Injection via String Formatting",
                            message="Dynamic SQL query composed via fmt.Sprintf or string concatenation in Go.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Formatting raw user parameters into SQL statements enables database injection attacks.",
                            recommendation="Use parameterized queries with database driver placeholders ($1, ?, etc.).",
                            suggestion='db.QueryContext(ctx, "SELECT * FROM users WHERE id = $1", userID)',
                            cwe_id="CWE-89",
                            cvss_score=9.8,
                            exploitability=0.95,
                        )
                    )
                # Error swallowing
                if re.search(r"""_\s*=\s*err\b""", line):
                    findings.append(
                        Finding(
                            id=f"SEC-GO-ERR-{idx}",
                            severity=SeverityEnum.MEDIUM,
                            category="error_handling",
                            title="Go Unhandled Error (Error Swallowed with '_')",
                            message="Ignoring error return with blank identifier '_' masks operational and security failures.",
                            line=idx,
                            code_snippet=line.strip(),
                            explanation="Swallowing errors leaves application state corrupted and bypasses security failure handlers.",
                            recommendation="Explicitly inspect if err != nil and return or log the error.",
                            suggestion='if err != nil {\n    return fmt.Errorf("operation failed: %w", err)\n}',
                            cwe_id="CWE-703",
                            cvss_score=6.0,
                        )
                    )

        # 13. Multi-Language: Rust Safety Findings
        rust_langs = ("rust", "rs")
        if language.lower() in rust_langs or (filename and filename.endswith(".rs")):
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                # Unsafe block without // SAFETY: documentation
                if re.search(r"""\bunsafe\s*\{""", line):
                    prev_context = "\n".join(lines[max(0, idx - 4) : idx])
                    if "SAFETY:" not in prev_context and "safety:" not in prev_context.lower():
                        findings.append(
                            Finding(
                                id=f"SEC-RUST-UNSAFE-{idx}",
                                severity=SeverityEnum.MEDIUM,
                                category="memory_safety",
                                title="Undocumented Rust 'unsafe' Block",
                                message="Rust 'unsafe' block without mandatory '// SAFETY:' rationale comment.",
                                line=idx,
                                code_snippet=line.strip(),
                                explanation="Unsafe Rust circumvents borrow-checker guarantees and must be accompanied by explicit safety invariant proofs.",
                                recommendation="Add a '// SAFETY:' comment above the unsafe block specifying why invariants are upheld.",
                                suggestion="// SAFETY: Pointer is guaranteed non-null, aligned, and valid for reads.\nunsafe { *ptr }",
                                cwe_id="CWE-242",
                                cvss_score=5.5,
                            )
                        )

        # Evaluate dynamically registered custom plugin rules
        custom = HeuristicEngine._custom_rules.get(language.lower(), [])
        for rule in custom:
            pat = rule.get("pattern")
            if not pat:
                continue
            for idx, line in enumerate(lines, 1):
                if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                    continue
                flags = re.IGNORECASE if rule.get("ignore_case", True) else 0
                if re.search(pat, line, flags):
                    sev_raw = rule.get("severity", "medium")
                    if isinstance(sev_raw, SeverityEnum):
                        sev_enum = sev_raw
                    else:
                        try:
                            sev_enum = SeverityEnum(str(sev_raw).lower())
                        except Exception:
                            sev_enum = SeverityEnum.MEDIUM
                    findings.append(
                        Finding(
                            id=f"{rule.get('id', 'CUSTOM')}-{idx}",
                            severity=sev_enum,
                            category=rule.get("category", "security"),
                            title=rule.get("title", "Custom Plugin Rule Finding"),
                            message=rule.get("message", "Custom rule pattern matched."),
                            line=idx,
                            code_snippet=line.strip(),
                            explanation=rule.get("explanation", "Detected by registered custom plugin rule."),
                            recommendation=rule.get("recommendation", "Review custom rule compliance requirements."),
                            suggestion=rule.get("suggestion"),
                            cwe_id=rule.get("cwe_id"),
                            cvss_score=rule.get("cvss_score", 5.0),
                        )
                    )

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
        code: str, language: str = "python", filename: Optional[str] = None
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
                                findings.append(
                                    Finding(
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
                                    )
                                )
                                break
        except Exception:
            pass

        # 2. Inefficient string concatenation in loops
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""\b\w+\s*\+=\s*["'].*["']""", line) or re.search(
                r"""\b\w+\s*=\s*\w+\s*\+\s*str\(.+""", line
            ):
                findings.append(
                    Finding(
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
                    )
                )

        # 3. Database query inside loop (N+1 Query Pattern)
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""(?:db|session|cursor|repository|User|Product)\.(?:execute|query|find|get)\(""", line):
                for prev in range(max(0, idx - 5), idx):
                    if "for " in lines[prev] or "while " in lines[prev]:
                        findings.append(
                            Finding(
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
                            )
                        )
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
        code: str, language: str = "python", filename: Optional[str] = None
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
                            findings.append(
                                Finding(
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
                                )
                            )

                    # 2. Long Functions (> 40 lines)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end_lineno = getattr(node, "end_lineno", node.lineno)
                        if (end_lineno - node.lineno) > 40:
                            findings.append(
                                Finding(
                                    id=f"QUAL-LEN-{node.lineno}",
                                    severity=SeverityEnum.LOW,
                                    category="maintainability",
                                    title=f"Function '{node.name}' is Excessively Long ({end_lineno - node.lineno} lines)",
                                    message="Long functions reduce readability and testability.",
                                    line=node.lineno,
                                    code_snippet=lines[node.lineno - 1].strip(),
                                    explanation="Large functions often violate the Single Responsibility Principle and are harder to unit test.",
                                    recommendation="Refactor into smaller, focused helper methods.",
                                )
                            )
        except Exception:
            pass

        # 3. Bare Except Clauses
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""^\s*except\s*:""", line):
                findings.append(
                    Finding(
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
                    )
                )

        # 4. Wildcard Imports
        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if re.search(r"""^\s*from\s+[\w\.]+\s+import\s+\*""", line):
                findings.append(
                    Finding(
                        id=f"QUAL-IMPORT-{idx}",
                        severity=SeverityEnum.LOW,
                        category="style",
                        title="Wildcard Import Detected (from module import *)",
                        message="Wildcard imports pollute the local namespace and obscure symbol origins.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Explicit imports prevent unintended variable shadowing and make static linters faster.",
                        recommendation="Import explicitly required symbols or the module name.",
                    )
                )

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
        code: str, language: str = "python", filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")

        # 1. Deep Relative Parent Import Detection
        for idx, line in enumerate(lines, 1):
            if "import " in line and "from .." in line:
                findings.append(
                    Finding(
                        id=f"ARCH-COUPLE-{idx}",
                        severity=SeverityEnum.LOW,
                        category="architecture",
                        title="Deep Relative Parent Import",
                        message="Importing from deep parent packages indicates potential architectural coupling.",
                        line=idx,
                        code_snippet=line.strip(),
                        explanation="Deep relative imports make components difficult to extract into separate packages or microservices.",
                        recommendation="Use absolute package imports or inversion of control.",
                    )
                )

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
                                    findings.append(
                                        Finding(
                                            id=f"ARCH-CYCLIC-{node.lineno}",
                                            severity=SeverityEnum.HIGH,
                                            category="dependency",
                                            title=f"Circular Self-Import Detected: '{alias.name}'",
                                            message=f"Module appears to import itself ('{alias.name}'), risking circular import recursion.",
                                            line=node.lineno,
                                            code_snippet=lines[node.lineno - 1].strip()
                                            if node.lineno <= len(lines)
                                            else "",
                                            explanation="Circular imports trigger ImportError during module loading and indicate tightly tangled dependencies.",
                                            recommendation="Refactor common symbols into a shared leaf module or use dependency injection.",
                                        )
                                    )
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                base_mod = node.module.split(".")[0]
                                imported_modules.add(base_mod)
                                if current_module and node.module.lower() == current_module:
                                    findings.append(
                                        Finding(
                                            id=f"ARCH-CYCLIC-{node.lineno}",
                                            severity=SeverityEnum.HIGH,
                                            category="dependency",
                                            title=f"Circular Self-Import Detected: '{node.module}'",
                                            message=f"Module appears to import from itself ('{node.module}'), risking circular import recursion.",
                                            line=node.lineno,
                                            code_snippet=lines[node.lineno - 1].strip()
                                            if node.lineno <= len(lines)
                                            else "",
                                            explanation="Circular imports trigger module resolution cycles and runtime deadlocks.",
                                            recommendation="Extract shared abstractions into an independent interface or helper module.",
                                        )
                                    )

                        # God Object / Monolithic Class Detection
                        if isinstance(node, ast.ClassDef):
                            method_count = sum(
                                1 for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            )
                            class_lines = (getattr(node, "end_lineno", node.lineno) - node.lineno) + 1
                            if method_count > 15 or class_lines > 250:
                                findings.append(
                                    Finding(
                                        id=f"ARCH-GOD-CLASS-{node.lineno}",
                                        severity=SeverityEnum.MEDIUM,
                                        category="modularity",
                                        title=f"God Object Anti-Pattern in Class '{node.name}'",
                                        message=f"Class '{node.name}' defines {method_count} methods across {class_lines} lines, indicating low cohesion.",
                                        line=node.lineno,
                                        code_snippet=lines[node.lineno - 1].strip()
                                        if node.lineno <= len(lines)
                                        else "",
                                        explanation="God Classes aggregate too many responsibilities, violating Single Responsibility Principle (SRP).",
                                        recommendation="Decompose class into cohesive sub-components, services, or strategy delegates.",
                                    )
                                )

                        # Tramp Data / Excessive Function Parameters
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            total_args = len(node.args.args) + len(node.args.kwonlyargs)
                            if node.args.args and node.args.args[0].arg in ("self", "cls"):
                                total_args -= 1
                            if total_args >= 7:
                                findings.append(
                                    Finding(
                                        id=f"ARCH-TRAMP-{node.lineno}",
                                        severity=SeverityEnum.LOW,
                                        category="architecture",
                                        title=f"Excessive Function Parameters ({total_args} params) in '{node.name}'",
                                        message=f"Function '{node.name}' takes {total_args} arguments, suggesting parameter grouping or a config object is needed.",
                                        line=node.lineno,
                                        code_snippet=lines[node.lineno - 1].strip()
                                        if node.lineno <= len(lines)
                                        else "",
                                        explanation="Functions with numerous parameters increase cognitive load and indicate improper abstraction boundaries.",
                                        recommendation="Encapsulate parameters into a typed dataclass, Pydantic model, or parameter object.",
                                    )
                                )

                    # Excessive External Fan-Out (High Coupling)
                    std_libs = {
                        "sys",
                        "os",
                        "re",
                        "math",
                        "time",
                        "typing",
                        "collections",
                        "datetime",
                        "pathlib",
                        "json",
                        "logging",
                        "asyncio",
                        "hashlib",
                        "secrets",
                        "uuid",
                        "abc",
                        "io",
                    }
                    external_deps = {m for m in imported_modules if m not in std_libs}
                    if len(external_deps) > 12:
                        findings.append(
                            Finding(
                                id="ARCH-COUPLING-FANOUT",
                                severity=SeverityEnum.MEDIUM,
                                category="coupling",
                                title=f"High Coupling / Excessive Fan-Out ({len(external_deps)} external dependencies)",
                                message=f"Module exhibits high fan-out coupling by directly importing {len(external_deps)} distinct external packages.",
                                line=1,
                                code_snippet=lines[0].strip() if lines else "",
                                explanation="Modules with excessive outgoing dependencies are fragile and sensitive to changes in any dependent library.",
                                recommendation="Introduce facade or adapter layers to consolidate external subsystem integrations.",
                            )
                        )

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
        code: str, language: str = "python", filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        findings: List[Finding] = []
        lines = code.split("\n")
        doc_lines = HeuristicEngine._extract_docstring_lines(code) if language.lower() == "python" else set()
        is_test = HeuristicEngine._is_test_or_fixture_context(filename)

        pii_patterns = [
            (
                r"""\b(?:ssn|social_security|credit_card|card_number|cvv|dob|date_of_birth)\b""",
                "PII / PCI-DSS Sensitive Data Exposure",
            ),
            (
                r"""(?:logger|logging)\.(?:debug|info|warning|warn|error|critical)\s*\(.*(?:password|token|secret|ssn)""",
                "Sensitive Data Emitted in Logs (HIPAA / SOC 2 violation)",
            ),
            (
                r"""print\s*\(.*(?:password|token|secret|ssn)""",
                "Sensitive Data Emitted via print() (HIPAA / SOC 2 violation)",
            ),
        ]

        for idx, line in enumerate(lines, 1):
            if HeuristicEngine._is_comment_or_docstring_line(line, doc_lines, idx):
                continue
            if is_test and "test" in line.lower() and not any(p in line.lower() for p in ("ssn", "password", "token")):
                continue

            for pat, desc in pii_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append(
                        Finding(
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
                        )
                    )

        score = 100.0 - (len(findings) * 20.0)
        return findings, max(0.0, score)

    # ===================================================================
    # MULTI-LANGUAGE SECURITY ANALYSIS (Java, C#, Ruby, PHP, Go, Rust)
    # ===================================================================

    @staticmethod
    def analyze_java_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Java code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")
        is_test = HeuristicEngine._is_test_or_fixture_context(filename)

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # SQL Injection via Statement
            if re.search(r"Statement\s+\w+\s*=.*\.createStatement\(\)", line):
                if re.search(r"\.execute(?:Query|Update)?\s*\([^?]*\+", line):
                    findings.append(
                        Finding(
                            id=f"JAVA-SQLI-{idx}",
                            severity=SeverityEnum.CRITICAL,
                            category="injection",
                            title="SQL Injection in Java (Statement)",
                            message="String concatenation detected in SQL Statement execution",
                            line=idx,
                            code_snippet=stripped,
                            recommendation="Use PreparedStatement with parameterized queries",
                            suggestion='PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id = ?"); ps.setInt(1, userId);',
                            cwe_id="CWE-89",
                            cvss_score=9.8,
                        )
                    )

            # XXE Vulnerability
            if "DocumentBuilderFactory.newInstance()" in line:
                # Check if secure features are set in nearby lines
                context_lines = "\n".join(lines[max(0, idx - 3) : min(len(lines), idx + 3)])
                if "setFeature" not in context_lines:
                    findings.append(
                        Finding(
                            id=f"JAVA-XXE-{idx}",
                            severity=SeverityEnum.HIGH,
                            category="xml",
                            title="XML External Entity (XXE) Vulnerability",
                            message="DocumentBuilderFactory created without disabling external entities",
                            line=idx,
                            code_snippet=stripped,
                            recommendation="Disable DTDs and external entities",
                            suggestion='factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);',
                            cwe_id="CWE-611",
                            cvss_score=8.2,
                        )
                    )

            # Insecure Random
            if "new Random()" in line or "Math.random()" in line:
                if not is_test:
                    findings.append(
                        Finding(
                            id=f"JAVA-WEAK-RANDOM-{idx}",
                            severity=SeverityEnum.MEDIUM,
                            category="cryptography",
                            title="Weak Random Number Generator",
                            message="Using non-cryptographic random generator for security-sensitive operations",
                            line=idx,
                            code_snippet=stripped,
                            recommendation="Use SecureRandom for cryptographic or security purposes",
                            suggestion="SecureRandom secureRandom = new SecureRandom();",
                            cwe_id="CWE-338",
                            cvss_score=5.3,
                        )
                    )

        return findings

    @staticmethod
    def analyze_csharp_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze C# code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # SQL Injection via string concatenation
            if re.search(r"new\s+SqlCommand\s*\([^)]*\+[^)]*\)", line):
                findings.append(
                    Finding(
                        id=f"CS-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in C# (SqlCommand)",
                        message="String concatenation detected in SqlCommand construction",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use parameterized queries with SqlParameter",
                        suggestion='SqlCommand cmd = new SqlCommand("SELECT * FROM users WHERE id = @id"); cmd.Parameters.AddWithValue("@id", userId);',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Command Injection
            if re.search(r"Process\.Start\s*\([^)]*\+", line):
                findings.append(
                    Finding(
                        id=f"CS-CMD-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="injection",
                        title="Command Injection in C# (Process.Start)",
                        message="User input concatenated into Process.Start command",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Validate and sanitize all user inputs, use ProcessStartInfo with Arguments property",
                        cwe_id="CWE-78",
                        cvss_score=8.4,
                    )
                )

            # Insecure Deserialization
            if "BinaryFormatter" in line or "NetDataContractSerializer" in line:
                findings.append(
                    Finding(
                        id=f"CS-DESER-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="deserialization",
                        title="Insecure Deserialization in C#",
                        message="BinaryFormatter and NetDataContractSerializer are vulnerable to deserialization attacks",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use Json.NET or DataContractSerializer with type filtering",
                        cwe_id="CWE-502",
                        cvss_score=8.1,
                    )
                )

        return findings

    @staticmethod
    def analyze_ruby_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Ruby code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # SQL Injection
            if re.search(r'\.where\s*\(["\'].*#\{.*\}', line) or re.search(r'\.find_by_sql\s*\(["\'].*#\{', line):
                findings.append(
                    Finding(
                        id=f"RUBY-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in Ruby/Rails",
                        message="String interpolation detected in SQL query",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use ActiveRecord parameterized queries",
                        suggestion='User.where("id = ?", user_id)',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Command Injection
            if re.search(r"`[^`]*#\{", line) or re.search(r'system\s*\(["\'].*#\{', line):
                findings.append(
                    Finding(
                        id=f"RUBY-CMD-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="injection",
                        title="Command Injection in Ruby",
                        message="User input interpolated into shell command",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use array form of system() or Open3 module",
                        suggestion='system("command", arg1, arg2)',
                        cwe_id="CWE-78",
                        cvss_score=8.4,
                    )
                )

            # eval() usage
            if re.search(r"\beval\s*\(", line):
                findings.append(
                    Finding(
                        id=f"RUBY-EVAL-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="Code Injection via eval()",
                        message="Dynamic code evaluation allows arbitrary code execution",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Avoid eval(), use safe alternatives like JSON.parse or YAML.safe_load",
                        cwe_id="CWE-94",
                        cvss_score=9.8,
                    )
                )

        return findings

    @staticmethod
    def analyze_php_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze PHP code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue

            # SQL Injection
            if re.search(r'mysql_query\s*\(["\'].*\$', line) or re.search(r'\$mysqli->query\s*\(["\'].*\$', line):
                findings.append(
                    Finding(
                        id=f"PHP-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in PHP",
                        message="Variable concatenation in SQL query",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use prepared statements with PDO or mysqli",
                        suggestion='$stmt = $pdo->prepare("SELECT * FROM users WHERE id = ?"); $stmt->execute([$userId]);',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Command Injection
            if re.search(r'\b(?:exec|shell_exec|system|passthru)\s*\(["\'].*\$', line):
                findings.append(
                    Finding(
                        id=f"PHP-CMD-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="injection",
                        title="Command Injection in PHP",
                        message="User input passed to shell execution function",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use escapeshellarg() or avoid shell functions entirely",
                        cwe_id="CWE-78",
                        cvss_score=8.4,
                    )
                )

            # File Inclusion
            if re.search(r'\b(?:include|require|include_once|require_once)\s*\(["\']?\$', line):
                findings.append(
                    Finding(
                        id=f"PHP-LFI-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="path_traversal",
                        title="Local File Inclusion Vulnerability",
                        message="User-controlled variable used in file inclusion",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use whitelist of allowed files, validate and sanitize inputs",
                        cwe_id="CWE-98",
                        cvss_score=7.5,
                    )
                )

            # eval() usage
            if re.search(r"\beval\s*\(", line):
                findings.append(
                    Finding(
                        id=f"PHP-EVAL-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="Code Injection via eval()",
                        message="eval() allows arbitrary code execution",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Avoid eval(), use safer alternatives",
                        cwe_id="CWE-94",
                        cvss_score=9.8,
                    )
                )

        return findings

    @staticmethod
    def analyze_go_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Go code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # SQL Injection via fmt.Sprintf
            if re.search(r'fmt\.Sprintf\s*\(["\'].*SELECT.*%[sv]', line):
                findings.append(
                    Finding(
                        id=f"GO-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in Go",
                        message="String formatting used to construct SQL query",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use parameterized queries with database/sql",
                        suggestion='db.Query("SELECT * FROM users WHERE id = $1", userID)',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Command Injection
            if re.search(r'exec\.Command\s*\(["\'][^"\']*\+', line):
                findings.append(
                    Finding(
                        id=f"GO-CMD-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="injection",
                        title="Command Injection in Go",
                        message="String concatenation in exec.Command",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Pass arguments separately to exec.Command",
                        suggestion='exec.Command("command", arg1, arg2)',
                        cwe_id="CWE-78",
                        cvss_score=8.4,
                    )
                )

            # Unhandled error
            if re.search(r"_\s*=\s*\w+\s*\(.*\)\s*$", line) and "err" in line:
                findings.append(
                    Finding(
                        id=f"GO-ERR-{idx}",
                        severity=SeverityEnum.LOW,
                        category="error_handling",
                        title="Ignored Error Return Value",
                        message="Error return value silently discarded with underscore",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Always check and handle error returns",
                        cwe_id="CWE-703",
                        cvss_score=3.1,
                    )
                )

        return findings

    @staticmethod
    def analyze_rust_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Rust code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # Undocumented unsafe block
            if "unsafe" in line and "{" in line:
                # Check for SAFETY comment in previous 2 lines
                context = "\n".join(lines[max(0, idx - 3) : idx])
                if "SAFETY:" not in context and "Safety:" not in context:
                    findings.append(
                        Finding(
                            id=f"RUST-UNSAFE-{idx}",
                            severity=SeverityEnum.MEDIUM,
                            category="unsafe_code",
                            title="Undocumented unsafe Block",
                            message="unsafe block without safety rationale comment",
                            line=idx,
                            code_snippet=stripped,
                            recommendation="Document all unsafe blocks with // SAFETY: explaining why it's safe",
                            cwe_id="CWE-242",
                            cvss_score=4.0,
                        )
                    )

            # Unwrap on Result/Option without handling
            if re.search(r"\.unwrap\(\)", line) and not (
                "test" in (filename or "").lower() or "example" in (filename or "").lower()
            ):
                findings.append(
                    Finding(
                        id=f"RUST-UNWRAP-{idx}",
                        severity=SeverityEnum.LOW,
                        category="error_handling",
                        title="Panic via unwrap()",
                        message="unwrap() will panic if Result/Option is Err/None",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use pattern matching, expect(), or the ? operator for error propagation",
                        suggestion='value.expect("descriptive error message")',
                        cwe_id="CWE-703",
                        cvss_score=2.3,
                    )
                )

        return findings

    @staticmethod
    def analyze_kotlin_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Kotlin code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*")):
                continue

            # SQL Injection via string interpolation in queries
            if re.search(r'(rawQuery|execSQL|createQuery|createNativeQuery)\s*\(\s*["\'].*\$.*["\']', line):
                findings.append(
                    Finding(
                        id=f"KOTLIN-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in Kotlin",
                        message="String interpolation used in raw SQL database query",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use parameterized query arguments instead of string interpolation",
                        suggestion='db.rawQuery("SELECT * FROM users WHERE id = ?", arrayOf(userId))',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Weak Random
            if "java.util.Random()" in line or ("Random(" in line and "SecureRandom" not in line):
                findings.append(
                    Finding(
                        id=f"KOTLIN-RANDOM-{idx}",
                        severity=SeverityEnum.MEDIUM,
                        category="cryptography",
                        title="Insecure Pseudo-Random Number Generator",
                        message="java.util.Random is not cryptographically secure",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use java.security.SecureRandom for security-sensitive tokens and keys",
                        suggestion="val random = java.security.SecureRandom()",
                        cwe_id="CWE-330",
                        cvss_score=5.3,
                    )
                )

            # Insecure TrustManager (SSL Verification Bypass)
            if re.search(r"checkServerTrusted\s*\([^)]*\)\s*\{\s*\}", line) or "TrustAllCerts" in line:
                findings.append(
                    Finding(
                        id=f"KOTLIN-SSL-BYPASS-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="cryptography",
                        title="SSL/TLS Certificate Verification Bypass",
                        message="Empty checkServerTrusted implementation disables TLS validation",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Rely on standard system CA trust certificates without custom bypasses",
                        cwe_id="CWE-295",
                        cvss_score=9.0,
                    )
                )

            # Hardcoded API credentials
            if re.search(
                r'(val|var)\s+(apiKey|secretKey|apiToken|password)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']',
                line,
                re.IGNORECASE,
            ):
                findings.append(
                    Finding(
                        id=f"KOTLIN-SECRET-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="secrets",
                        title="Hardcoded API Secret in Kotlin",
                        message="Hardcoded sensitive credential identified in source code",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Load secrets from secure runtime keystore or BuildConfig/environment variables",
                        cwe_id="CWE-798",
                        cvss_score=8.9,
                    )
                )

            # Insecure SharedPreferences World Readable/Writable
            if re.search(r"MODE_WORLD_READABLE|MODE_WORLD_WRITEABLE", line):
                findings.append(
                    Finding(
                        id=f"KOTLIN-PREFS-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="storage",
                        title="Insecure SharedPreferences Mode",
                        message="MODE_WORLD_READABLE or MODE_WORLD_WRITEABLE exposes private app data",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use EncryptedSharedPreferences with MODE_PRIVATE",
                        suggestion="context.getSharedPreferences(NAME, Context.MODE_PRIVATE)",
                        cwe_id="CWE-276",
                        cvss_score=7.5,
                    )
                )

        return findings

    @staticmethod
    def analyze_swift_security(code: str, filename: Optional[str] = None) -> List[Finding]:
        """Analyze Swift code for security vulnerabilities."""
        findings: List[Finding] = []
        lines = code.split("\n")

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*")):
                continue

            # SQL Injection via string interpolation in SQLite/CoreData/GRDB
            if re.search(r'(execute|query|rawQuery|prepareStatement)\s*\(\s*(sql:\s*)?["\'].*\\\(.*["\']', line) or re.search(
                r'["\'].*(SELECT|INSERT|UPDATE|DELETE)\s+.*\\\(.*["\']', line, re.IGNORECASE
            ):
                findings.append(
                    Finding(
                        id=f"SWIFT-SQLI-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="injection",
                        title="SQL Injection in Swift",
                        message="String interpolation used in raw SQL database statement",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Bind query arguments using statement parameters instead of string interpolation",
                        suggestion='try db.run("SELECT * FROM users WHERE id = ?", userId)',
                        cwe_id="CWE-89",
                        cvss_score=9.8,
                    )
                )

            # Insecure Keychain Accessibility
            if re.search(r"kSecAttrAccessibleAlways\b|kSecAttrAccessibleAlwaysThisDeviceOnly\b", line):
                findings.append(
                    Finding(
                        id=f"SWIFT-KEYCHAIN-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="storage",
                        title="Insecure Keychain Accessibility Level",
                        message="AccessibleAlways allows keychain access while the device is locked",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use kSecAttrAccessibleAfterFirstUnlock or kSecAttrAccessibleWhenUnlockedThisDeviceOnly",
                        suggestion="kSecAttrAccessibleWhenUnlockedThisDeviceOnly",
                        cwe_id="CWE-311",
                        cvss_score=7.4,
                    )
                )

            # Insecure Hashing MD5/SHA-1
            if re.search(r"\b(CC_MD5|CC_SHA1|Insecure\.MD5|Insecure\.SHA1)\b", line):
                findings.append(
                    Finding(
                        id=f"SWIFT-CRYPTO-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="cryptography",
                        title="Weak Cryptographic Hash Algorithm",
                        message="MD5 and SHA-1 are cryptographically broken and prone to collision attacks",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use CryptoKit with SHA256 or SHA512",
                        suggestion="SHA256.hash(data: data)",
                        cwe_id="CWE-328",
                        cvss_score=7.5,
                    )
                )

            # Insecure ATS flag
            if "NSAllowsArbitraryLoads" in line:
                findings.append(
                    Finding(
                        id=f"SWIFT-ATS-{idx}",
                        severity=SeverityEnum.HIGH,
                        category="network",
                        title="App Transport Security (ATS) Disabled",
                        message="NSAllowsArbitraryLoads disables TLS enforcement for network requests",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Enforce HTTPS via Apple App Transport Security standards",
                        cwe_id="CWE-319",
                        cvss_score=7.5,
                    )
                )

            # Insecure Randomness
            if re.search(r"\barc4random\s*\(", line):
                findings.append(
                    Finding(
                        id=f"SWIFT-RANDOM-{idx}",
                        severity=SeverityEnum.LOW,
                        category="cryptography",
                        title="Obsolete Random Generator",
                        message="arc4random is superseded and should not be used for cryptographic nonce generation",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Use SecRandomCopyBytes or SystemRandomNumberGenerator",
                        suggestion="SecRandomCopyBytes(kSecRandomDefault, count, &bytes)",
                        cwe_id="CWE-330",
                        cvss_score=3.5,
                    )
                )

            # Hardcoded API Secret
            if re.search(
                r'(let|var)\s+(apiKey|secretKey|token|password)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']',
                line,
                re.IGNORECASE,
            ):
                findings.append(
                    Finding(
                        id=f"SWIFT-SECRET-{idx}",
                        severity=SeverityEnum.CRITICAL,
                        category="secrets",
                        title="Hardcoded API Secret in Swift",
                        message="Hardcoded sensitive credential identified in source code",
                        line=idx,
                        code_snippet=stripped,
                        recommendation="Store API secrets securely in Keychain or fetch via authenticated backend",
                        cwe_id="CWE-798",
                        cvss_score=8.9,
                    )
                )

        return findings

    @staticmethod
    def analyze_multi_language_security(
        code: str, language: str, filename: Optional[str] = None
    ) -> Tuple[List[Finding], float]:
        """
        Unified multi-language security analyzer.
        Routes to language-specific analyzers based on detected language.
        """
        language_lower = language.lower()

        # Route to language-specific analyzers
        if language_lower == "java":
            lang_findings = HeuristicEngine.analyze_java_security(code, filename)
        elif language_lower in ("csharp", "c#", "cs"):
            lang_findings = HeuristicEngine.analyze_csharp_security(code, filename)
        elif language_lower == "ruby":
            lang_findings = HeuristicEngine.analyze_ruby_security(code, filename)
        elif language_lower == "php":
            lang_findings = HeuristicEngine.analyze_php_security(code, filename)
        elif language_lower in ("go", "golang"):
            lang_findings = HeuristicEngine.analyze_go_security(code, filename)
        elif language_lower == "rust":
            lang_findings = HeuristicEngine.analyze_rust_security(code, filename)
        elif language_lower in ("kotlin", "kt"):
            lang_findings = HeuristicEngine.analyze_kotlin_security(code, filename)
        elif language_lower == "swift":
            lang_findings = HeuristicEngine.analyze_swift_security(code, filename)
        elif language_lower == "python":
            # Use existing Python analyzer
            return HeuristicEngine.analyze_security(code, language, filename)
        else:
            # For unsupported languages, return empty findings
            lang_findings = []

        # Calculate score
        if not lang_findings:
            score = 100.0
        else:
            critical_count = sum(1 for f in lang_findings if f.severity == SeverityEnum.CRITICAL)
            high_count = sum(1 for f in lang_findings if f.severity == SeverityEnum.HIGH)
            medium_count = sum(1 for f in lang_findings if f.severity == SeverityEnum.MEDIUM)
            low_count = sum(1 for f in lang_findings if f.severity == SeverityEnum.LOW)

            deductions = (critical_count * 20) + (high_count * 10) + (medium_count * 5) + (low_count * 2)
            score = max(0.0, 100.0 - deductions)

        return lang_findings, score
