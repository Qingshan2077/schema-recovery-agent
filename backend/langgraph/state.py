"""Shared LangGraph state and result adapters."""

from __future__ import annotations

import operator
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, NotRequired, TypedDict


class AgentState(TypedDict):
    """State shared by all schema recovery graph nodes."""

    session_id: str
    started_at: str
    status: str
    survey_result: dict[str, Any] | None
    column_result: dict[str, Any] | None
    name_result: dict[str, Any] | None
    code_result: dict[str, Any] | None
    orm_result: dict[str, Any] | None
    merge_result: dict[str, Any] | None
    plan: dict[str, Any] | None
    total_steps: int
    errors: Annotated[list[str], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
    worker_call_log: Annotated[list[dict[str, Any]], operator.add]
    completed_workers: Annotated[list[str], operator.add]
    skipped_workers: Annotated[list[str], operator.add]
    er_diagram: NotRequired[dict[str, Any]]


def build_initial_state(session_id: str | None = None) -> AgentState:
    return {
        "session_id": session_id or f"ana_{uuid.uuid4().hex[:12]}",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "survey_result": None,
        "column_result": None,
        "name_result": None,
        "code_result": None,
        "orm_result": None,
        "merge_result": None,
        "plan": None,
        "total_steps": 7,
        "errors": [],
        "steps": [],
        "worker_call_log": [],
        "completed_workers": [],
        "skipped_workers": [],
    }


def build_result_from_state(state: AgentState) -> dict[str, Any]:
    steps = state.get("steps", [])
    result: dict[str, Any] = {
        "session_id": state["session_id"],
        "status": state.get("status", "completed" if state.get("merge_result") else "error"),
        "total_steps": len(steps),
        "steps": sorted(steps, key=lambda item: item.get("step", 0)),
        "graph": {
            "engine": "langgraph",
            "started_at": state.get("started_at"),
            "completed_workers": state.get("completed_workers", []),
            "skipped_workers": state.get("skipped_workers", []),
            "errors": state.get("errors", []),
        },
    }
    if state.get("merge_result"):
        result["merge_result"] = state["merge_result"]
        result["er_diagram"] = state.get("er_diagram") or build_er_diagram(state["merge_result"] or {})
    if state.get("errors"):
        result["error"] = "; ".join(state["errors"])
    return result


def build_er_diagram(merge_result: dict[str, Any]) -> dict[str, Any]:
    relations = merge_result.get("high_confidence_relations", []) + merge_result.get("medium_confidence_relations", [])
    er_tables: dict[str, dict[str, Any]] = {}
    for rel in relations:
        src = rel["source_table"]
        tgt = rel["target_table"]
        er_tables.setdefault(src, {"relations": [], "relation_count": 0})
        er_tables.setdefault(tgt, {"relations": [], "relation_count": 0})
        er_tables[src]["relations"].append(
            {"type": "has", "target": tgt, "via": rel["fk_column"], "confidence": rel.get("fused_confidence", 0)}
        )
        er_tables[src]["relation_count"] += 1
    return {"table_count": len(er_tables), "tables": er_tables}



