from backend.agent.orchestrator import Orchestrator
from backend.agent.router import Router
from backend.mcp.server import init_mcp_tools


def test_orchestrator_full_analysis():
    registry = init_mcp_tools()
    result = Orchestrator(registry).run_full_analysis()
    assert result["status"] == "completed"
    assert result["total_steps"] >= 6
    assert "er_diagram" in result
    assert result["er_diagram"]["table_count"] > 0


def test_orchestrator_has_relations():
    registry = init_mcp_tools()
    result = Orchestrator(registry).run_full_analysis()
    merge = result.get("merge_result", {})
    assert merge["summary"]["high_confidence"] > 0


def test_router():
    plan = Router().plan_analysis(
        {"summary": {"total_tables": 30, "total_views": 3, "total_procedures": 8, "total_orm_files": 5}}
    )
    assert len(plan["phases"]) == 4
    assert plan["summary"]["tables"] == 30

