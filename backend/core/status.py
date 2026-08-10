"""Canonical run status semantics and legacy result adapters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    RunStatus.SUCCESS,
    RunStatus.PARTIAL,
    RunStatus.DEGRADED,
    RunStatus.BLOCKED,
    RunStatus.ERROR,
    RunStatus.CANCELLED,
}

_LEGACY_STATUS_MAP = {
    "completed": RunStatus.SUCCESS,
    "complete": RunStatus.SUCCESS,
    "failed": RunStatus.ERROR,
    "failure": RunStatus.ERROR,
}

_PRIORITY = {
    RunStatus.SUCCESS: 0,
    RunStatus.PARTIAL: 1,
    RunStatus.DEGRADED: 2,
    RunStatus.BLOCKED: 3,
    RunStatus.ERROR: 4,
    RunStatus.CANCELLED: 5,
}


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    code: str
    category: Literal[
        "validation",
        "provider",
        "timeout",
        "rate_limit",
        "tool",
        "permission",
        "budget",
        "cancelled",
        "internal",
    ] = "internal"
    message: str
    retryable: bool = False
    source: str = "runtime"
    details: dict[str, Any] = Field(default_factory=dict)
    cause_span_id: str | None = None

    @field_validator("message", mode="after")
    @classmethod
    def redact_message(cls, value: str) -> str:
        return re.sub(
            r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
            r"\1=***",
            value,
        )[:1000]

    @field_validator("details", mode="after")
    @classmethod
    def redact_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _redact_error_value(value)


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    contract_version: Literal["2.0"] = "2.0"
    status: RunStatus
    output: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    decision_summary: str = ""
    next_actions: list[str] = Field(default_factory=list)
    error: AgentError | None = None
    model_profile: str | None = None
    prompt_version: str | None = None

    @field_validator("evidence_ids", "tool_call_ids", mode="after")
    @classmethod
    def deduplicate_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_status_contract(self) -> "AgentRunResult":
        if self.status == RunStatus.SUCCESS and self.error is not None:
            raise ValueError("success result cannot contain an error")
        if self.status in {RunStatus.ERROR, RunStatus.BLOCKED, RunStatus.CANCELLED} and self.error is None:
            raise ValueError(f"{self.status.value} result requires an error")
        if self.status == RunStatus.DEGRADED and not (self.uncertainties or self.next_actions or self.error):
            raise ValueError("degraded result must describe a capability gap")
        return self


def coerce_run_status(value: RunStatus | str) -> RunStatus:
    if isinstance(value, RunStatus):
        return value
    normalized = str(value).strip().lower()
    if normalized in _LEGACY_STATUS_MAP:
        return _LEGACY_STATUS_MAP[normalized]
    try:
        return RunStatus(normalized)
    except ValueError as exc:
        raise ValueError(f"unknown run status: {value!r}") from exc


def coerce_worker_status(value: str | None) -> str:
    """Normalize worker output without weakening explicit failures."""

    normalized = (value or "").strip().lower()
    if normalized in {"success", "partial", "degraded", "blocked", "error", "cancelled", "skipped"}:
        return normalized
    if normalized in {"completed", "complete"}:
        return "success"
    if normalized in {"failed", "failure"}:
        return "error"
    raise ValueError(f"unknown worker status: {value!r}")


def combine_run_status(statuses: Iterable[RunStatus | str]) -> RunStatus:
    canonical = [coerce_run_status(status) for status in statuses]
    canonical = [status for status in canonical if status != RunStatus.RUNNING]
    if not canonical:
        return RunStatus.RUNNING
    return max(canonical, key=lambda item: _PRIORITY[item])


def reduce_run_status(
    required_steps: Mapping[str, str] | Iterable[str],
    optional_steps: Mapping[str, str] | Iterable[str] = (),
    *,
    cancelled: bool = False,
    fallback: bool = False,
) -> RunStatus:
    """Reduce step outcomes using the Phase 0 deterministic precedence."""

    if cancelled:
        return RunStatus.CANCELLED

    required = _step_values(required_steps)
    optional = _step_values(optional_steps)
    if not required or any(status in {"", "missing", "skipped"} for status in required):
        return RunStatus.ERROR
    if any(status == "cancelled" for status in required + optional):
        return RunStatus.CANCELLED
    if any(status == "error" for status in required):
        return RunStatus.ERROR
    if any(status == "blocked" for status in required):
        return RunStatus.BLOCKED

    optional_failure = any(status in {"error", "blocked", "cancelled"} for status in optional)
    if fallback or any(status == "degraded" for status in required + optional):
        return RunStatus.DEGRADED
    if optional_failure or any(status == "partial" for status in required + optional):
        return RunStatus.PARTIAL
    return RunStatus.SUCCESS


def validate_terminal_result(
    status: RunStatus | str,
    output: dict[str, Any] | None,
    error: AgentError | dict[str, Any] | str | None,
    *,
    require_output: bool = True,
) -> None:
    canonical = coerce_run_status(status)
    if canonical not in TERMINAL_STATUSES:
        raise ValueError("running is not a valid terminal result")
    if canonical in {RunStatus.ERROR, RunStatus.BLOCKED, RunStatus.CANCELLED} and not error:
        raise ValueError(f"{canonical.value} status requires a structured error")
    if canonical == RunStatus.SUCCESS and require_output and not output:
        raise ValueError("success status requires a core output artifact")


def map_v2_status_to_v1(status: RunStatus | str) -> str:
    canonical = coerce_run_status(status)
    return "completed" if canonical == RunStatus.SUCCESS else canonical.value


def normalize_legacy_result(result: Mapping[str, Any]) -> AgentRunResult:
    status = coerce_run_status(result.get("status", ""))
    raw_output = result.get("output")
    if raw_output is None:
        raw_output = {
            key: value
            for key, value in result.items()
            if key not in {"status", "error", "evidence_ids", "tool_call_ids"}
        }
    if not isinstance(raw_output, dict):
        raw_output = {"value": raw_output}

    raw_error = result.get("error")
    error: AgentError | None = None
    if raw_error:
        if isinstance(raw_error, Mapping):
            category = str(raw_error.get("category", "internal"))
            if category not in {
                "validation", "provider", "timeout", "rate_limit", "tool",
                "permission", "budget", "cancelled", "internal",
            }:
                category = "internal"
            error = AgentError(
                code=str(raw_error.get("code", "legacy_error")),
                category=category,
                message=str(raw_error.get("message", raw_error)),
                retryable=bool(raw_error.get("retryable", False)),
                source=str(raw_error.get("source", "legacy_adapter")),
                details=dict(raw_error.get("details") or {}),
            )
        else:
            error = AgentError(code="legacy_error", message=str(raw_error), source="legacy_adapter")
    if status in {RunStatus.ERROR, RunStatus.BLOCKED, RunStatus.CANCELLED} and error is None:
        error = AgentError(
            code="legacy_error",
            category="cancelled" if status == RunStatus.CANCELLED else "internal",
            message=f"Legacy worker returned {status.value} without details",
            source="legacy_adapter",
        )

    uncertainties = list(result.get("uncertainties") or [])
    if status == RunStatus.DEGRADED and not uncertainties:
        uncertainties.append("legacy_worker_reported_degraded_without_structured_capability_details")

    return AgentRunResult(
        status=status,
        output=raw_output,
        evidence_ids=list(result.get("evidence_ids") or []),
        tool_call_ids=list(result.get("tool_call_ids") or []),
        assumptions=list(result.get("assumptions") or []),
        uncertainties=uncertainties,
        decision_summary=str(result.get("decision_summary") or ""),
        next_actions=list(result.get("next_actions") or []),
        error=error,
        model_profile=result.get("model_profile"),
        prompt_version=result.get("prompt_version"),
    )


def _step_values(steps: Mapping[str, str] | Iterable[str]) -> list[str]:
    values = steps.values() if isinstance(steps, Mapping) else steps
    return [
        value.value if isinstance(value, RunStatus) else str(value).strip().lower()
        for value in values
    ]


def _redact_error_value(value: Any) -> Any:
    sensitive = {"password", "passwd", "token", "secret", "api_key", "authorization", "connection_string"}
    if isinstance(value, dict):
        return {
            str(key): "***" if str(key).lower() in sensitive else _redact_error_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_error_value(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
            r"\1=***",
            value,
        )[:1000]
    return value
