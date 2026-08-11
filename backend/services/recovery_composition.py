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
from backend.config import Config
from backend.core.identity import RunIdentity
from backend.engines import EngineRegistry, LangGraphEngine, ManualEngine
from backend.evidence import EvidenceLedger, SQLiteEvidenceRepository
from backend.persistence import LangGraphPersistenceFactory, SQLiteEventLog, SQLiteRunRepository
from backend.workflow import StageRegistry, WorkflowResultBuilder, schema_recovery_v2


def preflight_recovery_persistence() -> None:
    """Fail startup before accepting runs when the selected graph backend is unusable."""

    if Config.RECOVERY_ENGINE not in {"langgraph_v2", "auto_v2"}:
        return
    persistence = LangGraphPersistenceFactory(
        checkpoint_backend=Config.CHECKPOINT_BACKEND,
        store_backend=Config.STORE_BACKEND,
        sqlite_path=Config.LANGGRAPH_CHECKPOINT_DB_PATH,
        postgres_dsn=Config.LANGGRAPH_POSTGRES_DSN,
    )
    try:
        persistence.create()
    finally:
        persistence.close()


def build_engine_factory(*, runtime, tool_registry, runs: SQLiteRunRepository, events: SQLiteEventLog):
    definition = schema_recovery_v2()

    def factory(state):
        identity = RunIdentity(run_id=state.run_id, trace_id=state.trace_id, thread_id=state.thread_id)
        run_budget = build_default_budget(Config)
        run_budget.deadline_at = state.deadline_at
        run_context = RunContext.from_identity(
            identity, agent_id="recovery.workflow", budget=run_budget,
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
        dependencies = HybridStageDependencies(
            run_context=run_context, tool_runtime=runtime.tool_runtime,
            model_gateway=runtime.model_gateway, ledger=ledger, legacy_workers=legacy_workers,
        )
        stages = StageRegistry()
        for worker in ("survey", "column", "name", "code", "orm", "merge"):
            stages.register(Phase4RecoveryStageAdapter(worker, dependencies))
        manual = ManualEngine(
            definition=definition, stages=stages, runs=runs, events=events,
            max_concurrency=Config.WORKFLOW_MAX_CONCURRENCY,
            max_attempts=Config.WORKFLOW_MAX_STAGE_ATTEMPTS,
        )
        persistence = LangGraphPersistenceFactory(
            checkpoint_backend=Config.CHECKPOINT_BACKEND,
            store_backend=Config.STORE_BACKEND,
            sqlite_path=Config.LANGGRAPH_CHECKPOINT_DB_PATH,
            postgres_dsn=Config.LANGGRAPH_POSTGRES_DSN,
        )
        graph = LangGraphEngine(
            definition=definition, portable_scheduler=manual, persistence=persistence,
            recursion_limit=Config.WORKFLOW_RECURSION_LIMIT,
            max_concurrency=Config.WORKFLOW_MAX_CONCURRENCY,
        )
        return EngineRegistry({"manual": manual, "langgraph": graph}), WorkflowResultBuilder(ledger)

    return factory
