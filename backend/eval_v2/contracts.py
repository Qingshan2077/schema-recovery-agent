"""Strict, versioned contracts for datasets, eval runs, metrics, judges and gates."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from backend.agent.runtime.contracts import StrictContract


class DatasetManifest(StrictContract):
    dataset_id: str
    version: str
    content_hash: str
    created_at: datetime
    dialects: list[str]
    domains: list[str]
    case_schema_version: str
    annotation_guideline_version: str
    fixture_hashes: dict[str, str]
    split_hashes: dict[str, str]
    licenses: list[str]
    pii_review: Literal["passed", "failed", "pending"]
    known_limitations: list[str] = Field(default_factory=list)


class EvalCase(StrictContract):
    case_id: str
    task_type: Literal["schema", "qa", "dba", "trajectory", "evidence", "memory", "system"]
    split: Literal["train", "dev", "calibration", "public_test", "hidden_test", "adversarial"]
    dialect: str
    domain: str
    fixture_id: str
    input: dict[str, Any]
    reference: dict[str, Any]
    ambiguity_policy: Literal["exact", "any_valid", "unknown", "adjudicated"] = "exact"
    slices: list[str] = Field(default_factory=list)
    annotator_id: str
    reviewer_id: str
    guideline_version: str
    disputed: bool = False
    adjudication_reason: str | None = None


class EvalRunManifest(StrictContract):
    eval_run_id: str
    git_sha: str
    dirty_worktree: bool
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    split: str
    case_ids_hash: str
    snapshot_hashes: dict[str, str]
    engine: str
    model_profiles: dict[str, str]
    provider_versions: dict[str, str]
    prompt_hashes: dict[str, str]
    tool_versions: dict[str, str]
    fusion_version: str
    calibration_version: str
    threshold_policy_version: str
    memory_mode: str
    runtime_config_hash: str
    trace_schema_version: str = "1.0"
    seed: int | None = None
    determinism: Literal["deterministic", "best_effort", "non_deterministic"]
    mode: Literal["pr_smoke", "affected_slice", "nightly", "release", "diagnostic"]
    gate_policy: str
    started_at: datetime
    parent_baseline_id: str | None = None


class EvalRunRecord(StrictContract):
    eval_run_id: str
    manifest_hash: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "incomplete"]
    sequence: int = Field(default=0, ge=0)
    total_cases: int = Field(ge=0)
    completed_cases: int = Field(default=0, ge=0)
    failed_cases: int = Field(default=0, ge=0)
    trace_complete: bool = True
    qualitative_complete: bool = True
    started_at: datetime
    finalized_at: datetime | None = None
    finalization_hash: str | None = None


class MetricResult(StrictContract):
    metric_id: str
    name: str
    value: float
    numerator: float | None = None
    denominator: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    slice_key: str = "overall"
    case_ids: list[str] = Field(default_factory=list)
    definition_version: str


class JudgeDimension(StrictContract):
    score: int = Field(ge=0, le=4)
    passed: bool
    reason_codes: list[str]
    evidence_refs: list[str]
    concise_rationale: str = Field(max_length=1000)


class JudgeResult(StrictContract):
    case_id: str
    rubric_version: str
    correctness: JudgeDimension
    groundedness: JudgeDimension
    evidence_quality: JudgeDimension
    trajectory_quality: JudgeDimension
    safety: JudgeDimension
    overall_pass: bool
    uncertainty: float = Field(ge=0, le=1)
    requires_human_review: bool
    judge_model: str
    prompt_hash: str


class JudgeCaseBundle(StrictContract):
    case_id: str
    task: str
    user_question: str | None = None
    reference: dict[str, Any]
    ambiguity_policy: str
    schema_excerpt: dict[str, Any]
    final_answer: dict[str, Any]
    citations: list[dict[str, Any]]
    trajectory_summary: list[dict[str, Any]]
    deterministic_facts: dict[str, Any]
    evidence_refs: list[str]


class GateRule(StrictContract):
    metric: str
    operator: Literal[">=", "<=", "=", "relative_drop<="]
    threshold: float
    safety_critical: bool = False
    slice_key: str = "overall"


class GateDecision(StrictContract):
    gate_id: str
    policy_version: str
    eval_run_id: str
    baseline_eval_run_id: str | None = None
    status: Literal["passed", "failed", "review", "infra_failed"]
    rule_results: list[dict[str, Any]]
    blocking_reasons: list[str]
    evaluated_at: datetime


class BaselinePromotion(StrictContract):
    promotion_id: str
    gate: str
    eval_run_id: str
    actor_id: str
    actor_role: str
    reason: str
    created_at: datetime


class EvalCreateRequest(StrictContract):
    dataset_id: str
    dataset_version: str
    split: Literal["dev", "calibration", "public_test", "hidden_test", "adversarial"]
    mode: Literal["pr_smoke", "affected_slice", "nightly", "release", "diagnostic"]
    engine: Literal["manual", "langgraph"]
    gate_policy: str
    case_ids: list[str] = Field(default_factory=list)
    seed: int | None = None

    @model_validator(mode="after")
    def release_restrictions(self) -> "EvalCreateRequest":
        if self.mode == "release" and self.split not in {"public_test", "hidden_test", "adversarial"}:
            raise ValueError("release mode requires a release-eligible split")
        return self
