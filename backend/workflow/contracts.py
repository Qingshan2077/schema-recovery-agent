"""Portable Phase 4 workflow, state, control, and persistence contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.agent.runtime.contracts import RuntimeUsage, StrictContract
from backend.agent.runtime.hybrid_contracts import WorkUnit
from backend.core.status import AgentError

WorkflowStatus = Literal[
    "queued", "running", "waiting_approval", "partial", "degraded",
    "blocked", "failed", "canceled", "completed", "expired",
]
EngineName = Literal["manual", "langgraph"]


class EngineTransition(StrictContract):
    from_engine: EngineName | None
    to_engine: EngineName
    reason: str
    sequence: int = Field(ge=0)
    changed_at: datetime


class CancellationState(StrictContract):
    requested: bool = False
    request_id: str | None = None
    reason: str | None = None
    requested_at: datetime | None = None


class InterruptRef(StrictContract):
    interrupt_id: str
    type: str
    requested_by_stage: str
    safe_summary: str
    option_schema: dict[str, Any]
    artifact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    payload_hash: str
    expires_at: datetime
    required_role: str


class RecoveryStateV2(StrictContract):
    state_schema_version: str = "2"
    workflow_version: str
    run_id: str
    trace_id: str
    thread_id: str
    session_id: str
    project_id: str
    connection_id: str
    snapshot_id: str | None = None
    database_fingerprint: str | None = None
    active_engine: EngineName
    engine_history: list[EngineTransition] = Field(default_factory=list)
    status: WorkflowStatus = "queued"
    phase: str = "load_context"
    work_plan_ref: str | None = None
    pending_work_units: list[WorkUnit] = Field(default_factory=list)
    completed_stage_keys: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    evidence_round: int = Field(default=0, ge=0)
    pending_interrupt: InterruptRef | None = None
    cancellation: CancellationState = Field(default_factory=CancellationState)
    budget: RuntimeUsage = Field(default_factory=RuntimeUsage)
    deadline_at: datetime | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    errors: list[AgentError] = Field(default_factory=list)
    last_event_sequence: int = Field(default=0, ge=0)
    result_ref: str | None = None
    output_refs: dict[str, str] = Field(default_factory=dict)
    version: int = Field(default=0, ge=0)

    @field_validator("run_id")
    @classmethod
    def run_prefix(cls, value: str) -> str:
        if not value.startswith("run_"):
            raise ValueError("run_id must use run_ prefix")
        return value

    @field_validator("trace_id")
    @classmethod
    def trace_prefix(cls, value: str) -> str:
        if not value.startswith("trc_"):
            raise ValueError("trace_id must use trc_ prefix")
        return value

    @field_validator("thread_id")
    @classmethod
    def thread_prefix(cls, value: str) -> str:
        if not value.startswith("thr_"):
            raise ValueError("thread_id must use thr_ prefix")
        return value


class StatePatch(StrictContract):
    active_engine: EngineName | None = None
    engine_history_add: list[EngineTransition] = Field(default_factory=list)
    phase: str | None = None
    status: WorkflowStatus | None = None
    snapshot_id: str | None = None
    database_fingerprint: str | None = None
    work_plan_ref: str | None = None
    pending_work_units_add: list[WorkUnit] = Field(default_factory=list)
    pending_work_unit_ids_remove: list[str] = Field(default_factory=list)
    completed_stage_keys_add: list[str] = Field(default_factory=list)
    artifact_ids_add: list[str] = Field(default_factory=list)
    evidence_ids_add: list[str] = Field(default_factory=list)
    relation_ids_add: list[str] = Field(default_factory=list)
    output_refs_merge: dict[str, str] = Field(default_factory=dict)
    attempts_merge: dict[str, int] = Field(default_factory=dict)
    errors_add: list[AgentError] = Field(default_factory=list)
    usage_delta: RuntimeUsage = Field(default_factory=RuntimeUsage)
    evidence_round: int | None = None
    pending_interrupt: InterruptRef | None = None
    clear_interrupt: bool = False
    cancellation: CancellationState | None = None
    result_ref: str | None = None
    last_event_sequence: int | None = None
    expected_version: int | None = None


class StageCapabilities(StrictContract):
    retry_safe: bool = False
    cancellable: bool = True
    interruptible: bool = False
    parallel_safe: bool = True
    max_concurrency: int = Field(default=1, ge=1)


class StageContext(StrictContract):
    run_id: str
    trace_id: str
    thread_id: str
    active_engine: EngineName
    workflow_version: str
    checkpoint_namespace: str
    deterministic_scheduler: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageExecutionRecord(StrictContract):
    run_id: str
    stage_key: str
    stage_id: str
    work_unit_id: str
    attempt: int = Field(ge=1)
    idempotency_key: str
    status: str
    input_hash: str
    output_ref: str | None = None
    error: AgentError | None = None
    started_at: datetime
    completed_at: datetime | None = None


class RunControl(StrictContract):
    run_id: str
    control_type: Literal["cancel", "resume", "interrupt"]
    request_id: str
    payload_hash: str
    status: Literal["pending", "resolved", "rejected", "expired"] = "pending"
    actor_id: str | None = None
    actor_role: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: datetime | None = None


class WorkflowEvent(StrictContract):
    event_id: str
    sequence: int = Field(gt=0)
    timestamp: datetime
    run_id: str
    session_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    agent_id: str
    node_id: str
    attempt: int = Field(ge=1)
    type: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    usage: RuntimeUsage = Field(default_factory=RuntimeUsage)
    redaction: dict[str, Any] = Field(default_factory=dict)


class WorkflowNode(StrictContract):
    node_id: str
    stage_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    route_key: str | None = None
    fanout_source: str | None = None
    join_policy: Literal["all", "required", "none"] = "none"
    retry_policy_ref: str = "default"
    timeout_seconds: int = Field(default=120, gt=0)
    required: bool = True
    loop_limit: int = Field(default=0, ge=0)
    writes: list[str] = Field(default_factory=list)


class WorkflowDefinition(StrictContract):
    workflow_id: str
    version: str
    state_schema_version: str
    entry_node: str
    nodes: list[WorkflowNode]
    reducers: dict[str, str]

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        if not self.version.strip() or not self.state_schema_version.strip():
            raise ValueError("workflow and state schema versions are required")
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow node ids must be unique")
        known = set(ids)
        if self.entry_node not in known:
            raise ValueError("workflow entry node is missing")
        for node in self.nodes:
            missing = set(node.depends_on) - known
            if missing:
                raise ValueError(f"node {node.node_id} has unknown dependencies: {sorted(missing)}")
            if node.loop_limit < 0:
                raise ValueError("loop limit cannot be negative")
            for field in node.writes:
                if field not in self.reducers:
                    raise ValueError(f"parallel write field has no reducer: {field}")
        unresolved = {node.node_id: set(node.depends_on) for node in self.nodes}
        resolved: set[str] = set()
        while unresolved:
            ready = {node_id for node_id, dependencies in unresolved.items() if dependencies <= resolved}
            if not ready:
                raise ValueError(f"workflow dependency cycle detected: {sorted(unresolved)}")
            resolved.update(ready)
            for node_id in ready:
                unresolved.pop(node_id)
        return self
