"""Monitor recorder for analysis runs."""

from __future__ import annotations

import json
import os
from backend.config import Config
import sqlite3


class MonitorRecorder:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "monitor.db")
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
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
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    tool_call_count INTEGER,
                    error TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_analysis(self, session_id: str, context: dict, steps: list[dict]):
        conn = sqlite3.connect(self.db_path)
        try:
            merge_result = context.get("merge_result", {})
            summary = merge_result.get("summary", {})
            survey_summary = context.get("survey_result", {}).get("summary", {})
            total_duration = sum(s.get("duration_ms", 0) for s in steps if s.get("worker") != "router")
            total_tool_calls = sum(len(s.get("tool_calls", [])) for s in steps if "tool_calls" in s)
            contributions = merge_result.get("source_contributions", {})

            conn.execute(
                """
                INSERT OR REPLACE INTO analysis_records
                    (session_id, status, total_duration_ms, total_tool_calls, table_count,
                     high_confidence_count, medium_confidence_count, low_confidence_count,
                     evidence_contributions, total_steps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    "completed",
                    total_duration,
                    total_tool_calls,
                    survey_summary.get("total_tables", 0),
                    summary.get("high_confidence", 0),
                    summary.get("medium_confidence", 0),
                    summary.get("low_confidence", 0),
                    json.dumps(contributions, ensure_ascii=False),
                    len(steps),
                ),
            )

            for step in steps:
                if step.get("worker") in {"router", "memory"}:
                    continue
                conn.execute(
                    """
                    INSERT INTO worker_records
                        (session_id, worker_id, status, duration_ms, tool_call_count, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        step.get("worker", "unknown"),
                        step.get("status", "unknown"),
                        step.get("duration_ms", 0),
                        len(step.get("tool_calls", [])),
                        step.get("error"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM analysis_records").fetchone()[0]
            if total == 0:
                return {"total_analyses": 0, "message": "No analysis records yet"}
            avg_duration = conn.execute("SELECT AVG(total_duration_ms) FROM analysis_records").fetchone()[0] or 0
            avg_tables = conn.execute("SELECT AVG(table_count) FROM analysis_records").fetchone()[0] or 0
            worker_avg = conn.execute(
                """
                SELECT worker_id,
                       COUNT(*) AS runs,
                       ROUND(AVG(duration_ms)) AS avg_duration,
                       ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate
                FROM worker_records
                GROUP BY worker_id
                """
            ).fetchall()
            recent = conn.execute("SELECT * FROM analysis_records ORDER BY created_at DESC LIMIT 5").fetchall()
            return {
                "total_analyses": total,
                "avg_duration_ms": round(avg_duration, 0),
                "avg_tables_per_analysis": round(avg_tables, 1),
                "worker_stats": [
                    {"worker_id": w[0], "runs": w[1], "avg_duration_ms": w[2], "success_rate": w[3]}
                    for w in worker_avg
                ],
                "recent_analyses": [
                    {
                        "session_id": row[1],
                        "status": row[2],
                        "duration_ms": row[3],
                        "high_confidence": row[6],
                        "date": row[11],
                    }
                    for row in recent
                ],
            }
        finally:
            conn.close()




