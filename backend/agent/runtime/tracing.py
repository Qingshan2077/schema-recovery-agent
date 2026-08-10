"""Runtime event envelopes and fail-safe event sinks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol

from backend.agent.runtime.contracts import RuntimeEvent
from backend.agent.runtime.redaction import RedactionPolicy
from backend.core.identity import new_id


class EventSink(Protocol):
    async def emit(self, event: RuntimeEvent) -> None: ...


class NullEventSink:
    async def emit(self, event: RuntimeEvent) -> None:
        return None


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []
        self._lock = RLock()

    async def emit(self, event: RuntimeEvent) -> None:
        with self._lock:
            self.events.append(event)


class CallbackEventSink:
    def __init__(self, callback: Callable[[dict[str, Any]], Any | Awaitable[Any]]):
        self.callback = callback

    async def emit(self, event: RuntimeEvent) -> None:
        result = self.callback(event.model_dump(mode="json"))
        if inspect.isawaitable(result):
            await result


class RunStoreEventSink:
    """Persist redacted runtime events in the Phase 0 process-local run store."""

    def __init__(self, run_store: Any):
        self.run_store = run_store

    async def emit(self, event: RuntimeEvent) -> None:
        self.run_store.record_runtime_event(event.model_dump(mode="json"))


class RuntimeTracer:
    def __init__(self, sink: EventSink | None = None):
        self.sink = sink or NullEventSink()
        self._sequence = 0
        self._lock = RLock()

    async def emit(
        self,
        *,
        context: "RunContextProtocol",
        event_type: str,
        status: str,
        span_id: str,
        parent_span_id: str | None,
        payload: dict[str, Any] | None = None,
        attempt: int = 1,
        security_required: bool = False,
    ) -> RuntimeEvent | None:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        event = RuntimeEvent(
            event_id=new_id("event"),
            sequence=sequence,
            timestamp=datetime.now(timezone.utc),
            thread_id=context.thread_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent_id=context.agent_id,
            attempt=attempt,
            event_type=event_type,
            status=status,
            payload=context.redaction_policy.redact(payload or {}),
            usage=context.budget.snapshot(),
            redaction={"level": context.redaction_policy.level},
        )
        try:
            await self.sink.emit(event)
        except Exception as exc:
            if security_required:
                raise RuntimeError("required security audit event could not be recorded") from exc
            if "runtime_event_sink_unavailable" not in context.audit_warnings:
                context.audit_warnings.append("runtime_event_sink_unavailable")
            return None
        return event


class RunContextProtocol(Protocol):
    thread_id: str | None
    run_id: str
    trace_id: str
    agent_id: str
    redaction_policy: RedactionPolicy
    budget: Any
    audit_warnings: list[str]


def new_span_id() -> str:
    return new_id("span")
