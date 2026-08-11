"""Strict contracts and state vocabulary for governed DDL operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from backend.agent.runtime.contracts import StrictContract

OperationStatus = Literal[
    "draft", "validating", "policy_blocked", "awaiting_approval", "approved", "rejected",
    "expired", "superseded", "executing", "executed", "verifying", "succeeded",
    "execution_failed", "executed_verification_failed", "uncertain", "cancelled",
]


class DDLPlan(StrictContract):
    intent: Literal["create_table", "alter_table", "drop_table", "rename", "other"]
    dialect: Literal["mysql", "postgresql"]
    connection_id: str
    environment: str
    statements: list[str] = Field(min_length=1, max_length=5)
    target_objects: list[str] = Field(min_length=1)
    requested_change: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list)
    risk_hints: list[str] = Field(default_factory=list)
    verification_goals: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalRequirement(StrictContract):
    role: Literal["dba_approver", "security_approver"]
    count: int = Field(default=1, ge=1, le=2)
    separation_from_requester: bool = True


class ApprovalOperation(StrictContract):
    operation_id: str
    version: int = Field(ge=1)
    tenant_id: str
    project_id: str
    thread_id: str
    run_id: str
    requester_id: str
    connection_id: str
    environment: str
    dialect: str
    normalized_ast: dict[str, Any]
    normalized_sql: list[str]
    normalized_sql_hash: str
    snapshot_id: str
    snapshot_hash: str
    preconditions: list[dict[str, Any]]
    diff: dict[str, Any]
    impact: dict[str, Any]
    rollback_plan: dict[str, Any]
    verification_plan: list[dict[str, Any]]
    guardrail_results: list[dict[str, Any]]
    policy_version: str
    plan_version: int = Field(ge=1)
    risk_level: Literal["low", "medium", "high", "critical"]
    required_approvals: list[ApprovalRequirement]
    idempotency_key: str
    status: OperationStatus
    created_at: datetime
    expires_at: datetime
    supersedes_version: int | None = None

    @model_validator(mode="after")
    def hash_prefix(self) -> "ApprovalOperation":
        if not self.normalized_sql_hash.startswith("sha256:"):
            raise ValueError("normalized_sql_hash must use sha256 prefix")
        return self


class ApprovalDecision(StrictContract):
    decision_id: str
    operation_id: str
    operation_version: int
    decision: Literal["approve", "reject", "request_changes"]
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)
    acknowledged_hash: str
    request_id: str
    created_at: datetime


class ExecutionAttempt(StrictContract):
    attempt_id: str
    operation_id: str
    operation_version: int
    idempotency_key: str
    status: Literal["executing", "executed", "failed", "uncertain"]
    database_audit_id: str | None = None
    before_schema_hash: str
    after_schema_hash: str | None = None
    error_code: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class VerificationResult(StrictContract):
    verification_id: str
    operation_id: str
    operation_version: int
    passed: bool
    checks: list[dict[str, Any]]
    snapshot_id: str | None = None
    targeted_run_id: str | None = None
    created_at: datetime


class ActorContext(StrictContract):
    actor_id: str
    roles: list[str]
    tenant_id: str
    project_id: str
    environment: str
    capabilities: list[str] = Field(default_factory=list)
