"""FastAPI entry point for Schema Recovery Agent."""

from __future__ import annotations

import asyncio
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
from backend.api.run_routes import create_run_router
from backend.api.memory_routes import create_memory_router
from backend.api.evidence_routes import create_evidence_router
from backend.api.eval_v2_routes import create_eval_v2_router
from backend.api.trace_routes import create_trace_router
from backend.api.dba_routes import create_dba_router
from backend.config import Config
from backend.core.identity import RunIdentity
from backend.core.legacy_ids import LegacyIdStore
from backend.core.run_store import RunStore
from backend.core.status import RunStatus, coerce_run_status
from backend.schemas import (
    ChatRequest,
    EventSequencer,
    analysis_result_v1,
    normalize_step,
    sanitize_analysis_result,
)

app = FastAPI(title="Schema Recovery Agent", version="1.0.0")
app.include_router(create_chat_router(lambda: _chat_service()))
app.include_router(create_run_router(lambda: _recovery_run_service()))
app.include_router(create_memory_router(lambda: _memory_service()))
app.include_router(create_evidence_router(lambda: _versioned_evidence_repository()))
app.include_router(create_eval_v2_router(lambda: _eval_service()))
app.include_router(create_trace_router(lambda: _trace_recorder()))
app.include_router(create_dba_router(lambda: _dba_service()))


@app.middleware("http")
async def trace_http_request(request, call_next):
    recorder = getattr(app.state, "trace_recorder", None)
    if recorder is None or not Config.OTEL_ENABLED:
        return await call_next(request)
    from backend.observability.tracing import parse_traceparent, traceparent
    incoming_trace, incoming_parent = parse_traceparent(request.headers.get("traceparent"))
    with recorder.span(
        "http.request", trace_id=incoming_trace, parent_span_id=incoming_parent,
        attributes={"http.method": request.method, "http.route": request.url.path},
    ) as span:
        response = await call_next(request)
        span.set(**{"http.status_code": response.status_code})
        response.headers["traceparent"] = traceparent(span.trace_id, span.span_id)
        return response


@app.on_event("startup")
async def startup() -> None:
    from backend.agent.memory.global_memory import GlobalMemory
    from backend.agent.memory.service import MemoryService
    from backend.evidence.versioned_repository import SQLiteVersionedEvidenceRepository
    from backend.eval_v2.artifacts import EvalArtifactStore
    from backend.eval_v2.case_executor import FixtureCaseExecutor
    from backend.eval_v2.registry import DatasetRegistry
    from backend.eval_v2.service import EvalService
    from backend.eval_v2.store import EvalStore
    from backend.observability.tracing import TraceRecorder
    from backend.agent.dba.operation_store import OperationStore
    from backend.agent.dba.planner import DDLPlanner
    from backend.agent.dba.service import DBAService
    from backend.mcp.server import init_mcp_tools

    app.state.runtime = build_runtime_container(Config)
    app.state.tool_registry = init_mcp_tools(app.state.runtime.tool_runtime)
    app.state.run_store = RunStore()
    app.state.legacy_id_store = LegacyIdStore()
    app.state.memory_service = MemoryService(
        Config.MEMORY_V2_DB_PATH, vector_enabled=Config.MEMORY_VECTOR_ENABLED,
    )
    app.state.versioned_evidence_repository = SQLiteVersionedEvidenceRepository(
        Config.EVIDENCE_DB_PATH,
    )
    from backend.evidence.policy_loader import calibration_artifact_from_policy
    app.state.versioned_evidence_repository.put_calibration(
        calibration_artifact_from_policy(
            Config.FUSION_POLICY_PATH,
            git_sha=Config.DEPLOYMENT_GIT_SHA,
        )
    )
    trace_exporters = []
    if Config.OTEL_ENABLED and Config.OTEL_EXPORTER_OTLP_ENDPOINT:
        from backend.observability.otel_exporter import OpenTelemetrySpanExporter
        trace_exporters.append(OpenTelemetrySpanExporter(
            endpoint=Config.OTEL_EXPORTER_OTLP_ENDPOINT,
            service_name=Config.OTEL_SERVICE_NAME,
        ))
    app.state.trace_recorder = TraceRecorder(Config.TRACE_DB_PATH, exporters=trace_exporters)
    app.state.eval_service = EvalService(
        registry=DatasetRegistry(Config.EVAL_DATASET_REGISTRY_PATH),
        store=EvalStore(Config.EVAL_V2_DB_PATH),
        artifacts=EvalArtifactStore(Config.EVAL_ARTIFACT_DIR),
        traces=app.state.trace_recorder,
        executor=FixtureCaseExecutor(
            runtime=app.state.runtime,
            traces=app.state.trace_recorder,
        ),
    )
    app.state.dba_service = DBAService(
        store=OperationStore(Config.DBA_OPERATION_DB_PATH),
        planner=DDLPlanner(), traces=app.state.trace_recorder,
        execution_enabled=Config.DBA_EXECUTION_ENABLED,
        connection_allowlist=Config.DBA_EXECUTION_CONNECTION_ALLOWLIST,
        ttl_minutes=Config.DBA_OPERATION_TTL_MINUTES,
    )
    from backend.persistence import SQLiteEventLog, SQLiteRunRepository
    from backend.services import RecoveryRunService, build_engine_factory, preflight_recovery_persistence

    await preflight_recovery_persistence()
    app.state.recovery_run_repository = SQLiteRunRepository(Config.RECOVERY_RUN_DB_PATH)
    app.state.recovery_event_log = SQLiteEventLog(
        Config.RECOVERY_RUN_DB_PATH, trace_recorder=app.state.trace_recorder,
    )
    engine_factory = build_engine_factory(
        runtime=app.state.runtime,
        tool_registry=app.state.tool_registry,
        runs=app.state.recovery_run_repository,
        events=app.state.recovery_event_log,
        traces=app.state.trace_recorder,
    )
    app.state.recovery_run_service = RecoveryRunService(
        runs=app.state.recovery_run_repository,
        events=app.state.recovery_event_log,
        engine_factory=engine_factory,
        workflow_version=Config.WORKFLOW_VERSION,
        state_schema_version=Config.STATE_SCHEMA_VERSION,
        configured_engine=Config.RECOVERY_ENGINE,
        auto_fallback=Config.AUTO_FALLBACK_ENABLED,
        max_fallbacks=Config.RUN_MAX_AUTO_FALLBACKS,
        deadline_seconds=Config.RUNTIME_DEADLINE_SECONDS,
    )
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
        traces=app.state.trace_recorder,
    )
    app.state.schema_graph = None
    app.state.langgraph_error = None
    if Config.RECOVERY_ENGINE in {"legacy", "shadow"} and Config.LANGGRAPH_ENABLED:
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


@app.on_event("shutdown")
async def shutdown() -> None:
    recovery_service = getattr(app.state, "recovery_run_service", None)
    if recovery_service is not None:
        await recovery_service.aclose()


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
        "recovery_engine": Config.RECOVERY_ENGINE,
        "workflow_version": Config.WORKFLOW_VERSION,
        "state_schema_version": Config.STATE_SCHEMA_VERSION,
        "checkpoint_backend": Config.CHECKPOINT_BACKEND,
        "store_backend": Config.STORE_BACKEND,
        "feature_flags": {
            "agent_workbench": Config.AGENT_WORKBENCH_ENABLED,
            "run_inspector": Config.RUN_INSPECTOR_ENABLED,
            "evidence_workbench": Config.EVIDENCE_WORKBENCH_ENABLED,
            "er_explorer_v2": Config.ER_EXPLORER_V2_ENABLED,
            "approval_center": Config.APPROVAL_CENTER_ENABLED and Config.DBA_V2_ENABLED,
            "memory_inspector": Config.MEMORY_INSPECTOR_ENABLED,
            "eval_v2": Config.EVAL_V2_ENABLED,
            "tracing": Config.OTEL_ENABLED,
        },
    }


@app.post("/api/analyze")
async def run_analysis() -> dict[str, Any]:
    if Config.RECOVERY_ENGINE not in {"legacy", "shadow"}:
        state = _recovery_run_service().create_run(
            project_id=Config.PROJECT_ID,
            connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
            tenant_id=Config.TENANT_ID,
            database_name=Config.DB_NAME,
            schema_name=Config.DB_NAME,
        )
        return analysis_result_v1(await _recovery_run_service().execute(state.run_id))
    identity = RunIdentity.create()
    store = _run_store()
    store.start(identity, engine="langgraph" if Config.LANGGRAPH_ENABLED else "manual")
    runtime_context = _new_runtime_context(identity, agent_id="orchestrator")
    result = _orchestrator(runtime_context).run_full_analysis(identity=identity)
    store.complete(identity.run_id, sanitize_analysis_result(result))
    return analysis_result_v1(result)


@app.post("/api/analyze/stream")
async def analyze_stream() -> StreamingResponse:
    if Config.RECOVERY_ENGINE not in {"legacy", "shadow"}:
        state = _recovery_run_service().create_run(
            project_id=Config.PROJECT_ID,
            connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
            tenant_id=Config.TENANT_ID,
            database_name=Config.DB_NAME,
            schema_name=Config.DB_NAME,
        )
        return StreamingResponse(
            _analysis_stream_v2(state.run_id),
            media_type="application/x-ndjson",
            headers={"X-Run-ID": state.run_id, "X-Trace-ID": state.trace_id},
        )
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
        if Config.DBA_V2_ENABLED and request.pending_operation:
            return _finish_chat(identity, {
                "type": "error", "session_id": thread_id, **identity.model_dump(),
                "message": "客户端确认载荷已停用，请在 Approval Center 审批服务端 operation。",
                "code": "approval_protocol_required",
            }, RunStatus.BLOCKED)
        if Config.DBA_V2_ENABLED and not any(value in request.message.lower() for value in ("show create", "建表语句")):
            from backend.agent.dba.contracts import ActorContext

            try:
                operation = await _dba_service().create_operation(
                    request.message,
                    actor=ActorContext(
                        actor_id="local-analyst", roles=["analyst"],
                        tenant_id=Config.TENANT_ID, project_id=Config.PROJECT_ID,
                        environment="dev", capabilities=["dba_plan", "dba_view_sql"],
                    ),
                    connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
                    thread_id=thread_id, run_id=identity.run_id, dialect="mysql",
                    snapshot_id="snp_pending", snapshot_hash="sha256:pending",
                )
                return _finish_chat(identity, {
                    "type": "approval", "session_id": thread_id, **identity.model_dump(),
                    "message": "DDL 计划已保存到服务端，需在 Approval Center 审批。",
                    "operation_id": operation.operation_id,
                    "operation_version": operation.version,
                    "operation_hash": operation.normalized_sql_hash,
                    "status": operation.status,
                }, RunStatus.BLOCKED)
            except ValueError as exc:
                return _finish_chat(identity, {
                    "type": "error", "session_id": thread_id, **identity.model_dump(),
                    "message": str(exc), "code": "unsupported_ddl",
                }, RunStatus.ERROR)
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
        }, coerce_run_status(qa_run.status))

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


def _recovery_run_service():
    service = getattr(app.state, "recovery_run_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="recovery_run_service_not_ready")
    return service


def _memory_service():
    service = getattr(app.state, "memory_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="memory_service_not_ready")
    return service


def _versioned_evidence_repository():
    repository = getattr(app.state, "versioned_evidence_repository", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="evidence_repository_not_ready")
    return repository


def _trace_recorder():
    recorder = getattr(app.state, "trace_recorder", None)
    if recorder is None: raise HTTPException(status_code=503, detail="trace_recorder_not_ready")
    return recorder


def _eval_service():
    service = getattr(app.state, "eval_service", None)
    if service is None: raise HTTPException(status_code=503, detail="eval_service_not_ready")
    return service


def _dba_service():
    service = getattr(app.state, "dba_service", None)
    if service is None: raise HTTPException(status_code=503, detail="dba_service_not_ready")
    return service


async def _analysis_stream_v2(run_id: str):
    service = _recovery_run_service()
    execution = asyncio.create_task(service.execute(run_id))
    after_sequence = 0
    result: dict[str, Any] | None = None
    try:
        while True:
            events = service.get_events(run_id, after_sequence=after_sequence)
            for event in events:
                after_sequence = max(after_sequence, int(event.get("sequence", 0)))
                legacy_type = _legacy_event_type(event.get("type", "heartbeat"))
                payload = {
                    **event,
                    "type": legacy_type,
                    "event_type": event.get("type"),
                    "run_id": run_id,
                }
                if legacy_type == "complete":
                    result = result or await execution
                    payload["data"] = analysis_result_v1(result)
                yield json.dumps(payload, ensure_ascii=False, default=str) + "\n"
            if execution.done():
                result = result or await execution
                if not service.get_events(run_id, after_sequence=after_sequence):
                    break
            await asyncio.sleep(0.05)
    except Exception as exc:
        yield _json_line({
            "type": "error",
            "event_type": "run.failed",
            "run_id": run_id,
            "error": _public_error(exc),
        })


def _legacy_event_type(event_type: str) -> str:
    if event_type == "run.started":
        return "started"
    if event_type.startswith("stage."):
        return "node_started" if event_type in {"stage.scheduled", "stage.started", "stage.retrying"} else "node_complete"
    if event_type.startswith("run.") and event_type.split(".", 1)[1] in {
        "completed", "partial", "degraded", "blocked", "failed", "canceled",
        "expired",
    }:
        return "complete"
    return "heartbeat"


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
            event_type="run.completed" if result["run_status"] != "failed" else "run.failed",
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
    recovery_service = getattr(app.state, "recovery_run_service", None)
    if recovery_service is not None:
        try:
            return recovery_service.get_run(run_id)
        except KeyError:
            pass
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
    if session_id.startswith("run_"):
        try:
            return analysis_result_v1(_recovery_run_service().get_run(session_id))
        except KeyError:
            pass
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
async def run_evaluation() -> dict[str, Any]:
    if Config.EVAL_V2_ENABLED:
        raise HTTPException(status_code=410, detail="use_post_api_v2_evals_runs_with_registered_dataset")
    from backend.eval.report import EvalReporter

    return EvalReporter().run_and_save_report()


@app.get("/api/eval/report")
async def get_latest_report() -> dict[str, Any]:
    if Config.EVAL_V2_ENABLED:
        baseline = _eval_service().store.current_baseline("release")
        if baseline is None:
            raise HTTPException(status_code=404, detail="no_finalized_eval_report")
        return _eval_service().report(str(baseline["eval_run_id"]))
    from backend.eval.report import EvalReporter

    report = EvalReporter().get_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="eval_report_not_found")
    return report
