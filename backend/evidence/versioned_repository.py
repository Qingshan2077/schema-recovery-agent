"""Append-only Phase 5 evidence, relation, feedback and calibration repository."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from backend.evidence.contracts import (
    CalibrationArtifact,
    EvidenceItem,
    HumanFeedback,
    RelationCandidateVersion,
)
from backend.evidence.normalizer import evidence_dedupe_key


class VersionedEvidenceConflict(RuntimeError):
    pass


class VersionedEvidenceNotFound(KeyError):
    pass


class SQLiteVersionedEvidenceRepository:
    schema_version = "5.0"

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def append_evidence(self, item: EvidenceItem) -> tuple[EvidenceItem, bool]:
        payload = item.model_dump(mode="json")
        digest = _hash(payload)
        dedupe = evidence_dedupe_key(
            excerpt_hash=item.excerpt_hash or item.artifact_hash,
            source_locator=item.source_locator,
            claim_key=item.claim_key,
            producer_version=item.producer_version,
        )
        namespace = item.namespace.project_key()
        with self._transaction() as connection:
            existing_id = connection.execute(
                "SELECT payload_json FROM evidence_items WHERE dedupe_key=?",
                (dedupe,),
            ).fetchone()
            if existing_id:
                return EvidenceItem.model_validate_json(existing_id["payload_json"]), False
            existing = connection.execute(
                "SELECT payload_hash FROM evidence_items WHERE evidence_id=?",
                (item.evidence_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise VersionedEvidenceConflict("evidence_id reused with different content")
                return item, False
            connection.execute(
                """INSERT INTO evidence_items(
                       evidence_id, tenant_key, project_key, connection_key,
                       database_key, schema_key, snapshot_id, claim_key,
                       relation_id, source_type, producer, producer_version,
                       polarity, root_fact_id, correlation_group, dedupe_key,
                       payload_hash, payload_json, created_by_run_id, trace_id,
                       span_id, created_at
                   ) VALUES(
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                (
                    item.evidence_id, *namespace, item.snapshot_id, item.claim_key,
                    item.relation_id, item.source_type, item.producer, item.producer_version,
                    item.polarity, item.root_fact_id, item.correlation_group, dedupe,
                    digest, _json(payload), item.created_by_run_id, item.trace_id,
                    item.span_id, item.created_at.isoformat(),
                ),
            )
        return item, True

    def get_evidence(self, evidence_id: str) -> EvidenceItem:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM evidence_items WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise VersionedEvidenceNotFound(evidence_id)
        return EvidenceItem.model_validate_json(row["payload_json"])

    def query_evidence(
        self,
        *,
        tenant_key: str | None = None,
        project_key: str | None = None,
        connection_key: str | None = None,
        database_key: str | None = None,
        schema_key: str | None = None,
        claim_key: str | None = None,
        relation_id: str | None = None,
        snapshot_id: str | None = None,
        include_tombstoned: bool = False,
    ) -> list[EvidenceItem]:
        clauses = ["1=1"]
        params: list[Any] = []
        for column, value in (
            ("tenant_key", tenant_key), ("project_key", project_key),
            ("connection_key", connection_key), ("database_key", database_key),
            ("schema_key", schema_key),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        if claim_key:
            clauses.append("claim_key=?")
            params.append(claim_key)
        if relation_id:
            clauses.append("relation_id=?")
            params.append(relation_id)
        if snapshot_id:
            clauses.append("snapshot_id=?")
            params.append(snapshot_id)
        if not include_tombstoned:
            clauses.append("tombstoned_at IS NULL")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM evidence_items WHERE {' AND '.join(clauses)} ORDER BY created_at, evidence_id",
                tuple(params),
            ).fetchall()
        return [EvidenceItem.model_validate_json(row["payload_json"]) for row in rows]

    def list_calibrations(self, *, limit: int = 100) -> list[CalibrationArtifact]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM calibration_versions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [CalibrationArtifact.model_validate_json(row["payload_json"]) for row in rows]

    def tombstone_evidence(self, evidence_id: str, *, reason_hash: str) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM evidence_items WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
            if row is None:
                raise VersionedEvidenceNotFound(evidence_id)
            item = EvidenceItem.model_validate_json(row["payload_json"])
            if item.tombstoned_at is not None:
                return
            now = datetime.now(timezone.utc)
            anonymized = item.model_copy(update={
                "summary": "[tombstoned]",
                "source_uri": None,
                "source_locator": {"audit_hash": _hash(item.source_locator), "reason_hash": reason_hash},
                "tombstoned_at": now,
            })
            payload = anonymized.model_dump(mode="json")
            connection.execute(
                "UPDATE evidence_items SET payload_json=?, payload_hash=?, tombstoned_at=? WHERE evidence_id=?",
                (_json(payload), _hash(payload), now.isoformat(), evidence_id),
            )

    def append_relation_version(self, item: RelationCandidateVersion) -> RelationCandidateVersion:
        payload = item.model_dump(mode="json")
        digest = _hash(payload)
        namespace = item.namespace.project_key()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM relation_versions WHERE relation_id=? AND version=?",
                (item.relation_id, item.version),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise VersionedEvidenceConflict("relation version is immutable")
                return item
            current = connection.execute(
                "SELECT current_version FROM relation_candidates WHERE relation_id=?",
                (item.relation_id,),
            ).fetchone()
            expected = 1 if current is None else int(current["current_version"]) + 1
            if item.version != expected:
                raise VersionedEvidenceConflict(f"relation version must be {expected}")
            if current is None:
                connection.execute(
                    "INSERT INTO relation_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.relation_id, *namespace, item.claim_key, item.version,
                        item.status, item.created_at.isoformat(),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE relation_candidates SET current_version=?, status=? WHERE relation_id=?",
                    (item.version, item.status, item.relation_id),
                )
                connection.execute(
                    "UPDATE relation_versions SET superseded_by_version=? WHERE relation_id=? AND version=?",
                    (item.version, item.relation_id, item.version - 1),
                )
            connection.execute(
                """INSERT INTO relation_versions VALUES(
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.relation_id, item.version, item.namespace.snapshot_id,
                    item.status, item.raw_score, item.raw_probability,
                    item.calibrated_probability, item.confidence_band,
                    item.feature_schema_hash, item.fusion_version,
                    item.calibration_version, item.threshold_policy_version,
                    digest, _json(payload), item.created_by_run_id,
                    item.created_at.isoformat(), item.superseded_by_version,
                ),
            )
            for evidence_id in item.evidence_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO relation_evidence VALUES (?, ?, ?)",
                    (item.relation_id, item.version, evidence_id),
                )
        return item

    def get_relation(self, relation_id: str, *, version: int | None = None) -> RelationCandidateVersion:
        with self._connect() as connection:
            if version is None:
                row = connection.execute(
                    """SELECT v.payload_json FROM relation_versions v
                       JOIN relation_candidates c ON c.relation_id=v.relation_id AND c.current_version=v.version
                       WHERE v.relation_id=?""",
                    (relation_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload_json FROM relation_versions WHERE relation_id=? AND version=?",
                    (relation_id, version),
                ).fetchone()
        if row is None:
            raise VersionedEvidenceNotFound(relation_id)
        return RelationCandidateVersion.model_validate_json(row["payload_json"])

    def list_relations(
        self,
        *,
        tenant_key: str,
        project_key: str,
        connection_key: str,
        database_key: str,
        schema_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[RelationCandidateVersion]:
        clauses = [
            "c.tenant_key=?", "c.project_key=?", "c.connection_key=?",
            "c.database_key=?", "c.schema_key=?",
        ]
        params: list[Any] = [tenant_key, project_key, connection_key, database_key, schema_key]
        if status:
            clauses.append("c.status=?")
            params.append(status)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT v.payload_json FROM relation_candidates c
                    JOIN relation_versions v ON v.relation_id=c.relation_id AND v.version=c.current_version
                    WHERE {' AND '.join(clauses)} ORDER BY v.calibrated_probability DESC LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [RelationCandidateVersion.model_validate_json(row["payload_json"]) for row in rows]

    def append_feedback(self, item: HumanFeedback, evidence_id: str) -> HumanFeedback:
        payload = item.model_dump(mode="json")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM human_feedback WHERE feedback_id=?",
                (item.feedback_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != _hash(payload):
                    raise VersionedEvidenceConflict("feedback id reused with different content")
                return item
            connection.execute(
                "INSERT INTO human_feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.feedback_id, item.relation_id, item.previous_version, item.action,
                    item.actor_id, item.actor_role, _hash(item.reason), evidence_id,
                    _hash(payload), _json(payload), item.created_at.isoformat(),
                ),
            )
        return item

    def put_calibration(self, item: CalibrationArtifact) -> CalibrationArtifact:
        payload = item.model_dump(mode="json")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash FROM calibration_versions WHERE calibration_version=?",
                (item.calibration_version,),
            ).fetchone()
            if existing and existing["content_hash"] != item.content_hash:
                raise VersionedEvidenceConflict("calibration version is immutable")
            connection.execute(
                "INSERT OR IGNORE INTO calibration_versions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item.calibration_version, item.fusion_version, item.feature_schema_hash,
                    item.content_hash, _json(payload), item.created_at.isoformat(),
                ),
            )
        return item

    def get_calibration(self, version: str) -> CalibrationArtifact:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM calibration_versions WHERE calibration_version=?",
                (version,),
            ).fetchone()
        if row is None:
            raise VersionedEvidenceNotFound(version)
        return CalibrationArtifact.model_validate_json(row["payload_json"])

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_items(
                    evidence_id TEXT PRIMARY KEY,
                    tenant_key TEXT NOT NULL, project_key TEXT NOT NULL,
                    connection_key TEXT NOT NULL, database_key TEXT NOT NULL, schema_key TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL, claim_key TEXT NOT NULL, relation_id TEXT,
                    source_type TEXT NOT NULL, producer TEXT NOT NULL, producer_version TEXT NOT NULL,
                    polarity TEXT NOT NULL, root_fact_id TEXT NOT NULL, correlation_group TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_by_run_id TEXT NOT NULL, trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, tombstoned_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_items(snapshot_id, claim_key, tombstoned_at);
                CREATE INDEX IF NOT EXISTS idx_evidence_relation_v2 ON evidence_items(relation_id, created_at);
                CREATE TABLE IF NOT EXISTS relation_candidates(
                    relation_id TEXT PRIMARY KEY,
                    tenant_key TEXT NOT NULL, project_key TEXT NOT NULL,
                    connection_key TEXT NOT NULL, database_key TEXT NOT NULL, schema_key TEXT NOT NULL,
                    claim_key TEXT NOT NULL, current_version INTEGER NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_relation_namespace_v2
                    ON relation_candidates(tenant_key, project_key, connection_key, database_key, schema_key, status);
                CREATE TABLE IF NOT EXISTS relation_versions(
                    relation_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot_id TEXT NOT NULL,
                    status TEXT NOT NULL, raw_score REAL NOT NULL, raw_probability REAL NOT NULL,
                    calibrated_probability REAL NOT NULL, confidence_band TEXT NOT NULL,
                    feature_schema_hash TEXT NOT NULL, fusion_version TEXT NOT NULL,
                    calibration_version TEXT NOT NULL, threshold_policy_version TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_by_run_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    superseded_by_version INTEGER,
                    PRIMARY KEY(relation_id, version),
                    FOREIGN KEY(relation_id) REFERENCES relation_candidates(relation_id)
                );
                CREATE TABLE IF NOT EXISTS relation_evidence(
                    relation_id TEXT NOT NULL, relation_version INTEGER NOT NULL, evidence_id TEXT NOT NULL,
                    PRIMARY KEY(relation_id, relation_version, evidence_id),
                    FOREIGN KEY(relation_id, relation_version) REFERENCES relation_versions(relation_id, version)
                );
                CREATE TABLE IF NOT EXISTS human_feedback(
                    feedback_id TEXT PRIMARY KEY, relation_id TEXT NOT NULL, previous_version INTEGER NOT NULL,
                    action TEXT NOT NULL, actor_id TEXT NOT NULL, actor_role TEXT NOT NULL,
                    reason_hash TEXT NOT NULL, evidence_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fusion_model_versions(
                    fusion_version TEXT PRIMARY KEY, feature_schema_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calibration_versions(
                    calibration_version TEXT PRIMARY KEY, fusion_version TEXT NOT NULL,
                    feature_schema_hash TEXT NOT NULL, content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
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
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
