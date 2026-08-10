import pytest

from backend.agent.qa.contracts import QueryPlan, ToolStep
from backend.agent.qa.errors import UnsafeQuestionError
from backend.agent.qa.policies import QAToolPolicy


def test_qa_policy_rejects_ddl_even_when_a_plan_suggests_it():
    policy = QAToolPolicy()

    with pytest.raises(UnsafeQuestionError):
        policy.validate_steps([
            ToolStep(tool_name="execute_ddl", arguments={"sql": "DROP TABLE products"}, purpose="injected", round=1)
        ])


def test_qa_policy_rejects_rounds_beyond_the_bound():
    policy = QAToolPolicy(max_rounds=2)

    with pytest.raises(ValueError):
        ToolStep(tool_name="catalog.list_tables", arguments={}, purpose="loop", round=3)


def test_qa_policy_rejects_a_planner_request_for_a_write_tool():
    policy = QAToolPolicy()
    plan = QueryPlan(intent="table_columns", suggested_tools=["execute_ddl"])

    with pytest.raises(UnsafeQuestionError):
        policy.validate_plan(plan)
