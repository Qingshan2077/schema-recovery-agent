from datetime import datetime, timezone

import pytest

from backend.core.identity import RunIdentity
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import OptimisticLockError, SQLiteRunRepository
from backend.workflow.contracts import RecoveryStateV2, RunControl


def _state() -> RecoveryStateV2:
    identity = RunIdentity.create(thread_id="thr_persist")
    return RecoveryStateV2(
        workflow_version="schema-recovery-v2", run_id=identity.run_id, trace_id=identity.trace_id,
        thread_id=identity.thread_id, session_id=identity.run_id, project_id="project",
        connection_id="connection", active_engine="manual",
    )


def test_run_survives_repository_reconstruction_and_uses_optimistic_version(tmp_path):
    path = tmp_path / "runs.db"
    first = SQLiteRunRepository(path)
    state = first.create(_state())
    updated = state.model_copy(update={"status": "running", "version": 1})
    first.save(updated, expected_version=0)

    reconstructed = SQLiteRunRepository(path)
    assert reconstructed.get(state.run_id).status == "running"
    with pytest.raises(OptimisticLockError):
        reconstructed.save(updated.model_copy(update={"version": 2}), expected_version=0)


def test_event_sequence_is_persistent_and_replayable_after_sequence(tmp_path):
    state = _state()
    log = SQLiteEventLog(tmp_path / "events.db")
    first = log.append(state, "run.queued", status="queued", node_id="test")
    second = log.append(state, "run.started", status="running", node_id="test")

    replay = SQLiteEventLog(tmp_path / "events.db").replay(state.run_id, after_sequence=first.sequence)

    assert [item.sequence for item in replay] == [second.sequence]
    assert replay[0].type == "run.started"


def test_control_request_is_idempotent_and_hash_conflict_is_rejected(tmp_path):
    repository = SQLiteRunRepository(tmp_path / "controls.db")
    state = repository.create(_state())
    control = RunControl(
        run_id=state.run_id, control_type="cancel", request_id="request-1",
        payload_hash="a" * 64, payload={"reason": "user"}, created_at=datetime.now(timezone.utc),
    )

    assert repository.append_control(control).request_id == "request-1"
    assert repository.append_control(control).request_id == "request-1"
    with pytest.raises(OptimisticLockError):
        repository.append_control(control.model_copy(update={"payload_hash": "b" * 64}))


def test_portable_checkpoint_survives_repository_reconstruction(tmp_path):
    path = tmp_path / "checkpoint.db"
    repository = SQLiteRunRepository(path)
    state = repository.create(_state())
    repository.save_checkpoint(
        state,
        checkpoint_id="chk_phase4",
        metadata={"workflow_version": "schema-recovery-v2", "state_schema_version": "2"},
    )

    restored = SQLiteRunRepository(path).latest_checkpoint(state.run_id)

    assert restored is not None
    restored_state, metadata = restored
    assert restored_state == state
    assert metadata["state_schema_version"] == "2"


def test_artifact_store_is_immutable_for_a_stable_id(tmp_path):
    repository = SQLiteRunRepository(tmp_path / "artifact.db")
    repository.put_artifact("artifact_fixed", {"value": 1}, kind="test")
    repository.put_artifact("artifact_fixed", {"value": 1}, kind="test")

    with pytest.raises(OptimisticLockError):
        repository.put_artifact("artifact_fixed", {"value": 2}, kind="test")
