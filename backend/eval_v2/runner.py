"""Isolated per-case evaluation orchestration with immutable attempts."""

from __future__ import annotations

from typing import Any, Protocol

from backend.eval_v2.artifacts import EvalArtifactStore
from backend.eval_v2.contracts import EvalCase, EvalRunManifest
from backend.eval_v2.metrics.schema import schema_metrics
from backend.eval_v2.store import EvalStore
from backend.observability.tracing import TraceRecorder


class CaseExecutor(Protocol):
    async def execute(self, case: EvalCase, *, namespace: str, manifest: EvalRunManifest) -> dict[str, Any]: ...
    async def cleanup(self, namespace: str) -> dict[str, Any]: ...


class EvalRunner:
    def __init__(self, *, store: EvalStore, artifacts: EvalArtifactStore, traces: TraceRecorder, executor: CaseExecutor):
        self.store = store
        self.artifacts = artifacts
        self.traces = traces
        self.executor = executor

    async def run(self, manifest: EvalRunManifest, cases: list[EvalCase]) -> tuple[dict[str, float], bool]:
        predicted: list[dict] = []
        gold: list[dict] = []
        trace_complete = True
        for case in cases:
            namespace = f"eval/{manifest.eval_run_id}/{case.case_id}/1"
            self.store.append_event(manifest.eval_run_id, "eval.case.started", {"case_id": case.case_id, "attempt": 1})
            with self.traces.span("eval.case", attributes={
                "eval.run.id": manifest.eval_run_id, "eval.case.id": case.case_id,
                "dataset.id": manifest.dataset_id, "dataset.version": manifest.dataset_version,
                "dataset.split": manifest.split, "engine": manifest.engine,
            }) as span:
                result = await self.executor.execute(case, namespace=namespace, manifest=manifest)
                span.set(status=str(result.get("status", "unknown")))
            cleanup = await self.executor.cleanup(namespace)
            if cleanup.get("leaked"):
                result["isolation_leak"] = True
            self.artifacts.write_once(manifest.eval_run_id, f"cases/{case.case_id}/1.json", result)
            self.store.append_event(manifest.eval_run_id, "eval.case.completed", {"case_id": case.case_id, "attempt": 1, "trace_id": result.get("trace_id")})
            if case.task_type == "schema":
                predicted.extend(result.get("relations") or [])
                gold.extend(case.reference.get("relations") or [])
            if not result.get("trace_complete", True): trace_complete = False
        return schema_metrics(predicted, gold), trace_complete
