"""L2 schema memory backed by SQLite."""

from __future__ import annotations

import json
import os
from backend.config import Config
import sqlite3


class SchemaMemory:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "schema_memory.db")
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovered_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    fk_column TEXT NOT NULL,
                    pk_column TEXT,
                    relation_type TEXT DEFAULT 'N:1',
                    confidence REAL DEFAULT 0.0,
                    top_evidence TEXT,
                    first_discovered TEXT DEFAULT (datetime('now')),
                    last_verified TEXT DEFAULT (datetime('now')),
                    discover_count INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_relation
                ON discovered_relations(source_table, target_table, fk_column)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    database_name TEXT,
                    analysis_date TEXT DEFAULT (datetime('now')),
                    table_count INTEGER,
                    relation_count INTEGER,
                    high_confidence_count INTEGER,
                    summary TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_relations(self, relations: list[dict], session_id: str):
        conn = sqlite3.connect(self.db_path)
        try:
            for rel in relations:
                top_ev = (rel.get("evidence_chain") or [{}])[0] if rel.get("evidence_chain") else {}
                conn.execute(
                    """
                    INSERT INTO discovered_relations
                        (source_table, target_table, fk_column, pk_column, relation_type, confidence, top_evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_table, target_table, fk_column)
                    DO UPDATE SET
                        confidence = (confidence + excluded.confidence) / 2,
                        discover_count = discover_count + 1,
                        last_verified = datetime('now'),
                        top_evidence = CASE WHEN excluded.confidence > confidence
                                            THEN excluded.top_evidence ELSE top_evidence END
                    """,
                    (
                        rel.get("source_table", ""),
                        rel.get("target_table", ""),
                        rel.get("fk_column", ""),
                        rel.get("pk_column", ""),
                        rel.get("relation_type", "N:1"),
                        rel.get("fused_confidence", 0.0),
                        json.dumps(top_ev, ensure_ascii=False),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def save_analysis_history(self, session_id: str, database: str, table_count: int, relation_count: int, high_count: int, summary: str):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO analysis_history
                    (session_id, database_name, table_count, relation_count, high_confidence_count, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, database, table_count, relation_count, high_count, summary),
            )
            conn.commit()
        finally:
            conn.close()

    def query_similar_relations(self, source_table: str | None = None, target_table: str | None = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            query = "SELECT * FROM discovered_relations WHERE is_active = 1"
            params = []
            if source_table:
                query += " AND source_table = ?"
                params.append(source_table)
            if target_table:
                query += " AND target_table = ?"
                params.append(target_table)
            query += " ORDER BY confidence DESC LIMIT 20"
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": row[0],
                    "source_table": row[1],
                    "target_table": row[2],
                    "fk_column": row[3],
                    "pk_column": row[4],
                    "relation_type": row[5],
                    "confidence": row[6],
                    "top_evidence": json.loads(row[7]) if row[7] else {},
                    "first_discovered": row[8],
                    "last_verified": row[9],
                    "discover_count": row[10],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_history(self, limit: int = 10) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM analysis_history ORDER BY analysis_date DESC LIMIT ?", (limit,)).fetchall()
            return [
                {
                    "id": r[0],
                    "session_id": r[1],
                    "database": r[2],
                    "date": r[3],
                    "tables": r[4],
                    "relations": r[5],
                    "high_confidence": r[6],
                    "summary": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()




