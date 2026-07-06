"""FastAPI entry point for Schema Recovery Agent."""

from __future__ import annotations

import json
from typing import Any, Iterable

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from backend.agent.orchestrator import Orchestrator
from backend.config import Config
from backend.schemas import normalize_step, stream_event

app = FastAPI(title="Schema Recovery Agent", version="1.0.0")


@app.on_event("startup")
async def startup():
    from backend.agent.memory.global_memory import GlobalMemory
    from backend.mcp.server import init_mcp_tools

    app.state.tool_registry = init_mcp_tools()
    app.state.schema_graph = None
    app.state.langgraph_error = None
    if Config.LANGGRAPH_ENABLED:
        try:
            from backend.langgraph import build_schema_recovery_graph

            app.state.schema_graph = build_schema_recovery_graph(app.state.tool_registry)
        except Exception as exc:
            app.state.langgraph_error = str(exc)
    GlobalMemory()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "langgraph_enabled": Config.LANGGRAPH_ENABLED,
        "langgraph_ready": bool(getattr(app.state, "schema_graph", None)),
        "langgraph_error": getattr(app.state, "langgraph_error", None),
    }


@app.post("/api/analyze")
async def run_analysis():
    return _orchestrator().run_full_analysis()


@app.post("/api/analyze/stream")
async def analyze_stream():
    return StreamingResponse(_analysis_stream(), media_type="application/x-ndjson")


def _orchestrator() -> Orchestrator:
    graph = getattr(app.state, "schema_graph", None) if Config.LANGGRAPH_ENABLED else None
    return Orchestrator(app.state.tool_registry, graph=graph)


def _analysis_stream() -> Iterable[str]:
    orch = _orchestrator()
    if not Config.LANGGRAPH_ENABLED or getattr(app.state, "schema_graph", None) is None:
        result = orch.run_manual_analysis(
            graph_meta={
                "engine": "manual_fallback" if Config.LANGGRAPH_ENABLED else "manual",
                "fallback_reason": getattr(app.state, "langgraph_error", None) or "langgraph_disabled",
            }
        )
        yield _json_line(stream_event(type="complete", session_id=result.get("session_id"), data=result))
        return

    from backend.langgraph import build_initial_state, build_result_from_state

    initial_state = build_initial_state()
    final_state: dict[str, Any] = initial_state
    emitted_step_keys: set[tuple[str, int]] = set()

    yield _json_line(stream_event(type="started", session_id=initial_state["session_id"], total_steps=initial_state["total_steps"]))
    yield _json_line(stream_event(type="node_started", session_id=initial_state["session_id"], node="survey_node"))
    try:
        for snapshot in app.state.schema_graph.stream(initial_state, stream_mode="values"):
            final_state = snapshot
            for step in sorted(snapshot.get("steps", []), key=lambda item: item.get("step", 0)):
                step_key = (step.get("worker", "unknown"), int(step.get("step", 0)))
                if step_key in emitted_step_keys:
                    continue
                emitted_step_keys.add(step_key)
                normalized_step = normalize_step(step)
                yield _json_line(
                    stream_event(
                        type="node_complete",
                        session_id=snapshot["session_id"],
                        node=f"{step.get('worker', 'unknown')}_node",
                        step=normalized_step,
                        progress={"completed": len(emitted_step_keys), "total": snapshot.get("total_steps", 7)},
                    )
                )
                next_node = _next_node_after(step.get("worker"), snapshot)
                if next_node:
                    yield _json_line(stream_event(type="node_started", session_id=snapshot["session_id"], node=next_node))

        result = build_result_from_state(final_state)
        if final_state.get("merge_result"):
            orch._persist_and_record(final_state["session_id"], orch._context_from_state(final_state), result["steps"])
        yield _json_line(stream_event(type="complete", session_id=final_state["session_id"], data=result))
    except Exception as exc:
        fallback = orch.run_manual_analysis(graph_meta={"engine": "manual_fallback", "fallback_reason": str(exc)})
        yield _json_line(stream_event(type="complete", session_id=fallback.get("session_id"), data=fallback))


def _next_node_after(worker: str | None, snapshot: dict[str, Any]) -> str | None:
    if worker == "survey":
        return "column_node,name_node"
    if worker in {"column", "name"}:
        completed = {step.get("worker") for step in snapshot.get("steps", [])}
        return "code_node" if {"column", "name"}.issubset(completed) else None
    if worker == "code":
        return "orm_node" if snapshot.get("survey_result", {}).get("orm_files", {}).get("count", 0) > 0 else "skip_orm_node"
    if worker == "orm":
        return "merge_node"
    return None


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


@app.get("/api/analyze/{session_id}")
async def get_analysis(session_id: str):
    from backend.agent.memory.schema_memory import SchemaMemory

    memory = SchemaMemory()
    return {
        "session_id": session_id,
        "history": memory.get_history(limit=10),
        "note": "Analysis results are persisted as summary/history records.",
    }


@app.get("/api/memory/query")
async def query_memory(source_table: str | None = None, target_table: str | None = None):
    from backend.agent.memory.schema_memory import SchemaMemory

    memory = SchemaMemory()
    return {
        "relations": memory.query_similar_relations(source_table, target_table),
        "history": memory.get_history(limit=10),
    }


@app.get("/api/monitor/stats")
async def get_monitor_stats():
    from backend.monitor.recorder import MonitorRecorder

    return MonitorRecorder().get_stats()


@app.get("/api/monitor/contributions")
async def get_contributions():
    from backend.monitor.weight_updater import WeightUpdater

    return WeightUpdater().get_evidence_source_overview()


@app.get("/api/monitor/weight-suggestions")
async def get_weight_suggestions():
    from backend.monitor.weight_updater import WeightUpdater

    return WeightUpdater().suggest_weight_adjustment()


@app.get("/api/eval/run")
async def run_evaluation():
    from backend.eval.report import EvalReporter

    return EvalReporter().run_full_report()


@app.get("/api/eval/report")
async def get_latest_report():
    from backend.eval.report import EvalReporter

    return EvalReporter().run_full_report()
