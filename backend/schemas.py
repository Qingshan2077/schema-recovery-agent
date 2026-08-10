"""API response contracts for analysis, chat, and streaming."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.core.identity import RunIdentity, new_id
from backend.core.status import RunStatus, coerce_run_status, map_v2_status_to_v1


class AnalysisStepModel(BaseModel):
    step: int
    worker: str
    status: str
    duration_ms: int = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    output: Any | None = None
    error: str | None = None


class StreamProgressModel(BaseModel):
    completed: int
    total: int


class StreamEventModel(BaseModel):
    type: Literal["started", "node_started", "node_complete", "complete", "error", "heartbeat"]
    event_type: str | None = None
    event_id: str | None = None
    sequence: int | None = None
    timestamp: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    status: str | None = None
    schema_version: str = "2.0"
    total_steps: int | None = None
    node: str | None = None
    step: AnalysisStepModel | None = None
    progress: StreamProgressModel | None = None
    data: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    error: str | None = None


class ChatMessageModel(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    thread_id: str | None = None
    history: list[ChatMessageModel] = Field(default_factory=list)
    confirmed: bool = False
    pending_operation: dict[str, Any] | None = None


def normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    normalized = AnalysisStepModel(**step).model_dump(exclude_none=True)
    normalized["tool_calls"] = [
        {
            key: _sanitize_public_value(value)
            for key, value in tool_call.items()
            if key in {"tool_call_id", "tool", "params"}
        }
        for tool_call in normalized.get("tool_calls", [])
    ]
    if "output" in normalized:
        normalized["output"] = _sanitize_public_value(normalized["output"])
    if "error" in normalized:
        normalized["error"] = _sanitize_public_value(normalized["error"])
    return normalized


def stream_event(**payload: Any) -> dict[str, Any]:
    return StreamEventModel(**payload).model_dump(exclude_none=True)


def analysis_result_v1(result: dict[str, Any]) -> dict[str, Any]:
    """Expose canonical identity while retaining the v1 completed status."""

    compatible = sanitize_analysis_result(result)
    canonical = coerce_run_status(result.get("run_status") or result.get("status") or RunStatus.ERROR.value)
    run_id = result.get("run_id") or result.get("session_id")
    compatible["run_status"] = canonical.value
    compatible["status"] = map_v2_status_to_v1(canonical)
    compatible["session_id"] = run_id
    compatible["run_id"] = run_id
    return compatible


def sanitize_analysis_result(result: dict[str, Any]) -> dict[str, Any]:
    public = dict(result)
    public["steps"] = [normalize_step(step) for step in result.get("steps", [])]
    if public.get("error"):
        public["error"] = _sanitize_public_value(public["error"])
    if public.get("error_detail"):
        public["error_detail"] = _sanitize_public_value(public["error_detail"])
    return public


class EventSequencer:
    """Create strictly increasing, backward-compatible stream envelopes."""

    def __init__(self, identity: RunIdentity):
        self.identity = identity
        self.sequence = 0

    def next(
        self,
        *,
        legacy_type: Literal["started", "node_started", "node_complete", "complete", "error", "heartbeat"],
        event_type: str,
        status: RunStatus | str | None = None,
        payload: dict[str, Any] | None = None,
        **legacy_payload: Any,
    ) -> dict[str, Any]:
        self.sequence += 1
        canonical_status = coerce_run_status(status).value if status is not None else None
        return stream_event(
            type=legacy_type,
            event_type=event_type,
            event_id=new_id("event"),
            sequence=self.sequence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=self.identity.run_id,
            thread_id=self.identity.thread_id,
            run_id=self.identity.run_id,
            trace_id=self.identity.trace_id,
            span_id=new_id("span"),
            status=canonical_status,
            payload=payload or {},
            **legacy_payload,
        )


_PRIVATE_EVENT_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "authorization",
    "connection_string",
    "content",
    "definition",
    "ddl_statement",
    "sql",
}


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if str(key).lower() in _PRIVATE_EVENT_KEYS else _sanitize_public_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "…"
    return value
