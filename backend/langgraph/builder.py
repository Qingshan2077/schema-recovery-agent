"""Build the schema recovery LangGraph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.langgraph.edges import route_after_survey, should_continue_after_code
from backend.langgraph.nodes.analysis_nodes import code_node, column_node, merge_node, name_node, orm_node, skipped_orm_node, survey_node
from backend.langgraph.state import AgentState
from backend.mcp.tool_registry import ToolRegistry


def build_schema_recovery_graph(tool_registry: ToolRegistry):
    builder = StateGraph(AgentState)

    builder.add_node("survey_node", lambda state: survey_node(state, tool_registry))
    builder.add_node("column_node", lambda state: column_node(state, tool_registry))
    builder.add_node("name_node", lambda state: name_node(state, tool_registry))
    builder.add_node("code_node", lambda state: code_node(state, tool_registry))
    builder.add_node("orm_node", lambda state: orm_node(state, tool_registry))
    builder.add_node("skip_orm_node", skipped_orm_node)
    builder.add_node("merge_node", lambda state: merge_node(state, tool_registry))

    builder.set_entry_point("survey_node")
    builder.add_conditional_edges("survey_node", route_after_survey)
    builder.add_edge(["column_node", "name_node"], "code_node")
    builder.add_conditional_edges(
        "code_node",
        should_continue_after_code,
        {"orm": "orm_node", "skip_orm": "skip_orm_node"},
    )
    builder.add_edge("orm_node", "merge_node")
    builder.add_edge("skip_orm_node", "merge_node")
    builder.add_edge("merge_node", END)

    return builder.compile()


