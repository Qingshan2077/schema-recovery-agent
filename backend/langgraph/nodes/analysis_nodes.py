"""Worker-backed LangGraph nodes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.agent.router import Router
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.merge import MergeWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.survey import SurveyWorker
from backend.langgraph.state import AgentState, build_er_diagram
from backend.mcp.tool_registry import ToolRegistry

WorkerFactory = Callable[[ToolRegistry], Any]
STEP_ORDER = {"survey": 1, "router": 2, "column": 3, "name": 4, "code": 5, "orm": 6, "merge": 7}


def survey_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    update = _run_worker(state, "survey", SurveyWorker, tool_registry, "survey_result")
    survey_result = update.get("survey_result")
    if update.get("errors"):
        return {**update, "status": "error"}

    plan = Router().plan_analysis(survey_result or {})
    router_step = {
        "step": _next_step("router"),
        "worker": "router",
        "status": "success",
        "duration_ms": 0,
        "output": plan,
    }
    return {**update, "plan": plan, "steps": update.get("steps", []) + [router_step]}


def column_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    return _run_worker(state, "column", ColumnWorker, tool_registry, "column_result")


def name_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    return _run_worker(state, "name", NameWorker, tool_registry, "name_result")


def code_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    return _run_worker(state, "code", CodeWorker, tool_registry, "code_result")


def orm_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    return _run_worker(state, "orm", ORMWorker, tool_registry, "orm_result")


def merge_node(state: AgentState, tool_registry: ToolRegistry) -> dict[str, Any]:
    normalized_state = dict(state)
    if normalized_state.get("orm_result") is None:
        normalized_state["orm_result"] = {"status": "success", "total_relations": 0, "relations": [], "message": "No ORM files found, skipping"}
    update = _run_worker(normalized_state, "merge", MergeWorker, tool_registry, "merge_result")
    merge_result = update.get("merge_result")
    if merge_result:
        update["er_diagram"] = build_er_diagram(merge_result)
        update["status"] = "completed"
    return update


def skipped_orm_node(state: AgentState) -> dict[str, Any]:
    step = {
        "step": _next_step("orm"),
        "worker": "orm",
        "status": "skipped",
        "duration_ms": 0,
        "output": {"message": "No ORM files found, skipping"},
    }
    return {
        "orm_result": {"status": "success", "total_relations": 0, "relations": [], "message": "No ORM files found, skipping"},
        "steps": [step],
        "skipped_workers": ["orm"],
    }


def _run_worker(
    state: AgentState,
    worker_id: str,
    worker_factory: WorkerFactory,
    tool_registry: ToolRegistry,
    result_key: str,
) -> dict[str, Any]:
    start = time.time()
    worker = worker_factory(tool_registry)
    try:
        output = worker.run(dict(state))
        duration_ms = int((time.time() - start) * 1000)
        status = "success" if output.get("status") == "success" else "partial"
        call_log = worker.get_call_log()
        step = {
            "step": _next_step(worker_id),
            "worker": worker_id,
            "status": status,
            "duration_ms": duration_ms,
            "tool_calls": call_log,
            "output": output,
        }
        return {
            result_key: output,
            "steps": [step],
            "worker_call_log": [
                {"worker_id": worker_id, "duration_ms": duration_ms, "status": status, "tool_calls": call_log}
            ],
            "completed_workers": [worker_id],
        }
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        step = {"step": _next_step(worker_id), "worker": worker_id, "status": "error", "duration_ms": duration_ms, "error": str(exc)}
        return {
            "status": "error",
            "steps": [step],
            "worker_call_log": [{"worker_id": worker_id, "duration_ms": duration_ms, "status": "error", "tool_calls": []}],
            "errors": [f"{worker_id}: {exc}"],
        }


def _next_step(worker_id: str) -> int:
    return STEP_ORDER.get(worker_id, 99)


