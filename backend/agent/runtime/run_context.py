"""Run identity propagation, cancellation, budget, and trace ownership."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from threading import Event
from typing import Iterator

from backend.agent.runtime.budget import BudgetLedger
from backend.agent.runtime.contracts import RunBudget
from backend.agent.runtime.redaction import RedactionPolicy
from backend.agent.runtime.tracing import EventSink, RuntimeTracer
from backend.core.identity import RunIdentity


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()
        self._reason = "cancelled"

    def cancel(self, reason: str = "cancelled") -> None:
        self._reason = reason
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise RuntimeCancelledError(self.reason)


class RuntimeCancelledError(RuntimeError):
    pass


@dataclass
class RunContext:
    run_id: str
    trace_id: str
    thread_id: str | None
    agent_id: str
    budget: BudgetLedger
    tracer: RuntimeTracer
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)
    parent_span_id: str | None = None
    audit_warnings: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_identity(
        cls,
        identity: RunIdentity,
        *,
        agent_id: str,
        budget: RunBudget,
        event_sink: EventSink | None = None,
        cancellation: CancellationToken | None = None,
        redaction_policy: RedactionPolicy | None = None,
    ) -> "RunContext":
        return cls(
            run_id=identity.run_id,
            trace_id=identity.trace_id,
            thread_id=identity.thread_id,
            agent_id=agent_id,
            budget=BudgetLedger(budget),
            tracer=RuntimeTracer(event_sink),
            cancellation=cancellation or CancellationToken(),
            redaction_policy=redaction_policy or RedactionPolicy(),
        )

    def for_agent(self, agent_id: str, *, parent_span_id: str | None = None) -> "RunContext":
        """Share one ledger/tracer/cancellation token across a child agent."""

        return replace(
            self,
            agent_id=agent_id,
            parent_span_id=parent_span_id if parent_span_id is not None else self.parent_span_id,
            audit_warnings=self.audit_warnings,
        )

    def ensure_identity(self, *, run_id: str, trace_id: str) -> None:
        if run_id != self.run_id or trace_id != self.trace_id:
            raise ValueError("tool/model request identity does not match RunContext")


_CURRENT_CONTEXT: ContextVar[RunContext | None] = ContextVar("agent_runtime_context", default=None)


def current_run_context() -> RunContext:
    context = _CURRENT_CONTEXT.get()
    if context is None:
        raise RuntimeError("No RunContext is bound to the current execution")
    return context


@contextmanager
def bind_run_context(context: RunContext) -> Iterator[RunContext]:
    token: Token[RunContext | None] = _CURRENT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_CONTEXT.reset(token)
