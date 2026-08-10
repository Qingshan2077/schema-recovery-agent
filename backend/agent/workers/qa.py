"""Schema question-answering worker."""

from __future__ import annotations

import asyncio
import re
from threading import Thread
from typing import TYPE_CHECKING, Any

from backend.agent.workers.base import BaseWorker
from backend.config import Config

if TYPE_CHECKING:
    from backend.agent.qa.agent import QAAgent


class QAWorker(BaseWorker):
    """v1 compatibility adapter; rules remain only as an explicit degraded fallback."""

    def __init__(self, *args: Any, qa_agent: "QAAgent | None" = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.qa_agent = qa_agent

    def run(self, context: dict) -> dict:
        if self.qa_agent is not None and self.run_context is not None:
            result = _await_sync(self.qa_agent.run(
                question=str(context.get("question") or ""),
                run_context=self.run_context.for_agent("qa"),
                messages=list(context.get("messages") or []),
            ))
            output = result.output
            return {
                "status": result.status.value,
                "answer": output.get("answer") or output.get("clarification_question") or (result.error.message if result.error else ""),
                "intent": output.get("intent", "unknown"),
                "data": output,
                "agent_run_result": result.model_dump(mode="json"),
            }
        return self._run_degraded_rules(context)

    def _run_degraded_rules(self, context: dict) -> dict:
        question = context.get("question", "")
        intent = self._classify_question(question)
        data = self._execute_intent(intent, question)
        return {
            "status": "success",
            "answer": self._template_answer(data, intent),
            "intent": intent,
            "data": data,
        }

    def _classify_question(self, question: str) -> str:
        q = question.lower()
        if any(keyword in q for keyword in ["field", "fields", "column", "columns", "schema", "\u5b57\u6bb5", "\u5217"]):
            return "table_columns"
        if any(keyword in q for keyword in ["create time", "created", "metadata", "engine", "create table", "\u5efa\u8868", "\u521b\u5efa\u65f6\u95f4", "\u5143\u6570\u636e"]):
            return "table_metadata"
        if any(keyword in q for keyword in ["how many tables", "table count", "overview", "summary", "\u591a\u5c11\u5f20\u8868", "\u51e0\u5f20\u8868", "\u603b\u5171", "\u6982\u51b5"]):
            return "database_overview"
        if any(keyword in q for keyword in ["relation", "relationship", "foreign", "foreign key", "\u5173\u7cfb", "\u5173\u8054", "\u5916\u952e"]):
            return "table_relations"
        if any(keyword in q for keyword in ["index", "indexes", "\u7d22\u5f15"]):
            return "table_indexes"
        return "database_overview"

    def _execute_intent(self, intent: str, question: str) -> dict:
        table_names = self._extract_table_names(question)
        table_name = table_names[0] if table_names else None

        if intent == "table_columns" and table_name:
            return self.call_tool("query_table_columns", table_name=table_name)
        if intent == "table_columns":
            return {"error": "missing_table_name", "table": None, "intent": intent}
        if intent == "table_metadata" and table_name:
            return self.call_tool("query_table_metadata", table_name=table_name)
        if intent == "table_metadata":
            return {"error": "missing_table_name", "table": None, "intent": intent}
        if intent == "table_indexes" and table_name:
            return self.call_tool("check_indexes", table_name=table_name)
        if intent == "table_indexes":
            return {"error": "missing_table_name", "table": None, "intent": intent}
        if intent == "table_relations":
            source = table_names[0] if table_names else None
            target = table_names[1] if len(table_names) > 1 else None
            return self.call_tool("query_saved_relations", source_table=source, target_table=target)
        return self.call_tool("database_overview")

    def _template_answer(self, data: dict, intent: str) -> str:
        if data.get("error"):
            return f"No matching schema information was found: {data['error']}"
        if intent == "table_columns":
            columns = data.get("columns", [])
            if not columns:
                return f"No column metadata was found for table {data.get('table', '')}."
            lines = [f"Table {data['table']} has {data.get('column_count', len(columns))} columns:"]
            for col in columns:
                key = f", key={col['key']}" if col.get("key") else ""
                nullable = "nullable" if col.get("nullable") else "not null"
                comment = f", {col['comment']}" if col.get("comment") else ""
                lines.append(f"- {col['name']}: {col['type']} ({nullable}{key}{comment})")
            return "\n".join(lines)
        if intent == "table_metadata":
            return (
                f"Table {data.get('table')} uses {data.get('engine') or '-'} engine, "
                f"with estimated rows {data.get('estimated_rows', 0)}.\n"
                f"Created at: {data.get('created_at') or '-'}\n"
                f"Updated at: {data.get('updated_at') or '-'}\n"
                f"Comment: {data.get('comment') or '-'}"
            )
        if intent == "table_indexes":
            indexes = data.get("indexes") or []
            if isinstance(indexes, list) and indexes:
                lines = [f"Indexes on {data.get('table', '')}:"]
                for idx in indexes:
                    lines.append(f"- {idx}")
                return "\n".join(lines)
            return f"Index inspection result: {data}"
        if intent == "table_relations":
            relations = data.get("relations", [])
            if not relations:
                return "No matching table relation was found in memory. Run schema analysis first."
            lines = [f"Found {data.get('relation_count', len(relations))} related relations:"]
            for rel in relations:
                confidence = rel.get("confidence", 0)
                lines.append(
                    f"- {rel.get('source_table')}.{rel.get('fk_column')} -> "
                    f"{rel.get('target_table')}.{rel.get('pk_column')} "
                    f"({rel.get('relation_type', 'N:1')}, confidence={confidence:.2f})"
                )
            return "\n".join(lines)

        tables = data.get("tables", [])
        names = ", ".join(table["name"] for table in tables[:8])
        latest = data.get("latest_analysis") or {}
        relation_count = latest.get("relations", 0)
        return (
            f"Database {data.get('database', '-')} has {data.get('table_count', len(tables))} business tables.\n"
            f"Example tables: {names or '-'}\n"
            f"The latest analysis found {relation_count} relations."
        )

    @staticmethod
    def _extract_table_names(question: str) -> list[str]:
        quoted = re.findall(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]", question)
        if Config.QA_REGEX_BASELINE_FIX:
            words = re.findall(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])", question)
        else:
            words = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", question)
        skip = {"table", "tables", "columns", "column", "index", "indexes", "show", "create", "metadata", "relation", "relationship", "foreign", "key", "schema", "what", "how", "many", "does", "have", "are", "is"}
        names: list[str] = []
        seen: set[str] = set()
        for candidate in quoted + words:
            lower = candidate.lower()
            if lower in skip or lower in seen:
                continue
            names.append(candidate)
            seen.add(lower)
        return names


def _await_sync(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    outcome: dict[str, Any] = {}

    def runner() -> None:
        try:
            outcome["result"] = asyncio.run(awaitable)
        except BaseException as exc:
            outcome["error"] = exc

    thread = Thread(target=runner, name="qa-worker-v2-bridge", daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]

