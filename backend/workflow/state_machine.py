"""Single workflow status transition authority for every engine and API."""

from __future__ import annotations

from backend.workflow.contracts import WorkflowStatus


class InvalidStateTransition(ValueError):
    pass


_ALLOWED: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "queued": {"running", "blocked", "canceled", "failed"},
    "running": {"waiting_approval", "partial", "degraded", "blocked", "failed", "canceled", "completed"},
    "waiting_approval": {"running", "canceled", "expired", "blocked"},
    "partial": set(), "degraded": set(), "blocked": set(), "failed": set(),
    "canceled": set(), "completed": set(), "expired": set(),
}


class RecoveryStateMachine:
    @staticmethod
    def transition(current: WorkflowStatus, target: WorkflowStatus) -> WorkflowStatus:
        if current == target:
            return current
        if target not in _ALLOWED[current]:
            raise InvalidStateTransition(f"illegal workflow transition: {current} -> {target}")
        return target

    @staticmethod
    def is_terminal(status: WorkflowStatus) -> bool:
        return status in {"partial", "degraded", "blocked", "failed", "canceled", "completed", "expired"}

    @staticmethod
    def terminal_for(
        *,
        required_failed: bool,
        optional_failed: bool,
        degraded: bool,
        has_result: bool,
        partial: bool = False,
    ) -> WorkflowStatus:
        if required_failed:
            return "failed"
        if degraded and has_result:
            return "degraded"
        if (optional_failed or partial) and has_result:
            return "partial"
        if not has_result:
            return "blocked"
        return "completed"
