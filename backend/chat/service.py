"""Application service coordinating persistent conversation state and QAAgent."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from backend.agent.qa.agent import QAAgent
from backend.agent.runtime import RuntimeContainer
from backend.agent.runtime.contracts import RuntimeEvent
from backend.agent.runtime.run_context import CancellationToken
from backend.chat.contracts import QARunRecord, StartedRun
from backend.chat.repository import SQLiteChatRepository
from backend.core.identity import RunIdentity, new_id


class ChatEventSink:
    def __init__(self, repository: SQLiteChatRepository, traces: object | None = None):
        self.repository = repository
        self.traces = traces

    async def emit(self, event: RuntimeEvent) -> None:
        if event.thread_id is None:
            return
        self.repository.append_event(
            thread_id=event.thread_id,
            run_id=event.run_id,
            event_type=event.event_type,
            status=event.status,
            payload=event.model_dump(mode="json"),
        )
        if self.traces is not None:
            self.traces.record_event(event)


class ChatService:
    def __init__(self, *, repository: SQLiteChatRepository, qa_agent: QAAgent, runtime: RuntimeContainer, traces: object | None = None):
        self.repository = repository
        self.qa_agent = qa_agent
        self.runtime = runtime
        self.traces = traces
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = RLock()

    def start_message(
        self,
        *,
        thread_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str | None = None,
    ) -> StartedRun:
        return self.repository.start_run(
            thread_id=thread_id,
            owner_id=owner_id,
            content=content,
            idempotency_key=idempotency_key,
        )

    async def execute(self, started: StartedRun, *, owner_id: str = "local") -> QARunRecord:
        existing = self.repository.get_run(started.run_id, owner_id=owner_id)
        if started.reused and existing and existing.status != "running":
            return existing
        token = CancellationToken()
        if existing and existing.cancel_requested:
            token.cancel("cancelled_by_user")
        with self._lock:
            self._tokens[started.run_id] = token
        try:
            identity = RunIdentity(run_id=started.run_id, trace_id=started.trace_id, thread_id=started.thread_id)
            context = self.runtime.new_context(
                identity,
                agent_id="qa",
                event_sink=ChatEventSink(self.repository, self.traces),
                cancellation=token,
            )
            async def emit_qa_event(event_type: str, status: str, payload: dict) -> None:
                persisted = self.repository.append_event(
                    thread_id=started.thread_id,
                    run_id=started.run_id,
                    event_type=event_type,
                    status=status,
                    payload=payload,
                )
                if self.traces is not None:
                    self.traces.record_event(RuntimeEvent(
                        event_id=persisted.event_id,
                        sequence=persisted.sequence,
                        timestamp=datetime.now(timezone.utc),
                        thread_id=started.thread_id,
                        run_id=started.run_id,
                        trace_id=started.trace_id,
                        span_id=new_id("span"),
                        parent_span_id=None,
                        agent_id="qa",
                        attempt=1,
                        event_type=event_type,
                        status=status,
                        payload=payload,
                        usage=context.budget.snapshot(),
                        redaction={"level": context.redaction_policy.level},
                    ))
            thread = self.repository.get_thread(started.thread_id, owner_id=owner_id)
            messages = []
            question = ""
            if thread:
                for message in thread.messages:
                    if message.message_id == started.message_id:
                        question = message.content
                        continue
                    messages.append(
                        {
                            "message_id": message.message_id,
                            "role": message.role,
                            "content": message.content,
                            "structured": message.structured,
                        }
                    )
            result = await self.qa_agent.run(
                question=question,
                run_context=context,
                messages=messages,
                event_emitter=emit_qa_event,
            )
            self.repository.complete_run(started.run_id, result=result.model_dump(mode="json"))
            completed = self.repository.get_run(started.run_id, owner_id=owner_id)
            if completed is None:
                raise RuntimeError("completed run could not be reloaded")
            return completed
        finally:
            with self._lock:
                self._tokens.pop(started.run_id, None)

    def cancel(self, run_id: str, *, owner_id: str = "local") -> bool:
        requested = self.repository.request_cancel(run_id, owner_id=owner_id)
        if not requested:
            return False
        with self._lock:
            token = self._tokens.get(run_id)
        if token:
            token.cancel("cancelled_by_user")
        return True
