from backend.core.identity import RunIdentity
from backend.workflow.contracts import RecoveryStateV2
from backend.workflow.parity import normalize_outcome, parity_diff


def _state(engine: str, artifacts: list[str]) -> RecoveryStateV2:
    identity = RunIdentity.create(thread_id="thr_parity")
    return RecoveryStateV2(
        workflow_version="schema-recovery-v2",
        run_id=identity.run_id,
        trace_id=identity.trace_id,
        thread_id=identity.thread_id,
        session_id=identity.run_id,
        project_id="project",
        connection_id="connection",
        active_engine=engine,
        status="completed",
        completed_stage_keys=["recovery.column:wunit_1:success"],
        artifact_ids=artifacts,
        result_ref="artifact_result",
    )


def test_parity_normalizer_ignores_engine_and_stable_id_order():
    manual = normalize_outcome(_state("manual", ["artifact_b", "artifact_a"]))
    graph = normalize_outcome(_state("langgraph", ["artifact_a", "artifact_b"]))

    assert parity_diff(manual, graph) == {}


def test_parity_diff_keeps_domain_status_difference():
    manual_state = _state("manual", ["artifact_a"])
    graph_state = _state("langgraph", ["artifact_a"]).model_copy(update={"status": "failed"})

    assert parity_diff(normalize_outcome(manual_state), normalize_outcome(graph_state))["status"] == {
        "manual": "completed",
        "langgraph": "failed",
    }
