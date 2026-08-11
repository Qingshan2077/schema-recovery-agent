"""Append-only, namespace-isolated L2 relation memory."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from backend.agent.memory.contracts import MemoryNamespace, RelationMemoryVersion
from backend.agent.memory.policy import MemoryPolicy
from backend.agent.memory.storage import MemoryItemNotFound, MemoryStoreConflict, SQLiteMemoryDatabase
from backend.agent.memory.store_utils import json_text, lexical_tokens, namespace_columns, payload_hash


class L2MemoryStore:
    def __init__(self, database: SQLiteMemoryDatabase, *, policy: MemoryPolicy | None = None):
        self.database = database
        self.policy = policy or MemoryPolicy()

    def append(self, item: RelationMemoryVersion) -> RelationMemoryVersion:
        namespace = namespace_columns(item.namespace, layer="l2")
        payload = item.model_dump(mode="json")
        digest = payload_hash(payload)
        keywords = lexical_tokens(
            item.source_table_id, item.target_table_id, *item.source_columns,
            *item.target_columns, item.summary,
        )
        with self.database.transaction() as connection:
            existing_version = connection.execute(
                "SELECT payload_hash FROM memory_item_versions WHERE memory_id=? AND version=?",
                (item.memory_id, item.version),
            ).fetchone()
            if existing_version:
                if existing_version["payload_hash"] != digest:
                    raise MemoryStoreConflict("memory version is immutable")
                return item
            current = connection.execute(
                "SELECT current_version FROM memory_items WHERE memory_id=?",
                (item.memory_id,),
            ).fetchone()
            expected = 1 if current is None else int(current["current_version"]) + 1
            if item.version != expected:
                raise MemoryStoreConflict(f"relation memory version must be {expected}")
            if current is None:
                connection.execute(
                    "INSERT INTO memory_items VALUES (?, 'l2', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.memory_id, *namespace, item.version, item.status,
                        item.created_by_run_id, item.created_at.isoformat(),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE memory_items SET current_version=?, status=? WHERE memory_id=?",
                    (item.version, item.status, item.memory_id),
                )
            connection.execute(
                """INSERT INTO memory_item_versions VALUES(
                   ?, ?, 'l2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.memory_id, item.version, *namespace, item.namespace.snapshot_id,
                    item.status, item.summary, json_text(sorted(keywords)),
                    json_text(item.root_fact_ids), json_text(item.evidence_ids),
                    json_text(item.source_object_ids), json_text(payload), digest,
                    item.created_by_run_id, item.created_at.isoformat(), item.superseded_by,
                ),
            )
        return item

    def get(self, memory_id: str, *, version: int | None = None) -> RelationMemoryVersion:
        with self.database.connect() as connection:
            if version is None:
                row = connection.execute(
                    """SELECT v.payload_json FROM memory_item_versions v
                       JOIN memory_items i ON i.memory_id=v.memory_id AND i.current_version=v.version
                       WHERE v.memory_id=? AND v.layer='l2'""",
                    (memory_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload_json FROM memory_item_versions WHERE memory_id=? AND version=? AND layer='l2'",
                    (memory_id, version),
                ).fetchone()
        if row is None:
            raise MemoryItemNotFound(memory_id)
        return RelationMemoryVersion.model_validate_json(row["payload_json"])

    def query(
        self,
        namespace: MemoryNamespace,
        *,
        current_run_id: str,
        object_ids: Iterable[str] = (),
        query_text: str = "",
        include_stale: bool = False,
        limit: int = 100,
    ) -> list[tuple[RelationMemoryVersion, str, float]]:
        keys = namespace_columns(namespace, layer="l2")
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT v.payload_json, v.keywords_json FROM memory_item_versions v
                   JOIN memory_items i ON i.memory_id=v.memory_id AND i.current_version=v.version
                   WHERE v.layer='l2' AND v.tenant_key=? AND v.project_key=?
                     AND v.connection_key=? AND v.database_key=? AND v.schema_key=?
                     AND i.status!='forgotten'
                   ORDER BY v.created_at DESC LIMIT ?""",
                (*keys, limit * 4),
            ).fetchall()
        wanted_ids = {item.casefold() for item in object_ids}
        query_tokens = lexical_tokens(query_text, *object_ids)
        matches: list[tuple[RelationMemoryVersion, str, float]] = []
        for row in rows:
            item = RelationMemoryVersion.model_validate_json(row["payload_json"])
            if not self.policy.relation_is_retrievable(
                item, include_stale=include_stale, current_run_id=current_run_id,
            ):
                continue
            object_tokens = {
                item.source_table_id.casefold(), item.target_table_id.casefold(),
                *(column.casefold() for column in item.source_columns),
                *(column.casefold() for column in item.target_columns),
            }
            exact = bool(wanted_ids & object_tokens)
            stored_tokens = set(json.loads(row["keywords_json"]))
            overlap = len(query_tokens & stored_tokens) / max(1, len(query_tokens))
            if exact:
                matches.append((item, "exact", min(1.0, 0.85 + overlap * 0.15)))
            elif overlap > 0:
                matches.append((item, "lexical", min(0.84, 0.35 + overlap * 0.49)))
        return sorted(matches, key=lambda value: (-value[2], value[0].memory_id))[:limit]

    def mark_stale(
        self,
        namespace: MemoryNamespace,
        *,
        affected_object_ids: set[str],
        created_by_run_id: str,
    ) -> list[RelationMemoryVersion]:
        candidates = self.query(
            namespace, current_run_id=created_by_run_id,
            object_ids=affected_object_ids, include_stale=True, limit=10000,
        )
        now = datetime.now(timezone.utc)
        stale: list[RelationMemoryVersion] = []
        affected = {item.casefold() for item in affected_object_ids}
        for current, _, _ in candidates:
            object_ids = {
                current.source_table_id.casefold(), current.target_table_id.casefold(),
                *(item.casefold() for item in current.source_columns),
                *(item.casefold() for item in current.target_columns),
            }
            if not affected.intersection(object_ids) or current.status == "stale":
                continue
            updated = current.model_copy(update={
                "version": current.version + 1,
                "status": "stale",
                "created_by_run_id": created_by_run_id,
                "created_at": now,
                "summary": f"Stale after snapshot object change: {current.summary}",
            })
            stale.append(self.append(updated))
        return stale
