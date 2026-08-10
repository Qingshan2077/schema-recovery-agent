"""Strict contracts for the Phase 2 QA pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.agent.runtime.contracts import StrictContract

QAIntent = Literal[
    "table_columns",
    "table_metadata",
    "relations",
    "indexes",
    "schema_overview",
    "analysis_status",
    "evidence_explain",
    "unknown",
]


class EntityMention(StrictContract):
    mention: str = Field(min_length=1, max_length=256)
    kind: Literal["table", "column", "relation", "database"] = "table"
    parent_mention: str | None = Field(default=None, max_length=256)


class QueryPlan(StrictContract):
    intent: QAIntent
    entities: list[EntityMention] = Field(default_factory=list, max_length=8)
    required_information: list[str] = Field(default_factory=list, max_length=12)
    suggested_tools: list[str] = Field(default_factory=list, max_length=6)
    clarification_question: str | None = Field(default=None, max_length=1000)
    language: Literal["zh-CN", "en"] = "zh-CN"
    plan_summary: str = Field(default="", max_length=2000)


class CatalogEntity(StrictContract):
    entity_id: str
    database: str
    schema_name: str
    name: str
    kind: Literal["table", "view"] = "table"
    aliases: list[str] = Field(default_factory=list)
    row_estimate: int = Field(default=0, ge=0)
    comment: str = ""


class SchemaEntityRef(StrictContract):
    mention: str
    status: Literal["resolved", "ambiguous", "not_found"]
    entity_id: str | None = None
    database: str | None = None
    schema_name: str | None = None
    canonical_name: str | None = None
    kind: Literal["table", "column", "relation", "database"] = "table"
    resolution_method: Literal["focus", "exact", "casefold", "alias", "fuzzy", "none"] = "none"
    candidates: list[CatalogEntity] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_resolution(self) -> "SchemaEntityRef":
        if self.status == "resolved" and not (self.entity_id and self.canonical_name):
            raise ValueError("resolved entity requires entity_id and canonical_name")
        if self.status == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous entity requires at least two candidates")
        return self


class ToolStep(StrictContract):
    tool_name: str
    arguments: dict[str, Any]
    purpose: str
    round: int = Field(ge=1, le=2)


class ToolExecution(StrictContract):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: Literal["success", "error", "cancelled"]
    output: dict[str, Any] | None = None
    output_hash: str | None = None
    cached: bool = False
    error_code: str | None = None


class VerifiedFact(StrictContract):
    fact_id: str
    fact_type: Literal["table", "column", "metadata", "index", "relation", "analysis", "overview"]
    subject_id: str
    predicate: str
    value: Any
    source_tool_call_id: str
    source_tool: str
    output_hash: str
    locator: dict[str, Any]


class FactSet(StrictContract):
    facts: list[VerifiedFact]
    tool_call_ids: list[str]
    catalog_version: str


class AnswerClaim(StrictContract):
    claim_id: str
    text: str = Field(min_length=1, max_length=4000)
    fact_ids: list[str] = Field(min_length=1)


class Citation(StrictContract):
    citation_id: str
    claim_id: str
    fact_ids: list[str] = Field(min_length=1)
    label: str
    locator: dict[str, Any]


class QAArtifact(StrictContract):
    artifact_id: str
    type: Literal["column_table", "relation_cards", "evidence_cards", "clarification_options", "metadata_card", "index_table", "overview"]
    title: str
    data: dict[str, Any]
    fact_ids: list[str] = Field(default_factory=list)


class SynthesisDraft(StrictContract):
    answer: str = Field(min_length=1, max_length=16000)
    claims: list[AnswerClaim]
    citations: list[Citation]
    artifacts: list[QAArtifact] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)


class QAOutput(SynthesisDraft):
    intent: QAIntent
    entities: list[SchemaEntityRef]
    citation_coverage: float = Field(ge=0, le=1)
    degraded_reasons: list[str] = Field(default_factory=list)

    @field_validator("citation_coverage")
    @classmethod
    def require_full_coverage(cls, value: float) -> float:
        if value != 1.0:
            raise ValueError("published QA output requires 100% citation coverage")
        return value


class ConversationTurn(StrictContract):
    message_id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    structured: dict[str, Any] | None = None


class QAContext(StrictContract):
    thread_id: str | None = None
    messages: list[ConversationTurn] = Field(default_factory=list)
    focus_entities: list[CatalogEntity] = Field(default_factory=list)


class PlannerOutcome(StrictContract):
    plan: QueryPlan
    degraded: bool = False
    reason: str | None = None


class VerificationReport(StrictContract):
    valid: bool
    citation_coverage: float = Field(ge=0, le=1)
    errors: list[str] = Field(default_factory=list)
