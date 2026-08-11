from datetime import datetime, timedelta, timezone

from backend.agent.memory.contracts import MemoryNamespace, RelationMemoryVersion
from backend.agent.memory.l2_store import L2MemoryStore
from backend.agent.memory.storage import SQLiteMemoryDatabase


def namespace(*, project: str = "project", run: str = "run_current") -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id="tenant", project_id=project, connection_id="connection",
        database_name="database", schema_name="public", snapshot_id="snp_current",
        thread_id="thr_current", run_id=run,
    )


def relation(ns: MemoryNamespace, *, run_id: str = "run_prior") -> RelationMemoryVersion:
    now = datetime.now(timezone.utc)
    return RelationMemoryVersion(
        memory_id="mem_relation", relation_id="rel_relation", version=1,
        namespace=ns, source_table_id="orders", source_columns=["user_id"],
        target_table_id="users", target_columns=["id"], cardinality="N:1",
        status="accepted", evidence_ids=["evd_catalog"], calibrated_probability=.91,
        calibration_version="cal-v1", first_seen_snapshot_id="snp_current",
        last_verified_snapshot_id="snp_current", created_by_run_id=run_id,
        root_fact_ids=["fact_catalog"], source_object_ids=["orders.user_id", "users.id"],
        summary="orders.user_id references users.id", created_at=now,
    )


def test_l2_namespace_isolation_and_same_run_exclusion(tmp_path):
    store = L2MemoryStore(SQLiteMemoryDatabase(tmp_path / "memory.db"))
    store.append(relation(namespace()))
    assert store.query(namespace(), current_run_id="run_current", query_text="orders")
    assert store.query(namespace(project="other"), current_run_id="run_current", query_text="orders") == []
    assert store.query(namespace(), current_run_id="run_prior", query_text="orders") == []
