"""Orchestrator for the full schema recovery workflow."""

from __future__ import annotations

import re
import time
from typing import Any

from backend.agent.router import Router
from backend.agent.runtime import build_default_budget
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.merge import MergeWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.survey import SurveyWorker
from backend.agent.workers.hybrid_stage import HybridWorkerRunner, configured_worker_mode
from backend.config import Config
from backend.core.identity import RunIdentity
from backend.core.lineage import attach_merge_lineage
from backend.core.status import (
    RunStatus,
    coerce_run_status,
    coerce_worker_status,
    combine_run_status,
    reduce_run_status,
    validate_terminal_result,
)
from backend.mcp.tool_registry import ToolRegistry
from backend.monitor.recorder import MonitorRecorder


class Orchestrator:
    REQUIRED_WORKERS = ("survey", "column", "name", "code", "merge")
    OPTIONAL_WORKERS = ("orm", "memory", "monitor")

    def __init__(
        self,
        tool_registry: ToolRegistry,
        graph: Any | None = None,
        *,
        recorder: MonitorRecorder | None = None,
        memory_db_path: str | None = None,
        global_memory_db_path: str | None = None,
        snapshot_db_path: str | None = None,
        run_context: RunContext | None = None,
        tool_runtime: ToolRuntime | None = None,
        model_gateway: ModelGateway | None = None,
    ):
        self.tool_registry = tool_registry
        self.graph = graph
        self.router = Router()
        self.recorder = recorder or MonitorRecorder()
        self.memory_db_path = memory_db_path
        self.global_memory_db_path = global_memory_db_path
        self.snapshot_db_path = snapshot_db_path
        self.run_context = run_context
        self.tool_runtime = tool_runtime or tool_registry.runtime
        self.model_gateway = model_gateway
        self.hybrid_runner: HybridWorkerRunner | None = None
        self.workers = {
            "survey": SurveyWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
            "column": ColumnWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
            "name": NameWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
            "code": CodeWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
            "orm": ORMWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
            "merge": MergeWorker(tool_registry, run_context=run_context, tool_runtime=self.tool_runtime, model_gateway=model_gateway),
        }
        if run_context is not None:
            for worker in self.workers.values():
                worker.configure_runtime(
                    run_context=run_context,
                    tool_runtime=self.tool_runtime,
                    model_gateway=model_gateway,
                )

    def run_full_analysis(self, identity: RunIdentity | None = None) -> dict[str, Any]:
        identity = identity or RunIdentity.create()
        if not Config.LANGGRAPH_ENABLED:
            return self.run_manual_analysis(
                identity=identity,
                graph_meta={"engine": "manual", "reason": "langgraph_disabled"},
            )
        try:
            return self.run_langgraph_analysis(identity=identity)
        except Exception as exc:
            # Phase 0 deliberately does not start a second full analysis after a
            # graph failure. The caller can explicitly retry the same run.
            return self.build_failed_result(
                identity,
                error=_safe_error(exc),
                graph_meta={
                    "engine": "langgraph",
                    "fallback_disabled": True,
                    "fallback_reason": _safe_error(exc),
                },
            )

    def run_langgraph_analysis(self, identity: RunIdentity | None = None) -> dict[str, Any]:
        from backend.langgraph import build_initial_state, build_result_from_state, build_schema_recovery_graph

        identity = identity or RunIdentity.create()
        initial_state = build_initial_state(
            identity=identity,
            snapshot_db_path=self.snapshot_db_path,
        )
        graph = self.graph or build_schema_recovery_graph(
            self.tool_registry,
            model_gateway=self.model_gateway,
        )
        final_state = graph.invoke(initial_state)
        if final_state.get("merge_result"):
            attach_merge_lineage(
                final_state["merge_result"],
                run_id=identity.run_id,
                trace_id=identity.trace_id,
                database_fingerprint=final_state.get("database_fingerprint"),
                snapshot_id=final_state.get("snapshot_id"),
            )
        result = build_result_from_state(final_state)
        context = self._context_from_state(final_state)
        final_status = self._persist_and_record(
            identity,
            context,
            result["steps"],
            result.get("run_status") or result["status"],
        )
        result["status"] = final_status.value
        result["run_status"] = final_status.value
        result["total_steps"] = len(result["steps"])
        return result

    def run_manual_analysis(
        self,
        graph_meta: dict[str, Any] | None = None,
        *,
        identity: RunIdentity | None = None,
    ) -> dict[str, Any]:
        identity = identity or RunIdentity.create()
        context: dict[str, Any] = {
            **identity.as_context(),
            "session_id": identity.run_id,
            "snapshot_db_path": self.snapshot_db_path,
        }
        steps: list[dict[str, Any]] = []

        survey_step = self._run_worker("survey", context, steps)
        if survey_step["status"] == "error":
            status = self._persist_and_record(identity, context, steps, RunStatus.ERROR)
            return self._build_result(
                identity,
                status,
                steps,
                context,
                error=survey_step.get("error"),
                graph_meta=graph_meta or {"engine": "manual"},
            )
        context["survey_result"] = survey_step["output"]
        _copy_snapshot_identity(context, survey_step["output"])

        plan = self.router.plan_analysis(context["survey_result"])
        steps.append(
            {
                "step": len(steps) + 1,
                "worker": "router",
                "status": "success",
                "duration_ms": 0,
                "output": plan,
            }
        )

        for worker_id, result_key in (
            ("column", "column_result"),
            ("name", "name_result"),
            ("code", "code_result"),
        ):
            step = self._run_worker(worker_id, context, steps)
            if step["status"] in {"success", "partial", "degraded"}:
                context[result_key] = step["output"]

        if context.get("survey_result", {}).get("orm_files", {}).get("count", 0) > 0:
            orm_step = self._run_worker("orm", context, steps)
            if orm_step["status"] in {"success", "partial", "degraded"}:
                context["orm_result"] = orm_step["output"]
        else:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "worker": "orm",
                    "status": "skipped",
                    "duration_ms": 0,
                    "output": {"message": "No ORM files found, skipping"},
                }
            )
            context["orm_result"] = {
                "status": "success",
                "total_relations": 0,
                "relations": [],
            }

        merge_step = self._run_worker("merge", context, steps)
        if merge_step["status"] in {"success", "partial", "degraded"}:
            context["merge_result"] = merge_step["output"]
            attach_merge_lineage(
                context["merge_result"],
                run_id=identity.run_id,
                trace_id=identity.trace_id,
                database_fingerprint=context.get("database_fingerprint"),
                snapshot_id=context.get("snapshot_id"),
            )

        status = self._reduce_analysis_status(steps)
        status = self._persist_and_record(identity, context, steps, status)
        error = _first_required_error(steps, self.REQUIRED_WORKERS)
        return self._build_result(
            identity,
            status,
            steps,
            context,
            error=error,
            graph_meta=graph_meta or {"engine": "manual"},
        )

    def _run_worker(
        self,
        worker_id: str,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.time()
        worker = self.workers[worker_id]
        if self.run_context is None:
            identity = RunIdentity(
                run_id=context["run_id"],
                trace_id=context["trace_id"],
                thread_id=context.get("thread_id"),
                parent_run_id=context.get("parent_run_id"),
                attempt=int(context.get("attempt", 1)),
            )
            self.run_context = RunContext.from_identity(
                identity,
                agent_id="orchestrator",
                budget=build_default_budget(Config),
            )
        worker.configure_runtime(
            run_context=self.run_context,
            tool_runtime=self.tool_runtime,
            model_gateway=self.model_gateway,
        )
        worker.reset_call_log()
        try:
            mode = configured_worker_mode(worker_id)
            if mode == "legacy":
                output = worker.run(context)
            else:
                if self.hybrid_runner is None:
                    self.hybrid_runner = HybridWorkerRunner(
                        run_context=self.run_context,
                        tool_runtime=self.tool_runtime,
                        model_gateway=self.model_gateway,
                    )
                output = self.hybrid_runner.run(worker_id, worker, context, mode)
            if not isinstance(output, dict):
                raise TypeError(f"{worker_id} worker returned a non-object result")
            status = coerce_worker_status(output.get("status"))
            duration = int((time.time() - start) * 1000)
            error = str(output.get("error")) if status == "error" and output.get("error") else None
            step = {
                "step": len(steps) + 1,
                "worker": worker_id,
                "status": status,
                "duration_ms": duration,
                "tool_calls": worker.get_call_log(),
                "output": output,
            }
            if error:
                step["error"] = error
            steps.append(step)
            return {"status": status, "output": output, "duration_ms": duration, "error": error}
        except Exception as exc:
            duration = int((time.time() - start) * 1000)
            error = _safe_error(exc)
            steps.append(
                {
                    "step": len(steps) + 1,
                    "worker": worker_id,
                    "status": "error",
                    "duration_ms": duration,
                    "tool_calls": worker.get_call_log(),
                    "error": error,
                }
            )
            return {"status": "error", "error": error, "duration_ms": duration}

    def _context_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": state["run_id"],
            "run_id": state["run_id"],
            "trace_id": state["trace_id"],
            "thread_id": state.get("thread_id"),
            "parent_run_id": state.get("parent_run_id"),
            "attempt": state.get("attempt", 1),
            "database_fingerprint": state.get("database_fingerprint"),
            "snapshot_id": state.get("snapshot_id"),
            "survey_result": state.get("survey_result"),
            "column_result": state.get("column_result"),
            "name_result": state.get("name_result"),
            "code_result": state.get("code_result"),
            "orm_result": state.get("orm_result"),
            "merge_result": state.get("merge_result"),
        }

    def _persist_and_record(
        self,
        identity: RunIdentity,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
        status: RunStatus | str,
    ) -> RunStatus:
        final_status = coerce_run_status(status)
        merge_result = context.get("merge_result")
        if Config.EVIDENCE_LEDGER_DUAL_WRITE and merge_result and final_status in {
            RunStatus.SUCCESS,
            RunStatus.PARTIAL,
            RunStatus.DEGRADED,
        }:
            try:
                from backend.agent.memory.memory_manager import MemoryManager

                memory = MemoryManager(
                    identity.run_id,
                    schema_db_path=self.memory_db_path,
                    global_db_path=self.global_memory_db_path,
                )
                database = context.get("survey_result", {}).get("server_info", {}).get("database", "unknown")
                memory.save_analysis_result(
                    identity,
                    database,
                    merge_result,
                    survey_result=context.get("survey_result") or {},
                )
            except Exception as exc:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "worker": "memory",
                        "status": "partial",
                        "duration_ms": 0,
                        "error": _safe_error(exc),
                    }
                )
                final_status = combine_run_status([final_status, RunStatus.PARTIAL])

        try:
            self.recorder.record_analysis(identity, context, steps, status=final_status)
        except Exception as exc:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "worker": "monitor",
                    "status": "partial",
                    "duration_ms": 0,
                    "error": _safe_error(exc),
                }
            )
            final_status = combine_run_status([final_status, RunStatus.PARTIAL])
        return final_status

    def _reduce_analysis_status(self, steps: list[dict[str, Any]]) -> RunStatus:
        by_worker = {step.get("worker"): step.get("status", "missing") for step in steps}
        required = {worker: by_worker.get(worker, "missing") for worker in self.REQUIRED_WORKERS}
        optional = {
            worker: by_worker[worker]
            for worker in self.OPTIONAL_WORKERS
            if worker in by_worker
        }
        return reduce_run_status(required, optional)

    def build_failed_result(
        self,
        identity: RunIdentity,
        *,
        error: str,
        steps: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        graph_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error = _safe_error(error)
        if graph_meta and graph_meta.get("fallback_reason"):
            graph_meta = {
                **graph_meta,
                "fallback_reason": _safe_error(graph_meta["fallback_reason"]),
            }
        failed_steps = list(steps or [])
        failed_steps.append(
            {
                "step": len(failed_steps) + 1,
                "worker": "runtime",
                "status": "error",
                "duration_ms": 0,
                "error": error,
            }
        )
        failed_context = context or {**identity.as_context(), "session_id": identity.run_id}
        status = self._persist_and_record(identity, failed_context, failed_steps, RunStatus.ERROR)
        return self._build_result(
            identity,
            status,
            failed_steps,
            failed_context,
            error=error,
            graph_meta=graph_meta,
        )

    def _build_result(
        self,
        identity: RunIdentity,
        status: RunStatus | str,
        steps: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        error: str | None = None,
        graph_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        canonical = coerce_run_status(status)
        result: dict[str, Any] = {
            "session_id": identity.run_id,
            **identity.model_dump(),
            "status": canonical.value,
            "run_status": canonical.value,
            "total_steps": len(steps),
            "steps": steps,
        }
        gaps = [
            {
                "worker": step.get("worker"),
                "status": step.get("status"),
                "error": step.get("error"),
            }
            for step in steps
            if step.get("status") in {"partial", "degraded", "blocked", "error", "cancelled"}
        ]
        result["capability_gaps"] = gaps
        result["next_actions"] = (
            ["Inspect the failed step and explicitly retry this run"]
            if canonical in {RunStatus.ERROR, RunStatus.PARTIAL, RunStatus.DEGRADED}
            else []
        )
        if context and context.get("merge_result"):
            result["er_diagram"] = self._build_er_diagram(context["merge_result"])
            result["merge_result"] = context["merge_result"]
            result["snapshot_id"] = context.get("snapshot_id")
            result["database_fingerprint"] = context.get("database_fingerprint")
        if graph_meta:
            result["graph"] = graph_meta
        if error:
            result["error"] = error
            result["error_detail"] = {
                "code": "analysis_failed",
                "category": "internal",
                "message": error,
                "retryable": canonical not in {RunStatus.CANCELLED, RunStatus.BLOCKED},
                "source": "orchestrator",
                "details": {},
            }
        validate_terminal_result(
            canonical,
            result.get("merge_result"),
            error,
            require_output=canonical == RunStatus.SUCCESS,
        )
        return result

    def _build_er_diagram(self, merge_result: dict[str, Any]) -> dict[str, Any]:
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


def _copy_snapshot_identity(context: dict[str, Any], survey_result: dict[str, Any]) -> None:
    server_info = survey_result.get("server_info") or {}
    context["database_fingerprint"] = server_info.get("database_fingerprint")
    context["snapshot_id"] = server_info.get("snapshot_id")


def _first_required_error(steps: list[dict[str, Any]], required_workers: tuple[str, ...]) -> str | None:
    required = set(required_workers)
    for step in steps:
        if step.get("worker") in required and step.get("status") == "error":
            return step.get("error") or f"{step.get('worker')} failed"
    return None


def _safe_error(error: Exception | str) -> str:
    message = str(error)
    return re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
        r"\1=***",
        message,
    )[:1000]
