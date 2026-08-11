import pytest

from backend.agent.runtime.budget import BudgetLedger
from backend.agent.runtime.contracts import RunBudget
from backend.agent.runtime.contracts import RuntimeUsage
from backend.core.identity import RunIdentity
from backend.workflow.contracts import RecoveryStateV2, StatePatch
from backend.workflow.definition import schema_recovery_v2
from backend.workflow.reducer import StateVersionConflict, apply_patch, merge_patches
from backend.workflow.state_machine import InvalidStateTransition, RecoveryStateMachine


def _state() -> RecoveryStateV2:
    identity = RunIdentity.create(thread_id="thr_phase4")
    return RecoveryStateV2(
        workflow_version="schema-recovery-v2",
        run_id=identity.run_id,
        trace_id=identity.trace_id,
        thread_id=identity.thread_id,
        session_id=identity.run_id,
        project_id="project",
        connection_id="connection",
        active_engine="manual",
    )


def test_reducer_deduplicates_stable_ids_and_sums_usage():
    state = _state()
    state = apply_patch(state, StatePatch(status="running", expected_version=0))
    patches = [
        StatePatch(artifact_ids_add=["art_a"], evidence_ids_add=["evd_a"], usage_delta=RuntimeUsage(tool_calls=1)),
        StatePatch(artifact_ids_add=["art_a", "art_b"], evidence_ids_add=["evd_a"], usage_delta=RuntimeUsage(model_calls=1)),
    ]

    merged = apply_patch(state, merge_patches(patches).model_copy(update={"expected_version": state.version}))

    assert merged.artifact_ids == ["art_a", "art_b"]
    assert merged.evidence_ids == ["evd_a"]
    assert merged.budget.tool_calls == 1
    assert merged.budget.model_calls == 1


def test_parallel_reducer_uses_error_severity_not_completion_order():
    first = merge_patches([StatePatch(status="failed"), StatePatch(status="blocked")])
    second = merge_patches([StatePatch(status="blocked"), StatePatch(status="failed")])

    assert first.status == second.status == "failed"


def test_parallel_reducer_rejects_same_output_key_with_different_refs():
    with pytest.raises(StateVersionConflict):
        merge_patches([
            StatePatch(output_refs_merge={"column_result": "artifact_a"}),
            StatePatch(output_refs_merge={"column_result": "artifact_b"}),
        ])


def test_reducer_rejects_stale_expected_version():
    with pytest.raises(StateVersionConflict):
        apply_patch(_state(), StatePatch(status="running", expected_version=9))


def test_state_machine_prevents_required_failure_from_becoming_completed():
    assert RecoveryStateMachine.terminal_for(
        required_failed=True, optional_failed=False, degraded=False, has_result=True,
    ) == "failed"
    with pytest.raises(InvalidStateTransition):
        RecoveryStateMachine.transition("failed", "completed")


def test_workflow_definition_declares_all_parallel_reducers_and_loop_limit():
    definition = schema_recovery_v2()
    assert definition.version == "schema-recovery-v2"
    assert definition.state_schema_version == "2"
    assert definition.reducers["artifact_ids"] == "stable_id_set"
    critic = next(item for item in definition.nodes if item.node_id == "critic")
    assert critic.loop_limit == 2


def test_budget_ledger_restores_persisted_usage_without_reset():
    ledger = BudgetLedger(
        RunBudget(
            max_model_calls=10, max_tool_calls=20,
            max_input_tokens=1000, max_output_tokens=1000,
            max_loop_iterations=5,
        ),
        initial_usage=RuntimeUsage(model_calls=3, tool_calls=4, input_tokens=120),
    )

    assert ledger.snapshot() == RuntimeUsage(model_calls=3, tool_calls=4, input_tokens=120)
    with pytest.raises(RuntimeError):
        ledger.restore(RuntimeUsage(model_calls=1))
