"""Evidence weight analysis helper."""

from __future__ import annotations

import json
import os
from backend.config import Config
import sqlite3


class WeightUpdater:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "monitor.db")

    def get_evidence_source_overview(self) -> dict:
        if not os.path.exists(self.db_path):
            return {}
        conn = sqlite3.connect(self.db_path)
        try:
            recent = conn.execute(
                "SELECT evidence_contributions FROM analysis_records ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            source_aggregate: dict[str, dict] = {}
            for row in recent:
                contributions = json.loads(row[0]) if row[0] else {}
                for source, info in contributions.items():
                    source_aggregate.setdefault(source, {"total_pct": 0, "count": 0})
                    source_aggregate[source]["total_pct"] += info.get("percentage", 0)
                    source_aggregate[source]["count"] += 1
            return {
                source: {"avg_percentage": round(info["total_pct"] / info["count"], 1), "appearances": info["count"]}
                for source, info in sorted(source_aggregate.items(), key=lambda item: -(item[1]["total_pct"] / item[1]["count"]))
            }
        finally:
            conn.close()

    def suggest_weight_adjustment(self) -> dict:
        overview = self.get_evidence_source_overview()
        suggestions = []
        reference_weights = {
            "sql_join": 0.40,
            "orm_association": 0.25,
            "orm_collection": 0.25,
            "column_name_suffix": 0.20,
            "primary_key_name_match": 0.20,
            "naming_convention_match": 0.18,
            "naming_cross_table": 0.15,
        }
        for source, info in overview.items():
            weight = reference_weights.get(source, 0.10)
            if info["avg_percentage"] < weight * 30:
                suggestions.append(
                    {
                        "source": source,
                        "current_weight": weight,
                        "avg_contribution": info["avg_percentage"],
                        "suggestion": "Review this source weight manually if the trend persists",
                    }
                )
        return {
            "evidence_source_overview": overview,
            "adjustment_suggestions": suggestions,
            "note": "Suggestions are informational; MergeWorker weights remain manually controlled.",
        }




