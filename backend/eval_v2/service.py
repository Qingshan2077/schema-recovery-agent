"""Create, execute, read, cancel and promote immutable eval runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.identity import new_id, stable_id
from backend.eval_v2.artifacts import EvalArtifactStore
from backend.eval_v2.contracts import BaselinePromotion, EvalCreateRequest, EvalRunRecord
from backend.eval_v2.gate import GateEngine
from backend.eval_v2.hashing import content_hash
from backend.eval_v2.manifest import build_manifest
from backend.eval_v2.registry import DatasetRegistry
from backend.eval_v2.runner import CaseExecutor, EvalRunner
from backend.eval_v2.store import EvalStore
from backend.observability.tracing import TraceRecorder


class EvalService:
    def __init__(self, *, registry: DatasetRegistry, store: EvalStore, artifacts: EvalArtifactStore, traces: TraceRecorder, executor: CaseExecutor | None = None):
        self.registry, self.store, self.artifacts, self.traces = registry, store, artifacts, traces
        self.executor = executor

    def runtime_versions(self) -> dict[str, Any]:
        runtime = getattr(self.executor, "runtime", None)
        if runtime is None:
            return {
                "model_profiles": {}, "provider_versions": {},
                "prompt_hashes": {}, "tool_versions": {},
                "determinism": "non_deterministic",
            }
        profiles = runtime.profiles.public_inventory()
        prompts = runtime.prompts.public_inventory()
        tools = runtime.tool_runtime.public_inventory()
        provider_versions = {
            str(item["name"]): f"{item['provider']}:{item['model']}"
            for item in profiles
        }
        return {
            "model_profiles": {str(item["name"]): str(item["model"]) for item in profiles},
            "provider_versions": provider_versions,
            "prompt_hashes": {
                f"{item['prompt_id']}@{item['version']}": str(item["sha256"])
                for item in prompts
            },
            "tool_versions": {str(item["name"]): str(item["version"]) for item in tools},
            "determinism": (
                "deterministic"
                if profiles and all(str(item["provider"]) == "fake" for item in profiles)
                else "non_deterministic"
            ),
        }

    def create(self, request: EvalCreateRequest, *, versions: dict[str, Any], git_sha: str, dirty_worktree: bool) -> tuple[EvalRunRecord, list]:
        dataset, cases = self.registry.load(request.dataset_id, request.dataset_version, request.split)
        if request.case_ids:
            wanted = set(request.case_ids)
            cases = [case for case in cases if case.case_id in wanted]
            if len(cases) != len(wanted): raise ValueError("request contains unknown case IDs")
        eval_run_id = new_id("eval_run")
        manifest = build_manifest(eval_run_id, request, dataset, cases, versions=versions, git_sha=git_sha, dirty_worktree=dirty_worktree)
        manifest_payload = manifest.model_dump(mode="json")
        digest = content_hash(manifest_payload)
        record = EvalRunRecord(
            eval_run_id=eval_run_id, manifest_hash=digest, status="queued",
            total_cases=len(cases), qualitative_complete=False,
            started_at=manifest.started_at,
        )
        self.artifacts.create_run(eval_run_id, manifest_payload)
        self.store.create(manifest, record)
        self.store.append_event(eval_run_id, "eval.run.started", {"eval_run_id": eval_run_id, "status": "queued"})
        return record, cases

    async def execute(self, eval_run_id: str, cases: list) -> EvalRunRecord:
        record = self.store.get(eval_run_id)
        if record.status == "canceled":
            return record
        manifest = self.store.manifest(eval_run_id)
        if self.executor is None:
            now = datetime.now(timezone.utc)
            metrics: dict[str, float] = {}
            gate = GateEngine().evaluate(eval_run_id, metrics, policy_version=manifest.gate_policy, trace_complete=False, infra_failed=True)
            self.store.put_gate(gate)
            self.artifacts.write_once(eval_run_id, "metrics.json", metrics)
            self.artifacts.write_once(eval_run_id, "gate-result.json", gate.model_dump(mode="json"))
            finalization = {"status": "failed", "reason": "case_executor_unavailable", "metrics_hash": content_hash(metrics), "gate_hash": content_hash(gate.model_dump(mode="json")), "finalized_at": now.isoformat()}
            finalization_hash = self.artifacts.write_once(eval_run_id, "finalization.json", finalization)
            failed = record.model_copy(update={"sequence": record.sequence + 1, "status": "failed", "qualitative_complete": False, "trace_complete": False, "failure_reason": "case_executor_unavailable", "finalized_at": now, "finalization_hash": finalization_hash})
            return self.store.save(failed, expected_sequence=record.sequence)
        running = self.store.save(record.model_copy(update={"sequence": record.sequence + 1, "status": "running"}), expected_sequence=record.sequence)
        metrics, trace_complete, infra_failed, completed_cases, failed_cases = await EvalRunner(store=self.store, artifacts=self.artifacts, traces=self.traces, executor=self.executor).run(manifest, cases)
        current = self.store.get(eval_run_id)
        if current.status == "canceled":
            return current
        gate = GateEngine().evaluate(eval_run_id, metrics, policy_version=manifest.gate_policy, trace_complete=trace_complete, infra_failed=infra_failed)
        self.store.put_gate(gate)
        self.artifacts.write_once(eval_run_id, "metrics.json", metrics)
        self.artifacts.write_once(eval_run_id, "gate-result.json", gate.model_dump(mode="json"))
        finalization = {"status": "completed" if gate.status != "infra_failed" else "failed", "metrics_hash": content_hash(metrics), "gate_hash": content_hash(gate.model_dump(mode="json")), "finalized_at": datetime.now(timezone.utc).isoformat()}
        finalization_hash = self.artifacts.write_once(eval_run_id, "finalization.json", finalization)
        final = running.model_copy(update={"sequence": running.sequence + 1, "status": finalization["status"], "completed_cases": completed_cases, "failed_cases": failed_cases, "trace_complete": trace_complete, "qualitative_complete": False, "failure_reason": "eval_infrastructure_failure" if infra_failed else None, "finalized_at": datetime.now(timezone.utc), "finalization_hash": finalization_hash})
        final = self.store.save(final, expected_sequence=running.sequence)
        self.store.append_event(eval_run_id, "eval.gate.evaluated", {"status": gate.status, "blocking_reasons": gate.blocking_reasons})
        self.store.append_event(eval_run_id, "eval.run.completed", {"status": final.status})
        return final

    def report(self, eval_run_id: str) -> dict[str, Any]:
        if not self.artifacts.finalized(eval_run_id): raise KeyError("no_finalized_eval_report")
        return {name: self.artifacts.read(eval_run_id, name)["payload"] for name in ("manifest.json", "metrics.json", "gate-result.json", "finalization.json")}

    def cancel(self, eval_run_id: str) -> EvalRunRecord:
        record = self.store.get(eval_run_id)
        if record.status in {"completed", "failed", "canceled"}:
            raise ValueError("eval_run_is_terminal")
        cancelled = record.model_copy(update={
            "sequence": record.sequence + 1, "status": "canceled",
            "finalized_at": datetime.now(timezone.utc),
        })
        cancelled = self.store.save(cancelled, expected_sequence=record.sequence)
        self.store.append_event(eval_run_id, "eval.run.canceled", {"status": "canceled"})
        return cancelled

    def promote(self, eval_run_id: str, *, gate: str, actor_id: str, actor_role: str, reason: str) -> BaselinePromotion:
        record = self.store.get(eval_run_id)
        manifest = self.store.manifest(eval_run_id)
        try:
            decision = self.store.gate_for_run(eval_run_id)
        except KeyError as exc:
            raise ValueError("eval run has no immutable gate decision") from exc
        if record.status != "completed" or not record.trace_complete or manifest.dirty_worktree or decision.status != "passed":
            raise ValueError("only gate-passed finalized clean-worktree trace-complete runs may become baselines")
        promotion = BaselinePromotion(promotion_id=stable_id("eval_run", "baseline", gate, eval_run_id), gate=gate, eval_run_id=eval_run_id, actor_id=actor_id, actor_role=actor_role, reason=reason, created_at=datetime.now(timezone.utc))
        self.store.promote(promotion)
        self.store.append_event(eval_run_id, "eval.baseline.promoted", promotion.model_dump(mode="json"))
        return promotion
