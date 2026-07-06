"""ColumnWorker implementation."""

from __future__ import annotations

import re

from backend.agent.workers.base import BaseWorker


class ColumnWorker(BaseWorker):
    def run(self, context: dict) -> dict:
        survey_result = context.get("survey_result", {})
        table_names = survey_result.get("tables", {}).get("list", [])
        if not table_names:
            return {"status": "error", "error": "No tables to analyze"}

        pk_map = self._collect_primary_keys(table_names)
        table_analyses = {table: self._analyze_single_table(table, pk_map) for table in table_names}
        all_relations = []
        for table, analysis in table_analyses.items():
            for rel in analysis["potential_relations"]:
                all_relations.append({"source_table": table, **rel})
        return {
            "status": "success",
            "table_count": len(table_names),
            "analyzed_tables": table_analyses,
            "potential_relations": all_relations,
            "relation_count": len(all_relations),
        }

    def _collect_primary_keys(self, table_names: list[str]) -> dict:
        pk_map = {}
        for table in table_names:
            columns = self.call_tool("analyze_table_columns", table_name=table)
            pk_cols = [c for c in columns["columns"] if c["is_primary_key"]]
            if pk_cols:
                pk_map[table] = {
                    "columns": [c["column_name"] for c in pk_cols],
                    "types": [c["data_type"] for c in pk_cols],
                }
            auto_inc = self.call_tool("check_auto_increment", table_name=table)
            if auto_inc["has_auto_increment"] and table not in pk_map:
                pk_map[table] = {
                    "columns": [c["COLUMN_NAME"] for c in auto_inc["auto_increment_columns"]],
                    "types": [c["COLUMN_TYPE"] for c in auto_inc["auto_increment_columns"]],
                }
        return pk_map

    def _analyze_single_table(self, table: str, pk_map: dict) -> dict:
        columns = self.call_tool("analyze_table_columns", table_name=table)
        indexes = self.call_tool("check_indexes", table_name=table)
        potential_relations = []

        for col in columns["columns"]:
            col_name = col["column_name"]
            if col["is_primary_key"] or self._is_not_fk_candidate(col_name, col["data_type"]):
                continue

            evidence = []
            confidence = 0.0
            base_name = col_name[:-3] if col_name.lower().endswith("_id") else col_name

            if col_name.lower().endswith("_id"):
                evidence.append({"source": "column_name_suffix", "strength": 0.8, "detail": f"{table}.{col_name} ends with _id"})
                confidence += 0.3

            for target_table, pk_info in pk_map.items():
                if target_table == table:
                    continue
                for pk_col in pk_info["columns"]:
                    if col_name == pk_col:
                        evidence.append({"source": "primary_key_name_match", "strength": 0.9, "detail": f"{col_name} matches {target_table}.{pk_col}"})
                        confidence += 0.4
                    elif self._name_matches_target(base_name, target_table):
                        evidence.append({"source": "naming_convention_match", "strength": 0.7, "detail": f"{col_name} matches table {target_table}"})
                        confidence += 0.35

            for idx in indexes["indexes"]:
                if col_name in idx["columns"] and not idx["is_unique"]:
                    evidence.append({"source": "index_exists", "strength": 0.5, "detail": f"{col_name} has non-unique index {idx['index_name']}"})
                    confidence += 0.15
                    break

            if col_name.lower().startswith(("fk_", "ref_")):
                evidence.append({"source": "explicit_fk_prefix", "strength": 1.0, "detail": f"{col_name} has explicit FK prefix"})
                confidence += 0.5

            if evidence:
                best = self._resolve_target_table(col_name, base_name, pk_map)
                if best:
                    potential_relations.append(
                        {
                            "target_table": best["table"],
                            "fk_column": col_name,
                            "pk_column": best["pk_column"],
                            "fk_type": col["data_type"],
                            "confidence": min(confidence, 1.0),
                            "evidence": evidence,
                        }
                    )

        return {"table": table, "column_count": columns["column_count"], "potential_relations": potential_relations, "relation_count": len(potential_relations)}

    def _is_not_fk_candidate(self, col_name: str, data_type: str) -> bool:
        keywords = [
            "time", "date", "status", "flag", "type", "desc", "comment", "content", "title",
            "name", "email", "phone", "address", "url", "image", "price", "amount", "count",
            "created", "updated", "deleted", "json", "text", "config", "remark", "note",
        ]
        if any(re.search(k, col_name, re.IGNORECASE) for k in keywords):
            return not (col_name.endswith("_id") and ("int" in data_type.lower()))
        return False

    @staticmethod
    def _name_matches_target(base_name: str, target_table: str) -> bool:
        return target_table in {base_name, f"{base_name}s", f"{base_name}es"} or target_table.rstrip("s") == base_name

    def _resolve_target_table(self, col_name: str, base_name: str, pk_map: dict) -> dict | None:
        for target_table, pk_info in pk_map.items():
            if self._name_matches_target(base_name, target_table):
                return {"table": target_table, "pk_column": pk_info["columns"][0]}
        for target_table, pk_info in pk_map.items():
            if target_table in col_name.lower() or base_name in target_table:
                return {"table": target_table, "pk_column": pk_info["columns"][0]}
        return None

