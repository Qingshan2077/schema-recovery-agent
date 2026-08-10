"""Guarded DBA worker for schema changes."""

from __future__ import annotations

import re

from backend.agent.orchestrator import Orchestrator
from backend.agent.workers.base import BaseWorker


class DBAWorker(BaseWorker):
    SAFE = "safe"
    CONFIRM = "confirm"
    DANGEROUS = "dangerous"
    CONFIRM_WORDS = {"confirm", "yes", "execute", "ok", "\u786e\u8ba4", "\u6211\u786e\u8ba4", "\u6267\u884c"}

    def run(self, context: dict) -> dict:
        question = context.get("question", "")
        confirmed = bool(context.get("confirmed")) or question.strip().lower() in self.CONFIRM_WORDS
        pending = context.get("pending_operation")
        parsed = pending if pending else self._parse_intent(question)
        safety_level = self._classify_safety(parsed.get("sql_type", ""), parsed.get("ddl_statement", ""))

        if parsed.get("intent") == "show_create_table":
            data = self.call_tool("show_create_table", table_name=parsed["table_name"])
            if data.get("error"):
                return {"status": "error", "message": data["error"], "data": data}
            return {"status": "success", "message": f"```sql\n{data['create_sql']}\n```", "data": data}

        if parsed.get("status") == "unsupported":
            return {
                "status": "error",
                "message": "I could not generate a safe DDL statement from this request. Please provide table name, column name, and data type.",
                "pending_operation": parsed,
            }

        if safety_level in {self.CONFIRM, self.DANGEROUS} and not confirmed:
            prompt = "Dangerous operation requires explicit confirmation" if safety_level == self.DANGEROUS else "Confirm this schema change"
            return {
                "status": "need_confirmation",
                "message": f"{prompt}:\n```sql\n{parsed['ddl_statement']};\n```",
                "pending_operation": parsed,
                "safety_level": safety_level,
            }

        result = self.call_tool("execute_ddl", sql=parsed["ddl_statement"])
        if not result.get("success"):
            return {"status": "error", "message": f"Execution failed: {result.get('error', 'unknown error')}", "data": result}

        analysis = Orchestrator(self.tool_registry).run_full_analysis()
        total_relations = analysis.get("merge_result", {}).get("summary", {}).get("total_relations", 0)
        return {
            "status": "success",
            "message": f"Operation executed: {parsed.get('summary', parsed['ddl_statement'])}\nRe-analysis finished and found {total_relations} relations.",
            "ddl_executed": parsed["ddl_statement"],
            "new_analysis": analysis,
        }

    def _parse_intent(self, question: str) -> dict:
        q = question.strip()
        lower = q.lower()
        table = self._extract_table_name(q)

        if any(keyword in lower for keyword in ["show create", "create table", "\u5efa\u8868\u8bed\u53e5"]):
            return {"intent": "show_create_table", "table_name": table or self._extract_first_identifier(q)}

        raw_sql = self._extract_sql(q)
        if raw_sql:
            return {
                "intent": "ddl",
                "sql_type": raw_sql.split()[0].upper(),
                "ddl_statement": raw_sql.rstrip(";"),
                "summary": "execute user-provided DDL",
            }

        if any(keyword in lower for keyword in ["drop", "delete table", "\u5220\u9664\u8868", "\u5220\u6389", "\u5220\u8868"]):
            if table:
                return {
                    "intent": "ddl",
                    "sql_type": "DROP",
                    "ddl_statement": f"DROP TABLE IF EXISTS `{table}`",
                    "summary": f"drop table {table}",
                }

        add_column = self._parse_add_column(q, table)
        if add_column:
            return add_column

        create_table = self._parse_create_table(q, table)
        if create_table:
            return create_table

        return {"status": "unsupported", "intent": "ddl", "sql_type": "UNKNOWN", "question": question}

    def _classify_safety(self, sql_type: str, ddl_statement: str) -> str:
        upper = f"{sql_type} {ddl_statement}".upper()
        if any(keyword in upper for keyword in ["DROP", "TRUNCATE", "ALTER TABLE", " DROP COLUMN"]):
            return self.DANGEROUS if any(keyword in upper for keyword in ["DROP", "TRUNCATE", "DROP COLUMN"]) else self.CONFIRM
        if sql_type.upper() in {"CREATE", "ALTER", "RENAME"}:
            return self.CONFIRM
        return self.SAFE

    @staticmethod
    def _extract_sql(text: str) -> str | None:
        fenced = re.search(r"```sql\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        stripped = text.strip()
        if re.match(r"^(CREATE|ALTER|DROP|TRUNCATE|RENAME)\b", stripped, flags=re.IGNORECASE):
            return stripped
        return None

    @staticmethod
    def _extract_table_name(text: str) -> str | None:
        patterns = [
            r"(?:table|\u8868)\s*`?([A-Za-z_][A-Za-z0-9_]*)`?",
            r"`?([A-Za-z_][A-Za-z0-9_]*)`?\s*(?:table|\u8868)",
            r"(?:in|on|from|to)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _extract_first_identifier(text: str) -> str | None:
        match = re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text)
        return match.group(0) if match else None

    def _parse_add_column(self, text: str, table: str | None) -> dict | None:
        if not table or not any(keyword in text.lower() for keyword in ["add", "\u6dfb\u52a0", "\u65b0\u589e", "\u52a0"]):
            return None
        column_match = re.search(r"`?([A-Za-z_][A-Za-z0-9_]*)`?\s*(?:field|column|\u5b57\u6bb5)?", text)
        identifiers = re.findall(r"`?([A-Za-z_][A-Za-z0-9_]*)`?", text)
        candidates = [item for item in identifiers if item != table and item.lower() not in {"add", "column", "field", "table", "alter", "to", "in", "on"}]
        column = candidates[0] if candidates else (column_match.group(1) if column_match else None)
        type_match = re.search(r"\b(varchar\(\d+\)|decimal\(\d+,\d+\)|int|bigint|datetime|date|text|json|tinyint)\b", text, flags=re.IGNORECASE)
        column_type = type_match.group(1).upper() if type_match else "VARCHAR(255)"
        if not column:
            return None
        return {
            "intent": "ddl",
            "sql_type": "ALTER",
            "ddl_statement": f"ALTER TABLE `{table}` ADD COLUMN `{column}` {column_type}",
            "summary": f"add column {column} to table {table}",
        }

    def _parse_create_table(self, text: str, table: str | None) -> dict | None:
        if not table or not any(keyword in text.lower() for keyword in ["create", "new table", "\u65b0\u5efa", "\u521b\u5efa", "\u5efa\u4e00\u4e2a", "\u5efa\u8868"]):
            return None
        return {
            "intent": "ddl",
            "sql_type": "CREATE",
            "ddl_statement": f"CREATE TABLE `{table}` (`id` BIGINT PRIMARY KEY AUTO_INCREMENT, `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "summary": f"create table {table}",
        }

