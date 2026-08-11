"""Strict contracts shared by all Phase 3 hybrid recovery stages."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.agent.runtime.contracts import StrictContract
from backend.core.status import AgentError, RunStatus

WorkerKind = Literal[
    "survey", "column", "name", "code", "orm", "merge",
    "memory_retrieve", "memory_verify", "memory_consolidate",
]
WorkerMode = Literal["legacy", "hybrid", "shadow", "deterministic"]


class BudgetSlice(StrictContract):
    max_model_calls: int = Field(default=2, ge=0, le=20)
    max_tool_calls: int = Field(default=30, ge=0, le=500)
    max_input_tokens: int = Field(default=24000, ge=0)
    max_output_tokens: int = Field(default=6000, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    timeout_seconds: int = Field(default=120, gt=0, le=3600)


class WorkUnit(StrictContract):
    work_unit_id: str
    run_id: str
    trace_id: str
    snapshot_id: str
    database_fingerprint: str
    worker: WorkerKind
    subject_refs: list[str] = Field(default_factory=list, max_length=1000)
    input_artifact_ids: list[str] = Field(default_factory=list)
    requested_by: str | None = None
    evidence_round: int = Field(default=0, ge=0, le=10)
    priority: int = Field(default=0, ge=-100, le=100)
    idempotency_key: str = Field(min_length=16, max_length=128)
    budget_slice: BudgetSlice = Field(default_factory=BudgetSlice)

    @field_validator("work_unit_id")
    @classmethod
    def validate_work_unit_id(cls, value: str) -> str:
        return _prefix(value, "wunit")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _prefix(value, "run")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return _prefix(value, "trc")

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        return _prefix(value, "snp")


class CollectorArtifact(StrictContract):
    artifact_id: str
    snapshot_id: str
    subject_refs: list[str]
    fact_schema_version: str = "3.0"
    content_ref: str
    content_hash: str
    completeness: float = Field(ge=0, le=1)
    missing_capabilities: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    collector_version: str


class CandidateAlternative(StrictContract):
    source_table: str
    source_columns: list[str]
    target_table: str
    target_columns: list[str]
    reason: str


class EvidenceRequest(StrictContract):
    request_id: str
    claim_key: str
    target_worker: WorkerKind
    requested_fact: str
    subject_refs: list[str]
    allowed_tools: list[str]
    reason: str
    expected_information_gain: float = Field(ge=0, le=1)
    estimated_budget: BudgetSlice
    round: int = Field(ge=1, le=10)
    dedupe_key: str = Field(min_length=16, max_length=128)


class RelationCandidate(StrictContract):
    relation_id: str
    claim_key: str
    source_table: str
    source_columns: list[str] = Field(min_length=1)
    target_table: str
    target_columns: list[str] = Field(min_length=1)
    cardinality: Literal["1:1", "1:N", "N:1", "N:N", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    validation_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_column_arity(self) -> "RelationCandidate":
        if len(self.source_columns) != len(self.target_columns):
            raise ValueError("relation column sets must have equal arity")
        return self


class ReasoningProposal(StrictContract):
    proposal_id: str
    worker: WorkerKind
    snapshot_id: str
    candidates: list[RelationCandidate] = Field(default_factory=list)
    alternatives: list[CandidateAlternative] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    decision_summary: str
    model_profile: str
    prompt_version: str
    model_call_ids: list[str] = Field(default_factory=list)
    used_memory_ids: list[str] = Field(default_factory=list)


class EvidenceItem(StrictContract):
    evidence_id: str
    snapshot_id: str
    database_fingerprint: str
    claim_key: str
    relation_id: str | None = None
    source_type: Literal[
        "catalog", "column_profile", "name_semantics", "sql_ast", "sql_llm",
        "orm", "memory", "human",
    ]
    producer: str
    polarity: Literal["support", "oppose", "neutral"]
    strength: float = Field(ge=0, le=1)
    reliability: float = Field(ge=0, le=1)
    summary: str = Field(max_length=2000)
    source_uri: str | None = None
    source_locator: dict[str, Any] = Field(default_factory=dict)
    artifact_id: str | None = None
    tool_call_id: str | None = None
    model_call_id: str | None = None
    trace_id: str
    correlation_key: str
    schema_version: str = "3.0"


class VerificationDecision(StrictContract):
    proposal_id: str
    accepted: list[RelationCandidate] = Field(default_factory=list)
    rejected: list[RelationCandidate] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    unresolved_requests: list[EvidenceRequest] = Field(default_factory=list)
    completeness: float = Field(ge=0, le=1)
    decision_summary: str


class ConfidenceContribution(StrictContract):
    evidence_id: str
    source_type: str
    polarity: str
    source_weight: float
    strength: float
    reliability: float
    log_odds_delta: float
    correlation_key: str
    included: bool
    exclusion_reason: str | None = None


class ConfidenceBreakdown(StrictContract):
    model_version: str
    weight_version: str
    prior_probability: float = Field(ge=0, le=1)
    prior_log_odds: float
    contributions: list[ConfidenceContribution]
    hard_constraint_adjustment: float
    conflict_adjustment: float
    final_log_odds: float
    probability: float = Field(ge=0, le=1)
    band: Literal["high", "medium", "low"]


class FusedRelation(StrictContract):
    candidate: RelationCandidate
    probability: float = Field(ge=0, le=1)
    band: Literal["high", "medium", "low"]
    breakdown: ConfidenceBreakdown


class CritiqueDecision(StrictContract):
    action: Literal["accept", "request_evidence", "needs_review", "stop_budget"]
    relation_ids: list[str] = Field(default_factory=list)
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    summary: str
    termination_reason: Literal[
        "accepted", "no_actionable_request", "max_rounds", "budget_exhausted",
        "capability_missing", "needs_human", "cancelled", "fatal_error",
    ] | None = None


class HybridWorkerResult(StrictContract):
    status: RunStatus
    worker: WorkerKind
    mode: WorkerMode
    work_unit_id: str
    snapshot_id: str
    artifact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    model_call_ids: list[str] = Field(default_factory=list)
    used_memory_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    error: AgentError | None = None
    ledger_revision: str | None = None
    idempotency_key: str

    @model_validator(mode="after")
    def validate_status(self) -> "HybridWorkerResult":
        if self.status == RunStatus.SUCCESS and self.error is not None:
            raise ValueError("successful hybrid result cannot contain an error")
        if self.status in {RunStatus.ERROR, RunStatus.BLOCKED, RunStatus.CANCELLED} and self.error is None:
            raise ValueError(f"{self.status.value} hybrid result requires an error")
        if self.status == RunStatus.DEGRADED and not (self.uncertainties or self.missing_capabilities):
            raise ValueError("degraded hybrid result requires a declared capability gap")
        return self


class StageResult(StrictContract):
    stage_id: str
    status: RunStatus
    state_patch: dict[str, Any]
    artifact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    new_work_units: list[WorkUnit] = Field(default_factory=list)
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    emitted_event_ids: list[str] = Field(default_factory=list)
    domain_events: list[dict[str, Any]] = Field(default_factory=list)
    usage_delta: dict[str, int | float | str] = Field(default_factory=dict)
    retry_classification: Literal["never", "safe", "explicit"] = "never"
    idempotency_record: dict[str, Any] = Field(default_factory=dict)
    error: AgentError | None = None


def _prefix(value: str, prefix: str) -> str:
    if not value.startswith(f"{prefix}_") or len(value) <= len(prefix) + 1:
        raise ValueError(f"identifier must use the {prefix}_ prefix")
    return value
