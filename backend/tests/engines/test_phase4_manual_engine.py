import pytest

from backend.agent.runtime.hybrid_contracts import StageResult
from backend.core.identity import RunIdentity
from backend.core.status import RunStatus
from backend.engines.manual import ManualEngine
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import SQLiteRunRepository
from backend.workflow.contracts import RecoveryStateV2, StageCapabilities
from backend.workflow.definition import schema_recovery_v2
from backend.workflow.stage_registry import StageRegistry


class FakeStage:
    input_schema_version = "3.0"
    output_schema_version = "3.0"
    capabilities = StageCapabilities(retry_safe=True, parallel_safe=True, max_concurrency=8)

    def __init__(self, worker: str):
        self.worker = worker
        self.stage_id = f"recovery.{worker}"
        self.calls = 0

    async def execute(self, state, unit, context):
        self.calls += 1
        patch = {"output_refs": {f"{self.worker}_result": f"art_{self.worker}"}}
        if self.worker == "survey":
            patch.update({"snapshot_id": "snp_fake", "database_fingerprint": "database_fake"})
        return StageResult(
            stage_id=self.stage_id, status=RunStatus.SUCCESS, state_patch=patch,
            artifact_ids=[f"art_{self.worker}"], idempotency_record={"key": unit.idempotency_key},
        )


@pytest.mark.asyncio
async def test_manual_engine_runs_shared_stages_and_replay_does_not_repeat(tmp_path):
    runs = SQLiteRunRepository(tmp_path / "workflow.db")
    events = SQLiteEventLog(tmp_path / "workflow.db")
    registry = StageRegistry()
    stages = {}
    for worker in ("survey", "column", "name", "code", "orm", "merge"):
        stages[worker] = FakeStage(worker)
        registry.register(stages[worker])
    engine = ManualEngine(
        definition=schema_recovery_v2(), stages=registry, runs=runs, events=events,
        deterministic_scheduler=True,
    )
    identity = RunIdentity.create(thread_id="thr_engine")
    state = RecoveryStateV2(
        workflow_version="schema-recovery-v2", run_id=identity.run_id, trace_id=identity.trace_id,
        thread_id=identity.thread_id, session_id=identity.run_id, project_id="project",
        connection_id="connection", active_engine="manual",
    )
    runs.create(state)

    final = await engine.run(state)
    replay = await engine.run(final)

    assert final.status == "completed"
    assert replay == final
    assert stages["survey"].calls == 1
    assert stages["merge"].calls == 1
    assert [event.sequence for event in events.replay(state.run_id)] == sorted(
        event.sequence for event in events.replay(state.run_id)
    )
