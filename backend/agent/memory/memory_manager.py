"""Unified memory manager."""

from __future__ import annotations

from backend.agent.memory.global_memory import GlobalMemory
from backend.agent.memory.schema_memory import SchemaMemory
from backend.agent.memory.session_memory import SessionMemory
from backend.core.identity import RunIdentity


class MemoryManager:
    def __init__(
        self,
        session_id: str,
        *,
        schema_db_path: str | None = None,
        global_db_path: str | None = None,
    ):
        self.session = SessionMemory(session_id)
        self.schema = SchemaMemory(db_path=schema_db_path)
        self.global_ctx = GlobalMemory(db_path=global_db_path)

    def save_analysis_result(
        self,
        identity: RunIdentity,
        database: str,
        merge_result: dict,
        *,
        survey_result: dict,
    ) -> None:
        relations = merge_result.get("high_confidence_relations", [])
        server_info = survey_result.get("server_info") or {}
        database_fingerprint = server_info.get("database_fingerprint") or "legacy"
        snapshot_id = server_info.get("snapshot_id") or "legacy"
        self.schema.save_relations(
            relations,
            identity,
            database_fingerprint=database_fingerprint,
            snapshot_id=snapshot_id,
        )
        summary = merge_result.get("summary") or {}
        survey_summary = survey_result.get("summary") or {}
        self.schema.save_analysis_history(
            identity,
            database,
            int(survey_summary.get("total_tables", 0) or 0),
            int(summary.get("total_relations", 0) or 0),
            int(summary.get("high_confidence", 0) or 0),
            f"Found {summary.get('high_confidence', 0)} high-confidence relations",
            database_fingerprint=database_fingerprint,
            snapshot_id=snapshot_id,
        )

    def get_non_fk_keywords(self) -> list[str]:
        keywords = []
        for rule in self.global_ctx.get_by_category("non_fk"):
            keywords.extend(rule["value"].split(","))
        return [item.strip() for item in keywords if item.strip()]

    def get_naming_rules(self) -> list[dict]:
        return self.global_ctx.get_by_category("naming")
