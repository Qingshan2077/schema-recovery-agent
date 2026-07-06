"""NameWorker implementation."""

from backend.agent.workers.base import BaseWorker


class NameWorker(BaseWorker):
    def run(self, context: dict) -> dict:
        naming = self.call_tool("analyze_naming_convention")
        column_matches = self.call_tool("find_column_name_matches")
        assoc_tables = self.call_tool("detect_associative_tables")

        relations = []
        for match in column_matches["matches"]:
            relations.append(
                {
                    "source_table": match["source_table"],
                    "fk_column": match["fk_column"],
                    "target_table": match["target_table"],
                    "pk_column": match["pk_column"],
                    "confidence": 0.7 if match.get("exact_type_match") else 0.4,
                    "evidence": [
                        {
                            "source": "naming_cross_table",
                            "strength": 0.7 if match.get("exact_type_match") else 0.4,
                            "detail": match.get("evidence", "naming match"),
                        }
                    ],
                    "relation_type": "naming_convention",
                }
            )

        assoc_details = []
        for table in assoc_tables["tables"]:
            parts = table["table"].split("_")
            assoc_details.append(
                {
                    "table": table["table"],
                    "id_columns": table["id_columns"],
                    "inferred_entities": [parts[0], "_".join(parts[1:])] if len(parts) >= 2 else parts,
                    "primary_key_columns": table["primary_key_columns"],
                }
            )

        return {
            "status": "success",
            "naming_convention": naming,
            "column_name_matches": {"count": column_matches["match_count"], "matches": relations},
            "associative_tables": {"count": assoc_tables["associative_table_count"], "tables": assoc_details},
            "total_relations": len(relations),
        }

