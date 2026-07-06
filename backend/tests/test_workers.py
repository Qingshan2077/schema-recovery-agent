from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.survey import SurveyWorker
from backend.mcp.server import init_mcp_tools


def test_survey_worker():
    registry = init_mcp_tools()
    result = SurveyWorker(registry).run({})
    assert result["status"] == "success"
    assert result["summary"]["total_tables"] == 30
    assert result["summary"]["total_views"] == 3
    assert result["summary"]["total_procedures"] >= 8


def test_column_worker():
    registry = init_mcp_tools()
    survey_result = SurveyWorker(registry).run({})
    result = ColumnWorker(registry).run({"survey_result": survey_result})
    assert result["status"] == "success"
    assert result["relation_count"] > 0


def test_name_worker():
    registry = init_mcp_tools()
    result = NameWorker(registry).run({})
    assert result["status"] == "success"
    assert result["column_name_matches"]["count"] > 0


def test_code_worker():
    registry = init_mcp_tools()
    survey_result = SurveyWorker(registry).run({})
    result = CodeWorker(registry).run({"survey_result": survey_result})
    assert result["status"] == "success"
    assert result["relation_count"] > 0

