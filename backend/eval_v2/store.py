"""Transactional eval run index; detailed immutable payloads stay in artifact storage."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from backend.eval_v2.contracts import BaselinePromotion, EvalRunManifest, EvalRunRecord, GateDecision
from backend.eval_v2.hashing import canonical_json, content_hash


class EvalStoreConflict(RuntimeError):
    pass


class EvalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def create(self, manifest: EvalRunManifest, record: EvalRunRecord) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO eval_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.eval_run_id, record.manifest_hash, record.status, record.sequence,
                    record.total_cases, record.completed_cases, record.failed_cases,
                    int(record.trace_complete), int(record.qualitative_complete),
                    canonical_json(record.model_dump(mode="json")),
                ),
            )
            connection.execute(
                "INSERT INTO eval_manifests VALUES (?, ?, ?)",
                (manifest.eval_run_id, record.manifest_hash, canonical_json(manifest.model_dump(mode="json"))),
            )

    def get(self, eval_run_id: str) -> EvalRunRecord:
        with self.connect() as connection:
            row = connection.execute("SELECT payload_json FROM eval_runs WHERE eval_run_id=?", (eval_run_id,)).fetchone()
        if row is None:
            raise KeyError(eval_run_id)
        return EvalRunRecord.model_validate_json(row["payload_json"])

    def manifest(self, eval_run_id: str) -> EvalRunManifest:
        with self.connect() as connection:
            row = connection.execute("SELECT payload_json FROM eval_manifests WHERE eval_run_id=?", (eval_run_id,)).fetchone()
        if row is None:
            raise KeyError(eval_run_id)
        return EvalRunManifest.model_validate_json(row["payload_json"])

    def save(self, record: EvalRunRecord, *, expected_sequence: int) -> EvalRunRecord:
        if record.sequence != expected_sequence + 1:
            raise EvalStoreConflict("eval sequence must increment exactly once")
        payload = canonical_json(record.model_dump(mode="json"))
        with self.transaction() as connection:
            cursor = connection.execute(
                """UPDATE eval_runs SET status=?, sequence=?, completed_cases=?, failed_cases=?,
                   trace_complete=?, qualitative_complete=?, payload_json=?
                   WHERE eval_run_id=? AND sequence=?""",
                (
                    record.status, record.sequence, record.completed_cases, record.failed_cases,
                    int(record.trace_complete), int(record.qualitative_complete), payload,
                    record.eval_run_id, expected_sequence,
                ),
            )
            if cursor.rowcount != 1:
                raise EvalStoreConflict("eval run changed concurrently")
        return record

    def append_event(self, eval_run_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with self.transaction() as connection:
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence), 0)+1 AS value FROM eval_events WHERE eval_run_id=?",
                (eval_run_id,),
            ).fetchone()["value"])
            connection.execute(
                "INSERT INTO eval_events VALUES (?, ?, ?, ?, datetime('now'))",
                (eval_run_id, sequence, event_type, canonical_json(payload)),
            )
        return sequence

    def events(self, eval_run_id: str, *, after: int, limit: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT sequence, event_type, payload_json, created_at FROM eval_events
                   WHERE eval_run_id=? AND sequence>? ORDER BY sequence LIMIT ?""",
                (eval_run_id, after, limit),
            ).fetchall()
        return [{"sequence": row["sequence"], "type": row["event_type"], "timestamp": row["created_at"], **json.loads(row["payload_json"])} for row in rows]

    def put_gate(self, decision: GateDecision) -> None:
        payload = decision.model_dump(mode="json")
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO eval_gate_decisions VALUES (?, ?, ?, ?, ?)",
                (decision.gate_id, decision.eval_run_id, decision.status, content_hash(payload), canonical_json(payload)),
            )

    def promote(self, promotion: BaselinePromotion) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE eval_baselines SET active=0 WHERE gate=?", (promotion.gate,))
            connection.execute(
                "INSERT INTO eval_baselines VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 1)",
                (promotion.promotion_id, promotion.gate, promotion.eval_run_id, promotion.actor_id, promotion.actor_role, promotion.reason),
            )

    def current_baseline(self, gate: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM eval_baselines WHERE gate=? AND active=1", (gate,)).fetchone()
        return dict(row) if row else None

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
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS eval_runs(eval_run_id TEXT PRIMARY KEY, manifest_hash TEXT NOT NULL,
              status TEXT NOT NULL, sequence INTEGER NOT NULL, total_cases INTEGER NOT NULL,
              completed_cases INTEGER NOT NULL, failed_cases INTEGER NOT NULL, trace_complete INTEGER NOT NULL,
              qualitative_complete INTEGER NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS eval_manifests(eval_run_id TEXT PRIMARY KEY, manifest_hash TEXT NOT NULL,
              payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS eval_events(eval_run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(eval_run_id, sequence));
            CREATE TABLE IF NOT EXISTS eval_gate_decisions(gate_id TEXT PRIMARY KEY, eval_run_id TEXT NOT NULL,
              status TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS eval_baselines(promotion_id TEXT PRIMARY KEY, gate TEXT NOT NULL,
              eval_run_id TEXT NOT NULL, actor_id TEXT NOT NULL, actor_role TEXT NOT NULL,
              reason TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_baseline ON eval_baselines(gate) WHERE active=1;
            """)
