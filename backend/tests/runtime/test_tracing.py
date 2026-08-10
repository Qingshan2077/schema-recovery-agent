import asyncio

from backend.agent.runtime.contracts import RunBudget
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tracing import InMemoryEventSink, new_span_id
from backend.core.identity import RunIdentity
from backend.core.run_store import RunStore
from backend.agent.runtime.tracing import RunStoreEventSink


def test_runtime_events_share_identity_and_increase_sequence():
    sink = InMemoryEventSink()
    identity = RunIdentity.create(thread_id="thr_runtime_test")
    context = RunContext.from_identity(
        identity,
        agent_id="qa",
        budget=RunBudget(
            max_model_calls=2,
            max_tool_calls=2,
            max_input_tokens=100,
            max_output_tokens=100,
            max_cost_usd=None,
            max_loop_iterations=2,
        ),
        event_sink=sink,
    )

    async def emit_events():
        for event_type in ("guardrail.passed", "tool.started", "tool.completed"):
            await context.tracer.emit(
                context=context,
                event_type=event_type,
                status="success",
                span_id=new_span_id(),
                parent_span_id=None,
                payload={"api_key": "must-not-leak"},
            )

    asyncio.run(emit_events())
    assert [event.sequence for event in sink.events] == [1, 2, 3]
    assert {event.run_id for event in sink.events} == {identity.run_id}
    assert {event.trace_id for event in sink.events} == {identity.trace_id}
    assert all(event.payload["api_key"] == "***" for event in sink.events)


def test_run_store_sink_keeps_runtime_events_queryable_by_run():
    store = RunStore()
    identity = RunIdentity.create()
    store.start(identity, engine="test")
    context = RunContext.from_identity(
        identity,
        agent_id="qa",
        budget=RunBudget(
            max_model_calls=1,
            max_tool_calls=1,
            max_input_tokens=10,
            max_output_tokens=10,
            max_cost_usd=None,
            max_loop_iterations=1,
        ),
        event_sink=RunStoreEventSink(store),
    )

    asyncio.run(
        context.tracer.emit(
            context=context,
            event_type="usage.updated",
            status="success",
            span_id=new_span_id(),
            parent_span_id=None,
            payload={},
        )
    )

    record = store.get(identity.run_id)
    assert record["runtime_events"][0]["trace_id"] == identity.trace_id
    assert record["runtime_last_sequence"] == 1
