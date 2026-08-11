"""Versioned Phase 5 evidence, relation, fusion and calibration contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from backend.agent.memory.contracts import MemoryNamespace
from backend.agent.runtime.contracts import StrictContract


class EvidenceItem(StrictContract):
    evidence_id: str
    namespace: MemoryNamespace
    snapshot_id: str
    claim_key: str
    relation_id: str | None = None
    source_type: Literal[
        "catalog", "column_profile", "name_semantics", "sql_ast", "sql_llm",
        "orm", "memory", "human", "legacy_import",
    ]
    producer: str
    producer_version: str
    polarity: Literal["support", "oppose", "neutral"]
    strength: float = Field(ge=0, le=1)
    reliability: float = Field(ge=0, le=1)
    source_uri: str | None = None
    source_locator: dict[str, Any] = Field(default_factory=dict)
    artifact_hash: str | None = None
    excerpt_hash: str | None = None
    summary: str = Field(max_length=2000)
    root_fact_id: str
    correlation_group: str
    parent_evidence_ids: list[str] = Field(default_factory=list)
    tool_call_id: str | None = None
    trace_id: str
    span_id: str
    model_profile: str | None = None
    prompt_version: str | None = None
    memory_id: str | None = None
    created_by_run_id: str
    created_at: datetime
    tombstoned_at: datetime | None = None

    @model_validator(mode="after")
    def validate_memory_origin(self) -> "EvidenceItem":
        if self.source_type == "memory" and not self.memory_id:
            raise ValueError("memory evidence requires memory_id")
        if self.namespace.snapshot_id != self.snapshot_id:
            raise ValueError("evidence snapshot must match namespace snapshot")
        return self


class Contribution(StrictContract):
    feature: str
    value: float
    coefficient: float
    log_odds_delta: float
    evidence_ids: list[str] = Field(default_factory=list)
    included: bool = True
    exclusion_reason: str | None = None


class RelationCandidateVersion(StrictContract):
    relation_id: str
    version: int = Field(ge=1)
    namespace: MemoryNamespace
    claim_key: str
    source_table_id: str
    source_column_ids: list[str] = Field(min_length=1)
    target_table_id: str
    target_column_ids: list[str] = Field(min_length=1)
    cardinality: Literal["1:1", "1:N", "N:1", "N:N", "unknown"]
    status: Literal["proposed", "accepted", "rejected", "corrected", "stale"]
    evidence_ids: list[str] = Field(default_factory=list)
    alternative_relation_ids: list[str] = Field(default_factory=list)
    validation_flags: list[str] = Field(default_factory=list)
    feature_vector: dict[str, float] = Field(default_factory=dict)
    feature_schema_hash: str
    raw_score: float
    raw_probability: float = Field(ge=0, le=1)
    calibrated_probability: float = Field(ge=0, le=1)
    confidence_band: Literal["high", "medium", "low"]
    fusion_version: str
    calibration_version: str
    threshold_policy_version: str
    contribution_breakdown: list[Contribution] = Field(default_factory=list)
    created_by_run_id: str
    created_at: datetime
    superseded_by_version: int | None = None

    @model_validator(mode="after")
    def validate_columns(self) -> "RelationCandidateVersion":
        self.namespace.require_l2()
        if len(self.source_column_ids) != len(self.target_column_ids):
            raise ValueError("source and target column arity must match")
        return self


class FusionResult(StrictContract):
    relation: RelationCandidateVersion
    independent_root_fact_ids: list[str]
    excluded_evidence_ids: list[str] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)
    evidence_request_hints: list[dict[str, Any]] = Field(default_factory=list)
    calibration_applied: bool


class CalibrationArtifact(StrictContract):
    calibration_version: str
    fusion_version: str
    feature_schema_hash: str
    dataset_version: str
    split: Literal["calibration"] = "calibration"
    git_sha: str
    algorithm: Literal["identity", "platt", "isotonic"]
    parameters: dict[str, Any]
    metrics: dict[str, float] = Field(default_factory=dict)
    created_at: datetime
    content_hash: str


class ThresholdPolicy(StrictContract):
    version: str
    high: float = Field(ge=0, le=1)
    medium: float = Field(ge=0, le=1)
    memory_only_high_forbidden: bool = True
    single_root_high_forbidden: bool = True

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ThresholdPolicy":
        if self.medium >= self.high:
            raise ValueError("medium threshold must be lower than high threshold")
        return self


class HumanFeedback(StrictContract):
    feedback_id: str
    relation_id: str
    previous_version: int
    action: Literal["accept", "reject", "correct_target", "correct_cardinality", "mark_stale", "comment", "undo"]
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)
    correction: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    created_at: datetime
