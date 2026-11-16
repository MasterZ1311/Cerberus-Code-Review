"""
Unit and Integration Tests for ZIP Archive Project Code Review.
Tests ZIP extraction security, multi-file orchestrator review, REST endpoints, and CLI.
"""

import io
import json
import zipfile
import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from cerberus.agents.orchestrator import orchestrator
from cerberus.api.app import app
from cerberus.cli.main import app as cli_app
from cerberus.core.zip_processor import (
    extract_code_from_zip,
    is_safe_zip_path,
    detect_language_from_path,
    is_ignored_path,
)
from cerberus.models.schemas import SeverityEnum, ZipReviewResponse


def _create_sample_zip_bytes(files_dict: dict) -> bytes:
    """Helper to create an in-memory zip archive from a dict of {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files_dict.items():
            if isinstance(content, str):
                zf.writestr(path, content.encode("utf-8"))
            else:
                zf.writestr(path, content)
    return buf.getvalue()


# =====================================================================
# 1. CORE ZIP PROCESSOR & SECURITY TESTS
# =====================================================================


def test_is_safe_zip_path_validation():
    assert is_safe_zip_path("src/app.py") is True
    assert is_safe_zip_path("nested/deep/module/code.js") is True

    # Rejection of Zip-Slip traversal attacks
    assert is_safe_zip_path("../app.py") is False
    assert is_safe_zip_path("src/../../etc/passwd") is False
    assert is_safe_zip_path("/etc/shadow") is False
    assert is_safe_zip_path("\\windows\\system32") is False


def test_language_detection():
    assert detect_language_from_path("main.py") == "python"
    assert detect_language_from_path("src/index.js") == "javascript"
    assert detect_language_from_path("app/Component.tsx") == "typescript"
    assert detect_language_from_path("db/schema.sql") == "sql"
    assert detect_language_from_path("Service.java") == "java"
    assert detect_language_from_path("main.go") == "go"
    assert detect_language_from_path("image.png") is None
    assert detect_language_from_path("binary.dll") is None


def test_ignored_path_filters():
    assert is_ignored_path("__pycache__/app.cpython-313.pyc") is True
    assert is_ignored_path("node_modules/express/index.js") is True
    assert is_ignored_path(".git/HEAD") is True
    assert is_ignored_path(".venv/lib/site.py") is True
    assert is_ignored_path(".hidden_file.py") is True
    assert is_ignored_path("assets/logo.png") is True
    assert is_ignored_path("src/models/user.py") is False


def test_extract_code_from_zip_clean():
    zip_bytes = _create_sample_zip_bytes(
        {
            "src/main.py": "def main():\n    print('Hello World')\n",
            "src/auth.py": "import os\nAPI_KEY = 'sk-live-12345'\n",
            "README.md": "# Project Title",
            ".git/config": "secret=true",
            "assets/photo.png": b"\x89PNG\r\n\x1a\n",
        }
    )

    result = extract_code_from_zip(zip_bytes, project_name="TestProject")
    assert result.project_name == "TestProject"
    assert len(result.code_files) == 2
    paths = [f.path for f in result.code_files]
    assert "src/main.py" in paths
    assert "src/auth.py" in paths
    assert result.language_distribution.get("python") == 2
    assert result.total_code_lines > 0


def test_extract_code_from_zip_slip_rejection():
    # Construct archive with unsafe path traversal
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../malicious.py", "import os; os.system('rm -rf /')")
        zf.writestr("valid.py", "print('clean')")

    result = extract_code_from_zip(buf.getvalue(), project_name="MaliciousTest")
    assert len(result.code_files) == 1
    assert result.code_files[0].path == "valid.py"
    assert any("unsafe path" in s for s in result.skipped_files)


# =====================================================================
# 2. ORCHESTRATOR ZIP REVIEW TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_orchestrator_execute_zip_review():
    sample_files = {
        "src/clean.py": """
def add(a: int, b: int) -> int:
    \"\"\"Sum two integers.\"\"\"
    return a + b
""",
        "src/vulnerable.py": """
import os
def run_command(cmd):
    # Security vulnerability: command injection
    os.system(cmd)
""",
    }
    zip_bytes = _create_sample_zip_bytes(sample_files)

    response: ZipReviewResponse = await orchestrator.execute_zip_review(
        zip_source=zip_bytes, project_name="MultiFileApp", agents=["security", "quality"]
    )

    assert response.project_name == "MultiFileApp"
    assert response.status == "completed"
    assert response.reviewed_files_count == 2
    assert len(response.file_reviews) == 2
    assert response.overall_project_score < 100.0

    # Ensure vulnerable file was detected
    vuln_rev = next(fr for fr in response.file_reviews if "vulnerable" in fr.file_path)
    assert vuln_rev.findings_count > 0

    # Ensure collaborative consensus exists
    assert response.collaborative_consensus is not None
    assert "pr_action" in response.collaborative_consensus


@pytest.mark.asyncio
async def test_orchestrator_empty_zip_handling():
    # Archive with no code files
    zip_bytes = _create_sample_zip_bytes(
        {
            "README.txt": "Just notes",
            "logo.png": b"\x89PNG\r\n\x1a\n",
        }
    )

    response = await orchestrator.execute_zip_review(zip_source=zip_bytes, project_name="EmptyCodeZip")

    assert response.reviewed_files_count == 0
    assert response.overall_project_score == 100.0
    assert "No supported source code" in response.summary


# =====================================================================
# 3. FASTAPI REST ENDPOINTS TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_upload_zip_endpoint():
    sample_files = {
        "calculator.py": "def add(x, y):\n    return x + y\n",
        "database.py": "import os\ndef query(user):\n    return 'SELECT * FROM users WHERE id = ' + user\n",
    }
    zip_bytes = _create_sample_zip_bytes(sample_files)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upload using multipart/form-data
        files = {"file": ("project.zip", zip_bytes, "application/zip")}
        data = {"project_name": "CalculatorProject", "agents": "security,performance"}

        res = await client.post(
            "/api/v1/review/upload-zip", files=files, data=data, headers={"Authorization": "Bearer cvai_dev_key_123"}
        )

        assert res.status_code == 200
        res_data = res.json()
        assert res_data["project_name"] == "CalculatorProject"
        assert res_data["reviewed_files_count"] == 2
        assert "overall_project_score" in res_data
        assert len(res_data["file_reviews"]) == 2

        # Verify retrieval via GET /api/v1/review/zip/{review_id}
        zip_rev_id = res_data["review_id"]
        get_res = await client.get(
            f"/api/v1/review/zip/{zip_rev_id}", headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert get_res.status_code == 200
        assert get_res.json()["review_id"] == zip_rev_id


@pytest.mark.asyncio
async def test_upload_non_zip_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("script.py", b"print('hello')", "text/x-python")}
        res = await client.post(
            "/api/v1/review/upload-zip", files=files, headers={"Authorization": "Bearer cvai_dev_key_123"}
        )
        assert res.status_code == 400
        assert "extension" in res.json()["detail"].lower()


# =====================================================================
# 4. CLI ZIP REVIEW TEST
# =====================================================================


def test_cli_zip_review(tmp_path):
    runner = CliRunner(env={"COLUMNS": "200"})
    zip_file = tmp_path / "sample_cli_project.zip"

    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("app/server.py", "import os\ndef ping(ip):\n    os.system('ping ' + ip)\n")
        zf.writestr("app/math_util.py", "def multiply(a, b):\n    return a * b\n")

    result = runner.invoke(cli_app, ["review", str(zip_file), "--agents", "security,quality"])
    assert result.exit_code == 0
    assert "Project Archive Review Summary" in result.stdout
    assert "File-by-File Quality Breakdown" in result.stdout
    assert "server.py" in result.stdout
