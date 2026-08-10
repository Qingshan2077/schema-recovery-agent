"""Monitor recorder for analysis runs."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from backend.config import Config
from backend.core.identity import RunIdentity
from backend.core.status import RunStatus, coerce_run_status


class MonitorRecorder:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "monitor.db")
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
                CREATE TABLE IF NOT EXISTS monitor_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    total_duration_ms INTEGER,
                    total_tool_calls INTEGER,
                    table_count INTEGER,
                    high_confidence_count INTEGER,
                    medium_confidence_count INTEGER,
                    low_confidence_count INTEGER,
                    evidence_contributions TEXT,
                    total_steps INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    run_id TEXT,
                    trace_id TEXT,
                    thread_id TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    database_fingerprint TEXT,
                    snapshot_id TEXT,
                    legacy_unverified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    tool_call_count INTEGER,
                    error TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    run_id TEXT,
                    trace_id TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._apply_v2_migration(connection)

    def _apply_v2_migration(self, connection: sqlite3.Connection) -> None:
        if connection.execute(
            "SELECT 1 FROM monitor_schema_migrations WHERE version = 2"
        ).fetchone():
            return
        analysis_columns = {
            "run_id": "TEXT",
            "trace_id": "TEXT",
            "thread_id": "TEXT",
            "attempt": "INTEGER NOT NULL DEFAULT 1",
            "database_fingerprint": "TEXT",
            "snapshot_id": "TEXT",
            "legacy_unverified": "INTEGER NOT NULL DEFAULT 0",
        }
        worker_columns = {
            "run_id": "TEXT",
            "trace_id": "TEXT",
            "attempt": "INTEGER NOT NULL DEFAULT 1",
        }
        _ensure_columns(connection, "analysis_records", analysis_columns)
        _ensure_columns(connection, "worker_records", worker_columns)
        connection.execute(
            """
            UPDATE analysis_records
            SET legacy_unverified = 1
            WHERE run_id IS NULL
            """
        )
        connection.execute("DROP INDEX IF EXISTS idx_analysis_run_id")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_analysis_run_id
            ON analysis_records(run_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_worker_run_id
            ON worker_records(run_id, worker_id, attempt)
            """
        )
        connection.execute("INSERT OR IGNORE INTO monitor_schema_migrations(version) VALUES (2)")

    def record_analysis(
        self,
        identity: RunIdentity,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
        *,
        status: RunStatus | str,
    ) -> None:
        canonical = coerce_run_status(status)
        merge_result = context.get("merge_result") or {}
        summary = merge_result.get("summary") or {}
        survey_summary = (context.get("survey_result") or {}).get("summary") or {}
        total_duration = sum(int(step.get("duration_ms", 0) or 0) for step in steps if step.get("worker") != "router")
        total_tool_calls = sum(len(step.get("tool_calls") or []) for step in steps)
        contributions = merge_result.get("source_contributions") or {}

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_records (
                    session_id, run_id, trace_id, thread_id, attempt, status,
                    total_duration_ms, total_tool_calls, table_count,
                    high_confidence_count, medium_confidence_count, low_confidence_count,
                    evidence_contributions, total_steps, database_fingerprint,
                    snapshot_id, legacy_unverified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(session_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    trace_id = excluded.trace_id,
                    thread_id = excluded.thread_id,
                    attempt = excluded.attempt,
                    status = excluded.status,
                    total_duration_ms = excluded.total_duration_ms,
                    total_tool_calls = excluded.total_tool_calls,
                    table_count = excluded.table_count,
                    high_confidence_count = excluded.high_confidence_count,
                    medium_confidence_count = excluded.medium_confidence_count,
                    low_confidence_count = excluded.low_confidence_count,
                    evidence_contributions = excluded.evidence_contributions,
                    total_steps = excluded.total_steps,
                    database_fingerprint = excluded.database_fingerprint,
                    snapshot_id = excluded.snapshot_id,
                    legacy_unverified = 0
                """,
                (
                    identity.run_id,
                    identity.run_id,
                    identity.trace_id,
                    identity.thread_id,
                    identity.attempt,
                    canonical.value,
                    total_duration,
                    total_tool_calls,
                    int(survey_summary.get("total_tables", 0) or 0),
                    int(summary.get("high_confidence", 0) or 0),
                    int(summary.get("medium_confidence", 0) or 0),
                    int(summary.get("low_confidence", 0) or 0),
                    json.dumps(contributions, ensure_ascii=False),
                    len(steps),
                    context.get("database_fingerprint"),
                    context.get("snapshot_id"),
                ),
            )
            connection.execute("DELETE FROM worker_records WHERE run_id = ?", (identity.run_id,))
            for step in steps:
                if step.get("worker") == "router":
                    continue
                connection.execute(
                    """
                    INSERT INTO worker_records (
                        session_id, run_id, trace_id, attempt, worker_id, status,
                        duration_ms, tool_call_count, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity.run_id,
                        identity.run_id,
                        identity.trace_id,
                        identity.attempt,
                        step.get("worker", "unknown"),
                        step.get("status", "unknown"),
                        int(step.get("duration_ms", 0) or 0),
                        len(step.get("tool_calls") or []),
                        step.get("error"),
                    ),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_records WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM analysis_records WHERE legacy_unverified = 0"
            ).fetchone()[0]
            legacy_total = connection.execute(
                "SELECT COUNT(*) FROM analysis_records WHERE legacy_unverified = 1"
            ).fetchone()[0]
            if total == 0:
                return {
                    "total_analyses": 0,
                    "legacy_unverified_analyses": legacy_total,
                    "message": "No verified analysis records yet",
                }
            avg_duration = connection.execute(
                "SELECT AVG(total_duration_ms) FROM analysis_records WHERE legacy_unverified = 0"
            ).fetchone()[0] or 0
            avg_tables = connection.execute(
                "SELECT AVG(table_count) FROM analysis_records WHERE legacy_unverified = 0"
            ).fetchone()[0] or 0
            worker_avg = connection.execute(
                """
                SELECT worker_id,
                       COUNT(*) AS runs,
                       ROUND(AVG(duration_ms)) AS avg_duration,
                       ROUND(100.0 * SUM(
                           CASE WHEN status IN ('success', 'skipped') THEN 1 ELSE 0 END
                       ) / COUNT(*), 1) AS success_rate
                FROM worker_records
                WHERE run_id IS NOT NULL
                GROUP BY worker_id
                """
            ).fetchall()
            recent = connection.execute(
                """
                SELECT run_id, session_id, status, total_duration_ms,
                       high_confidence_count, created_at, trace_id, snapshot_id,
                       legacy_unverified
                FROM analysis_records
                ORDER BY created_at DESC LIMIT 5
                """
            ).fetchall()
        return {
            "total_analyses": total,
            "legacy_unverified_analyses": legacy_total,
            "avg_duration_ms": round(avg_duration, 0),
            "avg_tables_per_analysis": round(avg_tables, 1),
            "worker_stats": [
                {
                    "worker_id": row["worker_id"],
                    "runs": row["runs"],
                    "avg_duration_ms": row["avg_duration"],
                    "success_rate": row["success_rate"],
                }
                for row in worker_avg
            ],
            "recent_analyses": [
                {
                    "run_id": row["run_id"],
                    "session_id": row["session_id"],
                    "trace_id": row["trace_id"],
                    "snapshot_id": row["snapshot_id"],
                    "status": row["status"],
                    "duration_ms": row["total_duration_ms"],
                    "high_confidence": row["high_confidence_count"],
                    "date": row["created_at"],
                    "legacy_unverified": bool(row["legacy_unverified"]),
                }
                for row in recent
            ],
        }


def _ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
