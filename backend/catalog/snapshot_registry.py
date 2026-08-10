"""Immutable SQLite registry for schema snapshot references."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from backend.config import Config
from backend.core.schema_identity import SchemaSnapshotRef, is_snapshot_stale


class SnapshotRegistry:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "schema_snapshots.db")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    component TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(component, version)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_snapshot_refs (
                    snapshot_id TEXT PRIMARY KEY,
                    database_fingerprint TEXT NOT NULL,
                    schema_names TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    capture_method TEXT NOT NULL,
                    completeness TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshot_database_time
                ON schema_snapshot_refs(database_fingerprint, captured_at DESC)
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(component, version)
                VALUES ('snapshot_registry', 1)
                """
            )

    def save(self, snapshot: SchemaSnapshotRef) -> SchemaSnapshotRef:
        payload = snapshot.model_dump(mode="json")
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT database_fingerprint, schema_hash, schema_names,
                       capture_method, completeness
                FROM schema_snapshot_refs WHERE snapshot_id = ?
                """,
                (snapshot.snapshot_id,),
            ).fetchone()
            if existing and (
                existing["database_fingerprint"] != snapshot.database_fingerprint
                or existing["schema_hash"] != snapshot.schema_hash
                or json.loads(existing["schema_names"]) != snapshot.schema_names
                or existing["capture_method"] != snapshot.capture_method
                or existing["completeness"] != snapshot.completeness.value
            ):
                raise ValueError(f"snapshot {snapshot.snapshot_id} is immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_snapshot_refs (
                    snapshot_id, database_fingerprint, schema_names, schema_hash,
                    captured_at, capture_method, completeness, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.database_fingerprint,
                    json.dumps(snapshot.schema_names, ensure_ascii=False),
                    snapshot.schema_hash,
                    snapshot.captured_at.isoformat(),
                    snapshot.capture_method,
                    snapshot.completeness.value,
                    payload_hash,
                ),
            )
        return snapshot

    def get(self, snapshot_id: str) -> SchemaSnapshotRef | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM schema_snapshot_refs WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def latest(self, database_fingerprint: str) -> SchemaSnapshotRef | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM schema_snapshot_refs
                WHERE database_fingerprint = ?
                ORDER BY captured_at DESC LIMIT 1
                """,
                (database_fingerprint,),
            ).fetchone()
        return self._from_row(row) if row else None

    def is_stale(self, snapshot_id: str, current_snapshot_id: str) -> bool:
        snapshot = self.get(snapshot_id)
        current = self.get(current_snapshot_id)
        if snapshot is None or current is None:
            return True
        return is_snapshot_stale(snapshot, current)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SchemaSnapshotRef:
        return SchemaSnapshotRef(
            snapshot_id=row["snapshot_id"],
            database_fingerprint=row["database_fingerprint"],
            schema_names=json.loads(row["schema_names"]),
            schema_hash=row["schema_hash"],
            captured_at=row["captured_at"],
            capture_method=row["capture_method"],
            completeness=row["completeness"],
        )
