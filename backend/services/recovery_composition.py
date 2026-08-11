"""Per-run Phase 4 composition without FastAPI or LangGraph dependencies in stages."""

from __future__ import annotations

from backend.agent.runtime import build_default_budget
from backend.agent.runtime.run_context import RunContext
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.hybrid_stage import HybridStageDependencies, Phase4RecoveryStageAdapter
from backend.agent.workers.merge import MergeWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.survey import SurveyWorker
from backend.agent.memory.service import MemoryService
from backend.agent.memory.stage import MemoryRecoveryStage
from backend.config import Config
from backend.core.identity import RunIdentity
from backend.engines import EngineRegistry, LangGraphEngine, ManualEngine
from backend.evidence import EvidenceLedger, SQLiteEvidenceRepository
from backend.evidence.versioned_repository import SQLiteVersionedEvidenceRepository
from backend.persistence import LangGraphPersistenceFactory, SQLiteEventLog, SQLiteRunRepository
from backend.workflow import StageRegistry, WorkflowResultBuilder, schema_recovery_v2


async def preflight_recovery_persistence() -> None:
    """Fail startup before accepting runs when the selected graph backend is unusable."""

    if Config.RECOVERY_ENGINE not in {"langgraph_v2", "auto_v2"}:
        return
    persistence = LangGraphPersistenceFactory(
        checkpoint_backend=Config.CHECKPOINT_BACKEND,
        store_backend=Config.STORE_BACKEND,
        sqlite_path=Config.LANGGRAPH_CHECKPOINT_DB_PATH,
        postgres_dsn=Config.LANGGRAPH_POSTGRES_DSN,
    )
    persistence.validate_dependencies()
    try:
        await persistence.acreate()
    finally:
        await persistence.aclose()


def build_engine_factory(*, runtime, tool_registry, runs: SQLiteRunRepository, events: SQLiteEventLog, traces=None):
    definition = schema_recovery_v2()
    persistence = LangGraphPersistenceFactory(
        checkpoint_backend=Config.CHECKPOINT_BACKEND,
        store_backend=Config.STORE_BACKEND,
        sqlite_path=Config.LANGGRAPH_CHECKPOINT_DB_PATH,
        postgres_dsn=Config.LANGGRAPH_POSTGRES_DSN,
    )

    def factory(state):
        identity = RunIdentity(run_id=state.run_id, trace_id=state.trace_id, thread_id=state.thread_id)
        run_budget = build_default_budget(Config)
        run_budget.deadline_at = state.deadline_at
        if traces is not None:
            from backend.observability.tracing import TraceEventSink
            trace_sink = TraceEventSink(traces)
        else:
            trace_sink = None
        run_context = RunContext.from_identity(
            identity, agent_id="recovery.workflow", budget=run_budget,
            event_sink=trace_sink,
        )
        run_context.budget.restore(state.budget)
        legacy_workers = {
            "survey": SurveyWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
            "column": ColumnWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
            "name": NameWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
            "code": CodeWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
            "orm": ORMWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
            "merge": MergeWorker(tool_registry, run_context=run_context, tool_runtime=runtime.tool_runtime, model_gateway=runtime.model_gateway),
        }
        ledger = EvidenceLedger(SQLiteEvidenceRepository(Config.EVIDENCE_DB_PATH))
        memory_service = MemoryService(
            Config.MEMORY_V2_DB_PATH,
            vector_enabled=Config.MEMORY_VECTOR_ENABLED,
        )
        versioned_repository = SQLiteVersionedEvidenceRepository(Config.EVIDENCE_DB_PATH)
        dependencies = HybridStageDependencies(
            run_context=run_context, tool_runtime=runtime.tool_runtime,
            model_gateway=runtime.model_gateway, ledger=ledger, legacy_workers=legacy_workers,
            memory_service=memory_service,
            versioned_evidence_repository=versioned_repository,
        )
        stages = StageRegistry()
        for worker in ("survey", "column", "name", "code", "orm", "merge"):
            stages.register(Phase4RecoveryStageAdapter(worker, dependencies))
        for worker in ("memory_retrieve", "memory_verify", "memory_consolidate"):
            stages.register(MemoryRecoveryStage(
                worker, memory_service, ledger,
                read_enabled=Config.MEMORY_V2_READ_ENABLED,
                write_enabled=Config.MEMORY_V2_WRITE_ENABLED,
                versioned_repository=versioned_repository,
                retrieval_top_k=Config.MEMORY_RETRIEVAL_TOP_K,
                context_token_budget=Config.MEMORY_CONTEXT_MAX_TOKENS,
            ))
        manual = ManualEngine(
            definition=definition, stages=stages, runs=runs, events=events,
            max_concurrency=Config.WORKFLOW_MAX_CONCURRENCY,
            max_attempts=Config.WORKFLOW_MAX_STAGE_ATTEMPTS,
        )
        graph = LangGraphEngine(
            definition=definition, portable_scheduler=manual, persistence=persistence,
            recursion_limit=Config.WORKFLOW_RECURSION_LIMIT,
            max_concurrency=Config.WORKFLOW_MAX_CONCURRENCY,
        )
        return EngineRegistry({"manual": manual, "langgraph": graph}), WorkflowResultBuilder(ledger)

    async def aclose() -> None:
        await persistence.aclose()

    factory.aclose = aclose  # type: ignore[attr-defined]
    return factory
