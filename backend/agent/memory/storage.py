"""Shared transactional SQLite storage and Phase 5 memory migration."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


class MemoryStoreConflict(RuntimeError):
    pass


class MemoryItemNotFound(KeyError):
    pass


class SQLiteMemoryDatabase:
    schema_version = "5.0"

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS phase5_schema_migrations(
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS thread_memory_index(
                    memory_id TEXT PRIMARY KEY,
                    tenant_key TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    run_id TEXT,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    checkpoint_ref TEXT,
                    summary_ref TEXT,
                    pending_approval_ref TEXT,
                    last_event_sequence INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    namespace_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_key, project_key, thread_id)
                );
                CREATE INDEX IF NOT EXISTS idx_thread_memory_expiry
                    ON thread_memory_index(status, expires_at);
                CREATE TABLE IF NOT EXISTS memory_items(
                    memory_id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    tenant_key TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    connection_key TEXT NOT NULL,
                    database_key TEXT NOT NULL,
                    schema_key TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_by_run_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_namespace
                    ON memory_items(layer, tenant_key, project_key, connection_key, database_key, schema_key, status);
                CREATE TABLE IF NOT EXISTS memory_item_versions(
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    layer TEXT NOT NULL,
                    tenant_key TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    connection_key TEXT NOT NULL,
                    database_key TEXT NOT NULL,
                    schema_key TEXT NOT NULL,
                    snapshot_id TEXT,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    root_fact_ids_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    source_object_ids_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_by_run_id TEXT,
                    created_at TEXT NOT NULL,
                    superseded_by TEXT,
                    PRIMARY KEY(memory_id, version),
                    FOREIGN KEY(memory_id) REFERENCES memory_items(memory_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_version_lookup
                    ON memory_item_versions(tenant_key, project_key, connection_key, database_key, schema_key, snapshot_id, status);
                CREATE TABLE IF NOT EXISTS memory_context_packages(
                    package_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    snapshot_id TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_retrievals(
                    retrieval_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    memory_version INTEGER NOT NULL,
                    layer TEXT NOT NULL,
                    retrieval_method TEXT NOT NULL,
                    retrieval_score REAL NOT NULL,
                    selected INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_retrieval_run ON memory_retrievals(run_id, created_at);
                CREATE TABLE IF NOT EXISTS memory_verifications(
                    verification_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    memory_version INTEGER NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, memory_id, memory_version, snapshot_id)
                );
                CREATE TABLE IF NOT EXISTS memory_promotion_proposals(
                    proposal_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    source_version INTEGER NOT NULL,
                    lifecycle TEXT NOT NULL,
                    proposed_by_run_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS memory_feedback(
                    feedback_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    memory_version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    reason_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_forget_events(
                    forget_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    reason_hash TEXT NOT NULL,
                    prior_payload_hash TEXT NOT NULL,
                    retained_audit_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO phase5_schema_migrations(version) VALUES ('5.0');
                """
            )
