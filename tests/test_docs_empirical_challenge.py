"""
Empirical Challenge Test Suite for Docs 5, 6, 7, and 8.
Validates:
- Doc 5 (DEPLOYMENT_GUIDE.md): Dockerfile, docker-compose.yml, K8s manifests, Helm templates
- Doc 6 (MONITORING_OPERATIONS.md): Prometheus rules, Grafana JSON, AlertManager YAML, PromQL
- Doc 7 (TESTING_STRATEGY.md): Pytest fixtures, test suites, Locust load test scripts via AST
- Doc 8 (PRODUCTION_LAUNCH_MANUAL.md): Shell scripts, checklists (100+ items), runbooks
- Universal: Absence of placeholder tokens (TODO, FIXME, <replace_me>)
"""

import ast
import json
import os
import re

import pytest
import yaml
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC5_PATH = os.path.join(REPO_ROOT, "DEPLOYMENT_GUIDE.md")
DOC6_PATH = os.path.join(REPO_ROOT, "MONITORING_OPERATIONS.md")
DOC7_PATH = os.path.join(REPO_ROOT, "TESTING_STRATEGY.md")
DOC8_PATH = os.path.join(REPO_ROOT, "PRODUCTION_LAUNCH_MANUAL.md")


def extract_code_blocks(filepath):
    """Extract code blocks from markdown file with line numbers and language."""
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()
    blocks = []
    in_block = False
    current_lang = ""
    current_lines = []
    start_line = 0
    for idx, line in enumerate(lines):
        if line.startswith("```"):
            if not in_block:
                in_block = True
                current_lang = line.strip()[3:].strip()
                current_lines = []
                start_line = idx + 1
            else:
                in_block = False
                blocks.append(
                    {
                        "start_line": start_line,
                        "lang": current_lang,
                        "content": "".join(current_lines),
                        "file": filepath,
                    }
                )
        elif in_block:
            current_lines.append(line)
    return blocks


# ============================================================================
# Universal Checks
# ============================================================================


@pytest.mark.parametrize("filepath", [DOC5_PATH, DOC6_PATH, DOC7_PATH, DOC8_PATH])
def test_no_forbidden_placeholders(filepath):
    """Verify strict absence of placeholder tokens: TODO, FIXME, <replace_me>, <replace-me>, REPLACE_ME."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    forbidden = ["TODO", "FIXME", "<replace_me>", "<replace-me>", "REPLACE_ME"]
    violations = []
    for tok in forbidden:
        matches = [m.start() for m in re.finditer(re.escape(tok), content)]
        if matches:
            violations.append(f"{tok} found {len(matches)} times")
    assert not violations, f"Forbidden placeholders found in {os.path.basename(filepath)}: {violations}"


@pytest.mark.parametrize("filepath", [DOC5_PATH, DOC6_PATH, DOC7_PATH, DOC8_PATH])
def test_all_code_blocks_have_language(filepath):
    """Verify that every markdown code block specifies a language tag."""
    blocks = extract_code_blocks(filepath)
    missing = [b["start_line"] for b in blocks if not b["lang"]]
    assert not missing, f"Code blocks missing language tag in {os.path.basename(filepath)} at lines: {missing}"


# ============================================================================
# Doc 5: DEPLOYMENT_GUIDE.md Checks
# ============================================================================


def test_doc5_dockerfile_multi_stage():
    """Verify Dockerfile syntax, multi-stage targets, security context, non-root user."""
    blocks = extract_code_blocks(DOC5_PATH)
    dockerfile_blocks = [b for b in blocks if b["lang"] == "dockerfile"]
    assert len(dockerfile_blocks) >= 1, "Dockerfile block not found in DEPLOYMENT_GUIDE.md"

    content = dockerfile_blocks[0]["content"]
    from_lines = [line.strip() for line in content.splitlines() if line.strip().upper().startswith("FROM")]
    assert len(from_lines) >= 4, (
        f"Expected 4 multi-stage builds (builder, tester, security-scan, runtime), found: {from_lines}"
    )
    assert "10001" in content, "Non-root user (10001) not specified in runtime Dockerfile"
    assert "ENTRYPOINT" in content, "ENTRYPOINT instruction missing from Dockerfile"


def test_doc5_docker_compose_valid_yaml():
    """Verify docker-compose.yml YAML syntax and essential services."""
    blocks = extract_code_blocks(DOC5_PATH)
    compose_blocks = [b for b in blocks if b["lang"] == "yaml" and "docker-compose.yml" in b["content"][:100]]
    assert len(compose_blocks) == 1, "docker-compose.yml code block not found"

    content = compose_blocks[0]["content"]
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "docker-compose.yml failed to parse as dictionary"
    assert "services" in data, "services key missing in docker-compose.yml"

    services = data["services"]
    required_services = ["api", "db", "redis", "mock-watsonx", "prometheus", "grafana", "jaeger"]
    for s in required_services:
        assert s in services, f"Service '{s}' missing in docker-compose.yml"


def test_doc5_k8s_manifests():
    """Verify Kubernetes manifests: Deployment, Service, Ingress, HPA, PDB, ConfigMap, Secret, NetworkPolicy."""
    blocks = extract_code_blocks(DOC5_PATH)
    k8s_files = [
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        "k8s/ingress.yaml",
        "k8s/hpa.yaml",
        "k8s/pdb.yaml",
        "k8s/configmap.yaml",
        "k8s/secret.yaml",
        "k8s/networkpolicy.yaml",
    ]

    found_manifests = {}
    for b in blocks:
        if b["lang"] == "yaml":
            first_lines = b["content"][:120]
            for kf in k8s_files:
                if kf in first_lines:
                    found_manifests[kf] = b["content"]

    for kf in k8s_files:
        assert kf in found_manifests, f"Manifest {kf} missing from DEPLOYMENT_GUIDE.md"
        docs = list(yaml.safe_load_all(found_manifests[kf]))
        assert len(docs) >= 1, f"No YAML docs in {kf}"
        for doc in docs:
            assert "apiVersion" in doc, f"Missing apiVersion in {kf}"
            assert "kind" in doc, f"Missing kind in {kf}"
            assert "metadata" in doc, f"Missing metadata in {kf}"

    deploy_doc = yaml.safe_load(found_manifests["k8s/deployment.yaml"])
    assert deploy_doc["kind"] == "Deployment"
    spec = deploy_doc["spec"]
    template_spec = spec["template"]["spec"]
    containers = template_spec["containers"]
    assert len(containers) >= 1, "Deployment containers list is empty"
    api_container = containers[0]

    assert "resources" in api_container, "resources limits/requests missing in Deployment"
    assert "requests" in api_container["resources"] and "limits" in api_container["resources"]
    assert "livenessProbe" in api_container, "livenessProbe missing in Deployment"
    assert "readinessProbe" in api_container, "readinessProbe missing in Deployment"
    assert "startupProbe" in api_container, "startupProbe missing in Deployment"
    assert "securityContext" in api_container, "securityContext missing in container"
    assert api_container["securityContext"].get("readOnlyRootFilesystem") is True
    assert api_container["securityContext"].get("runAsNonRoot") is True


def test_doc5_helm_chart_and_values():
    """Verify Helm Chart.yaml, values.yaml, and deployment templates."""
    blocks = extract_code_blocks(DOC5_PATH)
    chart_block = next((b for b in blocks if "Chart.yaml" in b["content"][:100]), None)
    values_block = next((b for b in blocks if "values.yaml" in b["content"][:100]), None)
    deploy_tpl_block = next((b for b in blocks if "templates/deployment.yaml" in b["content"][:100]), None)

    assert chart_block is not None, "Helm Chart.yaml block missing"
    assert values_block is not None, "Helm values.yaml block missing"
    assert deploy_tpl_block is not None, "Helm templates/deployment.yaml block missing"

    chart_data = yaml.safe_load(chart_block["content"])
    assert chart_data["apiVersion"] == "v2"
    assert chart_data["name"] in ("codevault", "cerberus")
    assert "version" in chart_data

    values_data = yaml.safe_load(values_block["content"])
    assert isinstance(values_data, dict)
    assert "replicaCount" in values_data
    assert "resources" in values_data
    assert "autoscaling" in values_data
    assert "securityContext" in values_data
    assert "podSecurityContext" in values_data

    tpl_content = deploy_tpl_block["content"]
    assert "livenessProbe:" in tpl_content, "livenessProbe missing in Helm deployment template"
    assert "readinessProbe:" in tpl_content, "readinessProbe missing in Helm deployment template"


def test_doc5_python_iam_auth_syntax():
    """Verify python code in DEPLOYMENT_GUIDE.md is syntactically valid."""
    blocks = extract_code_blocks(DOC5_PATH)
    python_blocks = [b for b in blocks if b["lang"] == "python"]
    assert len(python_blocks) >= 1
    for b in python_blocks:
        tree = ast.parse(b["content"])
        assert len(tree.body) > 0


# ============================================================================
# Doc 6: MONITORING_OPERATIONS.md Checks
# ============================================================================


def test_doc6_prometheus_alerting_rules_yaml_and_promql():
    """Verify Prometheus AlertManager rules YAML syntax and extract PromQL expressions."""
    blocks = extract_code_blocks(DOC6_PATH)
    yaml_blocks = [
        b for b in blocks
        if b["lang"] == "yaml" and ("codevault-alerts.yaml" in b["content"][:100] or "cerberus-alerts.yaml" in b["content"][:100])
    ]
    assert len(yaml_blocks) >= 1, "cerberus-alerts.yaml not found in MONITORING_OPERATIONS.md"

    content = yaml_blocks[0]["content"]
    data = yaml.safe_load(content)
    assert "spec" in data and "groups" in data["spec"], "No 'groups' found in codevault-alerts.yaml"

    total_rules = 0
    promql_exprs = []
    for group in data["spec"]["groups"]:
        rules = group.get("rules", [])
        total_rules += len(rules)
        for r in rules:
            assert "alert" in r, f"Rule missing 'alert' name: {r}"
            assert "expr" in r, f"Rule {r.get('alert')} missing 'expr'"
            assert "for" in r, f"Rule {r.get('alert')} missing 'for' duration"
            assert "labels" in r, f"Rule {r.get('alert')} missing labels"
            assert "annotations" in r, f"Rule {r.get('alert')} missing annotations"
            promql_exprs.append((r["alert"], r["expr"]))

    print(f"\n[Doc 6] Validated {total_rules} alerting rules across {len(data['spec']['groups'])} rule groups.")
    assert total_rules >= 30, f"Expected 30+ AlertManager rules as per R6, found: {total_rules}"

    # Check for balanced parens, braces, brackets
    for alert_name, expr in promql_exprs:
        assert len(expr.strip()) > 0, f"Empty expression for alert {alert_name}"
        assert expr.count("(") == expr.count(")"), f"Mismatched parens in {alert_name}: {expr}"
        assert expr.count("{") == expr.count("}"), f"Mismatched braces in {alert_name}: {expr}"
        assert expr.count("[") == expr.count("]"), f"Mismatched square brackets in {alert_name}: {expr}"


def test_doc6_alertmanager_config_yaml():
    """Verify AlertManager routing configuration YAML."""
    blocks = extract_code_blocks(DOC6_PATH)
    am_blocks = [b for b in blocks if b["lang"] == "yaml" and "alertmanager.yml" in b["content"][:100]]
    assert len(am_blocks) >= 1, "alertmanager.yml not found in MONITORING_OPERATIONS.md"

    content = am_blocks[0]["content"]
    data = yaml.safe_load(content)
    assert "route" in data, "route missing in alertmanager.yml"
    assert "receivers" in data, "receivers missing in alertmanager.yml"
    receiver_names = [r["name"] for r in data["receivers"]]
    assert "slack-default" in receiver_names
    assert "pagerduty-critical" in receiver_names


def test_doc6_grafana_dashboard_json():
    """Verify Grafana dashboard JSON syntax and 20+ panels across domains."""
    blocks = extract_code_blocks(DOC6_PATH)
    json_blocks = [
        b for b in blocks
        if b["lang"] == "json" and ("codevault-overview.json" in b["content"][:100] or "cerberus-overview.json" in b["content"][:100])
    ]
    assert len(json_blocks) >= 1, "Grafana dashboard JSON block not found"

    content = json_blocks[0]["content"]
    lines = [line for line in content.splitlines() if not line.strip().startswith("//")]
    dashboard = json.loads("\n".join(lines))

    assert "title" in dashboard, "Missing title in Grafana dashboard"
    panels = dashboard.get("panels", [])
    assert len(panels) >= 20, f"Expected 20+ Grafana dashboard panels as per R6, found: {len(panels)}"

    for p in panels:
        assert "id" in p, f"Panel missing id: {p}"
        assert "title" in p, f"Panel missing title: {p}"
    print(f"\n[Doc 6] Validated {len(panels)} Grafana dashboard panels.")


def test_doc6_python_instrumentation_syntax():
    """Verify OpenTelemetry and custom Prometheus metric exporter python scripts."""
    blocks = extract_code_blocks(DOC6_PATH)
    py_blocks = [b for b in blocks if b["lang"] == "python"]
    assert len(py_blocks) >= 1, "Python blocks missing in MONITORING_OPERATIONS.md"
    for b in py_blocks:
        tree = ast.parse(b["content"])
        assert len(tree.body) > 0


# ============================================================================
# Doc 7: TESTING_STRATEGY.md Checks
# ============================================================================


def test_doc7_python_syntax_and_test_cases():
    """Verify pytest fixtures, test cases, and Locust scripts parse with ast."""
    blocks = extract_code_blocks(DOC7_PATH)
    py_blocks = [b for b in blocks if b["lang"] == "python"]
    assert len(py_blocks) >= 5, f"Expected multiple Python test blocks, found {len(py_blocks)}"

    test_func_count = 0
    fixture_count = 0
    locust_classes = 0

    for b in py_blocks:
        content = b["content"]
        tree = ast.parse(content)
        assert len(tree.body) > 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_func_count += 1
                for dec in node.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            dec_name = dec.func.id
                        elif isinstance(dec.func, ast.Attribute):
                            dec_name = dec.func.attr
                    if "fixture" in dec_name:
                        fixture_count += 1
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name in ["HttpUser", "User", "FastHttpUser"]:
                        locust_classes += 1

    print(
        f"\n[Doc 7] Validated {len(py_blocks)} Python blocks. Found {test_func_count} test functions, {fixture_count} fixtures, {locust_classes} Locust User classes."
    )
    assert test_func_count >= 30, f"Expected 30+ test cases, found {test_func_count}"
    assert fixture_count >= 5, f"Expected 5+ fixtures, found {fixture_count}"
    assert locust_classes >= 1, f"Expected Locust User class, found {locust_classes}"


def test_doc7_pytest_ini_and_workflow_yaml():
    """Verify pytest.ini and GitHub Actions workflow YAML syntax in Doc 7."""
    blocks = extract_code_blocks(DOC7_PATH)
    yaml_blocks = [b for b in blocks if b["lang"] == "yaml"]
    assert len(yaml_blocks) >= 1, "Expected YAML blocks in TESTING_STRATEGY.md"
    for b in yaml_blocks:
        data = yaml.safe_load(b["content"])
        assert isinstance(data, dict), f"Failed to parse YAML block in Doc 7: {b['content'][:80]}"


# ============================================================================
# Doc 8: PRODUCTION_LAUNCH_MANUAL.md Checks
# ============================================================================


def test_doc8_checklist_count_100_plus():
    """Verify 100+ checklist items in PRODUCTION_LAUNCH_MANUAL.md."""
    with open(DOC8_PATH, encoding="utf-8") as f:
        content = f.read()

    table_items = re.findall(r"^\|\s*(\d+)\s*\|([^|]+)\|", content, re.MULTILINE)
    count = len(table_items)
    print(f"\n[Doc 8] Found {count} verification checklist items in PRODUCTION_LAUNCH_MANUAL.md tables.")
    assert count >= 100, f"Expected 100+ checklist items as per R8, found: {count}"


def test_doc8_scripts_and_python_syntax():
    """Verify shell scripts, python scripts, and SQL blocks in Doc 8."""
    blocks = extract_code_blocks(DOC8_PATH)
    py_blocks = [b for b in blocks if b["lang"] == "python"]
    for b in py_blocks:
        tree = ast.parse(b["content"])
        assert len(tree.body) > 0

    yaml_blocks = [b for b in blocks if b["lang"] == "yaml"]
    for b in yaml_blocks:
        data = yaml.safe_load(b["content"])
        assert isinstance(data, dict)


# ============================================================================
# Empirical Bug Reproduction & Contract Discrepancy Tests
# ============================================================================


def test_empirical_probe_contract_failure():
    """
    Empirically reproduce the probe route mismatch between k8s/deployment.yaml and actual/documented routes.
    Demonstrates that k8s/deployment.yaml probe paths return 404.
    """
    from cerberus.api.app import app

    client = TestClient(app)

    # Existing routes return 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code == 200

    # Routes configured in k8s/deployment.yaml return 404!
    assert client.get("/api/v1/health/liveness").status_code == 404
    assert client.get("/api/v1/health/readiness").status_code == 404
    assert client.get("/api/v1/health/startup").status_code == 404


def test_empirical_promql_syntax_error_in_doc6():
    """
    Empirically detect invalid PromQL syntax where range vector [5m] is placed inside label braces.
    """
    blocks = extract_code_blocks(DOC6_PATH)
    alert_block = [
        b for b in blocks
        if ("codevault-alerts.yaml" in b["content"][:100] or "cerberus-alerts.yaml" in b["content"][:100])
    ][0]
    data = yaml.safe_load(alert_block["content"])

    syntax_errors = []
    for g in data["spec"]["groups"]:
        for r in g["rules"]:
            expr = r["expr"]
            name = r["alert"]
            inside_braces = re.findall(r"\{([^}]+)\}", expr)
            for b_inner in inside_braces:
                if re.search(r"\[\s*\d+[smhdwy]\s*\]", b_inner):
                    syntax_errors.append((name, expr))

    assert len(syntax_errors) == 1, f"Expected 1 invalid PromQL expression to be identified, found: {syntax_errors}"
    assert syntax_errors[0][0] == "HighReviewFailureRate"
    assert '{status="failed"[5m]}' in syntax_errors[0][1]
