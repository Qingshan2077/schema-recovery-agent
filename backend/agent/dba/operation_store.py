"""Immutable operation versions, CAS state, idempotent decisions/executions and audit."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from backend.agent.dba.contracts import ApprovalDecision, ApprovalOperation, ExecutionAttempt, VerificationResult


class OperationConflict(RuntimeError): pass


class OperationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._migrate()

    def create(self, operation: ApprovalOperation) -> ApprovalOperation:
        payload = _json(operation.model_dump(mode="json"))
        with self.transaction() as db:
            db.execute("INSERT INTO dba_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (operation.operation_id, operation.tenant_id, operation.project_id, operation.version, operation.status, operation.risk_level, operation.environment, operation.expires_at.isoformat(), operation.created_at.isoformat(), payload))
            db.execute("INSERT INTO dba_operation_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (operation.operation_id, operation.version, operation.normalized_sql_hash, operation.status, payload, operation.created_at.isoformat(), None))
            self._audit(db, operation, "dba.operation.created", {"status": operation.status})
        return operation

    def get(self, operation_id: str, *, version: int | None = None) -> ApprovalOperation:
        with self.connect() as db:
            if version is None: row = db.execute("SELECT payload_json FROM dba_operations WHERE operation_id=?", (operation_id,)).fetchone()
            else: row = db.execute("SELECT payload_json FROM dba_operation_versions WHERE operation_id=? AND version=?", (operation_id, version)).fetchone()
        if row is None: raise KeyError(operation_id)
        return ApprovalOperation.model_validate_json(row["payload_json"])

    def list(self, *, tenant_id: str, project_id: str, status: str | None = None, risk: str | None = None, environment: str | None = None, limit: int = 100) -> list[ApprovalOperation]:
        clauses, params = ["tenant_id=?", "project_id=?"], [tenant_id, project_id]
        for column, value in (("status", status), ("risk_level", risk), ("environment", environment)):
            if value: clauses.append(f"{column}=?"); params.append(value)
        params.append(limit)
        with self.connect() as db:
            rows = db.execute(f"SELECT payload_json FROM dba_operations WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?", tuple(params)).fetchall()
        return [ApprovalOperation.model_validate_json(row["payload_json"]) for row in rows]

    def transition(self, operation_id: str, *, expected_version: int, allowed_from: set[str], status: str) -> ApprovalOperation:
        current = self.get(operation_id)
        if current.version != expected_version: raise OperationConflict("operation_version_conflict")
        if current.status not in allowed_from: raise OperationConflict("invalid_operation_transition")
        updated = current.model_copy(update={"status": status})
        payload = _json(updated.model_dump(mode="json"))
        with self.transaction() as db:
            cursor = db.execute("UPDATE dba_operations SET status=?, payload_json=? WHERE operation_id=? AND current_version=? AND status=?",
                (status, payload, operation_id, expected_version, current.status))
            if cursor.rowcount != 1: raise OperationConflict("operation_changed_concurrently")
            self._audit(db, updated, f"dba.operation.{status}", {"from": current.status, "to": status})
        return updated

    def append_decision(self, decision: ApprovalDecision) -> ApprovalDecision:
        payload = _json(decision.model_dump(mode="json"))
        with self.transaction() as db:
            existing = db.execute("SELECT payload_json FROM dba_approval_decisions WHERE operation_id=? AND request_id=?", (decision.operation_id, decision.request_id)).fetchone()
            if existing: return ApprovalDecision.model_validate_json(existing["payload_json"])
            db.execute("INSERT INTO dba_approval_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (decision.decision_id, decision.operation_id, decision.operation_version, decision.decision, decision.actor_id, decision.actor_role, decision.acknowledged_hash, decision.request_id, payload, decision.created_at.isoformat()))
        return decision

    def decisions(self, operation_id: str, version: int) -> list[ApprovalDecision]:
        with self.connect() as db:
            rows = db.execute("SELECT payload_json FROM dba_approval_decisions WHERE operation_id=? AND operation_version=? ORDER BY created_at", (operation_id, version)).fetchall()
        return [ApprovalDecision.model_validate_json(row["payload_json"]) for row in rows]

    def decision_by_request(self, operation_id: str, request_id: str) -> ApprovalDecision | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload_json FROM dba_approval_decisions WHERE operation_id=? AND request_id=?",
                (operation_id, request_id),
            ).fetchone()
        return ApprovalDecision.model_validate_json(row["payload_json"]) if row else None

    def append_execution(self, attempt: ExecutionAttempt) -> tuple[ExecutionAttempt, bool]:
        with self.transaction() as db:
            existing = db.execute("SELECT payload_json FROM dba_execution_attempts WHERE idempotency_key=?", (attempt.idempotency_key,)).fetchone()
            if existing: return ExecutionAttempt.model_validate_json(existing["payload_json"]), False
            db.execute("INSERT INTO dba_execution_attempts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt.attempt_id, attempt.operation_id, attempt.operation_version, attempt.idempotency_key, attempt.status, _json(attempt.model_dump(mode="json")), attempt.started_at.isoformat()))
        return attempt, True

    def update_execution(self, attempt: ExecutionAttempt, *, expected_status: str) -> ExecutionAttempt:
        with self.transaction() as db:
            cursor = db.execute(
                "UPDATE dba_execution_attempts SET status=?, payload_json=? WHERE attempt_id=? AND status=?",
                (attempt.status, _json(attempt.model_dump(mode="json")), attempt.attempt_id, expected_status),
            )
            if cursor.rowcount != 1: raise OperationConflict("execution_attempt_changed_concurrently")
        return attempt

    def append_verification(self, result: VerificationResult) -> None:
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO dba_verification_results VALUES (?, ?, ?, ?, ?, ?)",
                (result.verification_id, result.operation_id, result.operation_version, int(result.passed), _json(result.model_dump(mode="json")), result.created_at.isoformat()))

    def audit(self, operation_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT event_id,event_type,payload_json,created_at FROM dba_audit_events WHERE operation_id=? ORDER BY sequence", (operation_id,)).fetchall()
        return [{"event_id": row["event_id"], "type": row["event_type"], "timestamp": row["created_at"], "payload": json.loads(row["payload_json"])} for row in rows]

    def _audit(self, db, operation, event_type, payload):
        sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 value FROM dba_audit_events WHERE operation_id=?", (operation.operation_id,)).fetchone()["value"]
        db.execute("INSERT INTO dba_audit_events VALUES (?, ?, ?, ?, ?, ?)", (f"aud_{operation.operation_id}_{sequence}", operation.operation_id, sequence, event_type, _json(payload), operation.created_at.isoformat()))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try: yield db
            except Exception: db.rollback(); raise
            else: db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30); db.row_factory = sqlite3.Row; db.execute("PRAGMA journal_mode=WAL"); return db

    def _migrate(self):
        with self.connect() as db: db.executescript("""
        CREATE TABLE IF NOT EXISTS dba_operations(operation_id TEXT PRIMARY KEY,tenant_id TEXT,project_id TEXT,current_version INTEGER,status TEXT,risk_level TEXT,environment TEXT,expires_at TEXT,created_at TEXT,payload_json TEXT);
        CREATE TABLE IF NOT EXISTS dba_operation_versions(operation_id TEXT,version INTEGER,operation_hash TEXT,status TEXT,payload_json TEXT,created_at TEXT,superseded_by INTEGER,PRIMARY KEY(operation_id,version));
        CREATE TABLE IF NOT EXISTS dba_approval_decisions(decision_id TEXT PRIMARY KEY,operation_id TEXT,operation_version INTEGER,decision TEXT,actor_id TEXT,actor_role TEXT,acknowledged_hash TEXT,request_id TEXT,payload_json TEXT,created_at TEXT,UNIQUE(operation_id,request_id));
        CREATE TABLE IF NOT EXISTS dba_execution_attempts(attempt_id TEXT PRIMARY KEY,operation_id TEXT,operation_version INTEGER,idempotency_key TEXT UNIQUE,status TEXT,payload_json TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS dba_verification_results(verification_id TEXT PRIMARY KEY,operation_id TEXT,operation_version INTEGER,passed INTEGER,payload_json TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS dba_audit_events(event_id TEXT PRIMARY KEY,operation_id TEXT,sequence INTEGER,event_type TEXT,payload_json TEXT,created_at TEXT,UNIQUE(operation_id,sequence));
        CREATE INDEX IF NOT EXISTS idx_dba_pending ON dba_operations(tenant_id,project_id,status,risk_level,environment,expires_at);
        """)


def _json(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
