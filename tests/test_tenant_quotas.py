"""
Tests for Multi-Tenant Quota Metering, Tier Enforcement, and CLI commands.
"""

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cerberus.api.app import app
from cerberus.cli.main import app as cli_app
from cerberus.core.quota import TenantQuotaManager


def test_quota_manager_tier_limits():
    qm = TenantQuotaManager()

    assert qm.get_tier_limit("free") == 100
    assert qm.get_tier_limit("team") == 2500
    assert qm.get_tier_limit("pro") == 5000
    assert qm.get_tier_limit("enterprise") == 100000
    assert qm.get_tier_limit("unlimited") == 10000000


@pytest.mark.asyncio
async def test_quota_consumption_and_exhaustion():
    qm = TenantQuotaManager()
    tenant = "tenant_test_exhaust"

    # Default assigned tier is free (100)
    qm.set_tier(tenant, "free")
    info = await qm.get_quota_status(tenant)
    assert info["tier"] == "free"
    assert info["limit"] == 100
    assert info["used"] == 0

    # Advance usage directly to limit - 1
    key = qm._get_period_key(tenant)
    qm._usage[key] = 99

    # 100th review allowed
    allowed, current, limit = await qm.check_quota(tenant)
    assert allowed is True
    await qm.record_review(tenant)

    # 101st review blocked
    allowed, current, limit = await qm.check_quota(tenant)
    assert allowed is False

    # Upgrade to team (2500) -> immediately unblocked
    qm.set_tier(tenant, "team")
    allowed_up, _, _ = await qm.check_quota(tenant)
    assert allowed_up is True
    status_up = await qm.get_quota_status(tenant)
    assert status_up["limit"] == 2500

    # Reset usage
    await qm.reset_usage(tenant)
    status_reset = await qm.get_quota_status(tenant)
    assert status_reset["used"] == 0


def test_quota_api_endpoints():
    client = TestClient(app)
    headers = {"Authorization": "Bearer cvai_dev_key_123"}

    # 1. Get tiers list
    res_tiers = client.get("/api/v1/tenants/tiers", headers=headers)
    assert res_tiers.status_code == 200
    tiers_data = res_tiers.json()
    assert "tiers" in tiers_data
    tier_names = [t["tier"] for t in tiers_data["tiers"]]
    assert "pro" in tier_names
    assert "enterprise" in tier_names

    # 2. Get current tenant quota
    res_cur = client.get("/api/v1/tenants/current", headers=headers)
    assert res_cur.status_code == 200
    cur_data = res_cur.json()
    assert "tenant_id" in cur_data
    assert "tier" in cur_data
    assert "used" in cur_data
    assert "limit" in cur_data

    # 3. Upgrade tenant tier
    res_up = client.post(
        "/api/v1/tenants/upgrade",
        headers=headers,
        json={"tier": "enterprise"},
    )
    assert res_up.status_code == 200
    up_data = res_up.json()
    assert up_data["status"] == "success"
    assert up_data["tier"] == "enterprise"
    assert up_data["limit"] == 100000


def test_cli_plugins_and_quotas_commands():
    runner = CliRunner()

    # CLI: list-plugins
    result_plugins = runner.invoke(cli_app, ["list-plugins"])
    assert result_plugins.exit_code == 0
    assert "Registered Plugins" in result_plugins.output

    # CLI: quotas
    result_quotas = runner.invoke(cli_app, ["quotas", "--tenant", "default"])
    assert result_quotas.exit_code == 0
    assert "Tenant Quota" in result_quotas.output or "Active Tier" in result_quotas.output
