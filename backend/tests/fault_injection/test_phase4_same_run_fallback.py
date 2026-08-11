import pytest

from backend.engines.registry import EngineRegistry
from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import SQLiteRunRepository
from backend.services.recovery_run_service import RecoveryRunService
from backend.workflow.result_builder import WorkflowResultBuilder


class EmptyArtifactReader:
    def get_json(self, artifact_id):
        return None


class FailingGraph:
    async def run(self, state):
        raise ConnectionError("checkpoint connection unavailable")


class RecordingManual:
    def __init__(self):
        self.states = []

    async def run(self, state, *, resume=False):
        self.states.append(state)
        return state


@pytest.mark.asyncio
async def test_graph_infrastructure_failure_falls_back_without_new_run_or_session(tmp_path):
    runs = SQLiteRunRepository(tmp_path / "fallback-service.db")
    events = SQLiteEventLog(tmp_path / "fallback-service.db")
    manual = RecordingManual()

    def engine_factory(state):
        return (
            EngineRegistry({"langgraph": FailingGraph(), "manual": manual}),
            WorkflowResultBuilder(EmptyArtifactReader()),
        )

    service = RecoveryRunService(
        runs=runs,
        events=events,
        engine_factory=engine_factory,
        workflow_version="schema-recovery-v2",
        state_schema_version="2",
        configured_engine="auto_v2",
        auto_fallback=True,
        max_fallbacks=1,
    )
    created = service.create_run(project_id="project", connection_id="connection")

    result = await service.execute(created.run_id)

    assert result["run_id"] == created.run_id
    assert result["session_id"] == created.session_id
    assert result["active_engine"] == "manual"
    assert manual.states[0].run_id == created.run_id
    assert [item.type for item in events.replay(created.run_id) if item.type.startswith("run.fallback")] == [
        "run.fallback_started"
    ]
