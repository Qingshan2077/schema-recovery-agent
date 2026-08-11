"""Application service for run creation, execution, replay, resume, and cancel."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any

from backend.agent.runtime.redaction import RedactionPolicy
from backend.core.status import AgentError
from backend.engines.fallback import FallbackCoordinator
from backend.engines.registry import EngineRegistry
from backend.persistence.checkpoints import PersistenceBackendUnavailable
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import OptimisticLockError, SQLiteRunRepository
from backend.workflow.contracts import CancellationState, RecoveryStateV2, RunControl, StatePatch
from backend.workflow.reducer import apply_patch
from backend.workflow.result_builder import WorkflowResultBuilder
from backend.workflow.state_machine import RecoveryStateMachine
from backend.core.identity import RunIdentity, new_id, stable_id

EngineFactory = Callable[[RecoveryStateV2], tuple[EngineRegistry, WorkflowResultBuilder]]


class WorkflowCompatibilityError(ValueError):
    pass


class RecoveryRunService:
    def __init__(
        self,
        *,
        runs: SQLiteRunRepository,
        events: SQLiteEventLog,
        engine_factory: EngineFactory,
        workflow_version: str,
        state_schema_version: str,
        configured_engine: str,
        auto_fallback: bool = True,
        max_fallbacks: int = 1,
        deadline_seconds: int | None = None,
    ):
        self.runs = runs
        self.events = events
        self.engine_factory = engine_factory
        self.workflow_version = workflow_version
        self.state_schema_version = state_schema_version
        self.configured_engine = configured_engine
        self.auto_fallback = auto_fallback
        self.deadline_seconds = deadline_seconds
        self.fallback = FallbackCoordinator(runs, events, max_fallbacks=max_fallbacks)
        self._engine_bundles: dict[str, tuple[EngineRegistry, WorkflowResultBuilder]] = {}

    def create_run(
        self,
        *,
        project_id: str,
        connection_id: str,
        tenant_id: str = "default",
        database_name: str = "default",
        schema_name: str = "default",
        thread_id: str | None = None,
        session_id: str | None = None,
        engine: str | None = None,
    ) -> RecoveryStateV2:
        requested = engine or self.configured_engine
        if requested in {"legacy", "shadow"}:
            requested = "manual_v2"
        selected = self._engine_name(requested)
        identity = RunIdentity.create(thread_id=thread_id or new_id("thread"))
        state = RecoveryStateV2(
            workflow_version=self.workflow_version,
            state_schema_version=self.state_schema_version,
            run_id=identity.run_id,
            trace_id=identity.trace_id,
            thread_id=identity.thread_id or new_id("thread"),
            session_id=session_id or identity.run_id,
            project_id=project_id,
            connection_id=connection_id,
            tenant_id=tenant_id,
            database_name=database_name,
            schema_name=schema_name,
            active_engine=selected,
            deadline_at=(
                datetime.now(timezone.utc) + timedelta(seconds=self.deadline_seconds)
                if self.deadline_seconds is not None else None
            ),
        )
        self.runs.create(state)
        event = self.events.append(state, "run.queued", status="queued", node_id="run_service")
        next_state = apply_patch(state, StatePatch(last_event_sequence=event.sequence, expected_version=state.version))
        return self.runs.save(next_state, expected_version=state.version)

    async def execute(self, run_id: str) -> dict[str, Any]:
        state = self.runs.get(run_id)
        try:
            self._validate_versions(state)
        except WorkflowCompatibilityError as exc:
            state = self._block_incompatible(state, str(exc))
            _, result_builder = self._bundle(state)
            return result_builder.build(state)
        engines, result_builder = self._bundle(state)
        engine = engines.get(state.active_engine)
        try:
            final = await engine.run(state, resume=state.status == "running") if state.active_engine == "manual" else await engine.run(state)
        except Exception as exc:
            concurrent = self.runs.get(run_id)
            if isinstance(exc, OptimisticLockError) and concurrent.status == "canceled":
                return result_builder.build(concurrent)
            if not self._may_fallback(state) or not _is_engine_infrastructure_failure(exc):
                raise
            latest = concurrent
            safe = not self.runs.has_inflight_execution(run_id)
            takeover = self.fallback.takeover(latest, reason=_safe_error(exc), in_flight_known_safe=safe)
            engines, result_builder = self._bundle(takeover, rebuild=True)
            final = await engines.get("manual").run(takeover, resume=True)
        return result_builder.build(final)

    def get_run(self, run_id: str) -> dict[str, Any]:
        state = self.runs.get(run_id)
        _, builder = self._bundle(state)
        return builder.build(state)

    def get_events(self, run_id: str, *, after_sequence: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        self.runs.get(run_id)
        return [item.model_dump(mode="json") for item in self.events.replay(run_id, after_sequence=after_sequence, limit=limit)]

    async def stream_events(self, run_id: str, *, after_sequence: int = 0) -> AsyncIterator[dict[str, Any]]:
        for event in self.get_events(run_id, after_sequence=after_sequence):
            yield event

    async def resume(
        self,
        run_id: str,
        *,
        interrupt_id: str,
        request_id: str,
        decision: Any,
        payload_hash: str,
        actor_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        state = self.runs.get(run_id)
        try:
            self._validate_versions(state)
        except WorkflowCompatibilityError as exc:
            self._block_incompatible(state, str(exc))
            raise
        request_hash = _hash({
            "interrupt_id": interrupt_id,
            "decision": decision,
            "payload_hash": payload_hash,
        })
        prior_control = self.runs.get_control(run_id, request_id)
        if prior_control is not None:
            if prior_control.control_type != "resume" or prior_control.payload_hash != request_hash:
                raise PermissionError("resume request id was already used with a different payload")
            if prior_control.status == "resolved":
                return self.get_run(run_id)
            if (
                RecoveryStateMachine.is_terminal(state.status)
                and f"approval:{interrupt_id}" in state.output_refs
            ):
                self.runs.resolve_control(run_id, request_id, status="resolved")
                return self.get_run(run_id)
        if state.status != "waiting_approval" or state.pending_interrupt is None:
            raise ValueError("run is not waiting for approval")
        pending = state.pending_interrupt
        if pending.interrupt_id != interrupt_id or pending.payload_hash != payload_hash:
            raise PermissionError("interrupt identity or payload hash does not match")
        if datetime.now(timezone.utc) >= pending.expires_at:
            expired = apply_patch(state, StatePatch(status="expired", expected_version=state.version))
            expired = self.runs.save(expired, expected_version=state.version)
            interrupt_control = self.runs.get_control(run_id, interrupt_id)
            if interrupt_control is not None and interrupt_control.status == "pending":
                self.runs.resolve_control(run_id, interrupt_id, status="expired")
            expired = self._record_event(expired, "approval.expired", node_id="run_service")
            self.runs.save_checkpoint(
                expired,
                checkpoint_id=stable_id("checkpoint", run_id, expired.version, "expired"),
                metadata={
                    "reason": "approval_expired",
                    "workflow_version": expired.workflow_version,
                    "state_schema_version": expired.state_schema_version,
                    "active_engine": expired.active_engine,
                    "event_sequence": expired.last_event_sequence,
                },
            )
            raise ValueError("interrupt has expired")
        if actor_role != pending.required_role:
            raise PermissionError("actor role cannot resolve this interrupt")
        control = RunControl(
            run_id=run_id, control_type="resume", request_id=request_id,
            payload_hash=request_hash,
            actor_id=actor_id, actor_role=actor_role,
            payload={
                "interrupt_id": interrupt_id,
                "decision_hash": _hash(decision),
                "payload_hash": payload_hash,
            },
            created_at=datetime.now(timezone.utc),
        )
        existing = self.runs.append_control(control)
        if existing.status == "resolved":
            return self.get_run(run_id)
        interrupt_control = self.runs.get_control(run_id, interrupt_id)
        if interrupt_control is not None and interrupt_control.status == "pending":
            self.runs.resolve_control(run_id, interrupt_id, status="resolved")
        engines, builder = self._bundle(state)
        if state.active_engine == "langgraph":
            final = await engines.get("langgraph").run(state, resume_value={
                "interrupt_id": interrupt_id,
                "decision": decision,
                "request_id": request_id,
                "payload_hash": payload_hash,
                "actor_id": actor_id,
                "actor_role": actor_role,
            })
        else:
            decision_artifact = stable_id("artifact", run_id, interrupt_id, request_id, "human-decision")
            self.runs.put_artifact(
                decision_artifact,
                {
                    "interrupt_id": interrupt_id,
                    "request_id": request_id,
                    "decision": decision,
                    "payload_hash": payload_hash,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                },
                kind="human_control",
            )
            resumed = apply_patch(state, StatePatch(
                status="running", clear_interrupt=True,
                artifact_ids_add=[decision_artifact],
                output_refs_merge={f"approval:{interrupt_id}": decision_artifact},
                phase="human_resolved", expected_version=state.version,
            ))
            resumed = self.runs.save(resumed, expected_version=state.version)
            resumed = self._record_event(
                resumed, "approval.resolved", node_id="run_service",
                payload={"interrupt_id": interrupt_id, "request_id": request_id},
            )
            resumed = self._record_event(resumed, "run.resumed", node_id="run_service")
            final = await engines.get("manual").run(resumed, resume=True)
        self.runs.resolve_control(run_id, request_id, status="resolved")
        return builder.build(final)

    def cancel(self, run_id: str, *, request_id: str, reason: str, actor_id: str | None = None) -> dict[str, Any]:
        state = self.runs.get(run_id)
        safe_reason = str(RedactionPolicy().redact({"reason": reason}).get("reason", "cancelled"))
        control = RunControl(
            run_id=run_id, control_type="cancel", request_id=request_id,
            payload_hash=_hash({"reason": reason}), actor_id=actor_id,
            payload={"reason": safe_reason}, created_at=datetime.now(timezone.utc),
        )
        existing = self.runs.append_control(control)
        if existing.status == "resolved":
            return self.get_run(run_id)
        if RecoveryStateMachine.is_terminal(state.status):
            self.runs.resolve_control(run_id, request_id, status="resolved")
            return self.get_run(run_id)
        requested = apply_patch(state, StatePatch(
            cancellation=CancellationState(
                requested=True, request_id=request_id, reason=safe_reason,
                requested_at=datetime.now(timezone.utc),
            ),
            expected_version=state.version,
        ))
        state = self.runs.save(requested, expected_version=state.version)
        state = self._record_event(
            state, "run.cancel_requested", node_id="run_service",
            payload={"request_id": request_id},
        )
        engines, _ = self._bundle(state)
        engines.get("manual").cancel(safe_reason)
        latest = self.runs.get(run_id)
        if latest.status == "canceled":
            next_state = latest
        else:
            next_state = apply_patch(
                latest, StatePatch(status="canceled", expected_version=latest.version),
            )
            try:
                next_state = self.runs.save(next_state, expected_version=latest.version)
            except OptimisticLockError:
                next_state = self.runs.get(run_id)
                if next_state.status != "canceled":
                    raise
        self.runs.resolve_control(run_id, request_id, status="resolved")
        next_state = self._record_event(next_state, "run.canceled", node_id="run_service")
        self.runs.save_checkpoint(
            next_state,
            checkpoint_id=stable_id("checkpoint", run_id, next_state.version, "canceled"),
            metadata={
                "reason": "cancel",
                "workflow_version": next_state.workflow_version,
                "state_schema_version": next_state.state_schema_version,
                "active_engine": next_state.active_engine,
                "event_sequence": next_state.last_event_sequence,
            },
        )
        return self.get_run(run_id)

    def _record_event(
        self,
        state: RecoveryStateV2,
        event_type: str,
        *,
        node_id: str,
        payload: dict[str, Any] | None = None,
    ) -> RecoveryStateV2:
        event = self.events.append(
            state, event_type, status=state.status, node_id=node_id, payload=payload,
        )
        if event.sequence <= state.last_event_sequence:
            return state
        next_state = apply_patch(
            state,
            StatePatch(last_event_sequence=event.sequence, expected_version=state.version),
        )
        return self.runs.save(next_state, expected_version=state.version)

    def _may_fallback(self, state: RecoveryStateV2) -> bool:
        return self.auto_fallback and state.active_engine == "langgraph" and not RecoveryStateMachine.is_terminal(state.status)

    def _validate_versions(self, state: RecoveryStateV2) -> None:
        if state.workflow_version != self.workflow_version:
            raise WorkflowCompatibilityError(
                f"workflow version {state.workflow_version!r} cannot resume under {self.workflow_version!r}"
            )
        if state.state_schema_version != self.state_schema_version:
            raise WorkflowCompatibilityError(
                f"state schema {state.state_schema_version!r} requires an explicit migration to {self.state_schema_version!r}"
            )
        checkpoint = self.runs.latest_checkpoint(state.run_id)
        if checkpoint is None:
            return
        checkpoint_state, metadata = checkpoint
        if checkpoint_state.workflow_version != state.workflow_version:
            raise WorkflowCompatibilityError("portable checkpoint workflow version does not match the run")
        if checkpoint_state.state_schema_version != state.state_schema_version:
            raise WorkflowCompatibilityError("portable checkpoint state schema does not match the run")
        if metadata.get("workflow_version") not in {None, state.workflow_version}:
            raise WorkflowCompatibilityError("portable checkpoint metadata workflow version does not match the run")
        if metadata.get("state_schema_version") not in {None, state.state_schema_version}:
            raise WorkflowCompatibilityError("portable checkpoint metadata state schema does not match the run")

    def _block_incompatible(self, state: RecoveryStateV2, message: str) -> RecoveryStateV2:
        if RecoveryStateMachine.is_terminal(state.status):
            return state
        blocked = apply_patch(state, StatePatch(
            status="blocked",
            errors_add=[AgentError(
                code="workflow_version_incompatible",
                category="validation",
                message=message,
                retryable=False,
                source="run_service",
            )],
            expected_version=state.version,
        ))
        blocked = self.runs.save(blocked, expected_version=state.version)
        return self._record_event(
            blocked, "run.blocked", node_id="run_service",
            payload={"reason": "workflow_version_incompatible"},
        )

    def _bundle(self, state: RecoveryStateV2, *, rebuild: bool = False) -> tuple[EngineRegistry, WorkflowResultBuilder]:
        if rebuild or state.run_id not in self._engine_bundles:
            self._engine_bundles[state.run_id] = self.engine_factory(state)
        return self._engine_bundles[state.run_id]

    @staticmethod
    def _engine_name(value: str) -> str:
        normalized = value.casefold()
        if normalized in {"manual_v2", "manual"}:
            return "manual"
        if normalized in {"langgraph_v2", "langgraph", "auto_v2"}:
            return "langgraph"
        raise ValueError(f"engine {value!r} does not create a v2 run")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _safe_error(error: Exception) -> str:
    redacted = RedactionPolicy().redact({"message": str(error)[:500]})
    return str(redacted.get("message", "engine infrastructure failure"))


def _is_engine_infrastructure_failure(error: Exception) -> bool:
    return isinstance(error, (
        PersistenceBackendUnavailable,
        ConnectionError,
        TimeoutError,
        OSError,
        sqlite3.OperationalError,
    ))
