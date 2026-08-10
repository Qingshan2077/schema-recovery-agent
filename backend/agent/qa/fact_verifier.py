"""Normalize successful tool results into immutable, source-addressed facts."""

from __future__ import annotations

from typing import Any

from backend.agent.qa.contracts import FactSet, ToolExecution, VerifiedFact
from backend.core.identity import stable_id


class FactVerifier:
    def verify(self, executions: list[ToolExecution], *, catalog_version: str) -> FactSet:
        facts: list[VerifiedFact] = []
        for execution in executions:
            if execution.status != "success" or not execution.output or not execution.output_hash:
                continue
            facts.extend(self._facts_for(execution))
        return FactSet(
            facts=facts,
            tool_call_ids=[item.tool_call_id for item in executions],
            catalog_version=catalog_version,
        )

    def _facts_for(self, execution: ToolExecution) -> list[VerifiedFact]:
        output = execution.output or {}
        tool = execution.tool_name
        if tool == "catalog.query_table_columns":
            return [
                self._fact(
                    execution,
                    "column",
                    f"{output['table_id']}:{column['name']}",
                    "has_column",
                    column,
                    {"database": output["database"], "table": output["table"], "column": column["name"], "ordinal": column["ordinal"]},
                )
                for column in output.get("columns", [])
            ]
        if tool == "catalog.query_table_metadata":
            return [
                self._fact(execution, "metadata", output["table_id"], key, value, {"database": output["database"], "table": output["table"], "field": key})
                for key, value in output.items()
                if key in {"exists", "engine", "estimated_rows", "comment", "created_at", "updated_at"}
            ]
        if tool == "catalog.query_indexes":
            return [
                self._fact(execution, "index", output["table_id"], "has_index", index, {"database": output["database"], "table": output["table"], "index": index["name"]})
                for index in output.get("indexes", [])
            ]
        if tool == "evidence.query_relations":
            return [
                self._fact(execution, "relation", relation["relation_id"], "relation", relation, {"database": output["database"], "relation_id": relation["relation_id"]})
                for relation in output.get("relations", [])
            ]
        if tool == "analysis.get_status":
            return [self._fact(execution, "analysis", output["database"], "latest_analysis", output, {"database": output["database"]})]
        if tool == "catalog.list_tables":
            return [
                self._fact(execution, "table", table["entity_id"], "catalog_table", table, {"database": output["database"], "table": table["name"]})
                for table in output.get("tables", [])
            ]
        return []

    @staticmethod
    def _fact(
        execution: ToolExecution,
        fact_type: str,
        subject_id: str,
        predicate: str,
        value: Any,
        locator: dict[str, Any],
    ) -> VerifiedFact:
        fact_id = stable_id("fact", execution.output_hash, fact_type, subject_id, predicate, value)
        return VerifiedFact(
            fact_id=fact_id,
            fact_type=fact_type,
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            source_tool_call_id=execution.tool_call_id,
            source_tool=execution.tool_name,
            output_hash=execution.output_hash or "",
            locator=locator,
        )


FactSetVerifier = FactVerifier
