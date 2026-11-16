"""
Empirical test for PHASE_1_DETAILED_IMPLEMENTATION.md code block execution.
"""

import pytest
import asyncio
from pathlib import Path
from scripts.verify_python_blocks import extract_python_blocks, ROOT


@pytest.mark.asyncio
async def test_doc1_code_execution():
    doc1 = extract_python_blocks(ROOT / "PHASE_1_DETAILED_IMPLEMENTATION.md")[0]
    namespace = {}
    exec(doc1["content"], namespace)

    assert "MasterOrchestrator" in namespace
    assert "ResultAggregationService" in namespace
    assert "SecurityReviewAgent" in namespace
    assert "PerformanceReviewAgent" in namespace
    assert "TestingReviewAgent" in namespace
    assert "DocumentationReviewAgent" in namespace
    assert "BestPracticesReviewAgent" in namespace

    # Instantiate models
    req_cls = namespace["CodeReviewRequest"]
    req = req_cls(
        code="def hello():\n    print('world')\n",
        language="python",
        context=namespace["ReviewContext"](repository="test/repo", commit_hash="abc1234"),
        active_agents=["security", "performance", "testing", "documentation", "best_practices"],
        blocking_threshold=namespace["SeverityEnum"].HIGH,
    )
    assert req.language == "python"
    assert req.blocking_threshold == namespace["SeverityEnum"].HIGH

    # Test Orchestrator instantiation
    orch_cls = namespace["MasterOrchestrator"]
    orch = orch_cls()
    assert orch.security_agent is not None
    assert orch.performance_agent is not None
    assert orch.testing_agent is not None
    assert orch.documentation_agent is not None
    assert orch.best_practices_agent is not None
    assert orch.workflow_graph is not None

    # Test Aggregation Service
    agg_cls = namespace["ResultAggregationService"]
    agg = agg_cls()
    assert agg is not None

    # Test full end-to-end review via MasterOrchestrator.execute_review
    response = await orch.execute_review(req)
    assert response.review_id is not None
    assert response.status == "completed"
    assert len(response.findings) >= 0
    assert 0.0 <= response.overall_score <= 100.0
    assert response.severity_summary is not None
    assert len(response.agent_results) == 5
    print(
        "\n[SUCCESS] Orchestrator end-to-end review executed:",
        response.status,
        "Score:",
        response.overall_score,
        "Agents:",
        len(response.agent_results),
    )
