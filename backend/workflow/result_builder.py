"""One final result adapter shared by manual, LangGraph, and v1 facade."""

from __future__ import annotations

from typing import Any, Protocol

from backend.workflow.contracts import RecoveryStateV2


class ArtifactReader(Protocol):
    def get_json(self, artifact_id: str) -> dict[str, Any] | None: ...


class WorkflowResultBuilder:
    def __init__(self, artifacts: ArtifactReader):
        self.artifacts = artifacts

    def build(self, state: RecoveryStateV2) -> dict[str, Any]:
        result = self.artifacts.get_json(state.result_ref) if state.result_ref else None
        payload: dict[str, Any] = {
            "session_id": state.session_id,
            "run_id": state.run_id,
            "trace_id": state.trace_id,
            "thread_id": state.thread_id,
            "status": _legacy_status(state.status),
            "run_status": _legacy_status(state.status),
            "workflow_status": state.status,
            "workflow_version": state.workflow_version,
            "state_schema_version": state.state_schema_version,
            "active_engine": state.active_engine,
            "snapshot_id": state.snapshot_id,
            "database_fingerprint": state.database_fingerprint,
            "artifact_ids": state.artifact_ids,
            "evidence_ids": state.evidence_ids,
            "relation_ids": state.relation_ids,
            "result_ref": state.result_ref,
            "budget": state.budget.model_dump(mode="json"),
            "deadline_at": state.deadline_at.isoformat() if state.deadline_at else None,
            "errors": [item.model_dump(mode="json") for item in state.errors],
            "capability_gaps": [item.model_dump(mode="json") for item in state.errors],
            "engine_history": [item.model_dump(mode="json") for item in state.engine_history],
        }
        if result:
            payload["merge_result"] = result.get("merge_result", result)
            payload["er_diagram"] = result.get("er_diagram")
        if state.pending_interrupt:
            payload["pending_interrupt"] = state.pending_interrupt.model_dump(mode="json")
        return payload


def _legacy_status(status: str) -> str:
    return {
        "completed": "success", "failed": "error", "canceled": "cancelled",
        "waiting_approval": "blocked", "expired": "blocked", "queued": "blocked", "running": "blocked",
    }.get(status, status)
