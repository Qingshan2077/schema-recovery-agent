import asyncio

from backend.agent.runtime.contracts import RunBudget, ToolCallRequest, ToolSpec
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import LocalArtifactStore, ToolRuntime
from backend.core.identity import RunIdentity, new_id
from backend.tests.runtime.fixtures.fake_tools import (
    DDLInput,
    DDLOutput,
    EchoInput,
    EchoOutput,
    echo,
    fake_ddl,
    invalid_echo,
)


def _context():
    identity = RunIdentity.create()
    context = RunContext.from_identity(
        identity,
        agent_id="qa",
        budget=RunBudget(
            max_model_calls=2,
            max_tool_calls=10,
            max_input_tokens=100,
            max_output_tokens=100,
            max_cost_usd=None,
            max_loop_iterations=2,
        ),
    )
    return identity, context


def _request(identity, tool, arguments, *, approved=False, operation_id=None):
    return ToolCallRequest(
        tool_call_id=new_id("tool_call"),
        tool_name=tool,
        arguments=arguments,
        caller_agent="qa",
        run_id=identity.run_id,
        trace_id=identity.trace_id,
        parent_span_id=new_id("span"),
        approved=approved,
        operation_id=operation_id,
    )


def _echo_spec(**overrides):
    values = {
        "name": "echo",
        "version": "1.0.0",
        "description": "echo",
        "input_model": EchoInput,
        "output_model": EchoOutput,
        "capability": "schema:read",
        "side_effect": "read",
        "approval_policy": "never",
        "idempotent": True,
        "timeout_seconds": 1,
        "max_result_bytes": 1024,
        "sensitivity": "internal",
        "ready_for_agent": True,
        "max_retries": 1,
    }
    values.update(overrides)
    return ToolSpec(**values)


def test_tool_runtime_validates_input_and_output():
    identity, context = _context()
    runtime = ToolRuntime(allowlists={"qa": {"echo"}})
    runtime.register(_echo_spec(), echo)

    valid = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "hello"}), context))
    invalid = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "hello", "extra": True}), context))

    assert valid.status == "success"
    assert valid.output == {"echoed": "hello"}
    assert invalid.status == "error"
    assert invalid.error.code == "tool_input_invalid"


def test_invalid_tool_output_never_reaches_agent():
    identity, context = _context()
    runtime = ToolRuntime(allowlists={"qa": {"echo"}})
    runtime.register(_echo_spec(), invalid_echo)

    result = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "hello"}), context))

    assert result.status == "error"
    assert result.output is None
    assert result.error.code == "tool_output_invalid"


def test_readonly_agent_cannot_discover_or_execute_ddl():
    identity, context = _context()
    runtime = ToolRuntime(allowlists={"qa": {"echo"}})
    runtime.register(
        ToolSpec(
            name="ddl",
            version="1.0.0",
            description="ddl",
            input_model=DDLInput,
            output_model=DDLOutput,
            capability="schema:ddl",
            side_effect="ddl",
            approval_policy="always",
            idempotent=False,
            timeout_seconds=1,
            max_result_bytes=1024,
            sensitivity="restricted",
            ready_for_agent=True,
        ),
        fake_ddl,
    )

    result = asyncio.run(runtime.execute(_request(identity, "ddl", {"statement": "DROP TABLE x"}), context))

    assert "ddl" not in {tool["name"] for tool in runtime.discover("qa")}
    assert result.status == "error"
    assert result.error.category == "permission"


def test_large_result_is_replaced_with_artifact_reference(tmp_path):
    identity, context = _context()
    runtime = ToolRuntime(allowlists={"qa": {"echo"}}, artifact_store=LocalArtifactStore(tmp_path))
    runtime.register(_echo_spec(max_result_bytes=16), echo)

    result = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "x" * 100}), context))

    assert result.status == "success"
    assert result.artifact_uri
    assert result.output["artifact"] is True


def test_cancelled_context_prevents_executor_call():
    identity, context = _context()
    calls = []

    def tracked_echo(text):
        calls.append(text)
        return {"echoed": text}

    runtime = ToolRuntime(allowlists={"qa": {"echo"}})
    runtime.register(_echo_spec(), tracked_echo)
    context.cancellation.cancel("user_cancelled")

    result = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "hello"}), context))

    assert result.status == "cancelled"
    assert calls == []


def test_oversized_arguments_are_rejected_before_executor():
    identity, context = _context()
    calls = []

    def tracked_echo(text):
        calls.append(text)
        return {"echoed": text}

    runtime = ToolRuntime(allowlists={"qa": {"echo"}}, max_argument_bytes=32)
    runtime.register(_echo_spec(), tracked_echo)

    result = asyncio.run(runtime.execute(_request(identity, "echo", {"text": "x" * 100}), context))

    assert result.status == "error"
    assert result.error.code == "tool_input_too_large"
    assert calls == []
