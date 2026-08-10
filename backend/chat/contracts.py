"""HTTP and persistence contracts for Phase 2 conversations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract


class CreateThreadRequest(StrictContract):
    title: str = Field(default="", max_length=200)


class PostMessageRequest(StrictContract):
    content: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class ChatMessageRecord(StrictContract):
    message_id: str
    thread_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    structured: dict[str, Any] | None = None
    created_at: str


class ChatThreadRecord(StrictContract):
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ChatMessageRecord] = Field(default_factory=list)
    last_sequence: int = Field(default=0, ge=0)


class StartedRun(StrictContract):
    thread_id: str
    message_id: str
    run_id: str
    trace_id: str
    status: Literal["running"] = "running"
    reused: bool = False
    events_url: str


class QARunRecord(StrictContract):
    run_id: str
    thread_id: str
    trace_id: str
    user_message_id: str
    assistant_message_id: str | None = None
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    created_at: str
    updated_at: str


class ChatEventRecord(StrictContract):
    event_id: str
    thread_id: str
    run_id: str
    sequence: int = Field(gt=0)
    event_type: str
    status: str
    payload: dict[str, Any]
    created_at: str


class EventPage(StrictContract):
    events: list[ChatEventRecord]
    next_sequence: int = Field(default=0, ge=0)
