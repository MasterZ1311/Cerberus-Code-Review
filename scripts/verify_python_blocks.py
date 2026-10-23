"""
Empirical Python Code Block Validator for:
- PHASE_1_DETAILED_IMPLEMENTATION.md
- AGENT_SPECIFICATIONS.md
- API_SPECIFICATIONS.md
- DATABASE_DESIGN.md
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "PHASE_1_DETAILED_IMPLEMENTATION.md",
    "AGENT_SPECIFICATIONS.md",
    "DATABASE_DESIGN.md",
    "API_SPECIFICATIONS.md"
]

def extract_python_blocks(doc_path):
    text = doc_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    blocks = []
    in_block = False
    current_lang = ""
    start_line = 0
    current_content = []

    for idx, line in enumerate(lines, 1):
        if line.startswith("```"):
            if not in_block:
                in_block = True
                current_lang = line[3:].strip().lower()
                start_line = idx + 1
                current_content = []
            else:
                in_block = False
                end_line = idx - 1
                if current_lang == "python":
                    blocks.append({
                        "doc": doc_path.name,
                        "start": start_line,
                        "end": end_line,
                        "content": "\n".join(current_content)
                    })
        elif in_block:
            current_content.append(line)
    return blocks

class SymbolVisitor(ast.NodeVisitor):
    def __init__(self):
        self.defined_symbols = set()
        self.imported_symbols = set()
        self.referenced_symbols = set()
        self.type_annotations = []
        self.functions = []
        self.classes = []

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_symbols.add(name.split('.')[0])
            self.defined_symbols.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_symbols.add(name)
            self.defined_symbols.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined_symbols.add(node.name)
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined_symbols.add(node.name)
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.defined_symbols.add(node.name)
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.defined_symbols.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.referenced_symbols.add(node.id)
        self.generic_visit(node)

def validate_block(block):
    content = block["content"]
    # Check AST parse
    try:
        tree = ast.parse(content, filename=f"{block['doc']}:{block['start']}")
    except SyntaxError as e:
        return {
            "valid": False,
            "error_type": "SyntaxError",
            "message": str(e),
            "line": e.lineno,
            "offset": e.offset,
            "text": e.text
        }
    except Exception as e:
        return {
            "valid": False,
            "error_type": type(e).__name__,
            "message": str(e)
        }

    # Extract symbols
    visitor = SymbolVisitor()
    visitor.visit(tree)

    # Check for empty functions/methods or suspicious stubs
    suspicious = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # If function body is just pass or ...
            if len(node.body) == 1:
                if isinstance(node.body[0], ast.Pass):
                    # In protocols/abstract methods/overload, pass is valid, check if decorators or protocol
                    decorators = [ast.unparse(d) for d in node.decorator_list]
                    suspicious.append(f"Function {node.name} body is only 'pass' (decorators: {decorators})")
                elif isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and node.body[0].value.value is Ellipsis:
                    suspicious.append(f"Function {node.name} body is only '...'")

    return {
        "valid": True,
        "classes": visitor.classes,
        "functions": visitor.functions,
        "imported": list(visitor.imported_symbols),
        "suspicious": suspicious,
        "num_statements": len(tree.body)
    }

def main():
    total_blocks = 0
    passed_blocks = 0
    failed_blocks = 0

    for doc_name in DOCS:
        doc_path = ROOT / doc_name
        if not doc_path.exists():
            continue
        blocks = extract_python_blocks(doc_path)
        print(f"\n=======================================================")
        print(f"DOCUMENT: {doc_name} ({len(blocks)} Python blocks)")
        print(f"=======================================================")

        for idx, block in enumerate(blocks, 1):
            total_blocks += 1
            result = validate_block(block)
            first_line = block['content'].splitlines()[0] if block['content'].splitlines() else ""
            lines_count = len(block['content'].splitlines())
            
            if result["valid"]:
                passed_blocks += 1
                print(f"[PASS] Block #{idx} (lines {block['start']}-{block['end']}, {lines_count} lines): {first_line[:50]}")
                print(f"       Statements: {result['num_statements']}, Classes: {len(result['classes'])}, Functions: {len(result['functions'])}")
                if result["suspicious"]:
                    for s in result["suspicious"]:
                        print(f"       WARNING: {s}")
            else:
                failed_blocks += 1
                print(f"[FAIL] Block #{idx} (lines {block['start']}-{block['end']}): {result['error_type']}: {result['message']}")
                if "line" in result and result["line"]:
                    err_line = result["line"]
                    print(f"       Error at block relative line {err_line} (doc line {block['start'] + err_line - 1})")
                    print(f"       Line text: {result.get('text', '').strip()}")

    print(f"\nSUMMARY:")
    print(f"Total Python blocks: {total_blocks}")
    print(f"Passed AST Parse:    {passed_blocks}")
    print(f"Failed AST Parse:    {failed_blocks}")

if __name__ == "__main__":
    main()
