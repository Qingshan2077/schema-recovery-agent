"""Unified memory manager."""

from backend.agent.memory.global_memory import GlobalMemory
from backend.agent.memory.schema_memory import SchemaMemory
from backend.agent.memory.session_memory import SessionMemory


class MemoryManager:
    def __init__(self, session_id: str):
        self.session = SessionMemory(session_id)
        self.schema = SchemaMemory()
        self.global_ctx = GlobalMemory()

    def save_analysis_result(self, session_id: str, database: str, merge_result: dict):
        relations = merge_result.get("high_confidence_relations", [])
        self.schema.save_relations(relations, session_id)
        summary = merge_result.get("summary", {})
        self.schema.save_analysis_history(
            session_id,
            database,
            summary.get("total_relations", 0),
            summary.get("total_relations", 0),
            summary.get("high_confidence", 0),
            f"Found {summary.get('high_confidence', 0)} high-confidence relations",
        )

    def get_non_fk_keywords(self) -> list[str]:
        keywords = []
        for rule in self.global_ctx.get_by_category("non_fk"):
            keywords.extend(rule["value"].split(","))
        return [item.strip() for item in keywords if item.strip()]

    def get_naming_rules(self) -> list[dict]:
        return self.global_ctx.get_by_category("naming")

