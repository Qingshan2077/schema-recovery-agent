"""API response contracts for analysis and streaming."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    type: Literal["started", "node_started", "node_complete", "complete", "error"]
    session_id: str | None = None
    total_steps: int | None = None
    node: str | None = None
    step: AnalysisStepModel | None = None
    progress: StreamProgressModel | None = None
    data: dict[str, Any] | None = None
    error: str | None = None


def normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    return AnalysisStepModel(**step).model_dump(exclude_none=True)


def stream_event(**payload: Any) -> dict[str, Any]:
    return StreamEventModel(**payload).model_dump(exclude_none=True)
