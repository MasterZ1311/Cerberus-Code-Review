"""
Tests for the Cerberus dynamic plugin architecture, custom rules, and lifecycle hooks.
"""

import pytest
from fastapi.testclient import TestClient

from cerberus.api.app import app
from cerberus.core.plugins import BasePlugin, PluginManager
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse
from cerberus.plugins.secret_scanner import SecretScannerPlugin
from cerberus.plugins.team_style import TeamStylePlugin
from cerberus.providers.heuristic_engine import HeuristicEngine


class DummyTestPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__()
        self.name = "dummy_test"
        self.version = "0.1.0"
        self.author = "Unit Tester"
        self.description = "Plugin for automated testing"
        self.pre_hook_called = False
        self.post_hook_called = False

    def on_load(self) -> None:
        pass

    def on_unload(self) -> None:
        pass

    async def pre_review_hook(self, request: CodeReviewRequest) -> CodeReviewRequest:
        self.pre_hook_called = True
        request.code = request.code + "\n# Hook injected"
        return request

    async def post_review_hook(self, response: CodeReviewResponse) -> CodeReviewResponse:
        self.post_hook_called = True
        if response.results is None:
            response.results = {}
        if isinstance(response.results, dict):
            response.results["dummy_post_hook"] = True
        return response


@pytest.mark.asyncio
async def test_base_plugin_lifecycle():
    pm = PluginManager()
    plugin = DummyTestPlugin()
    pm.register_plugin(plugin)

    assert pm.get_plugin("dummy_test") is plugin
    plugins = pm.list_plugins()
    dummy_entry = next((p for p in plugins if p["name"] == "dummy_test"), None)
    assert dummy_entry is not None
    assert dummy_entry["is_enabled"] is True

    # Test hooks execution
    req = CodeReviewRequest(code="x = 1", file_path="app.py", language="python")
    modified_req = await pm.execute_pre_review_hooks(req)
    assert "# Hook injected" in modified_req.code
    assert plugin.pre_hook_called is True

    res = CodeReviewResponse(
        review_id="rev-test-123",
        status="completed",
        created_at="2026-11-16T12:00:00Z",
        overall_score=8.5,
        summary="Test",
        critical_issues=[],
        warnings=[],
        suggestions=[],
        agents_scheduled=["dummy"],
        results={},
    )
    res_mod = await pm.execute_post_review_hooks(res)
    assert res_mod.results.get("dummy_post_hook") is True
    assert plugin.post_hook_called is True

    # Test disabling plugin
    pm.disable_plugin("dummy_test")
    assert pm.get_plugin("dummy_test").is_enabled is False

    # Unregister
    pm.unregister_plugin("dummy_test")
    assert pm.get_plugin("dummy_test") is None


def test_heuristic_engine_custom_rules():
    engine = HeuristicEngine()
    engine.clear_custom_rules()

    custom_rules = [
        {
            "id": "CUSTOM-001",
            "pattern": r"TEST_CUSTOM_VULN",
            "title": "Custom Test Vulnerability",
            "severity": "HIGH",
            "category": "security",
            "message": "Found test vulnerability marker in source.",
        }
    ]

    engine.register_custom_rules("python", custom_rules)

    # Check finding generation
    test_code = "v = TEST_CUSTOM_VULN(arg=1)"
    findings, score = engine.analyze_security(test_code, language="python", filename="test.py")
    custom_findings = [f for f in findings if "CUSTOM-001" in f.id]
    assert len(custom_findings) == 1
    assert str(custom_findings[0].severity).upper() in ("SEVERITYENUM.HIGH", "HIGH")
    assert custom_findings[0].category == "security"

    # Clear custom rules
    engine.clear_custom_rules()
    findings_after, _ = engine.analyze_security(test_code, language="python", filename="test.py")
    custom_after = [f for f in findings_after if "CUSTOM-001" in f.id]
    assert len(custom_after) == 0


def test_builtin_secret_scanner_plugin():
    scanner = SecretScannerPlugin()
    rules = scanner.get_custom_rules()
    assert "python" in rules
    assert len(rules["python"]) >= 2

    # Verify AWS secret detection
    engine = HeuristicEngine()
    engine.clear_custom_rules()
    engine.register_custom_rules("python", rules["python"])

    code_with_leak = "aws_key = 'AKIAIOSFODNN7EXAMPLE'"
    findings, score = engine.analyze_security(code_with_leak, language="python", filename="config.py")
    secret_findings = [f for f in findings if "AWS-KEY" in f.id]
    assert len(secret_findings) >= 1
    assert str(secret_findings[0].severity).upper() in ("SEVERITYENUM.CRITICAL", "CRITICAL")


def test_builtin_team_style_plugin():
    style = TeamStylePlugin()
    rules = style.get_custom_rules()
    assert "python" in rules

    engine = HeuristicEngine()
    engine.clear_custom_rules()
    engine.register_custom_rules("python", rules["python"])

    code_with_print = 'print("debugging to stdout")'
    findings, score = engine.analyze_security(code_with_print, language="python", filename="worker.py")
    style_findings = [f for f in findings if "PRINT" in f.id]
    assert len(style_findings) >= 1
    assert str(style_findings[0].severity).upper() in ("SEVERITYENUM.LOW", "LOW")


def test_plugins_api_endpoints():
    client = TestClient(app)
    headers = {"Authorization": "Bearer cvai_dev_key_123"}

    # List plugins
    res = client.get("/api/v1/plugins", headers=headers)
    assert res.status_code == 200
    data = res.json()
    plugins = data["plugins"] if isinstance(data, dict) and "plugins" in data else data
    assert isinstance(plugins, list)
    plugin_names = [p["name"] for p in plugins]
    assert "secret_scanner" in plugin_names
    assert "team_conventions" in plugin_names

    # Disable plugin
    res_dis = client.post("/api/v1/plugins/secret_scanner/disable", headers=headers)
    assert res_dis.status_code == 200
    assert res_dis.json()["status"] == "success"

    # Enable plugin
    res_en = client.post("/api/v1/plugins/secret_scanner/enable", headers=headers)
    assert res_en.status_code == 200
    assert res_en.json()["status"] == "success"

    # Reload plugins
    res_rel = client.post("/api/v1/plugins/reload", headers=headers)
    assert res_rel.status_code == 200
    assert res_rel.json()["reloaded"] is True
