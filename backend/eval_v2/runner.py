"""Isolated per-case evaluation orchestration with immutable attempts."""

from __future__ import annotations

from typing import Any, Protocol

from backend.eval_v2.artifacts import EvalArtifactStore
from backend.eval_v2.contracts import EvalCase, EvalRunManifest
from backend.eval_v2.metrics.schema import schema_metrics
from backend.eval_v2.metrics.qa import qa_metrics
from backend.eval_v2.metrics.calibration import calibration_metrics
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

    async def run(self, manifest: EvalRunManifest, cases: list[EvalCase]) -> tuple[dict[str, float], bool, bool, int, int]:
        predicted: list[dict] = []
        gold: list[dict] = []
        qa_rows: list[tuple[dict, dict]] = []
        probabilities: list[float] = []
        labels: list[int] = []
        isolation_leaks = 0
        completed_cases = 0
        failed_cases = 0
        infrastructure_failures = 0
        trace_complete = True
        for case in cases:
            if self.store.get(manifest.eval_run_id).status == "canceled":
                break
            namespace = f"eval/{manifest.eval_run_id}/{case.case_id}/1"
            self.store.append_event(manifest.eval_run_id, "eval.case.started", {"case_id": case.case_id, "attempt": 1})
            try:
                with self.traces.span("eval.case", attributes={
                    "eval.run.id": manifest.eval_run_id, "eval.case.id": case.case_id,
                    "dataset.id": manifest.dataset_id, "dataset.version": manifest.dataset_version,
                    "dataset.split": manifest.split, "engine": manifest.engine,
                }) as span:
                    result = await self.executor.execute(case, namespace=namespace, manifest=manifest)
                    span.set(**{"eval.case.status": str(result.get("status", "unknown"))})
                if result.get("status") in {"failed", "blocked", "canceled"}:
                    failed_cases += 1
                else:
                    completed_cases += 1
            except Exception as exc:
                failed_cases += 1
                infrastructure_failures += 1
                trace_complete = False
                result = {
                    "status": "failed", "case_id": case.case_id,
                    "error": {"code": "eval_case_execution_failed", "type": type(exc).__name__},
                    "trace_complete": False,
                }
            try:
                cleanup = await self.executor.cleanup(namespace)
            except Exception as exc:
                cleanup = {"leaked": True, "error_type": type(exc).__name__}
                infrastructure_failures += 1
            if cleanup.get("leaked"):
                result["isolation_leak"] = True
                isolation_leaks += 1
            self.artifacts.write_once(manifest.eval_run_id, f"cases/{case.case_id}/1.json", result)
            case_event = "eval.case.completed" if result.get("status") not in {"failed", "blocked", "canceled"} else "eval.case.failed"
            self.store.append_event(manifest.eval_run_id, case_event, {"case_id": case.case_id, "attempt": 1, "trace_id": result.get("trace_id"), "status": result.get("status")})
            if case.task_type == "schema":
                predicted.extend(result.get("relations") or [])
                gold.extend(case.reference.get("relations") or [])
                for relation in result.get("relations") or []:
                    probabilities.append(float(relation.get("calibrated_probability", relation.get("confidence", 0.0))))
                    labels.append(int(any(_same_edge(relation, expected) for expected in case.reference.get("relations") or [])))
            if case.task_type == "qa":
                qa_rows.append((result, case.reference))
            if not result.get("trace_complete", True): trace_complete = False
        metrics: dict[str, float] = {}
        if predicted or gold:
            metrics.update(schema_metrics(predicted, gold))
        metrics.update(qa_metrics(qa_rows))
        if probabilities:
            metrics.update(calibration_metrics(probabilities, labels))
        metrics["memory_cross_namespace_leakage"] = float(isolation_leaks)
        metrics["trace_provenance_completeness"] = 1.0 if trace_complete else 0.0
        metrics["eval_case_execution_success_rate"] = completed_cases / len(cases) if cases else 0.0
        metrics["eval_case_outcome_failure_rate"] = failed_cases / len(cases) if cases else 0.0
        metrics["eval_infrastructure_failure_count"] = float(infrastructure_failures)
        return metrics, trace_complete, bool(infrastructure_failures or isolation_leaks), completed_cases, failed_cases


def _same_edge(left: dict, right: dict) -> bool:
    def edge(value: dict) -> tuple:
        return (
            str(value.get("source_table", "")).casefold(),
            tuple(str(item).casefold() for item in value.get("source_columns") or [value.get("fk_column", "")]),
            str(value.get("target_table", "")).casefold(),
            tuple(str(item).casefold() for item in value.get("target_columns") or [value.get("pk_column", "")]),
        )
    return edge(left) == edge(right)
