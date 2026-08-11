"""Persistent ordered workflow event log with after-sequence replay."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from backend.agent.runtime.contracts import RuntimeUsage
from backend.agent.runtime.redaction import RedactionPolicy
from backend.core.identity import new_id, stable_id
from backend.workflow.contracts import RecoveryStateV2, WorkflowEvent


class SQLiteEventLog:
    def __init__(self, db_path: str | Path, redaction: RedactionPolicy | None = None, trace_recorder: Any | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.redaction = redaction or RedactionPolicy()
        self.trace_recorder = trace_recorder
        self._migrate()

    def append(
        self,
        state: RecoveryStateV2,
        event_type: str,
        *,
        status: str,
        node_id: str,
        payload: dict[str, Any] | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        attempt: int = 1,
    ) -> WorkflowEvent:
        event_id = new_id("event")
        with self._transaction() as connection:
            row = connection.execute("SELECT COALESCE(MAX(sequence), 0) AS last FROM run_events WHERE run_id=?", (state.run_id,)).fetchone()
            sequence = int(row["last"]) + 1
            run_span_id = stable_id("span", state.run_id, "run")
            event_span_id = span_id or (
                run_span_id if node_id == "run_service"
                else stable_id("span", state.run_id, node_id, attempt)
            )
            event = WorkflowEvent(
                event_id=event_id, sequence=sequence, timestamp=datetime.now(timezone.utc),
                run_id=state.run_id, session_id=state.session_id, trace_id=state.trace_id,
                span_id=event_span_id,
                parent_span_id=parent_span_id or (None if event_span_id == run_span_id else run_span_id),
                agent_id=state.active_engine, node_id=node_id, attempt=attempt,
                type=event_type, status=status, payload=self.redaction.redact(payload or {}),
                usage=state.budget, redaction={"level": self.redaction.level},
            )
            connection.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.run_id, event.sequence, event.event_id, event.type, _json(event.payload),
                    event.session_id, event.trace_id, event.span_id, event.parent_span_id,
                    event.agent_id, event.node_id, event.attempt, event.status,
                    _json(event.usage.model_dump(mode="json")), event.timestamp.isoformat(),
                ),
            )
        if self.trace_recorder is not None:
            self.trace_recorder.record_event(event)
        return event

    def replay(self, run_id: str, *, after_sequence: int = 0, limit: int = 1000) -> list[WorkflowEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM run_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, after_sequence, limit),
            ).fetchall()
        return [_event(row) for row in rows]

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS run_events(
                    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL, payload_json TEXT NOT NULL, session_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL, span_id TEXT NOT NULL, parent_span_id TEXT,
                    agent_id TEXT NOT NULL, node_id TEXT NOT NULL, attempt INTEGER NOT NULL,
                    status TEXT NOT NULL, usage_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, sequence)
                );
            """)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _event(row: sqlite3.Row) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=row["event_id"], sequence=row["sequence"], timestamp=datetime.fromisoformat(row["created_at"]),
        run_id=row["run_id"], session_id=row["session_id"], trace_id=row["trace_id"],
        span_id=row["span_id"], parent_span_id=row["parent_span_id"], agent_id=row["agent_id"],
        node_id=row["node_id"], attempt=row["attempt"], type=row["type"], status=row["status"],
        payload=json.loads(row["payload_json"]), usage=RuntimeUsage.model_validate_json(row["usage_json"]),
        redaction={"level": "persisted"},
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
