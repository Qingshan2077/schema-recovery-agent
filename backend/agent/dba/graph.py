"""Engine-neutral DBA approval graph facade for Manual/LangGraph interrupt adapters."""

from __future__ import annotations

from typing import Any

from backend.agent.dba.contracts import ActorContext
from backend.agent.dba.service import DBAService


class DBAApprovalGraph:
    def __init__(self, service: DBAService): self.service = service

    async def plan_and_interrupt(self, request: str, *, actor: ActorContext, context: dict[str, Any]) -> dict[str, Any]:
        operation = await self.service.create_operation(
            request, actor=actor, connection_id=context["connection_id"],
            thread_id=context["thread_id"], run_id=context["run_id"],
            dialect=context["dialect"], snapshot_id=context["snapshot_id"],
            snapshot_hash=context["snapshot_hash"],
        )
        if operation.status != "awaiting_approval":
            return {"route": "blocked", "operation_id": operation.operation_id, "status": operation.status}
        return {
            "route": "interrupt", "operation_id": operation.operation_id,
            "operation_version": operation.version,
            "acknowledged_hash": operation.normalized_sql_hash,
            "expires_at": operation.expires_at.isoformat(),
            "safe_summary": {
                "risk_level": operation.risk_level,
                "environment": operation.environment,
                "target_objects": operation.diff.get("targets", []),
                "required_approvals": [item.model_dump(mode="json") for item in operation.required_approvals],
            },
        }

    def resume(self, operation_id: str, *, decision: dict[str, Any], actor: ActorContext) -> dict[str, Any]:
        operation = self.service.resolve(
            operation_id, expected_version=int(decision["expected_version"]),
            decision=str(decision["decision"]), reason=str(decision["reason"]),
            acknowledged_hash=str(decision["acknowledged_hash"]),
            request_id=str(decision["request_id"]), actor=actor,
        )
        return {"route": "execute" if operation.status == "approved" else "wait_or_finalize", "operation_id": operation.operation_id, "status": operation.status}
