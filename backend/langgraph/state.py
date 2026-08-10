"""Shared LangGraph state and result adapters."""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Any, NotRequired, TypedDict

from backend.core.identity import RunIdentity
from backend.core.status import RunStatus, coerce_run_status, combine_run_status, reduce_run_status


def reduce_state_status(left: str, right: str) -> str:
    statuses = [coerce_run_status(left), coerce_run_status(right)]
    terminal = [status for status in statuses if status != RunStatus.RUNNING]
    return combine_run_status(terminal).value if terminal else RunStatus.RUNNING.value


class AgentState(TypedDict):
    """State shared by all schema recovery graph nodes."""

    session_id: str
    run_id: str
    trace_id: str
    thread_id: str | None
    parent_run_id: str | None
    attempt: int
    started_at: str
    status: Annotated[str, reduce_state_status]
    database_fingerprint: str | None
    snapshot_id: str | None
    snapshot_db_path: str | None
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


def build_initial_state(
    session_id: str | None = None,
    *,
    identity: RunIdentity | None = None,
    thread_id: str | None = None,
    snapshot_db_path: str | None = None,
) -> AgentState:
    # session_id is a legacy compatibility input only. New code passes the
    # explicit RunIdentity and never infers entity meaning from the old prefix.
    identity = identity or RunIdentity.create(thread_id=thread_id)
    return {
        "session_id": identity.run_id,
        "run_id": identity.run_id,
        "trace_id": identity.trace_id,
        "thread_id": identity.thread_id,
        "parent_run_id": identity.parent_run_id,
        "attempt": identity.attempt,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": RunStatus.RUNNING.value,
        "database_fingerprint": None,
        "snapshot_id": None,
        "snapshot_db_path": snapshot_db_path,
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
    steps = sorted(state.get("steps", []), key=lambda item: item.get("step", 0))
    by_worker = {step.get("worker"): step.get("status", "missing") for step in steps}
    required = {
        worker: by_worker.get(worker, "missing")
        for worker in ("survey", "column", "name", "code", "merge")
    }
    optional = {"orm": by_worker["orm"]} if "orm" in by_worker else {}
    reduced = reduce_run_status(required, optional)
    state_status = coerce_run_status(state.get("status", RunStatus.RUNNING.value))
    status = combine_run_status([reduced, state_status]) if state_status != RunStatus.RUNNING else reduced

    result: dict[str, Any] = {
        "session_id": state["run_id"],
        "run_id": state["run_id"],
        "trace_id": state["trace_id"],
        "thread_id": state.get("thread_id"),
        "parent_run_id": state.get("parent_run_id"),
        "attempt": state.get("attempt", 1),
        "status": status.value,
        "run_status": status.value,
        "total_steps": len(steps),
        "steps": steps,
        "capability_gaps": [
            {
                "worker": step.get("worker"),
                "status": step.get("status"),
                "error": step.get("error"),
            }
            for step in steps
            if step.get("status") in {"partial", "degraded", "blocked", "error", "cancelled"}
        ],
        "next_actions": (
            ["Inspect the failed step and explicitly retry this run"]
            if status in {RunStatus.ERROR, RunStatus.PARTIAL, RunStatus.DEGRADED}
            else []
        ),
        "snapshot_id": state.get("snapshot_id"),
        "database_fingerprint": state.get("database_fingerprint"),
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
    elif status == RunStatus.ERROR:
        result["error"] = "Required analysis step did not produce a valid result"
    if result.get("error"):
        result["error_detail"] = {
            "code": "analysis_failed",
            "message": result["error"],
            "retryable": True,
        }
    return result


def build_er_diagram(merge_result: dict[str, Any]) -> dict[str, Any]:
    relations = merge_result.get("high_confidence_relations", []) + merge_result.get("medium_confidence_relations", [])
    er_tables: dict[str, dict[str, Any]] = {}
    for relation in relations:
        source = relation["source_table"]
        target = relation["target_table"]
        er_tables.setdefault(source, {"relations": [], "relation_count": 0})
        er_tables.setdefault(target, {"relations": [], "relation_count": 0})
        er_tables[source]["relations"].append(
            {
                "type": "has",
                "target": target,
                "via": relation["fk_column"],
                "confidence": relation.get("fused_confidence", 0),
            }
        )
        er_tables[source]["relation_count"] += 1
    return {"table_count": len(er_tables), "tables": er_tables}
