from backend.agent.memory.schema_memory import SchemaMemory
from backend.catalog.snapshot_registry import SnapshotRegistry
from backend.core.identity import RunIdentity
from backend.core.legacy_ids import LegacyIdStore
from backend.core.run_store import RunStore
from backend.core.schema_identity import create_snapshot_ref, is_snapshot_stale
from backend.core.status import RunStatus, normalize_legacy_result, reduce_run_status
from backend.monitor.recorder import MonitorRecorder
from backend.schemas import EventSequencer


def test_run_identity_retry_preserves_business_identity():
    identity = RunIdentity.create(thread_id="thr_test")
    retry = identity.next_attempt()

    assert identity.run_id.startswith("run_")
    assert identity.trace_id.startswith("trc_")
    assert retry.run_id == identity.run_id
    assert retry.trace_id == identity.trace_id
    assert retry.attempt == 2


def test_legacy_id_mapping_is_explicit_and_stable(tmp_path):
    store = LegacyIdStore(str(tmp_path / "identity.db"))

    first = store.resolve("chat_legacy", entity_type="thread")
    second = store.resolve("chat_legacy", entity_type="thread")

    assert first.startswith("thr_")
    assert second == first


def test_required_error_is_never_reduced_to_partial():
    status = reduce_run_status(
        {"survey": "success", "column": "error", "merge": "success"},
        {"orm": "skipped"},
    )

    assert status == RunStatus.ERROR


def test_optional_error_reduces_success_to_partial():
    status = reduce_run_status(
        {"survey": "success", "column": "success", "merge": "success"},
        {"orm": "error"},
    )

    assert status == RunStatus.PARTIAL


def test_legacy_error_result_keeps_error_semantics():
    result = normalize_legacy_result({"status": "error", "error": "boom"})

    assert result.status == RunStatus.ERROR
    assert result.error is not None
    assert result.error.message == "boom"


def test_snapshot_hash_is_stable_for_reordered_catalog_and_detects_changes():
    first = create_snapshot_ref(
        database_fingerprint="db-test",
        schema_names=["main"],
        schema_metadata={"tables": [{"name": "b"}, {"name": "a"}]},
        capture_method="test",
        completeness="partial",
    )
    reordered = create_snapshot_ref(
        database_fingerprint="db-test",
        schema_names=["main"],
        schema_metadata={"tables": [{"name": "a"}, {"name": "b"}]},
        capture_method="test",
        completeness="partial",
    )
    changed = create_snapshot_ref(
        database_fingerprint="db-test",
        schema_names=["main"],
        schema_metadata={"tables": [{"name": "a"}, {"name": "c"}]},
        capture_method="test",
        completeness="partial",
    )

    assert first.snapshot_id == reordered.snapshot_id
    assert not is_snapshot_stale(first, reordered)
    assert is_snapshot_stale(first, changed)


def test_snapshot_registry_is_immutable(tmp_path):
    registry = SnapshotRegistry(str(tmp_path / "snapshots.db"))
    snapshot = create_snapshot_ref(
        database_fingerprint="db-test",
        schema_names=["main"],
        schema_metadata={"tables": [{"name": "products"}]},
        capture_method="test",
        completeness="partial",
    )

    registry.save(snapshot)
    registry.save(snapshot)

    assert registry.get(snapshot.snapshot_id) == snapshot


def test_event_sequence_and_run_store_are_run_scoped():
    identity = RunIdentity.create()
    sequencer = EventSequencer(identity)
    started = sequencer.next(
        legacy_type="started",
        event_type="run.started",
        status=RunStatus.RUNNING,
    )
    completed = sequencer.next(
        legacy_type="complete",
        event_type="run.completed",
        status=RunStatus.SUCCESS,
        data={"run_id": identity.run_id},
    )
    store = RunStore()
    store.start(identity)
    store.record_sequence(identity.run_id, completed["sequence"])
    store.complete(
        identity.run_id,
        {"run_id": identity.run_id, "status": "success", "run_status": "success"},
    )

    assert started["sequence"] == 1
    assert completed["sequence"] == 2
    assert started["run_id"] == completed["run_id"] == identity.run_id
    assert store.get(identity.run_id)["last_sequence"] == 2


def test_monitor_and_memory_persist_canonical_run_identity(tmp_path):
    identity = RunIdentity.create()
    monitor = MonitorRecorder(str(tmp_path / "monitor.db"))
    monitor.record_analysis(
        identity,
        {"survey_result": {"summary": {"total_tables": 3}}},
        [{"worker": "survey", "status": "error", "duration_ms": 1, "error": "boom"}],
        status=RunStatus.ERROR,
    )
    record = monitor.get_run(identity.run_id)

    memory = SchemaMemory(str(tmp_path / "memory.db"))
    memory.save_analysis_history(
        identity,
        "demo",
        3,
        1,
        1,
        "summary",
        database_fingerprint="db-test",
        snapshot_id="snp-test",
    )
    history = memory.get_history(limit=1)[0]

    assert record["status"] == "error"
    assert record["run_id"] == identity.run_id
    assert history["tables"] == 3
    assert history["relations"] == 1
    assert history["run_id"] == identity.run_id
