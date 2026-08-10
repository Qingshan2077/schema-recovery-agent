"""L2 schema memory backed by SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from backend.config import Config
from backend.core.identity import RunIdentity, stable_id


class SchemaMemory:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "schema_memory.db")
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
                CREATE TABLE IF NOT EXISTS memory_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS discovered_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    fk_column TEXT NOT NULL,
                    pk_column TEXT NOT NULL DEFAULT '',
                    relation_type TEXT DEFAULT 'N:1',
                    confidence REAL DEFAULT 0.0,
                    top_evidence TEXT,
                    first_discovered TEXT DEFAULT (datetime('now')),
                    last_verified TEXT DEFAULT (datetime('now')),
                    discover_count INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    relation_id TEXT,
                    run_id TEXT,
                    database_fingerprint TEXT NOT NULL DEFAULT 'legacy',
                    snapshot_id TEXT NOT NULL DEFAULT 'legacy',
                    evidence_chain TEXT,
                    legacy_unverified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    database_name TEXT,
                    analysis_date TEXT DEFAULT (datetime('now')),
                    table_count INTEGER,
                    relation_count INTEGER,
                    high_confidence_count INTEGER,
                    summary TEXT,
                    run_id TEXT,
                    trace_id TEXT,
                    database_fingerprint TEXT,
                    snapshot_id TEXT,
                    legacy_unverified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._apply_v2_migration(connection)

    def _apply_v2_migration(self, connection: sqlite3.Connection) -> None:
        if connection.execute(
            "SELECT 1 FROM memory_schema_migrations WHERE version = 2"
        ).fetchone():
            return
        _ensure_columns(
            connection,
            "discovered_relations",
            {
                "relation_id": "TEXT",
                "run_id": "TEXT",
                "database_fingerprint": "TEXT NOT NULL DEFAULT 'legacy'",
                "snapshot_id": "TEXT NOT NULL DEFAULT 'legacy'",
                "evidence_chain": "TEXT",
                "legacy_unverified": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        _ensure_columns(
            connection,
            "analysis_history",
            {
                "run_id": "TEXT",
                "trace_id": "TEXT",
                "database_fingerprint": "TEXT",
                "snapshot_id": "TEXT",
                "legacy_unverified": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        connection.execute("DROP INDEX IF EXISTS idx_unique_relation")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_relation_v2
            ON discovered_relations(
                database_fingerprint, snapshot_id, source_table,
                target_table, fk_column, pk_column
            )
            """
        )
        connection.execute("DROP INDEX IF EXISTS idx_analysis_history_run")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_analysis_history_run
            ON analysis_history(run_id)
            """
        )
        connection.execute(
            """
            UPDATE discovered_relations
            SET legacy_unverified = 1
            WHERE run_id IS NULL
            """
        )
        connection.execute(
            """
            UPDATE analysis_history
            SET legacy_unverified = 1
            WHERE run_id IS NULL
            """
        )
        connection.execute("INSERT OR IGNORE INTO memory_schema_migrations(version) VALUES (2)")

    def save_relations(
        self,
        relations: list[dict[str, Any]],
        identity: RunIdentity,
        *,
        database_fingerprint: str,
        snapshot_id: str,
    ) -> None:
        with self._connect() as connection:
            for relation in relations:
                source_table = str(relation.get("source_table", "")).lower()
                target_table = str(relation.get("target_table", "")).lower()
                fk_column = str(relation.get("fk_column", "")).lower()
                pk_column = str(relation.get("pk_column", "")).lower()
                relation_id = stable_id(
                    "relation",
                    database_fingerprint,
                    snapshot_id,
                    source_table,
                    target_table,
                    fk_column,
                    pk_column,
                )
                evidence_chain = relation.get("evidence_chain") or []
                top_evidence = evidence_chain[0] if evidence_chain else {}
                connection.execute(
                    """
                    INSERT INTO discovered_relations (
                        source_table, target_table, fk_column, pk_column,
                        relation_type, confidence, top_evidence, relation_id,
                        run_id, database_fingerprint, snapshot_id,
                        evidence_chain, legacy_unverified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(
                        database_fingerprint, snapshot_id, source_table,
                        target_table, fk_column, pk_column
                    ) DO UPDATE SET
                        confidence = (
                            discovered_relations.confidence * discovered_relations.discover_count
                            + excluded.confidence
                        ) / (discovered_relations.discover_count + 1),
                        discover_count = discovered_relations.discover_count + 1,
                        last_verified = datetime('now'),
                        run_id = excluded.run_id,
                        relation_id = excluded.relation_id,
                        evidence_chain = excluded.evidence_chain,
                        top_evidence = CASE
                            WHEN excluded.confidence > discovered_relations.confidence
                            THEN excluded.top_evidence
                            ELSE discovered_relations.top_evidence
                        END,
                        legacy_unverified = 0
                    """,
                    (
                        source_table,
                        target_table,
                        fk_column,
                        pk_column,
                        relation.get("relation_type", "N:1"),
                        float(relation.get("fused_confidence", 0.0) or 0.0),
                        json.dumps(top_evidence, ensure_ascii=False),
                        relation_id,
                        identity.run_id,
                        database_fingerprint,
                        snapshot_id,
                        json.dumps(evidence_chain, ensure_ascii=False),
                    ),
                )

    def save_analysis_history(
        self,
        identity: RunIdentity,
        database: str,
        table_count: int,
        relation_count: int,
        high_count: int,
        summary: str,
        *,
        database_fingerprint: str,
        snapshot_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_history (
                    session_id, run_id, trace_id, database_name, table_count,
                    relation_count, high_confidence_count, summary,
                    database_fingerprint, snapshot_id, legacy_unverified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(run_id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    database_name = excluded.database_name,
                    table_count = excluded.table_count,
                    relation_count = excluded.relation_count,
                    high_confidence_count = excluded.high_confidence_count,
                    summary = excluded.summary,
                    database_fingerprint = excluded.database_fingerprint,
                    snapshot_id = excluded.snapshot_id,
                    legacy_unverified = 0
                """,
                (
                    identity.run_id,
                    identity.run_id,
                    identity.trace_id,
                    database,
                    table_count,
                    relation_count,
                    high_count,
                    summary,
                    database_fingerprint,
                    snapshot_id,
                ),
            )

    def query_similar_relations(
        self,
        source_table: str | None = None,
        target_table: str | None = None,
        *,
        database_fingerprint: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM discovered_relations WHERE is_active = 1"
        params: list[Any] = []
        if source_table:
            query += " AND source_table = ?"
            params.append(source_table.lower())
        if target_table:
            query += " AND target_table = ?"
            params.append(target_table.lower())
        if database_fingerprint:
            query += " AND database_fingerprint = ?"
            params.append(database_fingerprint)
        if snapshot_id:
            query += " AND snapshot_id = ?"
            params.append(snapshot_id)
        query += " ORDER BY confidence DESC LIMIT 20"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "relation_id": row["relation_id"],
                "run_id": row["run_id"],
                "database_fingerprint": row["database_fingerprint"],
                "snapshot_id": row["snapshot_id"],
                "source_table": row["source_table"],
                "target_table": row["target_table"],
                "fk_column": row["fk_column"],
                "pk_column": row["pk_column"],
                "relation_type": row["relation_type"],
                "confidence": row["confidence"],
                "top_evidence": json.loads(row["top_evidence"]) if row["top_evidence"] else {},
                "evidence_chain": json.loads(row["evidence_chain"]) if row["evidence_chain"] else [],
                "first_discovered": row["first_discovered"],
                "last_verified": row["last_verified"],
                "discover_count": row["discover_count"],
                "legacy_unverified": bool(row["legacy_unverified"]),
            }
            for row in rows
        ]

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_history ORDER BY analysis_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "trace_id": row["trace_id"],
                "database": row["database_name"],
                "database_fingerprint": row["database_fingerprint"],
                "snapshot_id": row["snapshot_id"],
                "date": row["analysis_date"],
                "tables": row["table_count"],
                "relations": row["relation_count"],
                "high_confidence": row["high_confidence_count"],
                "summary": row["summary"],
                "legacy_unverified": bool(row["legacy_unverified"]),
            }
            for row in rows
        ]


def _ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
