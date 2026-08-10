import pytest
from pydantic import ValidationError

from backend.agent.runtime.contracts import AgentError, AgentRunResult
from backend.core.status import RunStatus


def test_agent_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentRunResult(status=RunStatus.SUCCESS, output={"ok": True}, unknown=True)


def test_terminal_failure_requires_structured_error():
    with pytest.raises(ValidationError):
        AgentRunResult(status=RunStatus.BLOCKED)


def test_success_cannot_carry_error_and_ids_are_deduplicated():
    with pytest.raises(ValidationError):
        AgentRunResult(
            status=RunStatus.SUCCESS,
            error=AgentError(code="bad", message="bad"),
        )

    result = AgentRunResult(
        status=RunStatus.SUCCESS,
        output={"ok": True},
        evidence_ids=["evd_one", "evd_one"],
        tool_call_ids=["tcall_one", "tcall_one"],
    )
    assert result.evidence_ids == ["evd_one"]
    assert result.tool_call_ids == ["tcall_one"]
