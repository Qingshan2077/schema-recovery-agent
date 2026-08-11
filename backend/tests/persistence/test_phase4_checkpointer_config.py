import pytest

from backend.persistence.checkpoints import (
    LangGraphPersistenceFactory,
    PersistenceBackendUnavailable,
    checkpoint_config,
)


def test_checkpoint_namespace_keeps_thread_run_project_and_versions_separate():
    config = checkpoint_config(
        run_id="run_1", thread_id="thr_1", project_id="project_a",
        workflow_version="schema-recovery-v2", recursion_limit=32, max_concurrency=4,
    )

    assert config["configurable"] == {
        "thread_id": "thr_1",
        "run_id": "run_1",
        "checkpoint_ns": "project_a/schema-recovery-v2",
    }


def test_split_checkpoint_and_store_backends_fail_closed(tmp_path):
    factory = LangGraphPersistenceFactory(
        checkpoint_backend="sqlite", store_backend="postgres",
        sqlite_path=str(tmp_path / "graph.db"), postgres_dsn="postgresql://unused",
    )

    with pytest.raises(PersistenceBackendUnavailable):
        factory.capabilities()
