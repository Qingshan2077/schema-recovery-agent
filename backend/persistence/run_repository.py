"""Transactional SQLite run repository and portable checkpoint store."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from backend.workflow.contracts import RecoveryStateV2, RunControl, StageExecutionRecord


class RunNotFoundError(KeyError):
    pass


class OptimisticLockError(RuntimeError):
    pass


class SQLiteRunRepository:
    schema_version = "4.0"

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def create(self, state: RecoveryStateV2) -> RecoveryStateV2:
        now = _now()
        payload = _json(state.model_dump(mode="json"))
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO recovery_runs(
                    run_id, thread_id, workflow_version, state_schema_version, project_id,
                    connection_id, snapshot_id, active_engine, status, phase, budget_json,
                    result_ref, state_json, created_at, updated_at, terminal_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
                (
                    state.run_id, state.thread_id, state.workflow_version, state.state_schema_version,
                    state.project_id, state.connection_id, state.snapshot_id, state.active_engine,
                    state.status, state.phase, _json(state.budget.model_dump(mode="json")), state.result_ref,
                    payload, now, now, state.version,
                ),
            )
        return state

    def get(self, run_id: str) -> RecoveryStateV2:
        with self._connect() as connection:
            row = connection.execute("SELECT state_json FROM recovery_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return RecoveryStateV2.model_validate_json(row["state_json"])

    def save(self, state: RecoveryStateV2, *, expected_version: int) -> RecoveryStateV2:
        terminal = _now() if state.status in {"partial", "degraded", "blocked", "failed", "canceled", "completed", "expired"} else None
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE recovery_runs SET snapshot_id=?, active_engine=?, status=?, phase=?, budget_json=?,
                    result_ref=?, state_json=?, updated_at=?, terminal_at=COALESCE(terminal_at, ?), version=?
                    WHERE run_id=? AND version=?""",
                (
                    state.snapshot_id, state.active_engine, state.status, state.phase,
                    _json(state.budget.model_dump(mode="json")), state.result_ref,
                    _json(state.model_dump(mode="json")), _now(), terminal, state.version,
                    state.run_id, expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise OptimisticLockError(f"run {state.run_id} version changed")
        return state

    def reserve_execution(self, record: StageExecutionRecord) -> StageExecutionRecord | None:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM stage_executions WHERE run_id=? AND idempotency_key=?",
                (record.run_id, record.idempotency_key),
            ).fetchone()
            if existing:
                return _execution(existing)
            connection.execute(
                """INSERT INTO stage_executions(
                    run_id, stage_key, stage_id, work_unit_id, attempt, idempotency_key,
                    status, input_hash, output_ref, error_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.run_id, record.stage_key, record.stage_id, record.work_unit_id,
                    record.attempt, record.idempotency_key, record.status, record.input_hash,
                    record.output_ref, _json(record.error.model_dump(mode="json")) if record.error else None,
                    record.started_at.isoformat(), record.completed_at.isoformat() if record.completed_at else None,
                ),
            )
        return None

    def complete_execution(self, record: StageExecutionRecord) -> None:
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE stage_executions SET status=?, output_ref=?, error_json=?, completed_at=?, attempt=?
                    WHERE run_id=? AND idempotency_key=?""",
                (
                    record.status, record.output_ref,
                    _json(record.error.model_dump(mode="json")) if record.error else None,
                    record.completed_at.isoformat() if record.completed_at else _now(), record.attempt,
                    record.run_id, record.idempotency_key,
                ),
            )
            if cursor.rowcount != 1:
                raise OptimisticLockError("stage execution reservation disappeared")

    def save_checkpoint(self, state: RecoveryStateV2, *, checkpoint_id: str, metadata: dict[str, Any]) -> str:
        payload = state.model_dump(mode="json")
        state_hash = _hash(payload)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT state_hash, metadata_json FROM portable_checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
            ).fetchone()
            if existing and (
                existing["state_hash"] != state_hash or existing["metadata_json"] != _json(metadata)
            ):
                raise OptimisticLockError("checkpoint id reused with different portable state")
            connection.execute(
                """INSERT OR IGNORE INTO portable_checkpoints(
                    checkpoint_id, run_id, thread_id, workflow_version, state_schema_version,
                    phase, state_json, metadata_json, state_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint_id, state.run_id, state.thread_id, state.workflow_version,
                    state.state_schema_version, state.phase, _json(payload), _json(metadata),
                    state_hash, _now(),
                ),
            )
        return checkpoint_id

    def latest_checkpoint(self, run_id: str) -> tuple[RecoveryStateV2, dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, metadata_json FROM portable_checkpoints WHERE run_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RecoveryStateV2.model_validate_json(row["state_json"]), json.loads(row["metadata_json"])

    def has_inflight_execution(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM stage_executions WHERE run_id=? AND status='running' LIMIT 1", (run_id,)
            ).fetchone()
        return row is not None

    def put_artifact(self, artifact_id: str, content: dict[str, Any], *, kind: str, content_hash: str | None = None) -> str:
        payload_hash = content_hash or _hash(content)
        with self._transaction() as connection:
            existing = connection.execute("SELECT content_hash FROM workflow_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if existing and existing["content_hash"] != payload_hash:
                raise OptimisticLockError("artifact id reused with different content")
            connection.execute(
                "INSERT OR IGNORE INTO workflow_artifacts VALUES (?, ?, ?, ?, ?)",
                (artifact_id, kind, payload_hash, _json(content), _now()),
            )
        return artifact_id

    def get_json(self, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT content_json FROM workflow_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        return json.loads(row["content_json"]) if row else None

    def append_control(self, control: RunControl) -> RunControl:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM run_controls WHERE run_id=? AND request_id=?", (control.run_id, control.request_id)
            ).fetchone()
            if existing:
                if existing["payload_hash"] != control.payload_hash or existing["control_type"] != control.control_type:
                    raise OptimisticLockError("control request id reused with different payload")
                return _control(existing)
            connection.execute(
                "INSERT INTO run_controls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    control.run_id, control.control_type, control.request_id, control.payload_hash,
                    control.status, control.actor_id, control.actor_role, _json(control.payload),
                    control.created_at.isoformat(), control.resolved_at.isoformat() if control.resolved_at else None,
                ),
            )
        return control

    def get_control(self, run_id: str, request_id: str) -> RunControl | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM run_controls WHERE run_id=? AND request_id=?",
                (run_id, request_id),
            ).fetchone()
        return _control(row) if row else None

    def resolve_control(self, run_id: str, request_id: str, *, status: str) -> RunControl:
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE run_controls SET status=?, resolved_at=? WHERE run_id=? AND request_id=? AND status='pending'",
                (status, _now(), run_id, request_id),
            )
            row = connection.execute("SELECT * FROM run_controls WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
            if row is None:
                raise RunNotFoundError(request_id)
            if cursor.rowcount == 0 and row["status"] != status:
                raise OptimisticLockError("control was resolved concurrently")
        return _control(row)

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS workflow_schema_migrations(
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS recovery_runs(
                    run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, workflow_version TEXT NOT NULL,
                    state_schema_version TEXT NOT NULL, project_id TEXT NOT NULL, connection_id TEXT NOT NULL,
                    snapshot_id TEXT, active_engine TEXT NOT NULL, status TEXT NOT NULL, phase TEXT NOT NULL,
                    budget_json TEXT NOT NULL, result_ref TEXT, state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, terminal_at TEXT, version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stage_executions(
                    run_id TEXT NOT NULL, stage_key TEXT NOT NULL, stage_id TEXT NOT NULL,
                    work_unit_id TEXT NOT NULL, attempt INTEGER NOT NULL, idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL, input_hash TEXT NOT NULL, output_ref TEXT, error_json TEXT,
                    started_at TEXT NOT NULL, completed_at TEXT, UNIQUE(run_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS portable_checkpoints(
                    checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    workflow_version TEXT NOT NULL, state_schema_version TEXT NOT NULL, phase TEXT NOT NULL,
                    state_json TEXT NOT NULL, metadata_json TEXT NOT NULL, state_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_checkpoint_run ON portable_checkpoints(run_id, created_at);
                CREATE TABLE IF NOT EXISTS workflow_artifacts(
                    artifact_id TEXT PRIMARY KEY, kind TEXT NOT NULL, content_hash TEXT NOT NULL,
                    content_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_controls(
                    run_id TEXT NOT NULL, control_type TEXT NOT NULL, request_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, status TEXT NOT NULL, actor_id TEXT, actor_role TEXT,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT,
                    PRIMARY KEY(run_id, request_id)
                );
                INSERT OR IGNORE INTO workflow_schema_migrations(version) VALUES ('4.0');
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
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _execution(row: sqlite3.Row) -> StageExecutionRecord:
    return StageExecutionRecord(
        run_id=row["run_id"], stage_key=row["stage_key"], stage_id=row["stage_id"],
        work_unit_id=row["work_unit_id"], attempt=row["attempt"], idempotency_key=row["idempotency_key"],
        status=row["status"], input_hash=row["input_hash"], output_ref=row["output_ref"],
        error=json.loads(row["error_json"]) if row["error_json"] else None,
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def _control(row: sqlite3.Row) -> RunControl:
    return RunControl(
        run_id=row["run_id"], control_type=row["control_type"], request_id=row["request_id"],
        payload_hash=row["payload_hash"], status=row["status"], actor_id=row["actor_id"],
        actor_role=row["actor_role"], payload=json.loads(row["payload_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
