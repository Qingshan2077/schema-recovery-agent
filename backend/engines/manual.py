"""Portable asynchronous DAG scheduler backed by shared RecoveryStages."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from backend.agent.critics import EvidenceRequestPolicy
from backend.agent.runtime.hybrid_contracts import BudgetSlice, EvidenceRequest, StageResult, WorkUnit
from backend.agent.runtime.contracts import RuntimeUsage
from backend.agent.memory.stage import stage_id_for_worker
from backend.core.identity import new_id, stable_id
from backend.core.status import AgentError, RunStatus
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import SQLiteRunRepository
from backend.workflow.contracts import (
    InterruptRef,
    RecoveryStateV2,
    RunControl,
    StageContext,
    StageExecutionRecord,
    StatePatch,
    WorkflowDefinition,
)
from backend.workflow.reducer import apply_patch, merge_patches
from backend.workflow.stage_registry import StageRegistry
from backend.workflow.state_machine import RecoveryStateMachine


class ManualEngine:
    name = "manual"

    def __init__(
        self,
        *,
        definition: WorkflowDefinition,
        stages: StageRegistry,
        runs: SQLiteRunRepository,
        events: SQLiteEventLog,
        max_concurrency: int = 4,
        max_attempts: int = 2,
        deterministic_scheduler: bool = False,
    ):
        stages.validate_definition(definition)
        self.definition = definition
        self.stages = stages
        self.runs = runs
        self.events = events
        self.max_concurrency = max(1, max_concurrency)
        self.max_attempts = max(1, max_attempts)
        self.deterministic_scheduler = deterministic_scheduler
        self.evidence_policy = EvidenceRequestPolicy()
        self.max_evidence_rounds = next(
            node.loop_limit for node in definition.nodes if node.node_id == "critic"
        )

    def cancel(self, reason: str) -> None:
        self.stages.cancel_all(reason)

    async def resume_from_latest_checkpoint(self, run_id: str) -> RecoveryStateV2:
        """Validate the portable checkpoint and continue from authoritative run state."""

        state = self.runs.get(run_id)
        checkpoint = self.runs.latest_checkpoint(run_id)
        if checkpoint is not None:
            checkpoint_state, metadata = checkpoint
            if checkpoint_state.workflow_version != self.definition.version:
                raise ValueError("portable checkpoint workflow version is incompatible")
            if checkpoint_state.state_schema_version != self.definition.state_schema_version:
                raise ValueError("portable checkpoint state schema is incompatible")
            if metadata.get("workflow_version") not in {None, self.definition.version}:
                raise ValueError("portable checkpoint metadata is incompatible")
            if not set(checkpoint_state.completed_stage_keys).issubset(state.completed_stage_keys):
                raise ValueError("authoritative run state is behind its portable checkpoint")
        return await self.run(state, resume=True)

    async def run(self, state: RecoveryStateV2, *, resume: bool = False) -> RecoveryStateV2:
        if state.active_engine != self.name:
            raise ValueError("ManualEngine may only execute a state assigned to manual")
        if RecoveryStateMachine.is_terminal(state.status):
            return state
        if state.status == "waiting_approval":
            return state
        if state.cancellation.requested:
            return await self._cancel(state)
        if state.status == "queued":
            state = self._commit(state, StatePatch(status="running", phase="load_context", expected_version=state.version))
            state = self._event(state, "run.started", node_id="load_context")
        elif resume:
            state = self._event(state, "checkpoint.restored", node_id=state.phase)

        if not state.snapshot_id:
            survey = self._work_unit(state, "survey", evidence_round=0)
            state = await self._run_group(state, [survey], phase="survey")
            if self._must_stop(state):
                return self._finish_stopped(state)

        if self.stages.has("memory.retrieve") and not self._completed_worker(state, "memory_retrieve"):
            memory_retrieve = self._work_unit(state, "memory_retrieve", evidence_round=0)
            state, _ = await self._run_one_and_apply(state, memory_retrieve, phase="memory_retrieve")

        resumed_frontier = [
            unit for unit in state.pending_work_units
            if not self._completed_unit(state, unit.work_unit_id)
        ]
        if resumed_frontier:
            state = self._event(
                state, "fanout.restored", node_id="resume_frontier",
                payload={"work_unit_ids": [item.work_unit_id for item in resumed_frontier]},
            )
            state = await self._run_group(state, resumed_frontier, phase="resume_frontier")
            if self._must_stop(state):
                return self._finish_stopped(state)

        if not self._completed_worker(state, "column"):
            fanout = [self._work_unit(state, worker, evidence_round=state.evidence_round) for worker in ("column", "name", "code", "orm")]
            state = self._persist_work_plan(state, fanout, reason="initial_fanout")
            state = self._event(state, "fanout.created", node_id="fan_out", payload={"work_unit_ids": [item.work_unit_id for item in fanout]})
            state = await self._run_group(state, fanout, phase="fan_out")
            state = self._event(state, "join.completed", node_id="validate_join")
            if self._must_stop(state):
                return self._finish_stopped(state)

        if self.stages.has("memory.verify") and not self._completed_worker(state, "memory_verify"):
            memory_verify = self._work_unit(state, "memory_verify", evidence_round=state.evidence_round)
            state, _ = await self._run_one_and_apply(state, memory_verify, phase="memory_verify")

        approval_resolved = any(key.startswith("approval:") for key in state.output_refs)
        while not (approval_resolved and state.output_refs.get("merge_result")):
            merge = self._work_unit(state, "merge", evidence_round=state.evidence_round)
            state, merge_result = await self._run_one_and_apply(state, merge, phase="merge")
            if self._must_stop(state):
                return self._finish_stopped(state)
            if merge_result.state_patch.get("critic_action") == "needs_review":
                return self._pause_for_approval(state, merge_result)
            requests = self._authorized_requests(merge_result, merge)
            if not requests:
                break
            if state.evidence_round >= self.max_evidence_rounds:
                break
            child_units = [self.evidence_policy.to_work_unit(request, merge) for request in requests]
            state = self._commit(state, StatePatch(evidence_round=state.evidence_round + 1, expected_version=state.version))
            state = self._persist_work_plan(state, child_units, reason="critic_evidence")
            state = await self._run_group(state, child_units, phase="critic_re_evidence")
            if self._must_stop(state):
                return self._finish_stopped(state)

        result_ref = state.output_refs.get("merge_result")
        if self.stages.has("memory.consolidate") and not self._completed_worker(state, "memory_consolidate"):
            memory_consolidate = self._work_unit(
                state, "memory_consolidate", evidence_round=state.evidence_round,
            )
            state, _ = await self._run_one_and_apply(
                state, memory_consolidate, phase="memory_consolidate",
            )
        has_result = bool(result_ref)
        required_failed = any(error.source in {"survey", "column", "name", "code", "merge"} for error in state.errors)
        optional_failed = any(error.source == "orm" for error in state.errors)
        degraded = any(key.endswith(":degraded") for key in state.completed_stage_keys)
        partial = any(key.endswith(":partial") for key in state.completed_stage_keys)
        terminal = RecoveryStateMachine.terminal_for(
            required_failed=required_failed,
            optional_failed=optional_failed,
            degraded=degraded,
            has_result=has_result,
            partial=partial,
        )
        state = self._commit(state, StatePatch(status=terminal, phase="finalize", result_ref=result_ref, expected_version=state.version))
        state = self._checkpoint(state, reason=f"terminal:{terminal}")
        state = self._event(state, f"run.{terminal}", node_id="finalize")
        return state

    def _pause_for_approval(
        self,
        state: RecoveryStateV2,
        merge_result: StageResult,
    ) -> RecoveryStateV2:
        safe_payload = {
            "run_id": state.run_id,
            "type": "relation_review",
            "safe_summary": merge_result.state_patch.get(
                "critic_summary", "Review ambiguous relations",
            ),
            "artifact_ids": state.artifact_ids,
            "evidence_ids": state.evidence_ids,
        }
        payload_hash = _hash(safe_payload)
        interrupt_id = stable_id(
            "interrupt", state.run_id, state.evidence_round, payload_hash,
        )
        interrupt_ref = InterruptRef(
            interrupt_id=interrupt_id,
            type="relation_review",
            requested_by_stage="critic",
            safe_summary=safe_payload["safe_summary"],
            option_schema={"type": "string", "enum": ["accept", "reject"]},
            artifact_ids=state.artifact_ids,
            evidence_ids=state.evidence_ids,
            payload_hash=payload_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            required_role="schema_reviewer",
        )
        self.runs.append_control(RunControl(
            run_id=state.run_id,
            control_type="interrupt",
            request_id=interrupt_id,
            payload_hash=payload_hash,
            payload=safe_payload,
            created_at=datetime.now(timezone.utc),
        ))
        state = self._commit(state, StatePatch(
            status="waiting_approval",
            pending_interrupt=interrupt_ref,
            phase="human_interrupt",
            expected_version=state.version,
        ))
        state = self._event(
            state, "approval.required", node_id="human_interrupt",
            payload={"interrupt_id": interrupt_id},
        )
        state = self._event(state, "run.paused", node_id="human_interrupt")
        return self._checkpoint(state, reason="manual:human_interrupt")

    async def _run_group(self, state: RecoveryStateV2, units: list[WorkUnit], *, phase: str) -> RecoveryStateV2:
        not_pending = {item.work_unit_id for item in state.pending_work_units}
        additions = [item for item in units if item.work_unit_id not in not_pending]
        if additions:
            state = self._commit(state, StatePatch(
                phase=phase, pending_work_units_add=additions, expected_version=state.version,
            ))
        if self.deterministic_scheduler:
            ordered: list[tuple[WorkUnit, StageResult]] = []
            for unit in sorted(units, key=lambda item: (item.priority, item.worker, item.work_unit_id)):
                current, result = await self._run_one_and_apply(state, unit, phase=phase)
                state = current
                ordered.append((unit, result))
                if self._must_stop(state):
                    break
            return state

        semaphore = asyncio.Semaphore(self.max_concurrency)
        stage_semaphores: dict[str, asyncio.Semaphore] = {}

        async def execute(unit: WorkUnit) -> tuple[WorkUnit, StageResult]:
            stage = self.stages.get(stage_id_for_worker(unit.worker))
            stage_semaphore = stage_semaphores.setdefault(
                stage.stage_id,
                asyncio.Semaphore(min(self.max_concurrency, stage.capabilities.max_concurrency)),
            )
            async with semaphore, stage_semaphore:
                return unit, await self._execute_stage(state, unit)

        completed = await asyncio.gather(*(execute(unit) for unit in units))
        patches = [self._patch_for_result(state, unit, result, phase) for unit, result in completed]
        state = self._commit(state, merge_patches(patches).model_copy(update={"expected_version": state.version}))
        if any(_has_usage(result) for _, result in completed):
            state = self._event(
                state, "usage.updated", node_id=phase,
                payload={"budget": state.budget.model_dump(mode="json")},
            )
        return self._checkpoint(state, reason=f"join:{phase}")

    async def _run_one_and_apply(
        self, state: RecoveryStateV2, unit: WorkUnit, *, phase: str, execution_engine: str = "manual",
    ) -> tuple[RecoveryStateV2, StageResult]:
        result = await self._execute_stage(state, unit, execution_engine=execution_engine)
        state = self._commit(state, self._patch_for_result(state, unit, result, phase))
        if _has_usage(result):
            state = self._event(
                state, "usage.updated", node_id=f"recovery.{unit.worker}",
                payload={"budget": state.budget.model_dump(mode="json")},
            )
        return self._checkpoint(state, reason=f"stage:{unit.worker}"), result

    async def _execute_stage(self, state: RecoveryStateV2, unit: WorkUnit, *, execution_engine: str = "manual") -> StageResult:
        stage_id = stage_id_for_worker(unit.worker)
        stage = self.stages.get(stage_id)
        stage_key = f"{stage_id}:{unit.work_unit_id}"
        input_hash = _hash({
            "unit": unit.model_dump(mode="json"),
            "input_refs": dict(sorted(state.output_refs.items())),
        })
        attempt = state.attempts.get(stage_key, 0) + 1
        record = StageExecutionRecord(
            run_id=state.run_id, stage_key=stage_key, stage_id=stage_id,
            work_unit_id=unit.work_unit_id, attempt=attempt, idempotency_key=unit.idempotency_key,
            status="running", input_hash=input_hash, started_at=datetime.now(timezone.utc),
        )
        self.events.append(
            state, "stage.scheduled", status=state.status, node_id=stage_id,
            payload={"work_unit_id": unit.work_unit_id}, attempt=attempt,
        )
        existing = self.runs.reserve_execution(record)
        if existing and existing.input_hash != input_hash:
            return StageResult(
                stage_id=stage_id, status=RunStatus.BLOCKED, state_patch={},
                error=AgentError(
                    code="idempotency_input_conflict", category="validation",
                    message="The idempotency key was previously used with different stage inputs",
                    source=unit.worker,
                ),
            )
        if existing and existing.status in {"completed", "success", "degraded", "partial"} and existing.output_ref:
            payload = self.runs.get_json(existing.output_ref)
            if payload is None:
                return StageResult(
                    stage_id=stage_id, status=RunStatus.BLOCKED, state_patch={},
                    error=AgentError(code="execution_output_missing", category="validation", message="Committed execution output is missing", source=unit.worker),
                )
            return StageResult.model_validate(payload)
        if existing and existing.status == "running":
            return StageResult(
                stage_id=stage_id, status=RunStatus.BLOCKED, state_patch={},
                error=AgentError(code="execution_reconciliation_required", category="validation", message="Prior execution completion is unknown", source=unit.worker),
            )

        self.events.append(state, "stage.started", status=state.status, node_id=stage_id, payload={"work_unit_id": unit.work_unit_id}, attempt=attempt)
        context = StageContext(
            run_id=state.run_id, trace_id=state.trace_id, thread_id=state.thread_id,
            active_engine=execution_engine, workflow_version=state.workflow_version,
            checkpoint_namespace=f"{state.project_id}/{state.workflow_version}",
            deterministic_scheduler=self.deterministic_scheduler,
        )
        timeout_seconds = next(
            node.timeout_seconds for node in self.definition.nodes if node.stage_id == stage_id
        )
        result = await self._invoke_stage(stage, state, unit, context, timeout_seconds)
        accumulated_usage = RuntimeUsage.model_validate(result.usage_delta)
        while result.status == RunStatus.ERROR and result.retry_classification == "safe" and attempt < self.max_attempts:
            attempt += 1
            self.events.append(state, "stage.retrying", status=state.status, node_id=stage_id, payload={"work_unit_id": unit.work_unit_id}, attempt=attempt)
            await asyncio.sleep(min(2.0, 0.25 * (2 ** (attempt - 2))))
            result = await self._invoke_stage(stage, state, unit, context, timeout_seconds)
            accumulated_usage = _sum_usage(
                accumulated_usage,
                RuntimeUsage.model_validate(result.usage_delta),
            )
        result = result.model_copy(update={
            "usage_delta": accumulated_usage.model_dump(mode="json"),
            "idempotency_record": {
                **result.idempotency_record,
                "idempotency_key": unit.idempotency_key,
                "attempt_count": attempt,
            },
        })
        output_ref = stable_id("artifact", state.run_id, unit.idempotency_key, "stage-result")
        self.runs.put_artifact(output_ref, result.model_dump(mode="json"), kind="stage_result")
        completed = record.model_copy(update={
            "attempt": attempt, "status": result.status.value, "output_ref": output_ref,
            "error": result.error, "completed_at": datetime.now(timezone.utc),
        })
        self.runs.complete_execution(completed)
        event_type = "stage.completed" if result.status in {RunStatus.SUCCESS, RunStatus.DEGRADED, RunStatus.PARTIAL} else "stage.failed"
        self.events.append(state, event_type, status=result.status.value, node_id=stage_id, payload={"work_unit_id": unit.work_unit_id, "output_ref": output_ref}, attempt=attempt)
        for domain_event in result.domain_events:
            event_payload = dict(domain_event)
            event_name = str(event_payload.pop("type", "memory.event"))
            self.events.append(
                state, event_name, status=result.status.value, node_id=stage_id,
                payload=event_payload, attempt=attempt,
            )
        return result

    async def _invoke_stage(
        self,
        stage: Any,
        state: RecoveryStateV2,
        unit: WorkUnit,
        context: StageContext,
        timeout_seconds: int,
    ) -> StageResult:
        try:
            return await asyncio.wait_for(
                stage.execute(
                    state.model_dump(mode="json"),
                    unit,
                    context.model_dump(mode="json"),
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return StageResult(
                stage_id=stage.stage_id,
                status=RunStatus.ERROR,
                state_patch={},
                retry_classification="safe" if stage.capabilities.retry_safe else "never",
                error=AgentError(
                    code="stage_timeout",
                    category="timeout",
                    message=f"stage exceeded its {timeout_seconds}s execution deadline",
                    retryable=stage.capabilities.retry_safe,
                    source=unit.worker,
                ),
            )

    def _patch_for_result(self, state: RecoveryStateV2, unit: WorkUnit, result: StageResult, phase: str) -> StatePatch:
        raw = result.state_patch
        errors = [result.error] if result.error else []
        stage_key = f"{stage_id_for_worker(unit.worker)}:{unit.work_unit_id}:{result.status.value}"
        status = None
        if unit.worker in {"survey", "column", "name", "code", "merge"}:
            if result.status == RunStatus.BLOCKED:
                status = "blocked"
            elif result.status == RunStatus.CANCELLED:
                status = "canceled"
            elif result.status == RunStatus.ERROR:
                status = "failed"
        return StatePatch(
            phase=phase,
            status=status,
            snapshot_id=raw.get("snapshot_id"),
            database_fingerprint=raw.get("database_fingerprint"),
            pending_work_unit_ids_remove=[unit.work_unit_id],
            pending_work_units_add=result.new_work_units,
            completed_stage_keys_add=[stage_key],
            artifact_ids_add=result.artifact_ids,
            evidence_ids_add=result.evidence_ids,
            relation_ids_add=result.relation_ids,
            output_refs_merge=dict(raw.get("output_refs") or {}),
            usage_delta=RuntimeUsage.model_validate(result.usage_delta),
            attempts_merge={
                f"{stage_id_for_worker(unit.worker)}:{unit.work_unit_id}": int(
                    result.idempotency_record.get("attempt_count", 1)
                )
            },
            errors_add=errors,
        )

    def _work_unit(self, state: RecoveryStateV2, worker: str, *, evidence_round: int) -> WorkUnit:
        snapshot_id = state.snapshot_id or stable_id("snapshot", state.run_id, "pending")
        fingerprint = state.database_fingerprint or state.connection_id
        idempotency = _hash({"run": state.run_id, "snapshot": snapshot_id, "worker": worker, "round": evidence_round})
        return WorkUnit(
            work_unit_id=stable_id("work_unit", state.run_id, worker, evidence_round),
            run_id=state.run_id, trace_id=state.trace_id, snapshot_id=snapshot_id,
            database_fingerprint=fingerprint, worker=worker, evidence_round=evidence_round,
            idempotency_key=idempotency, budget_slice=BudgetSlice(),
        )

    def _authorized_requests(self, result: StageResult, parent: WorkUnit) -> list[EvidenceRequest]:
        authorized = []
        for request in result.evidence_requests:
            allowed, _ = self.evidence_policy.authorize(request, parent)
            if allowed:
                authorized.append(request)
        return authorized

    def _persist_work_plan(
        self,
        state: RecoveryStateV2,
        units: list[WorkUnit],
        *,
        reason: str,
    ) -> RecoveryStateV2:
        plan = {
            "workflow_version": state.workflow_version,
            "snapshot_id": state.snapshot_id,
            "evidence_round": state.evidence_round,
            "reason": reason,
            "work_units": [item.model_dump(mode="json") for item in units],
        }
        plan_ref = stable_id("artifact", state.run_id, "work-plan", state.evidence_round, reason)
        self.runs.put_artifact(plan_ref, plan, kind="work_plan")
        return self._commit(state, StatePatch(
            work_plan_ref=plan_ref,
            artifact_ids_add=[plan_ref],
            expected_version=state.version,
        ))

    def _completed_worker(self, state: RecoveryStateV2, worker: str) -> bool:
        return any(key.startswith(f"{stage_id_for_worker(worker)}:") for key in state.completed_stage_keys)

    @staticmethod
    def _completed_unit(state: RecoveryStateV2, work_unit_id: str) -> bool:
        return any(f":{work_unit_id}:" in key for key in state.completed_stage_keys)

    def _must_stop(self, state: RecoveryStateV2) -> bool:
        return state.cancellation.requested or state.status in {"waiting_approval", "blocked", "failed", "canceled"}

    async def _cancel(self, state: RecoveryStateV2) -> RecoveryStateV2:
        state = self._commit(state, StatePatch(status="canceled", phase=state.phase, expected_version=state.version))
        return self._finish_stopped(state)

    def _finish_stopped(self, state: RecoveryStateV2) -> RecoveryStateV2:
        if state.status not in {"failed", "blocked", "canceled"}:
            return state
        if state.phase != "finalize":
            state = self._commit(state, StatePatch(phase="finalize", expected_version=state.version))
        state = self._checkpoint(state, reason=f"terminal:{state.status}")
        return self._event(state, f"run.{state.status}", node_id="finalize")

    def _checkpoint(self, state: RecoveryStateV2, *, reason: str) -> RecoveryStateV2:
        checkpoint_id = stable_id("checkpoint", state.run_id, state.version, state.phase)
        self.runs.save_checkpoint(state, checkpoint_id=checkpoint_id, metadata={
            "reason": reason, "workflow_version": state.workflow_version,
            "state_schema_version": state.state_schema_version, "active_engine": state.active_engine,
            "completed_stage_keys": state.completed_stage_keys, "artifact_ids": state.artifact_ids,
            "evidence_ids": state.evidence_ids, "budget": state.budget.model_dump(mode="json"),
            "event_sequence": state.last_event_sequence,
        })
        return self._event(state, "checkpoint.created", node_id=state.phase, payload={"checkpoint_id": checkpoint_id})

    def _commit(self, state: RecoveryStateV2, patch: StatePatch) -> RecoveryStateV2:
        next_state = apply_patch(state, patch)
        return self.runs.save(next_state, expected_version=state.version)

    def _event(self, state: RecoveryStateV2, event_type: str, *, node_id: str, payload: dict[str, Any] | None = None, attempt: int = 1) -> RecoveryStateV2:
        event = self.events.append(state, event_type, status=state.status, node_id=node_id, payload=payload, attempt=attempt)
        if event.sequence <= state.last_event_sequence:
            return state
        return self._commit(state, StatePatch(last_event_sequence=event.sequence, expected_version=state.version))


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _sum_usage(left: RuntimeUsage, right: RuntimeUsage) -> RuntimeUsage:
    return RuntimeUsage(
        model_calls=left.model_calls + right.model_calls,
        tool_calls=left.tool_calls + right.tool_calls,
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cost_usd=left.cost_usd + right.cost_usd,
        loop_iterations=left.loop_iterations + right.loop_iterations,
    )


def _has_usage(result: StageResult) -> bool:
    usage = RuntimeUsage.model_validate(result.usage_delta)
    return bool(
        usage.model_calls or usage.tool_calls or usage.input_tokens or
        usage.output_tokens or usage.cost_usd or usage.loop_iterations
    )
