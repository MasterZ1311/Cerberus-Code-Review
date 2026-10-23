"""
Validate OpenAPI 3.1 YAML extracted from API_SPECIFICATIONS.md.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

def extract_yaml_blocks(doc_path):
    text = doc_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    blocks = []
    in_block = False
    start_line = 0
    current_content = []

    for idx, line in enumerate(lines, 1):
        if line.startswith("```"):
            if not in_block:
                lang = line[3:].strip().lower()
                if lang in ["yaml", "yml"]:
                    in_block = True
                    start_line = idx + 1
                    current_content = []
            else:
                if in_block:
                    in_block = False
                    end_line = idx - 1
                    blocks.append({
                        "start": start_line,
                        "end": end_line,
                        "content": "\n".join(current_content)
                    })
        elif in_block:
            current_content.append(line)
    return blocks

def validate_openapi():
    doc_path = ROOT / "API_SPECIFICATIONS.md"
    yaml_blocks = extract_yaml_blocks(doc_path)
    print(f"Total YAML blocks in API_SPECIFICATIONS.md: {len(yaml_blocks)}")
    
    for idx, b in enumerate(yaml_blocks, 1):
        print(f"\nValidating YAML block #{idx} (lines {b['start']}-{b['end']}, {len(b['content'].splitlines())} lines)...")
        try:
            parsed = yaml.safe_load(b["content"])
            print("  YAML syntax: VALID")
        except Exception as e:
            print(f"  YAML syntax ERROR: {e}")
            continue
            
        if not isinstance(parsed, dict):
            print("  Warning: Root is not a dict")
            continue
            
        # Check OpenAPI fields
        openapi_ver = parsed.get("openapi")
        info = parsed.get("info", {})
        paths = parsed.get("paths", {})
        components = parsed.get("components", {})
        
        print(f"  OpenAPI version: {openapi_ver}")
        print(f"  Title: {info.get('title')}, version: {info.get('version')}")
        print(f"  Total Paths: {len(paths)}")
        print(f"  Total Schemas in components: {len(components.get('schemas', {}))}")
        print(f"  Security Schemes: {list(components.get('securitySchemes', {}).keys())}")
        
        required_endpoints = [
            "/reviews",
            "/reviews/{id}",
            "/reviews/{id}/status",
            "/reviews/{id}/approve",
            "/analytics/trends",
            "/rules/custom",
            "/teams/expertise",
            "/reviews/{id}/stream"
        ]
        
        print("\n  Checking required endpoints against YAML paths:")
        for ep in required_endpoints:
            # Handle possible prefix like /api/v1
            matching = [p for p in paths if p == ep or p == f"/api/v1{ep}" or p.endswith(ep)]
            if matching:
                methods = list(paths[matching[0]].keys())
                print(f"    [FOUND] {ep} -> {matching[0]} ({methods})")
            else:
                print(f"    [MISSING] {ep}")

if __name__ == "__main__":
    validate_openapi()
