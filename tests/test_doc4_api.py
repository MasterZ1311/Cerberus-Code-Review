"""
Empirical test for API_SPECIFICATIONS.md OpenAPI YAML and FastAPI application.
"""

import pytest
import yaml
from pathlib import Path
from scripts.verify_python_blocks import ROOT
from scripts.verify_openapi_yaml import extract_yaml_blocks
from scripts.test_api_assembly import assemble_full_api


def test_doc4_openapi_yaml():
    doc_path = ROOT / "API_SPECIFICATIONS.md"
    blocks = extract_yaml_blocks(doc_path)
    assert len(blocks) == 1

    spec = yaml.safe_load(blocks[0]["content"])
    assert spec["openapi"] == "3.1.0"
    assert len(spec["paths"]) >= 15
    assert "components" in spec
    assert "BearerAuth" in spec["components"]["securitySchemes"]

    # Required core endpoints
    assert "/reviews" in spec["paths"]
    assert "/reviews/{review_id}" in spec["paths"]
    assert "/reviews/{review_id}/status" in spec["paths"]
    assert "/reviews/{review_id}/approve" in spec["paths"]
    assert "/analytics/trends" in spec["paths"]
    assert "/rules/custom" in spec["paths"]
    assert "/teams/expertise" in spec["paths"]


def test_doc4_fastapi_assembly():
    app, schema = assemble_full_api()
    assert app is not None
    assert len(schema["paths"]) >= 15
