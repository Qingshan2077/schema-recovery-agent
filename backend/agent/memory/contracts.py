"""Strict Phase 5 memory contracts and namespace isolation rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.agent.runtime.contracts import StrictContract

MemoryLayer = Literal["l1", "l2", "l3"]
MemoryLifecycle = Literal[
    "active", "completed", "expired", "proposed", "accepted", "rejected",
    "corrected", "stale", "candidate", "review", "deprecated", "forgotten",
]


class MemoryNamespace(StrictContract):
    tenant_id: str
    project_id: str
    connection_id: str | None = None
    database_name: str | None = None
    schema_name: str | None = None
    snapshot_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    dialect: str | None = None
    domain: str | None = None
    canonical_tenant_id: str = ""
    canonical_project_id: str = ""
    canonical_connection_id: str | None = None
    canonical_database_name: str | None = None
    canonical_schema_name: str | None = None

    @model_validator(mode="after")
    def fill_canonical_values(self) -> "MemoryNamespace":
        object.__setattr__(self, "canonical_tenant_id", _canonical(self.tenant_id))
        object.__setattr__(self, "canonical_project_id", _canonical(self.project_id))
        object.__setattr__(self, "canonical_connection_id", _optional_canonical(self.connection_id))
        object.__setattr__(self, "canonical_database_name", _optional_canonical(self.database_name))
        object.__setattr__(self, "canonical_schema_name", _optional_canonical(self.schema_name))
        return self

    def require_l1(self) -> "MemoryNamespace":
        if not self.thread_id:
            raise ValueError("invalid_namespace: L1 requires thread_id")
        return self

    def require_l2(self) -> "MemoryNamespace":
        if not all((self.connection_id, self.database_name, self.schema_name, self.snapshot_id)):
            raise ValueError(
                "invalid_namespace: L2 requires connection_id, database_name, schema_name, and snapshot_id"
            )
        return self

    def project_key(self) -> tuple[str, str, str, str, str]:
        self.require_l2()
        return (
            self.canonical_tenant_id,
            self.canonical_project_id,
            self.canonical_connection_id or "",
            self.canonical_database_name or "",
            self.canonical_schema_name or "",
        )


class ThreadMemoryRecord(StrictContract):
    memory_id: str
    namespace: MemoryNamespace
    version: int = Field(ge=1)
    status: Literal["active", "completed", "expired"] = "active"
    checkpoint_ref: str | None = None
    summary_ref: str | None = None
    summary_provenance: dict[str, Any] = Field(default_factory=dict)
    message_event_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    temporary_relation_ids: list[str] = Field(default_factory=list)
    pending_approval_ref: str | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    last_event_sequence: int = Field(default=0, ge=0)
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class RelationMemoryVersion(StrictContract):
    memory_id: str
    relation_id: str
    version: int = Field(ge=1)
    namespace: MemoryNamespace
    source_table_id: str
    source_columns: list[str] = Field(min_length=1)
    target_table_id: str
    target_columns: list[str] = Field(min_length=1)
    cardinality: Literal["1:1", "1:N", "N:1", "N:N", "unknown"]
    status: Literal["proposed", "accepted", "rejected", "corrected", "stale"]
    evidence_ids: list[str] = Field(default_factory=list)
    calibrated_probability: float = Field(ge=0, le=1)
    calibration_version: str
    first_seen_snapshot_id: str
    last_verified_snapshot_id: str
    superseded_by: str | None = None
    created_by_run_id: str
    root_fact_ids: list[str] = Field(default_factory=list)
    source_object_ids: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=2000)
    created_at: datetime

    @model_validator(mode="after")
    def validate_snapshot_namespace(self) -> "RelationMemoryVersion":
        self.namespace.require_l2()
        if self.namespace.snapshot_id != self.last_verified_snapshot_id:
            raise ValueError("last_verified_snapshot_id must match namespace snapshot_id")
        if len(self.source_columns) != len(self.target_columns):
            raise ValueError("source and target column arity must match")
        return self


class GlobalMemoryItem(StrictContract):
    memory_id: str
    category: str
    pattern: dict[str, Any]
    rule_summary: str = Field(max_length=2000)
    scope: list[str] = Field(min_length=1)
    dialects: list[str] = Field(min_length=1)
    domains: list[str] = Field(min_length=1)
    source: Literal["curated", "human", "cross_project_eval"]
    lifecycle: Literal["candidate", "review", "active", "deprecated"]
    confidence: float = Field(ge=0, le=1)
    support_project_count: int = Field(ge=0)
    support_eval_ids: list[str] = Field(default_factory=list)
    version: int = Field(ge=1)
    effective_from: datetime
    expires_at: datetime | None = None
    superseded_by: str | None = None
    negative_examples: list[str] = Field(default_factory=list)
    created_by_run_id: str | None = None


class MemoryRetrievalQuery(StrictContract):
    namespace: MemoryNamespace
    task_type: str
    object_ids: list[str] = Field(default_factory=list)
    query_text: str = ""
    top_k: int = Field(default=20, ge=1, le=200)
    token_budget: int = Field(default=4000, ge=128)
    include_stale: bool = False
    current_run_id: str


class MemoryContextItem(StrictContract):
    memory_id: str
    version: int
    layer: MemoryLayer
    retrieval_method: Literal["exact", "lexical", "vector"]
    retrieval_score: float = Field(ge=0, le=1)
    namespace_match: bool
    freshness: Literal["current", "inherited", "stale", "expired"]
    status: str
    root_fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str
    verification_requirements: list[str] = Field(default_factory=list)
    source_run_id: str | None = None
    estimated_tokens: int = Field(default=0, ge=0)


class MemoryContextPackage(StrictContract):
    package_id: str
    namespace: MemoryNamespace
    query: MemoryRetrievalQuery
    items: list[MemoryContextItem]
    selected_count: int = Field(ge=0)
    discarded_count: int = Field(ge=0)
    discarded_reasons: dict[str, int] = Field(default_factory=dict)
    estimated_tokens: int = Field(ge=0)
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class MemoryVerification(StrictContract):
    verification_id: str
    run_id: str
    memory_id: str
    memory_version: int
    snapshot_id: str
    outcome: Literal["verified", "rejected", "stale", "insufficient"]
    reason_codes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    verified_at: datetime


class PromotionProposal(StrictContract):
    proposal_id: str
    memory_id: str
    source_version: int
    lifecycle: Literal["candidate", "review", "active", "deprecated"] = "candidate"
    proposed_by_run_id: str
    excluded_project_ids: list[str] = Field(default_factory=list)
    support_project_ids: list[str] = Field(default_factory=list)
    support_eval_ids: list[str] = Field(default_factory=list)
    reviewer_id: str | None = None
    resolution_reason: str | None = None
    expires_at: datetime
    created_at: datetime
    resolved_at: datetime | None = None


class MemoryFeedback(StrictContract):
    action: Literal["accept", "reject", "correct", "mark_stale", "comment", "undo"]
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)
    correction: dict[str, Any] = Field(default_factory=dict)
    request_id: str


def _canonical(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("namespace value cannot be empty")
    return normalized.casefold()


def _optional_canonical(value: str | None) -> str | None:
    return _canonical(value) if value is not None else None
