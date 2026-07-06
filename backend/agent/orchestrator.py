"""Orchestrator for the full schema recovery workflow."""

from __future__ import annotations

import time
import uuid
from typing import Any

from backend.agent.router import Router
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.merge import MergeWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.survey import SurveyWorker
from backend.config import Config
from backend.mcp.tool_registry import ToolRegistry
from backend.monitor.recorder import MonitorRecorder


class Orchestrator:
    def __init__(self, tool_registry: ToolRegistry, graph: Any | None = None):
        self.tool_registry = tool_registry
        self.graph = graph
        self.router = Router()
        self.recorder = MonitorRecorder()
        self.workers = {
            "survey": SurveyWorker(tool_registry),
            "column": ColumnWorker(tool_registry),
            "name": NameWorker(tool_registry),
            "code": CodeWorker(tool_registry),
            "orm": ORMWorker(tool_registry),
            "merge": MergeWorker(tool_registry),
        }

    def run_full_analysis(self) -> dict:
        if not Config.LANGGRAPH_ENABLED:
            return self.run_manual_analysis(graph_meta={"engine": "manual", "reason": "langgraph_disabled"})
        try:
            return self.run_langgraph_analysis()
        except Exception as exc:
            return self.run_manual_analysis(graph_meta={"engine": "manual_fallback", "fallback_reason": str(exc)})

    def run_langgraph_analysis(self) -> dict:
        from backend.langgraph import build_initial_state, build_result_from_state, build_schema_recovery_graph

        initial_state = build_initial_state()
        graph = self.graph or build_schema_recovery_graph(self.tool_registry)
        final_state = graph.invoke(initial_state)
        result = build_result_from_state(final_state)

        if final_state.get("merge_result"):
            context = self._context_from_state(final_state)
            self._persist_and_record(final_state["session_id"], context, result["steps"])
        return result

    def run_manual_analysis(self, graph_meta: dict[str, Any] | None = None) -> dict:
        session_id = self._new_session_id()
        context: dict[str, Any] = {"session_id": session_id}
        steps: list[dict] = []

        step1 = self._run_worker("survey", context, steps)
        if step1["status"] == "error":
            return self._build_result(session_id, "error", steps, error=step1.get("error"), graph_meta=graph_meta)
        context["survey_result"] = step1["output"]

        plan = self.router.plan_analysis(context["survey_result"])
        steps.append({"step": len(steps) + 1, "worker": "router", "status": "success", "duration_ms": 0, "output": plan})

        for worker_id, result_key in [
            ("column", "column_result"),
            ("name", "name_result"),
            ("code", "code_result"),
        ]:
            step = self._run_worker(worker_id, context, steps)
            if step["status"] in {"success", "partial"}:
                context[result_key] = step["output"]

        if context.get("survey_result", {}).get("orm_files", {}).get("count", 0) > 0:
            step = self._run_worker("orm", context, steps)
            if step["status"] in {"success", "partial"}:
                context["orm_result"] = step["output"]
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
            context["orm_result"] = {"total_relations": 0, "relations": []}

        step6 = self._run_worker("merge", context, steps)
        if step6["status"] in {"success", "partial"}:
            context["merge_result"] = step6["output"]

        if context.get("merge_result"):
            self._persist_and_record(session_id, context, steps)
        return self._build_result(session_id, "completed", steps, context, graph_meta=graph_meta or {"engine": "manual"})

    def _run_worker(self, worker_id: str, context: dict, steps: list[dict]) -> dict:
        start = time.time()
        try:
            worker = self.workers[worker_id]
            output = worker.run(context)
            duration = int((time.time() - start) * 1000)
            status = "success" if output.get("status") == "success" else "partial"
            step = {
                "step": len(steps) + 1,
                "worker": worker_id,
                "status": status,
                "duration_ms": duration,
                "tool_calls": worker.get_call_log(),
                "output": output,
            }
            steps.append(step)
            return {"status": status, "output": output, "duration_ms": duration}
        except Exception as exc:
            duration = int((time.time() - start) * 1000)
            steps.append({"step": len(steps) + 1, "worker": worker_id, "status": "error", "duration_ms": duration, "error": str(exc)})
            return {"status": "error", "error": str(exc)}

    def _context_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": state["session_id"],
            "survey_result": state.get("survey_result"),
            "column_result": state.get("column_result"),
            "name_result": state.get("name_result"),
            "code_result": state.get("code_result"),
            "orm_result": state.get("orm_result"),
            "merge_result": state.get("merge_result"),
        }

    def _persist_and_record(self, session_id: str, context: dict[str, Any], steps: list[dict]) -> None:
        try:
            from backend.agent.memory.memory_manager import MemoryManager

            memory = MemoryManager(session_id)
            db_name = context.get("survey_result", {}).get("server_info", {}).get("database", "unknown")
            memory.save_analysis_result(session_id, db_name, context["merge_result"])
        except Exception as exc:
            steps.append({"step": len(steps) + 1, "worker": "memory", "status": "warning", "duration_ms": 0, "error": str(exc)})

        self.recorder.record_analysis(session_id, context, steps)

    @staticmethod
    def _new_session_id() -> str:
        return f"ana_{uuid.uuid4().hex[:12]}"

    def _build_result(
        self,
        session_id: str,
        status: str,
        steps: list[dict],
        context: dict | None = None,
        error: str | None = None,
        graph_meta: dict[str, Any] | None = None,
    ) -> dict:
        result = {"session_id": session_id, "status": status, "total_steps": len(steps), "steps": steps}
        if context and "merge_result" in context:
            result["er_diagram"] = self._build_er_diagram(context["merge_result"])
            result["merge_result"] = context["merge_result"]
        if graph_meta:
            result["graph"] = graph_meta
        if error:
            result["error"] = error
        return result

    def _build_er_diagram(self, merge_result: dict) -> dict:
        relations = merge_result.get("high_confidence_relations", []) + merge_result.get("medium_confidence_relations", [])
        er_tables: dict[str, dict] = {}
        for rel in relations:
            src = rel["source_table"]
            tgt = rel["target_table"]
            er_tables.setdefault(src, {"relations": [], "relation_count": 0})
            er_tables.setdefault(tgt, {"relations": [], "relation_count": 0})
            er_tables[src]["relations"].append({"type": "has", "target": tgt, "via": rel["fk_column"], "confidence": rel.get("fused_confidence", 0)})
            er_tables[src]["relation_count"] += 1
        return {"table_count": len(er_tables), "tables": er_tables}
