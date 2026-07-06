"""Conditional routing for the schema recovery graph."""

from __future__ import annotations

from langgraph.graph import END

from backend.langgraph.state import AgentState


def route_after_survey(state: AgentState) -> list[str] | str:
    if state.get("status") == "error" or not state.get("survey_result"):
        return END
    return ["column_node", "name_node"]


def should_continue_after_code(state: AgentState) -> str:
    survey = state.get("survey_result") or {}
    orm_count = survey.get("orm_files", {}).get("count")
    if orm_count is None:
        orm_count = survey.get("summary", {}).get("total_orm_files", 0)
    return "orm" if orm_count and orm_count > 0 else "skip_orm"


