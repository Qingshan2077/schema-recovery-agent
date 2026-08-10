"""SQLite implementation of the append-only evidence repository protocol."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Protocol

from backend.agent.runtime.hybrid_contracts import EvidenceItem, RelationCandidate
from backend.core.identity import new_id, stable_id


class EvidenceIntegrityError(RuntimeError):
    pass


class EvidenceRepository(Protocol):
    def append_artifact(self, *, artifact_id: str, snapshot_id: str, content_hash: str, content: dict[str, Any], metadata: dict[str, Any]) -> str: ...
    def append_evidence(self, item: EvidenceItem) -> bool: ...
    def append_relation(self, candidate: RelationCandidate, *, snapshot_id: str, producer: str) -> bool: ...
    def query_evidence(self, *, snapshot_id: str, claim_key: str | None = None, relation_id: str | None = None) -> list[EvidenceItem]: ...
    def query_relations(self, *, snapshot_id: str) -> list[RelationCandidate]: ...
    def create_revision(self, *, snapshot_id: str, reason: str) -> str: ...
    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None: ...


class SQLiteEvidenceRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def append_artifact(
        self,
        *,
        artifact_id: str,
        snapshot_id: str,
        content_hash: str,
        content: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash FROM recovery_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if existing:
                if existing["content_hash"] != content_hash:
                    raise EvidenceIntegrityError("artifact id was reused with different content")
                return artifact_id
            connection.execute(
                "INSERT INTO recovery_artifacts VALUES (?, ?, ?, ?, ?, ?)",
                (artifact_id, snapshot_id, content_hash, _json(content), _json(metadata), _now()),
            )
        return artifact_id

    def append_evidence(self, item: EvidenceItem) -> bool:
        payload = item.model_dump(mode="json")
        payload_hash = _hash_payload(payload)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM evidence_ledger WHERE evidence_id = ?",
                (item.evidence_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise EvidenceIntegrityError("evidence id was reused with different content")
                return False
            connection.execute(
                """INSERT INTO evidence_ledger(
                    evidence_id, snapshot_id, database_fingerprint, claim_key, relation_id,
                    source_type, producer, polarity, strength, reliability, correlation_key,
                    payload_hash, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.evidence_id, item.snapshot_id, item.database_fingerprint, item.claim_key,
                    item.relation_id, item.source_type, item.producer, item.polarity, item.strength,
                    item.reliability, item.correlation_key, payload_hash, _json(payload), _now(),
                ),
            )
        return True

    def append_relation(self, candidate: RelationCandidate, *, snapshot_id: str, producer: str) -> bool:
        payload = candidate.model_dump(mode="json")
        payload_hash = _hash_payload(payload)
        event_id = stable_id("artifact", snapshot_id, producer, candidate.relation_id, payload_hash)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM relation_candidate_events WHERE candidate_event_id = ?",
                (event_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise EvidenceIntegrityError("relation candidate event id was reused with different content")
                return False
            connection.execute(
                "INSERT INTO relation_candidate_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, candidate.relation_id, snapshot_id, candidate.claim_key, producer, payload_hash, _json(payload), _now()),
            )
        return True

    def create_revision(self, *, snapshot_id: str, reason: str) -> str:
        revision_id = new_id("revision")
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO evidence_revisions VALUES (?, ?, ?, ?)",
                (revision_id, snapshot_id, reason, _now()),
            )
        return revision_id

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content_json FROM recovery_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        return json.loads(row["content_json"]) if row else None

    def query_evidence(
        self,
        *,
        snapshot_id: str,
        claim_key: str | None = None,
        relation_id: str | None = None,
    ) -> list[EvidenceItem]:
        clauses = ["snapshot_id = ?"]
        params: list[Any] = [snapshot_id]
        if claim_key:
            clauses.append("claim_key = ?")
            params.append(claim_key)
        if relation_id:
            clauses.append("relation_id = ?")
            params.append(relation_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM evidence_ledger WHERE {' AND '.join(clauses)} ORDER BY created_at, evidence_id",
                tuple(params),
            ).fetchall()
        return [EvidenceItem.model_validate_json(row["payload_json"]) for row in rows]

    def query_relations(self, *, snapshot_id: str) -> list[RelationCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM relation_candidate_events WHERE snapshot_id = ? ORDER BY claim_key, producer, created_at",
                (snapshot_id,),
            ).fetchall()
        return [RelationCandidate.model_validate_json(row["payload_json"]) for row in rows]

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS recovery_artifacts(
                    artifact_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                    content_json TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_ledger(
                    evidence_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, database_fingerprint TEXT NOT NULL,
                    claim_key TEXT NOT NULL, relation_id TEXT, source_type TEXT NOT NULL, producer TEXT NOT NULL,
                    polarity TEXT NOT NULL, strength REAL NOT NULL, reliability REAL NOT NULL,
                    correlation_key TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_snapshot_claim ON evidence_ledger(snapshot_id, claim_key);
                CREATE INDEX IF NOT EXISTS idx_evidence_relation ON evidence_ledger(snapshot_id, relation_id);
                CREATE TABLE IF NOT EXISTS relation_candidate_events(
                    candidate_event_id TEXT PRIMARY KEY, relation_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL, claim_key TEXT NOT NULL, producer TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_relation_events_snapshot ON relation_candidate_events(snapshot_id, claim_key);
                CREATE TABLE IF NOT EXISTS evidence_revisions(
                    revision_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )

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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
