"""DBA tools for guarded schema changes."""

from __future__ import annotations

import re

from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator

def show_create_table(table_name: str) -> dict:
    safe_name = _safe_identifier(table_name)
    rows = MySQLSimulator.execute_query(f"SHOW CREATE TABLE `{safe_name}`")
    if not rows:
        return {"error": f"Table '{table_name}' not found"}
    create_sql = rows[0].get("Create Table") or rows[0].get("Create View") or ""
    return {"table": safe_name, "create_sql": create_sql}


def _safe_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid identifier: {name}")
    return name


def register_all(registry: ToolRegistry):
    # Mutating DDL is deliberately absent from the ordinary ToolRegistry.
    # Phase 7 execution is available only through PrivilegedDDLAdapter.
    registry.register(
        "show_create_table",
        show_create_table,
        "Show CREATE TABLE SQL",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
    )
