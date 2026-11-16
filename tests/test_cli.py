"""
Tests for cerberus CLI Commands.
"""

from typer.testing import CliRunner

from cerberus.cli.main import app

runner = CliRunner()


def test_cli_health():
    result = runner.invoke(app, ["health"])
    assert result.exit_code == 0
    assert "HEALTHY" in result.stdout


def test_cli_list_agents():
    result = runner.invoke(app, ["list-agents"])
    assert result.exit_code == 0
    assert "security" in result.stdout
    assert "performance" in result.stdout


def test_cli_create_api_key():
    result = runner.invoke(app, ["create-api-key", "--name", "test-key"])
    assert result.exit_code == 0
    assert "cvai_" in result.stdout


def test_cli_review_snippet():
    result = runner.invoke(app, ["review", "--snippet", "def add(a, b): return a + b"])
    assert result.exit_code == 0
    assert "Overall Quality Score" in result.stdout
