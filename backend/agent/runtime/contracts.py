"""Versioned, strict contracts shared by agents, models, tools, and traces."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.status import AgentError, AgentRunResult, RunStatus

CONTRACT_VERSION = "2.0"


class StrictContract(BaseModel):
    """Runtime contract base: unknown fields are never silently accepted."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ModelCapabilities(StrictContract):
    supports_tools: bool = False
    supports_strict_schema: bool = False
    supports_streaming: bool = False
    supports_previous_response: bool = False
    max_context_tokens: int | None = Field(default=None, gt=0)


class ModelProfile(StrictContract):
    name: Literal["fast", "reasoning", "synthesis", "judge", "embedding"]
    provider: str
    model: str
    capabilities: ModelCapabilities
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0, le=10)
    temperature: float | None = Field(default=None, ge=0, le=2)
    available: bool = True


class ModelUsage(StrictContract):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def fill_total(self) -> "ModelUsage":
        calculated = self.input_tokens + self.output_tokens
        if self.total_tokens == 0:
            object.__setattr__(self, "total_tokens", calculated)
        elif self.total_tokens < calculated:
            raise ValueError("total_tokens cannot be smaller than input plus output tokens")
        return self


class ModelRequest(StrictContract):
    profile: str
    prompt_id: str
    prompt_version: str
    input: dict[str, Any]
    output_schema: dict[str, Any]
    tool_specs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fallback_profile: str | None = None


class ModelResult(StrictContract):
    contract_version: Literal["2.0"] = CONTRACT_VERSION
    status: Literal["success", "degraded", "error", "cancelled"]
    parsed: dict[str, Any] | None = None
    response_id: str | None = None
    model: str
    provider: str
    usage: ModelUsage = Field(default_factory=ModelUsage)
    attempt_count: int = Field(ge=0)
    model_call_id: str
    error: AgentError | None = None
    prompt_hash: str | None = None
    repaired: bool = False
    fallback_used: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)

    @field_validator("model_call_id")
    @classmethod
    def validate_model_call_id(cls, value: str) -> str:
        return _require_prefix(value, "mcall")

    @model_validator(mode="after")
    def validate_result(self) -> "ModelResult":
        if self.status == "success" and (self.parsed is None or self.error is not None):
            raise ValueError("successful model result requires parsed output and no error")
        if self.status in {"error", "cancelled"} and self.error is None:
            raise ValueError(f"{self.status} model result requires an error")
        if self.status == "degraded" and not (
            self.fallback_used or self.repaired or self.error or self.degradation_reasons
        ):
            raise ValueError("degraded model result must declare its reason")
        return self


class ModelEvent(StrictContract):
    event: Literal["delta", "completed", "failed"]
    model_call_id: str
    text: str = ""
    result: ModelResult | None = None


class ToolSpec(StrictContract):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=True)

    name: str
    version: str = "1.0.0"
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    capability: str
    side_effect: Literal["none", "read", "write", "ddl"]
    approval_policy: Literal["never", "conditional", "always"]
    idempotent: bool
    timeout_seconds: float = Field(gt=0)
    max_result_bytes: int = Field(gt=0)
    sensitivity: Literal["public", "internal", "restricted"]
    ready_for_agent: bool = False
    max_retries: int = Field(default=0, ge=0, le=5)


class ToolCallRequest(StrictContract):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    caller_agent: str
    run_id: str
    trace_id: str
    parent_span_id: str
    operation_id: str | None = None
    approved: bool = False

    @field_validator("tool_call_id")
    @classmethod
    def validate_tool_call_id(cls, value: str) -> str:
        return _require_prefix(value, "tcall")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _require_prefix(value, "run")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return _require_prefix(value, "trc")

    @field_validator("parent_span_id")
    @classmethod
    def validate_parent_span_id(cls, value: str) -> str:
        return _require_prefix(value, "spn")


class ToolCallResult(StrictContract):
    contract_version: Literal["2.0"] = CONTRACT_VERSION
    tool_call_id: str
    status: Literal["success", "error", "cancelled"]
    output: dict[str, Any] | None = None
    artifact_uri: str | None = None
    output_hash: str | None = None
    duration_ms: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    error: AgentError | None = None

    @field_validator("tool_call_id")
    @classmethod
    def validate_tool_call_id(cls, value: str) -> str:
        return _require_prefix(value, "tcall")

    @model_validator(mode="after")
    def validate_result(self) -> "ToolCallResult":
        if self.status == "success" and self.error is not None:
            raise ValueError("successful tool result cannot contain an error")
        if self.status in {"error", "cancelled"} and self.error is None:
            raise ValueError(f"{self.status} tool result requires an error")
        return self


class RunBudget(StrictContract):
    max_model_calls: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    max_loop_iterations: int = Field(gt=0)
    deadline_at: datetime | None = None


class RuntimeUsage(StrictContract):
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
    loop_iterations: int = Field(default=0, ge=0)


class RuntimeEvent(StrictContract):
    contract_version: Literal["2.0"] = CONTRACT_VERSION
    event_id: str
    sequence: int = Field(gt=0)
    timestamp: datetime
    thread_id: str | None = None
    run_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    agent_id: str
    attempt: int = Field(ge=1)
    event_type: Literal[
        "model.started",
        "model.completed",
        "model.failed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "usage.updated",
        "guardrail.passed",
        "guardrail.blocked",
        "worker.started",
        "worker.completed",
        "worker.degraded",
        "worker.failed",
        "collector.started",
        "collector.completed",
        "verifier.started",
        "verifier.completed",
        "artifact.created",
        "evidence.created",
        "relation.proposed",
        "critic.started",
        "critic.evidence_requested",
        "critic.completed",
    ]
    status: str
    schema_version: Literal["2.0"] = CONTRACT_VERSION
    payload: dict[str, Any] = Field(default_factory=dict)
    usage: RuntimeUsage = Field(default_factory=RuntimeUsage)
    redaction: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        return _require_prefix(value, "evt")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _require_prefix(value, "run")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return _require_prefix(value, "trc")

    @field_validator("span_id")
    @classmethod
    def validate_span_id(cls, value: str) -> str:
        return _require_prefix(value, "spn")

    @field_validator("parent_span_id")
    @classmethod
    def validate_parent_span_id(cls, value: str | None) -> str | None:
        return _require_prefix(value, "spn") if value else value


def _require_prefix(value: str, prefix: str) -> str:
    if not value.startswith(f"{prefix}_") or len(value) <= len(prefix) + 1:
        raise ValueError(f"identifier must use the {prefix}_ prefix")
    return value


__all__ = [
    "AgentError",
    "AgentRunResult",
    "CONTRACT_VERSION",
    "ModelCapabilities",
    "ModelEvent",
    "ModelProfile",
    "ModelRequest",
    "ModelResult",
    "ModelUsage",
    "RunBudget",
    "RunStatus",
    "RuntimeEvent",
    "RuntimeUsage",
    "StrictContract",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolSpec",
]
