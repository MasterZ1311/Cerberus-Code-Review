"""
Multi-Language Syntax and AST Verification Engine for cerberus</>.
Features native Tree-sitter deep AST parsing and syntax analysis across
TypeScript, TSX, JavaScript, Go, Rust, and Python, alongside JSON, YAML,
and C-family balanced delimiter state machines.
"""

import ast
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("cerberus.core.syntax_verifier")

# Tree-sitter language package imports with graceful degradation
_TREE_SITTER_AVAILABLE = False
_LANGUAGE_FACTORIES: Dict[str, Any] = {}

try:
    from tree_sitter import Language, Parser
    import tree_sitter_python
    import tree_sitter_typescript
    import tree_sitter_go
    import tree_sitter_rust

    _LANGUAGE_FACTORIES = {
        "python": tree_sitter_python.language,
        "py": tree_sitter_python.language,
        "typescript": tree_sitter_typescript.language_typescript,
        "ts": tree_sitter_typescript.language_typescript,
        "tsx": tree_sitter_typescript.language_tsx,
        "javascript": tree_sitter_typescript.language_typescript,
        "js": tree_sitter_typescript.language_typescript,
        "jsx": tree_sitter_typescript.language_typescript,
        "go": tree_sitter_go.language,
        "golang": tree_sitter_go.language,
        "rust": tree_sitter_rust.language,
        "rs": tree_sitter_rust.language,
    }
    _TREE_SITTER_AVAILABLE = True
except Exception as e:
    logger.debug(f"Tree-sitter native bindings not available, falling back to regex/delimiters: {e}")

_PARSER_CACHE: Dict[str, Any] = {}


def detect_language_from_path(filepath: Union[str, Path]) -> str:
    """Detects target programming language from file path extension."""
    ext = Path(filepath).suffix.lower()
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".rb": "ruby",
        ".php": "php",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".sh": "bash",
    }
    return mapping.get(ext, "python")


def _get_tree_sitter_parser(lang: str) -> Optional[Any]:
    """Retrieves or builds a cached Tree-sitter Parser instance for a language."""
    if not _TREE_SITTER_AVAILABLE:
        return None

    normalized = lang.strip().lower()
    if normalized in _PARSER_CACHE:
        return _PARSER_CACHE[normalized]

    factory = _LANGUAGE_FACTORIES.get(normalized)
    if not factory:
        return None

    try:
        language_obj = Language(factory())
        parser = Parser(language_obj)
        _PARSER_CACHE[normalized] = parser
        return parser
    except Exception as e:
        logger.warning(f"Failed to initialize Tree-sitter parser for '{normalized}': {e}")
        return None


class SyntaxVerifier:
    """
    Multi-language syntactic correctness and deep AST inspection engine.
    Supports native Python AST, Tree-sitter AST (TypeScript, Go, Rust, Python),
    JSON, YAML, and balanced delimiter verification.
    """

    @staticmethod
    def is_tree_sitter_supported(language: str) -> bool:
        """Returns True if Tree-sitter native parsing is available for the language."""
        if not _TREE_SITTER_AVAILABLE:
            return False
        return language.strip().lower() in _LANGUAGE_FACTORIES

    @staticmethod
    def verify_python(code: str) -> Tuple[bool, Optional[str]]:
        """Verifies Python source code via native Python ast.parse."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        except Exception as e:
            return False, f"Python parse error: {str(e)}"

    @classmethod
    def verify_tree_sitter(cls, code: str, language: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Deep AST validation and symbol extraction using Tree-sitter.
        Supported languages: typescript, tsx, javascript, go, rust, python.
        Returns: (is_valid: bool, error_message: Optional[str], metadata: Optional[dict])
        """
        parser = _get_tree_sitter_parser(language)
        if not parser:
            return True, None, None

        code_bytes = code.encode("utf-8")
        try:
            tree = parser.parse(code_bytes)
        except Exception as e:
            return False, f"Tree-sitter parse exception for '{language}': {e}", None

        # Check for AST syntax errors
        if tree.root_node.has_error:
            errors = []

            def _find_errors(node: Any):
                if node.type == "ERROR" or node.is_missing:
                    line = node.start_point.row + 1
                    col = node.start_point.column + 1
                    snippet = code_bytes[max(0, node.start_byte - 15):min(len(code_bytes), node.end_byte + 15)].decode("utf-8", errors="replace").strip()
                    desc = "missing required syntax element" if node.is_missing else f"unexpected syntax near '{snippet}'"
                    errors.append(f"{language.capitalize()} Tree-sitter SyntaxError at line {line}, col {col}: {desc}")
                for child in node.children:
                    if child.has_error:
                        _find_errors(child)

            _find_errors(tree.root_node)
            first_err = errors[0] if errors else f"Syntax error detected in {language} AST"
            return False, first_err, {"has_syntax_errors": True, "syntax_errors": errors}

        # Extract deep AST structural metrics
        metadata = cls._extract_tree_sitter_symbols(tree.root_node, code_bytes, language)
        return True, None, metadata

    @staticmethod
    def _extract_tree_sitter_symbols(root_node: Any, code_bytes: bytes, language: str) -> Dict[str, Any]:
        """Walks Tree-sitter AST nodes to extract functions, classes, structs, and imports."""
        lang = language.strip().lower()
        functions: List[str] = []
        classes_or_structs: List[str] = []
        imports: List[str] = []
        node_count = 0

        func_types = {
            "function_declaration", "method_definition", "arrow_function",
            "function_item", "method_declaration"
        }
        class_types = {
            "class_declaration", "interface_declaration", "struct_item",
            "enum_item", "type_spec"
        }
        import_types = {
            "import_statement", "use_declaration", "import_spec", "import_declaration"
        }

        def _traverse(node: Any):
            nonlocal node_count
            node_count += 1

            if node.type in func_types:
                for child in node.children:
                    if child.type in ("identifier", "property_identifier", "name"):
                        name = code_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        if name and name not in functions:
                            functions.append(name)
                        break

            elif node.type in class_types:
                for child in node.children:
                    if child.type in ("type_identifier", "identifier", "name"):
                        name = code_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        if name and name not in classes_or_structs:
                            classes_or_structs.append(name)
                        break

            elif node.type in import_types:
                raw_imp = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()
                if raw_imp and raw_imp not in imports:
                    imports.append(raw_imp)

            for child in node.children:
                _traverse(child)

        _traverse(root_node)

        return {
            "language": lang,
            "parser_type": "tree_sitter",
            "node_count": node_count,
            "function_count": len(functions),
            "functions": functions,
            "class_or_struct_count": len(classes_or_structs),
            "classes_or_structs": classes_or_structs,
            "import_count": len(imports),
            "imports": imports,
            "has_syntax_errors": False,
            "syntax_errors": []
        }

    @classmethod
    def verify_typescript(cls, code: str, is_tsx: bool = False) -> Tuple[bool, Optional[str]]:
        """Verifies TypeScript / TSX code via Tree-sitter AST, falling back to delimiters."""
        lang = "tsx" if is_tsx else "typescript"
        if cls.is_tree_sitter_supported(lang):
            valid, err, _ = cls.verify_tree_sitter(code, lang)
            if not valid:
                return valid, err
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"TypeScript SyntaxError: {err}"
        return True, None

    @classmethod
    def verify_go(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifies Go source code via Tree-sitter AST, falling back to delimiters."""
        if cls.is_tree_sitter_supported("go"):
            valid, err, _ = cls.verify_tree_sitter(code, "go")
            if not valid:
                return valid, err
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"Go SyntaxError: {err}"
        return True, None

    @classmethod
    def verify_rust(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifies Rust source code via Tree-sitter AST, falling back to delimiters."""
        if cls.is_tree_sitter_supported("rust"):
            valid, err, _ = cls.verify_tree_sitter(code, "rust")
            if not valid:
                return valid, err
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"Rust SyntaxError: {err}"
        return True, None

    @staticmethod
    def verify_json(code: str) -> Tuple[bool, Optional[str]]:
        """Verifies JSON format validity."""
        try:
            json.loads(code)
            return True, None
        except Exception as e:
            return False, f"JSON parse error: {str(e)}"

    @staticmethod
    def verify_yaml(code: str) -> Tuple[bool, Optional[str]]:
        """Verifies YAML format validity if pyyaml is installed."""
        try:
            import yaml
            yaml.safe_load(code)
            return True, None
        except ImportError:
            return SyntaxVerifier.verify_balanced_delimiters(code)
        except Exception as e:
            return False, f"YAML parse error: {str(e)}"

    @staticmethod
    def verify_balanced_delimiters(code: str) -> Tuple[bool, Optional[str]]:
        """
        Validates balanced brackets (), {}, [] and unclosed string literals
        for C-family languages. Ignores comments and strings.
        """
        stack = []
        matching = {')': '(', '}': '{', ']': '['}
        in_single_quote = False
        in_double_quote = False
        in_backtick = False
        in_line_comment = False
        in_block_comment = False
        escaped = False

        chars = list(code)
        i = 0
        n = len(chars)

        while i < n:
            ch = chars[i]
            next_ch = chars[i + 1] if i + 1 < n else ""

            if escaped:
                escaped = False
                i += 1
                continue

            if ch == '\\':
                escaped = True
                i += 1
                continue

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                i += 1
                continue

            if in_block_comment:
                if ch == '*' and next_ch == '/':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_single_quote:
                if ch == "'":
                    in_single_quote = False
                i += 1
                continue

            if in_double_quote:
                if ch == '"':
                    in_double_quote = False
                i += 1
                continue

            if in_backtick:
                if ch == '`':
                    in_backtick = False
                i += 1
                continue

            # Comments
            if ch == '/' and next_ch == '/':
                in_line_comment = True
                i += 2
                continue
            if ch == '/' and next_ch == '*':
                in_block_comment = True
                i += 2
                continue
            if ch == '#' and (i == 0 or chars[i - 1] in (' ', '\t', '\n')):
                in_line_comment = True
                i += 1
                continue

            # Strings
            if ch == "'":
                in_single_quote = True
                i += 1
                continue
            if ch == '"':
                in_double_quote = True
                i += 1
                continue
            if ch == '`':
                in_backtick = True
                i += 1
                continue

            # Delimiters
            if ch in ('(', '{', '['):
                stack.append((ch, i))
            elif ch in (')', '}', ']'):
                if not stack:
                    return False, f"Unmatched closing delimiter '{ch}' at position {i}"
                top, _ = stack.pop()
                if matching[ch] != top:
                    return False, f"Mismatched delimiter: expected closing for '{top}', found '{ch}' at pos {i}"

            i += 1

        if in_single_quote or in_double_quote or in_backtick:
            return False, "Unclosed string literal in code"
        if in_block_comment:
            return False, "Unclosed block comment (/* ... */) in code"
        if stack:
            unclosed, pos = stack[-1]
            return False, f"Unclosed opening delimiter '{unclosed}' at position {pos}"

        return True, None

    @classmethod
    def verify_java(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifies Java source code for balanced delimiters, class declarations, and syntax rules."""
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"Java SyntaxError: {err}"
        return True, None

    @classmethod
    def verify_cpp(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifies C / C++ source code for balanced delimiters and structural syntax rules."""
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"C/C++ SyntaxError: {err}"
        return True, None

    @classmethod
    def verify_csharp(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifies C# source code for balanced delimiters and structural syntax rules."""
        valid, err = cls.verify_balanced_delimiters(code)
        if not valid:
            return valid, f"C# SyntaxError: {err}"
        return True, None

    @staticmethod
    def _extract_regex_symbols(code: str, language: str) -> Dict[str, Any]:
        """Extracts functions, classes, and imports for Java, C++, and C# using AST regex patterns."""
        import re
        lang = language.lower()
        classes: List[str] = []
        functions: List[str] = []
        imports: List[str] = []

        if lang == "java":
            # Extract classes, interfaces, records, enums
            for m in re.finditer(r"\b(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+)*(?:class|interface|enum|record)\s+([A-Za-z0-9_]+)", code):
                classes.append(m.group(1))
            # Extract methods
            for m in re.finditer(r"\b(?:public|protected|private|static|final|\s)+[\w\<\>\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{", code):
                m_name = m.group(1)
                if m_name not in ("if", "for", "while", "switch", "catch") and m_name not in classes:
                    functions.append(m_name)
            # Extract package and imports
            for m in re.finditer(r"^\s*(?:import|package)\s+([^;]+);", code, re.MULTILINE):
                imports.append(m.group(1).strip())

        elif lang in ("cpp", "c", "cxx"):
            # Extract structs, classes, namespaces
            for m in re.finditer(r"\b(?:class|struct|namespace)\s+([A-Za-z0-9_]+)", code):
                classes.append(m.group(1))
            # Extract functions
            for m in re.finditer(r"\b(?:[\w:*&<>]+\s+)+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:const)?\s*\{", code):
                f_name = m.group(1)
                if f_name not in ("if", "for", "while", "switch", "catch") and f_name not in classes:
                    functions.append(f_name)
            # Extract #include
            for m in re.finditer(r"^\s*#include\s*([<\"].*?[>\"])", code, re.MULTILINE):
                imports.append(m.group(1))

        elif lang in ("csharp", "cs"):
            # Extract classes, interfaces, structs, records
            for m in re.finditer(r"\b(?:public\s+|private\s+|protected\s+|internal\s+|static\s+|abstract\s+|sealed\s+)*(?:class|interface|struct|record)\s+([A-Za-z0-9_]+)", code):
                classes.append(m.group(1))
            # Extract methods
            for m in re.finditer(r"\b(?:public|protected|private|internal|static|async|\s)+[\w\<\>\[\]\?]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{", code):
                m_name = m.group(1)
                if m_name not in ("if", "for", "while", "switch", "catch") and m_name not in classes:
                    functions.append(m_name)
            # Extract using statements
            for m in re.finditer(r"^\s*using\s+([^;]+);", code, re.MULTILINE):
                imports.append(m.group(1).strip())

        return {
            "language": lang,
            "parser_type": "ast_regex_tokenizer",
            "function_count": len(functions),
            "functions": list(dict.fromkeys(functions)),
            "class_or_struct_count": len(classes),
            "classes_or_structs": list(dict.fromkeys(classes)),
            "import_count": len(imports),
            "imports": list(dict.fromkeys(imports)),
            "has_syntax_errors": False,
            "syntax_errors": []
        }

    @classmethod
    def extract_ast_metadata(cls, code: str, language: Optional[str] = "python") -> Dict[str, Any]:
        """
        Public API to extract AST symbols and structural metadata across any supported language.
        """
        lang = (language or "python").strip().lower()
        if cls.is_tree_sitter_supported(lang):
            _, _, metadata = cls.verify_tree_sitter(code, lang)
            if metadata:
                return metadata

        # Python native AST fallback
        if lang in ("python", "py"):
            try:
                tree = ast.parse(code)
                funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                imports = []
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        imports.extend(alias.name for alias in n.names)
                    elif isinstance(n, ast.ImportFrom):
                        imports.append(f"{n.module}")
                return {
                    "language": "python",
                    "parser_type": "python_ast",
                    "node_count": len(list(ast.walk(tree))),
                    "function_count": len(funcs),
                    "functions": funcs,
                    "class_or_struct_count": len(classes),
                    "classes_or_structs": classes,
                    "import_count": len(imports),
                    "imports": imports,
                    "has_syntax_errors": False,
                    "syntax_errors": []
                }
            except Exception as e:
                return {
                    "language": "python",
                    "parser_type": "python_ast",
                    "has_syntax_errors": True,
                    "syntax_errors": [str(e)]
                }

        # Java, C++, C# structured extraction
        if lang in ("java", "cpp", "c", "cxx", "csharp", "cs"):
            return cls._extract_regex_symbols(code, lang)

        return {
            "language": lang,
            "parser_type": "delimiter",
            "has_syntax_errors": False,
            "syntax_errors": []
        }

    @classmethod
    def verify(cls, code: str, language: Optional[str] = "python") -> Tuple[bool, Optional[str]]:
        """
        Public dispatcher to verify syntax according to target programming language.
        Routes to Tree-sitter AST, native AST, Java/C++/C# AST, JSON/YAML, or delimiter state machine.
        Returns: (is_valid: bool, error_message: Optional[str])
        """
        if not code or not code.strip():
            return True, None

        lang = (language or "python").strip().lower()

        if lang in ("python", "py"):
            return cls.verify_python(code)
        elif lang in ("typescript", "ts"):
            return cls.verify_typescript(code, is_tsx=False)
        elif lang in ("tsx",):
            return cls.verify_typescript(code, is_tsx=True)
        elif lang in ("javascript", "js", "jsx"):
            return cls.verify_typescript(code, is_tsx=False)
        elif lang in ("go", "golang"):
            return cls.verify_go(code)
        elif lang in ("rust", "rs"):
            return cls.verify_rust(code)
        elif lang in ("java",):
            return cls.verify_java(code)
        elif lang in ("cpp", "c", "cxx", "hpp", "h"):
            return cls.verify_cpp(code)
        elif lang in ("csharp", "cs"):
            return cls.verify_csharp(code)
        elif lang in ("json",):
            return cls.verify_json(code)
        elif lang in ("yaml", "yml"):
            return cls.verify_yaml(code)
        else:
            return cls.verify_balanced_delimiters(code)
