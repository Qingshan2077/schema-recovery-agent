"""CodeWorker implementation."""

from backend.agent.workers.base import BaseWorker


class CodeWorker(BaseWorker):
    def run(self, context: dict) -> dict:
        survey_result = context.get("survey_result", {})
        views = survey_result.get("views", {})
        procs = survey_result.get("stored_procedures", {})
        triggers = survey_result.get("triggers", {})
        all_relations = []
        source_stats = {"views": 0, "procedures": 0, "triggers": 0}

        for view in views.get("details", []):
            result = self.call_tool("parse_view_definition", view_name=view["name"], definition=view["definition"])
            for rel in result.get("relations", []):
                for pair in rel.get("column_pairs", []):
                    all_relations.append(self._build_code_relation("view", view["name"], pair, 0.9))
            source_stats["views"] += result.get("relation_count", 0)

        for proc in procs.get("details", []):
            result = self.call_tool("parse_stored_procedure_sql", proc_name=proc["name"], definition=proc["definition"])
            for rel in result.get("relations", []):
                for pair in rel.get("column_pairs", []):
                    confidence = 0.95 if rel.get("relation_type") != "subquery_ref" else 0.7
                    all_relations.append(self._build_code_relation("stored_procedure", proc["name"], pair, confidence))
            source_stats["procedures"] += result.get("relation_count", 0)

        for trigger in triggers.get("details", []):
            result = self.call_tool(
                "analyze_trigger_body",
                trigger_name=trigger["name"],
                event=trigger["event"],
                table=trigger["table"],
                definition=trigger["definition"],
            )
            source_stats["triggers"] += result.get("table_count", 0)

        return {
            "status": "success",
            "source_stats": source_stats,
            "relations": all_relations,
            "relation_count": len(all_relations),
            "highest_quality_evidence": len(all_relations),
        }

    def _build_code_relation(self, source_type: str, source_name: str, pair: dict, confidence: float) -> dict:
        left_table, left_col = self._split_pair_side(pair.get("left", ""))
        right_table, right_col = self._split_pair_side(pair.get("right", ""))
        source_table, fk_column, target_table, pk_column = self._orient_relation(left_table, left_col, right_table, right_col)
        return {
            "source_table": source_table,
            "fk_column": fk_column,
            "target_table": target_table,
            "pk_column": pk_column,
            "confidence": confidence,
            "evidence": [
                {
                    "source": f"sql_{source_type}",
                    "strength": confidence,
                    "detail": f"Found JOIN in {source_type} {source_name}: {pair.get('left')} = {pair.get('right')}",
                }
            ],
            "relation_type": "sql_join",
            "source_file": source_type,
            "source_name": source_name,
        }

    @staticmethod
    def _split_pair_side(value: str) -> tuple[str, str]:
        parts = value.split(".")
        return (parts[0], parts[1]) if len(parts) >= 2 else (value, "")

    @staticmethod
    def _orient_relation(left_table: str, left_col: str, right_table: str, right_col: str) -> tuple[str, str, str, str]:
        if left_col == "id" and right_col != "id":
            return right_table, right_col, left_table, left_col
        return left_table, left_col, right_table, right_col

