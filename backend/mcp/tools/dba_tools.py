"""DBA tools for guarded schema changes."""

from __future__ import annotations

import re

from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator

ALLOWED_DDL_PREFIXES = ("CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME")
DISALLOWED_DML_PREFIXES = ("INSERT", "UPDATE", "DELETE", "SELECT", "REPLACE", "MERGE")
PROTECTED_TABLES = {"users", "orders", "products", "information_schema", "mysql", "performance_schema", "sys"}


def execute_ddl(sql: str) -> dict:
    statement = _single_statement(sql)
    upper = statement.upper()
    if not upper.startswith(ALLOWED_DDL_PREFIXES):
        return {"success": False, "error": "Only DDL statements are allowed."}
    if upper.startswith(DISALLOWED_DML_PREFIXES):
        return {"success": False, "error": "DML statements are not allowed."}

    protected = _find_protected_table(statement)
    if protected:
        return {"success": False, "error": f"Operation on protected table '{protected}' is not allowed."}

    try:
        MySQLSimulator.execute_query(statement)
        return {"success": True, "sql": statement}
    except Exception as exc:
        return {"success": False, "error": str(exc), "sql": statement}


def show_create_table(table_name: str) -> dict:
    safe_name = _safe_identifier(table_name)
    rows = MySQLSimulator.execute_query(f"SHOW CREATE TABLE `{safe_name}`")
    if not rows:
        return {"error": f"Table '{table_name}' not found"}
    create_sql = rows[0].get("Create Table") or rows[0].get("Create View") or ""
    return {"table": safe_name, "create_sql": create_sql}


def _single_statement(sql: str) -> str:
    statement = sql.strip().rstrip(";")
    if ";" in statement:
        raise ValueError("Only a single DDL statement is allowed.")
    return statement


def _safe_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid identifier: {name}")
    return name


def _find_protected_table(sql: str) -> str | None:
    tokens = {token.lower() for token in re.findall(r"`?([A-Za-z_][A-Za-z0-9_]*)`?", sql)}
    return next((table for table in PROTECTED_TABLES if table in tokens), None)


def register_all(registry: ToolRegistry):
    registry.register(
        "execute_ddl",
        execute_ddl,
        "Execute a guarded DDL statement",
        {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
    )
    registry.register(
        "show_create_table",
        show_create_table,
        "Show CREATE TABLE SQL",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
    )
