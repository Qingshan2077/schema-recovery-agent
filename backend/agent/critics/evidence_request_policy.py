"""Safety and budget policy for Critic-authored evidence requests."""

from __future__ import annotations

from backend.agent.runtime.hybrid_contracts import EvidenceRequest, WorkUnit
from backend.config import Config
from backend.core.identity import stable_id


WORKER_TOOL_ALLOWLISTS = {
    "survey": {"recovery.get_catalog", "recovery.get_analysis_snapshot"},
    "column": {"recovery.get_table_contract", "recovery.profile_column", "recovery.profile_relationship"},
    "name": {"recovery.get_table_contract"},
    "code": {"recovery.parse_sql_asset"},
    "orm": {"recovery.detect_orm_asset", "recovery.extract_orm_asset"},
    "merge": set(),
}


class EvidenceRequestPolicy:
    """Fail-closed policy; it authorizes requests but never executes them."""

    def authorize(
        self,
        request: EvidenceRequest,
        parent: WorkUnit,
        *,
        executed_dedupe_keys: set[str] | None = None,
    ) -> tuple[bool, str | None]:
        if request.round > Config.RUN_MAX_EVIDENCE_ROUNDS or request.round <= parent.evidence_round:
            return False, "max_rounds"
        if request.dedupe_key in (executed_dedupe_keys or set()):
            return False, "duplicate_request"
        allowed = WORKER_TOOL_ALLOWLISTS.get(request.target_worker, set())
        if not request.allowed_tools or not set(request.allowed_tools).issubset(allowed):
            return False, "tool_not_allowlisted"
        if request.estimated_budget.max_model_calls != 0:
            return False, "critic_request_may_not_delegate_model_calls"
        if request.estimated_budget.max_tool_calls > parent.budget_slice.max_tool_calls:
            return False, "work_unit_tool_budget_exceeded"
        requested = request.requested_fact.casefold()
        forbidden = ("raw row", "raw value", "sample value", "source code dump", "credential")
        if any(marker in requested for marker in forbidden):
            return False, "privacy_policy_rejected"
        return True, None

    def to_work_unit(
        self,
        request: EvidenceRequest,
        parent: WorkUnit,
        *,
        executed_dedupe_keys: set[str] | None = None,
    ) -> WorkUnit:
        authorized, reason = self.authorize(
            request,
            parent,
            executed_dedupe_keys=executed_dedupe_keys,
        )
        if not authorized:
            raise PermissionError(f"evidence request rejected: {reason}")
        return WorkUnit(
            work_unit_id=stable_id("work_unit", parent.run_id, request.dedupe_key),
            run_id=parent.run_id,
            trace_id=parent.trace_id,
            snapshot_id=parent.snapshot_id,
            database_fingerprint=parent.database_fingerprint,
            worker=request.target_worker,
            subject_refs=request.subject_refs,
            requested_by=request.request_id,
            evidence_round=request.round,
            priority=parent.priority + 1,
            idempotency_key=request.dedupe_key,
            budget_slice=request.estimated_budget,
        )
