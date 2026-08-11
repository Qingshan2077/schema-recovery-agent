from backend.core.identity import RunIdentity
from backend.engines.fallback import FallbackCoordinator
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import SQLiteRunRepository
from backend.workflow.contracts import RecoveryStateV2


def test_fallback_preserves_run_thread_snapshot_and_budget(tmp_path):
    runs = SQLiteRunRepository(tmp_path / "fallback.db")
    events = SQLiteEventLog(tmp_path / "fallback.db")
    identity = RunIdentity.create(thread_id="thr_fallback")
    state = RecoveryStateV2(
        workflow_version="schema-recovery-v2", run_id=identity.run_id, trace_id=identity.trace_id,
        thread_id=identity.thread_id, session_id=identity.run_id, project_id="project",
        connection_id="connection", snapshot_id="snp_fixed", database_fingerprint="database_fixed",
        active_engine="langgraph", status="running",
    )
    runs.create(state)

    takeover = FallbackCoordinator(runs, events, max_fallbacks=1).takeover(
        state, reason="checkpoint backend unavailable", in_flight_known_safe=True,
    )

    assert takeover.run_id == state.run_id
    assert takeover.thread_id == state.thread_id
    assert takeover.snapshot_id == state.snapshot_id
    assert takeover.budget == state.budget
    assert takeover.active_engine == "manual"
