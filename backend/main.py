"""FastAPI entry point for Schema Recovery Agent."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.agent.orchestrator import Orchestrator
from backend.agent.runtime import RuntimeContainer, build_runtime_container
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tracing import RunStoreEventSink
from backend.agent.workers.dba import DBAWorker
from backend.agent.workers.qa import QAWorker
from backend.api.v2 import create_chat_router
from backend.config import Config
from backend.core.identity import RunIdentity
from backend.core.legacy_ids import LegacyIdStore
from backend.core.run_store import RunStore
from backend.core.status import RunStatus
from backend.schemas import (
    ChatRequest,
    EventSequencer,
    analysis_result_v1,
    normalize_step,
    sanitize_analysis_result,
)

app = FastAPI(title="Schema Recovery Agent", version="1.0.0")
app.include_router(create_chat_router(lambda: _chat_service()))


@app.on_event("startup")
async def startup() -> None:
    from backend.agent.memory.global_memory import GlobalMemory
    from backend.mcp.server import init_mcp_tools

    app.state.runtime = build_runtime_container(Config)
    app.state.tool_registry = init_mcp_tools(app.state.runtime.tool_runtime)
    app.state.run_store = RunStore()
    app.state.legacy_id_store = LegacyIdStore()
    from backend.agent.qa import QAAgent
    from backend.chat import ChatService, SQLiteChatRepository

    qa_mode = Config.QA_AGENT_V2.strip().lower()
    if qa_mode not in {"disabled", "shadow", "enabled"}:
        raise ValueError("QA_AGENT_V2 must be disabled, shadow, or enabled")
    app.state.chat_repository = SQLiteChatRepository(Config.QA_CHAT_DB_PATH)
    app.state.qa_agent = QAAgent(
        model_gateway=app.state.runtime.model_gateway,
        tool_runtime=app.state.runtime.tool_runtime,
        max_tool_calls=Config.QA_MAX_TOOL_CALLS,
        max_tool_rounds=Config.QA_MAX_TOOL_ROUNDS,
        max_context_messages=Config.QA_MAX_CONTEXT_MESSAGES,
        max_question_chars=Config.QA_MAX_QUESTION_CHARS,
    )
    app.state.chat_service = ChatService(
        repository=app.state.chat_repository,
        qa_agent=app.state.qa_agent,
        runtime=app.state.runtime,
    )
    app.state.schema_graph = None
    app.state.langgraph_error = None
    if Config.LANGGRAPH_ENABLED:
        try:
            from backend.langgraph import build_schema_recovery_graph

            app.state.schema_graph = build_schema_recovery_graph(
                app.state.tool_registry,
                event_sink=RunStoreEventSink(app.state.run_store),
                model_gateway=app.state.runtime.model_gateway,
            )
        except Exception as exc:
            app.state.langgraph_error = _public_error(exc)
    GlobalMemory()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "langgraph_enabled": Config.LANGGRAPH_ENABLED,
        "langgraph_ready": bool(getattr(app.state, "schema_graph", None)),
        "langgraph_error": getattr(app.state, "langgraph_error", None),
        "agent_runtime": Config.AGENT_RUNTIME_V2,
        "model_provider_mode": Config.MODEL_PROVIDER_MODE,
        "model_profiles": _runtime().profiles.public_inventory(),
        "qa_agent_v2": Config.QA_AGENT_V2,
    }


@app.post("/api/analyze")
async def run_analysis() -> dict[str, Any]:
    identity = RunIdentity.create()
    store = _run_store()
    store.start(identity, engine="langgraph" if Config.LANGGRAPH_ENABLED else "manual")
    runtime_context = _new_runtime_context(identity, agent_id="orchestrator")
    result = _orchestrator(runtime_context).run_full_analysis(identity=identity)
    store.complete(identity.run_id, sanitize_analysis_result(result))
    return analysis_result_v1(result)


@app.post("/api/analyze/stream")
async def analyze_stream() -> StreamingResponse:
    identity = RunIdentity.create()
    _run_store().start(identity, engine="langgraph" if Config.LANGGRAPH_ENABLED else "manual")
    runtime_context = _new_runtime_context(identity, agent_id="orchestrator")
    return StreamingResponse(
        _analysis_stream(identity, runtime_context),
        media_type="application/x-ndjson",
        headers={"X-Run-ID": identity.run_id, "X-Trace-ID": identity.trace_id},
    )


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    thread_id = _legacy_id_store().resolve(
        request.thread_id or request.session_id,
        entity_type="thread",
    )
    identity = RunIdentity.create(thread_id=thread_id)
    _run_store().start(identity, engine="chat")
    runtime_context = _new_runtime_context(identity, agent_id="chat")
    intent = classify_chat_intent(request.message, request.pending_operation)
    shared_context = {
        "question": request.message,
        "messages": _chat_history_without_current(request),
        "thread_id": thread_id,
        "run_id": identity.run_id,
        "trace_id": identity.trace_id,
        "llm_available": bool(Config.LLM_API_KEY),
    }

    if intent == "ddl":
        worker = DBAWorker(
            app.state.tool_registry,
            run_context=runtime_context.for_agent("dba") if runtime_context else None,
            tool_runtime=_runtime().tool_runtime,
            model_gateway=_runtime().model_gateway,
        )
        result = worker.run(
            {
                **shared_context,
                "confirmed": request.confirmed,
                "pending_operation": request.pending_operation,
            }
        )
        if result["status"] == "need_confirmation":
            return _finish_chat(identity, {
                "type": "confirmation",
                "session_id": thread_id,
                **identity.model_dump(),
                "message": result["message"],
                "pending": result.get("pending_operation"),
                "safety_level": result.get("safety_level"),
            }, RunStatus.BLOCKED)
        payload = {
            "type": "result" if result["status"] == "success" else "error",
            "session_id": thread_id,
            **identity.model_dump(),
            "message": result["message"],
            "ddl_executed": result.get("ddl_executed"),
            "new_analysis": (
                analysis_result_v1(result["new_analysis"])
                if result.get("new_analysis")
                else None
            ),
            "data": result.get("data"),
        }
        return _finish_chat(
            identity,
            payload,
            RunStatus.SUCCESS if result["status"] == "success" else RunStatus.ERROR,
        )

    qa_mode = Config.QA_AGENT_V2.strip().lower()
    if qa_mode in {"enabled", "shadow"}:
        service = _chat_service()
        service.repository.ensure_thread(thread_id, owner_id="local")
        started = service.start_message(thread_id=thread_id, owner_id="local", content=request.message)
        qa_run = await service.execute(started, owner_id="local")
        output = qa_run.result or {}
    if qa_mode == "enabled":
        blocked = qa_run.status == "blocked"
        return _finish_chat(identity, {
            "type": "answer" if not blocked else "clarification",
            "session_id": thread_id,
            **identity.model_dump(),
            "content": output.get("answer") or output.get("clarification_question") or (qa_run.error or {}).get("message", ""),
            "intent": output.get("intent"),
            "data": output,
            "qa_run_id": qa_run.run_id,
            "citations": output.get("citations", []),
            "artifacts": output.get("artifacts", []),
        }, RunStatus(qa_run.status))

    worker = QAWorker(
        app.state.tool_registry,
        run_context=runtime_context.for_agent("qa") if runtime_context else None,
        tool_runtime=_runtime().tool_runtime,
        model_gateway=_runtime().model_gateway,
    )
    result = worker.run(shared_context)
    return _finish_chat(identity, {
        "type": "answer",
        "session_id": thread_id,
        **identity.model_dump(),
        "content": result["answer"],
        "intent": result.get("intent"),
        "data": result.get("data"),
    }, RunStatus.SUCCESS if result.get("status") == "success" else RunStatus.ERROR)


def classify_chat_intent(question: str, pending_operation: dict[str, Any] | None = None) -> str:
    if pending_operation:
        return "ddl"
    q = question.lower()
    ddl_keywords = [
        "删除",
        "删掉",
        "新建",
        "创建",
        "添加",
        "新增",
        "修改",
        "改成",
        "加一个",
        "建一个",
        "建表",
        "drop",
        "create",
        "alter",
        "truncate",
        "rename",
        "add column",
    ]
    readonly_dba_keywords = ["建表语句", "show create"]
    if any(keyword in q for keyword in readonly_dba_keywords):
        return "ddl"
    return "ddl" if any(keyword in q for keyword in ddl_keywords) else "query"


def _chat_history_without_current(request: ChatRequest) -> list[dict[str, Any]]:
    history = [message.model_dump() for message in request.history]
    if (
        history
        and history[-1].get("role") == "user"
        and history[-1].get("content", "").strip() == request.message.strip()
    ):
        return history[:-1]
    return history


def _orchestrator(runtime_context: RunContext | None = None) -> Orchestrator:
    graph = getattr(app.state, "schema_graph", None) if Config.LANGGRAPH_ENABLED else None
    runtime = _runtime()
    return Orchestrator(
        app.state.tool_registry,
        graph=graph,
        run_context=runtime_context,
        tool_runtime=runtime.tool_runtime,
        model_gateway=runtime.model_gateway,
    )


def _chat_service():
    service = getattr(app.state, "chat_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="chat_service_not_ready")
    return service


def _analysis_stream(identity: RunIdentity, runtime_context: RunContext | None) -> Iterable[str]:
    orchestrator = _orchestrator(runtime_context)
    store = _run_store()
    sequencer = EventSequencer(identity)

    yield _event_line(
        sequencer,
        store,
        legacy_type="started",
        event_type="run.started",
        status=RunStatus.RUNNING,
        total_steps=7,
    )

    if not Config.LANGGRAPH_ENABLED or getattr(app.state, "schema_graph", None) is None:
        result = orchestrator.run_manual_analysis(
            identity=identity,
            graph_meta={
                "engine": "manual",
                "reason": getattr(app.state, "langgraph_error", None) or "langgraph_disabled",
            },
        )
        store.complete(identity.run_id, sanitize_analysis_result(result))
        yield _event_line(
            sequencer,
            store,
            legacy_type="complete",
            event_type="run.completed" if result["run_status"] != "error" else "run.failed",
            status=result["run_status"],
            data=analysis_result_v1(result),
        )
        return

    from backend.langgraph import build_initial_state, build_result_from_state

    initial_state = build_initial_state(
        identity=identity,
        snapshot_db_path=orchestrator.snapshot_db_path,
    )
    final_state: dict[str, Any] = initial_state
    emitted_step_keys: set[tuple[str, int]] = set()

    yield _event_line(
        sequencer,
        store,
        legacy_type="node_started",
        event_type="step.started",
        node="survey_node",
        payload={"node": "survey_node"},
    )
    try:
        for snapshot in app.state.schema_graph.stream(initial_state, stream_mode="values"):
            final_state = snapshot
            for step in sorted(snapshot.get("steps", []), key=lambda item: item.get("step", 0)):
                step_key = (step.get("worker", "unknown"), int(step.get("step", 0)))
                if step_key in emitted_step_keys:
                    continue
                emitted_step_keys.add(step_key)
                normalized_step = normalize_step(step)
                yield _event_line(
                    sequencer,
                    store,
                    legacy_type="node_complete",
                    event_type="step.completed",
                    node=f"{step.get('worker', 'unknown')}_node",
                    step=normalized_step,
                    progress={"completed": len(emitted_step_keys), "total": snapshot.get("total_steps", 7)},
                    payload={"worker": step.get("worker"), "step_status": step.get("status")},
                )
                next_node = _next_node_after(step.get("worker"), snapshot)
                if next_node:
                    yield _event_line(
                        sequencer,
                        store,
                        legacy_type="node_started",
                        event_type="step.started",
                        node=next_node,
                        payload={"node": next_node},
                    )
            yield _event_line(
                sequencer,
                store,
                legacy_type="heartbeat",
                event_type="heartbeat",
                payload={"completed_steps": len(emitted_step_keys)},
            )

        result = build_result_from_state(final_state)
        context = orchestrator._context_from_state(final_state)
        final_status = orchestrator._persist_and_record(
            identity,
            context,
            result["steps"],
            result["run_status"],
        )
        result["status"] = final_status.value
        result["run_status"] = final_status.value
        result["total_steps"] = len(result["steps"])
        store.complete(identity.run_id, sanitize_analysis_result(result))
        yield _event_line(
            sequencer,
            store,
            legacy_type="complete",
            event_type="run.completed" if final_status != RunStatus.ERROR else "run.failed",
            status=final_status,
            data=analysis_result_v1(result),
        )
    except Exception as exc:
        context = orchestrator._context_from_state(final_state)
        failure = orchestrator.build_failed_result(
            identity,
            error=str(exc),
            steps=final_state.get("steps", []),
            context=context,
            graph_meta={
                "engine": "langgraph",
                "fallback_disabled": True,
                "fallback_reason": str(exc),
            },
        )
        store.complete(identity.run_id, sanitize_analysis_result(failure))
        yield _event_line(
            sequencer,
            store,
            legacy_type="error",
            event_type="run.failed",
            status=RunStatus.ERROR,
            error=failure.get("error"),
            data=analysis_result_v1(failure),
        )


def _event_line(
    sequencer: EventSequencer,
    store: RunStore,
    **event_args: Any,
) -> str:
    event = sequencer.next(**event_args)
    store.record_sequence(sequencer.identity.run_id, sequencer.sequence)
    if not Config.STREAM_EVENTS_V2:
        legacy_keys = {
            "type",
            "session_id",
            "total_steps",
            "node",
            "step",
            "progress",
            "data",
            "error",
        }
        event = {key: value for key, value in event.items() if key in legacy_keys}
    return _json_line(event)


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


def _public_error(error: Exception | str) -> str:
    return re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
        r"\1=***",
        str(error),
    )[:1000]


def _run_store() -> RunStore:
    store = getattr(app.state, "run_store", None)
    if store is None:
        store = RunStore()
        app.state.run_store = store
    return store


def _legacy_id_store() -> LegacyIdStore:
    store = getattr(app.state, "legacy_id_store", None)
    if store is None:
        store = LegacyIdStore()
        app.state.legacy_id_store = store
    return store


def _runtime() -> RuntimeContainer:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        runtime = build_runtime_container(Config)
        app.state.runtime = runtime
    return runtime


def _new_runtime_context(identity: RunIdentity, *, agent_id: str) -> RunContext | None:
    if str(Config.AGENT_RUNTIME_V2).strip().lower() != "enabled":
        return None
    return _runtime().new_context(
        identity,
        agent_id=agent_id,
        event_sink=RunStoreEventSink(_run_store()),
    )


def _finish_chat(identity: RunIdentity, payload: dict[str, Any], status: RunStatus) -> dict[str, Any]:
    _run_store().complete(
        identity.run_id,
        {
            **payload,
            "status": status.value,
            "run_status": status.value,
            **identity.model_dump(),
        },
    )
    return payload


@app.get("/api/v2/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        qa_run = chat_service.repository.get_run(run_id, owner_id="local")
        if qa_run is not None:
            return qa_run.model_dump(mode="json")
    record = _run_store().get(run_id)
    if record is None:
        from backend.monitor.recorder import MonitorRecorder

        persisted = MonitorRecorder().get_run(run_id)
        if persisted:
            return persisted
        raise HTTPException(status_code=404, detail="run_not_found")
    return record


@app.get("/api/analyze/{session_id}")
async def get_analysis(session_id: str) -> dict[str, Any]:
    record = _run_store().get(session_id)
    if record:
        return record

    from backend.agent.memory.schema_memory import SchemaMemory

    memory = SchemaMemory()
    return {
        "session_id": session_id,
        "run_id": session_id if session_id.startswith("run_") else None,
        "history": memory.get_history(limit=10),
        "note": "Analysis results are persisted as summary/history records.",
    }


@app.get("/api/memory/query")
async def query_memory(source_table: str | None = None, target_table: str | None = None) -> dict[str, Any]:
    from backend.agent.memory.schema_memory import SchemaMemory

    memory = SchemaMemory()
    return {
        "relations": memory.query_similar_relations(source_table, target_table),
        "history": memory.get_history(limit=10),
    }


@app.get("/api/monitor/stats")
async def get_monitor_stats() -> dict[str, Any]:
    from backend.monitor.recorder import MonitorRecorder

    return MonitorRecorder().get_stats()


@app.get("/api/monitor/contributions")
async def get_contributions() -> dict[str, Any]:
    from backend.monitor.weight_updater import WeightUpdater

    return WeightUpdater().get_evidence_source_overview()


@app.get("/api/monitor/weight-suggestions")
async def get_weight_suggestions() -> dict[str, Any]:
    from backend.monitor.weight_updater import WeightUpdater

    return WeightUpdater().suggest_weight_adjustment()


@app.post("/api/eval/run")
@app.post("/api/v2/evals/runs")
async def run_evaluation() -> dict[str, Any]:
    from backend.eval.report import EvalReporter

    return EvalReporter().run_and_save_report()


@app.get("/api/eval/report")
async def get_latest_report() -> dict[str, Any]:
    from backend.eval.report import EvalReporter

    report = EvalReporter().get_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="eval_report_not_found")
    return report
