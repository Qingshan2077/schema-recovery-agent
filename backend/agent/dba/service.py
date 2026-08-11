"""Plan, persist, approve, execute and verify server-owned DDL operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hmac
from typing import Any

from backend.agent.dba.ast_validator import validate_and_normalize
from backend.agent.dba.contracts import ActorContext, ApprovalDecision, ApprovalOperation, ExecutionAttempt, VerificationResult
from backend.agent.dba.executor import ExecutionUnavailable, PrivilegedDDLAdapter
from backend.agent.dba.operation_store import OperationConflict, OperationStore
from backend.agent.dba.planner import DDLPlanner
from backend.agent.dba.policy import evaluate_policy
from backend.core.identity import new_id, stable_id
from backend.eval_v2.hashing import content_hash
from backend.observability.tracing import TraceRecorder


class DBAService:
    def __init__(self, *, store: OperationStore, planner: DDLPlanner, traces: TraceRecorder, executor: PrivilegedDDLAdapter | None = None, execution_enabled: bool = False, connection_allowlist: tuple[str, ...] = (), ttl_minutes: int = 30):
        self.store, self.planner, self.traces, self.executor = store, planner, traces, executor
        self.execution_enabled, self.connection_allowlist, self.ttl_minutes = execution_enabled, set(connection_allowlist), ttl_minutes

    async def create_operation(self, request: str, *, actor: ActorContext, connection_id: str, thread_id: str, run_id: str, dialect: str, snapshot_id: str, snapshot_hash: str) -> ApprovalOperation:
        if not any(role in actor.roles for role in ("analyst", "dba_approver", "admin")):
            raise PermissionError("dba_plan_role_missing")
        with self.traces.span("dba.plan", attributes={"agent.id": "dba.planner", "db.namespace_hash": connection_id, "status": "running"}):
            plan = await self.planner.plan(request, connection_id=connection_id, environment=actor.environment, dialect=dialect)
            normalized_sql, ast = validate_and_normalize(plan.statements, dialect=dialect)
            dry_run = {"capability": "limited", "reason_codes": ["provider_dry_run_unavailable"]}
            policy = evaluate_policy(ast=ast, actor=actor, environment=actor.environment, dry_run_capability=dry_run["capability"])
            operation_id = new_id("operation")
            risk = policy["risk_level"]
            hash_input = {"ast": ast, "sql": normalized_sql, "connection_id": connection_id, "environment": actor.environment, "dialect": dialect, "targets": plan.target_objects, "snapshot_hash": snapshot_hash, "policy_version": policy["policy_version"], "plan_version": 1, "verification": plan.verification_goals}
            operation_hash = content_hash(hash_input)
            now = datetime.now(timezone.utc)
            operation = ApprovalOperation(
                operation_id=operation_id, version=1, tenant_id=actor.tenant_id,
                project_id=actor.project_id, thread_id=thread_id, run_id=run_id,
                requester_id=actor.actor_id, connection_id=connection_id,
                environment=actor.environment, dialect=dialect, normalized_ast=ast,
                normalized_sql=normalized_sql, normalized_sql_hash=operation_hash,
                snapshot_id=snapshot_id, snapshot_hash=snapshot_hash,
                preconditions=[{"type": "snapshot_hash", "expected": snapshot_hash}],
                diff={"targets": plan.target_objects, "requested_change": plan.requested_change},
                impact={"dry_run": dry_run, "risk_hints": plan.risk_hints, "affected_objects": plan.target_objects},
                rollback_plan={"mode": "forward_fix_or_manual", "transactional_rollback_guaranteed": False},
                verification_plan=plan.verification_goals or [{"type": "schema_hash_changed", "targets": plan.target_objects}],
                guardrail_results=[{"policy_version": policy["policy_version"], "decision": policy["decision"], "reason_codes": policy["reason_codes"]}],
                policy_version=policy["policy_version"], plan_version=1, risk_level=risk,
                required_approvals=policy["requirements"],
                idempotency_key=stable_id("operation", actor.tenant_id, actor.project_id, operation_hash),
                status="policy_blocked" if policy["decision"] == "deny" else "awaiting_approval",
                created_at=now, expires_at=now + timedelta(minutes=self.ttl_minutes),
            )
            return self.store.create(operation)

    def resolve(self, operation_id: str, *, expected_version: int, decision: str, reason: str, acknowledged_hash: str, request_id: str, actor: ActorContext) -> ApprovalOperation:
        operation = self._authorized(operation_id, actor)
        prior_request = self.store.decision_by_request(operation_id, request_id)
        if prior_request is not None:
            if prior_request.decision != decision or prior_request.acknowledged_hash != acknowledged_hash:
                raise OperationConflict("decision_idempotency_conflict")
            return operation
        if datetime.now(timezone.utc) >= operation.expires_at:
            return self.store.transition(operation_id, expected_version=expected_version, allowed_from={"awaiting_approval"}, status="expired")
        if operation.version != expected_version: raise OperationConflict("operation_version_conflict")
        if not hmac.compare_digest(operation.normalized_sql_hash, acknowledged_hash): raise OperationConflict("operation_hash_mismatch")
        if actor.actor_id == operation.requester_id: raise PermissionError("self_approval_forbidden")
        required_roles = {requirement.role for requirement in operation.required_approvals}
        role = next((value for value in actor.roles if value in required_roles), None)
        if role is None: raise PermissionError("approval_role_missing")
        item = ApprovalDecision(decision_id=new_id("approval"), operation_id=operation_id, operation_version=operation.version, decision=decision, actor_id=actor.actor_id, actor_role=role, reason=reason, acknowledged_hash=acknowledged_hash, request_id=request_id, created_at=datetime.now(timezone.utc))
        prior = self.store.append_decision(item)
        if prior.decision != decision or prior.acknowledged_hash != acknowledged_hash: raise OperationConflict("decision_idempotency_conflict")
        if decision == "reject": return self.store.transition(operation_id, expected_version=expected_version, allowed_from={"awaiting_approval"}, status="rejected")
        if decision == "request_changes": return self.store.transition(operation_id, expected_version=expected_version, allowed_from={"awaiting_approval"}, status="superseded")
        approvals = self.store.decisions(operation_id, operation.version)
        roles = {value.actor_role for value in approvals if value.decision == "approve"}
        if required_roles <= roles:
            return self.store.transition(operation_id, expected_version=expected_version, allowed_from={"awaiting_approval"}, status="approved")
        return self.store.get(operation_id)

    def execute_approved(self, operation_id: str, *, current_snapshot_hash: str) -> tuple[ApprovalOperation, ExecutionAttempt, VerificationResult | None]:
        operation = self.store.get(operation_id)
        if not self.execution_enabled or self.executor is None: raise ExecutionUnavailable("dba_execution_disabled")
        if operation.connection_id not in self.connection_allowlist: raise ExecutionUnavailable("connection_not_allowlisted")
        if operation.status != "approved": raise OperationConflict("operation_not_approved")
        if datetime.now(timezone.utc) >= operation.expires_at: raise OperationConflict("operation_expired")
        if not hmac.compare_digest(operation.snapshot_hash, current_snapshot_hash): raise OperationConflict("precondition_snapshot_changed")
        executing = self.store.transition(operation_id, expected_version=operation.version, allowed_from={"approved"}, status="executing")
        now = datetime.now(timezone.utc)
        attempt = ExecutionAttempt(attempt_id=stable_id("operation", operation_id, operation.version, "execute"), operation_id=operation_id, operation_version=operation.version, idempotency_key=operation.idempotency_key, status="executing", before_schema_hash=current_snapshot_hash, started_at=now)
        prior, created = self.store.append_execution(attempt)
        if not created:
            if prior.status == "executing": raise OperationConflict("execution_reconciliation_required")
            return self.store.get(operation_id), prior, None
        result = self.executor.execute(operation.connection_id, operation.normalized_sql, statement_timeout_ms=30000, lock_timeout_ms=5000, idempotency_key=operation.idempotency_key)
        if result.get("uncertain"):
            uncertain = attempt.model_copy(update={"status": "uncertain", "completed_at": datetime.now(timezone.utc), "error_code": "execution_outcome_uncertain"})
            self.store.update_execution(uncertain, expected_status="executing")
            return self.store.transition(operation_id, expected_version=operation.version, allowed_from={"executing"}, status="uncertain"), uncertain, None
        if not result.get("success"):
            failed = attempt.model_copy(update={"status": "failed", "completed_at": datetime.now(timezone.utc), "error_code": str(result.get("error_code") or "ddl_execution_failed")})
            self.store.update_execution(failed, expected_status="executing")
            return self.store.transition(operation_id, expected_version=operation.version, allowed_from={"executing"}, status="execution_failed"), failed, None
        self.store.transition(operation_id, expected_version=operation.version, allowed_from={"executing"}, status="executed")
        verify_raw = self.executor.verify(operation.connection_id, operation.verification_plan)
        verification = VerificationResult(verification_id=stable_id("operation", operation_id, "verify"), operation_id=operation_id, operation_version=operation.version, passed=bool(verify_raw.get("passed")), checks=list(verify_raw.get("checks") or []), snapshot_id=verify_raw.get("snapshot_id"), targeted_run_id=verify_raw.get("targeted_run_id"), created_at=datetime.now(timezone.utc))
        self.store.append_verification(verification)
        terminal = self.store.transition(operation_id, expected_version=operation.version, allowed_from={"executed"}, status="succeeded" if verification.passed else "executed_verification_failed")
        completed = attempt.model_copy(update={"status": "executed", "completed_at": datetime.now(timezone.utc)})
        self.store.update_execution(completed, expected_status="executing")
        return terminal, completed, verification

    def _authorized(self, operation_id: str, actor: ActorContext) -> ApprovalOperation:
        operation = self.store.get(operation_id)
        if operation.tenant_id != actor.tenant_id or operation.project_id != actor.project_id: raise KeyError(operation_id)
        return operation
