"""Persistent L1 thread/checkpoint index with optimistic version and TTL."""

from __future__ import annotations

from datetime import timedelta
import json

from backend.agent.memory.contracts import MemoryNamespace, ThreadMemoryRecord
from backend.agent.memory.policy import Clock, SystemClock
from backend.agent.memory.storage import MemoryStoreConflict, SQLiteMemoryDatabase
from backend.agent.memory.store_utils import json_text, payload_hash


class L1MemoryStore:
    def __init__(self, database: SQLiteMemoryDatabase, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    def get(self, namespace: MemoryNamespace) -> ThreadMemoryRecord | None:
        namespace.require_l1()
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT payload_json FROM thread_memory_index
                   WHERE tenant_key=? AND project_key=? AND thread_id=?""",
                (
                    namespace.canonical_tenant_id,
                    namespace.canonical_project_id,
                    namespace.thread_id,
                ),
            ).fetchone()
        return ThreadMemoryRecord.model_validate_json(row["payload_json"]) if row else None

    def upsert(self, record: ThreadMemoryRecord, *, expected_version: int | None) -> ThreadMemoryRecord:
        record.namespace.require_l1()
        payload = record.model_dump(mode="json")
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT version, payload_hash FROM thread_memory_index WHERE memory_id=?",
                (record.memory_id,),
            ).fetchone()
            if existing is None:
                if expected_version not in {None, 0} or record.version != 1:
                    raise MemoryStoreConflict("L1 create requires version 1 and expected_version 0")
                connection.execute(
                    """INSERT INTO thread_memory_index VALUES(
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.memory_id,
                        record.namespace.canonical_tenant_id,
                        record.namespace.canonical_project_id,
                        record.namespace.thread_id,
                        record.namespace.run_id,
                        record.version,
                        record.status,
                        record.checkpoint_ref,
                        record.summary_ref,
                        record.pending_approval_ref,
                        record.last_event_sequence,
                        record.expires_at.isoformat(),
                        json_text(record.namespace.model_dump(mode="json")),
                        json_text(payload),
                        payload_hash(payload),
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                    ),
                )
                return record
            if expected_version != int(existing["version"]):
                raise MemoryStoreConflict("L1 expected_version does not match persisted version")
            if record.version != int(existing["version"]) + 1:
                raise MemoryStoreConflict("L1 updates must increment version exactly once")
            cursor = connection.execute(
                """UPDATE thread_memory_index SET run_id=?, version=?, status=?, checkpoint_ref=?,
                   summary_ref=?, pending_approval_ref=?, last_event_sequence=?, expires_at=?,
                   namespace_json=?, payload_json=?, payload_hash=?, updated_at=?
                   WHERE memory_id=? AND version=?""",
                (
                    record.namespace.run_id,
                    record.version,
                    record.status,
                    record.checkpoint_ref,
                    record.summary_ref,
                    record.pending_approval_ref,
                    record.last_event_sequence,
                    record.expires_at.isoformat(),
                    json_text(record.namespace.model_dump(mode="json")),
                    json_text(payload),
                    payload_hash(payload),
                    record.updated_at.isoformat(),
                    record.memory_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise MemoryStoreConflict("L1 record changed concurrently")
        return record

    def expire_due(self, *, completed_ttl_days: int) -> list[str]:
        now = self.clock.now()
        expired: list[str] = []
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM thread_memory_index WHERE status!='expired' AND expires_at<=?",
                (now.isoformat(),),
            ).fetchall()
        for row in rows:
            current = ThreadMemoryRecord.model_validate_json(row["payload_json"])
            if current.pending_approval_ref:
                continue
            updated = current.model_copy(update={
                "version": current.version + 1,
                "status": "expired",
                "artifact_ids": [],
                "message_event_ids": [],
                "temporary_relation_ids": [],
                "expires_at": now + timedelta(days=completed_ttl_days),
                "updated_at": now,
            })
            self.upsert(updated, expected_version=current.version)
            expired.append(current.memory_id)
        return expired
