"""Worker-backed LangGraph nodes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from backend.agent.router import Router
from backend.agent.runtime import build_default_budget
from backend.agent.runtime.run_context import RunContext
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.merge import MergeWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.survey import SurveyWorker
from backend.core.status import coerce_worker_status
from backend.core.identity import RunIdentity
from backend.config import Config
from backend.core.lineage import attach_merge_lineage
from backend.langgraph.state import AgentState, build_er_diagram
from backend.mcp.tool_registry import ToolRegistry

WorkerFactory = Callable[[ToolRegistry], Any]
STEP_ORDER = {"survey": 1, "router": 2, "column": 3, "name": 4, "code": 5, "orm": 6, "merge": 7}


def survey_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    update = _run_worker(state, "survey", SurveyWorker, tool_registry, "survey_result", event_sink)
    survey_result = update.get("survey_result")
    if update.get("errors") or not survey_result:
        return update

    server_info = survey_result.get("server_info") or {}
    plan = Router().plan_analysis(survey_result)
    router_step = {
        "step": _next_step("router"),
        "worker": "router",
        "status": "success",
        "duration_ms": 0,
        "output": plan,
    }
    return {
        **update,
        "database_fingerprint": server_info.get("database_fingerprint"),
        "snapshot_id": server_info.get("snapshot_id"),
        "plan": plan,
        "steps": update.get("steps", []) + [router_step],
    }


def column_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    return _run_worker(state, "column", ColumnWorker, tool_registry, "column_result", event_sink)


def name_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    return _run_worker(state, "name", NameWorker, tool_registry, "name_result", event_sink)


def code_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    return _run_worker(state, "code", CodeWorker, tool_registry, "code_result", event_sink)


def orm_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    return _run_worker(state, "orm", ORMWorker, tool_registry, "orm_result", event_sink)


def merge_node(state: AgentState, tool_registry: ToolRegistry, event_sink: Any = None) -> dict[str, Any]:
    normalized_state = dict(state)
    if normalized_state.get("orm_result") is None:
        normalized_state["orm_result"] = {
            "status": "success",
            "total_relations": 0,
            "relations": [],
            "message": "No ORM files found, skipping",
        }
    update = _run_worker(normalized_state, "merge", MergeWorker, tool_registry, "merge_result", event_sink)
    merge_result = update.get("merge_result")
    if merge_result:
        attach_merge_lineage(
            merge_result,
            run_id=state["run_id"],
            trace_id=state["trace_id"],
            database_fingerprint=state.get("database_fingerprint"),
            snapshot_id=state.get("snapshot_id"),
        )
        update["er_diagram"] = build_er_diagram(merge_result)
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
        "orm_result": {
            "status": "success",
            "total_relations": 0,
            "relations": [],
            "message": "No ORM files found, skipping",
        },
        "steps": [step],
        "skipped_workers": ["orm"],
    }


def _run_worker(
    state: AgentState,
    worker_id: str,
    worker_factory: WorkerFactory,
    tool_registry: ToolRegistry,
    result_key: str,
    event_sink: Any = None,
) -> dict[str, Any]:
    start = time.time()
    identity = RunIdentity(
        run_id=state["run_id"],
        trace_id=state["trace_id"],
        thread_id=state.get("thread_id"),
        parent_run_id=state.get("parent_run_id"),
        attempt=int(state.get("attempt", 1)),
    )
    run_context = RunContext.from_identity(
        identity,
        agent_id=worker_id,
        budget=build_default_budget(Config),
        event_sink=event_sink,
    )
    worker = worker_factory(
        tool_registry,
        run_context=run_context,
        tool_runtime=tool_registry.runtime,
    )
    worker.reset_call_log()
    try:
        output = worker.run(dict(state))
        if not isinstance(output, dict):
            raise TypeError(f"{worker_id} worker returned a non-object result")
        duration_ms = int((time.time() - start) * 1000)
        status = coerce_worker_status(output.get("status"))
        call_log = worker.get_call_log()
        error = str(output.get("error")) if status == "error" and output.get("error") else None
        step = {
            "step": _next_step(worker_id),
            "worker": worker_id,
            "status": status,
            "duration_ms": duration_ms,
            "tool_calls": call_log,
            "output": output,
        }
        if error:
            step["error"] = error
        update: dict[str, Any] = {
            "status": status,
            "steps": [step],
            "worker_call_log": [
                {
                    "worker_id": worker_id,
                    "duration_ms": duration_ms,
                    "status": status,
                    "tool_calls": call_log,
                }
            ],
        }
        if status in {"success", "partial", "degraded"}:
            update[result_key] = output
            update["completed_workers"] = [worker_id]
        else:
            update["errors"] = [f"{worker_id}: {error or status}"]
        return update
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        error = _safe_error(exc)
        step = {
            "step": _next_step(worker_id),
            "worker": worker_id,
            "status": "error",
            "duration_ms": duration_ms,
            "tool_calls": worker.get_call_log(),
            "error": error,
        }
        return {
            "status": "error",
            "steps": [step],
            "worker_call_log": [
                {
                    "worker_id": worker_id,
                    "duration_ms": duration_ms,
                    "status": "error",
                    "tool_calls": worker.get_call_log(),
                }
            ],
            "errors": [f"{worker_id}: {error}"],
        }


def _next_step(worker_id: str) -> int:
    return STEP_ORDER.get(worker_id, 99)


def _safe_error(error: Exception | str) -> str:
    return re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
        r"\1=***",
        str(error),
    )[:1000]
