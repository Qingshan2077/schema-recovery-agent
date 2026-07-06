"""Survey tools for collecting database inventory."""

from __future__ import annotations

import os

from backend.config import Config
from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


def connect_database():
    try:
        result = MySQLSimulator.execute_query("SELECT VERSION() AS version")
        return {"connected": True, "server_version": result[0]["version"], "database": Config.DB_NAME}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def list_tables():
    result = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, ENGINE, TABLE_COMMENT, TABLE_ROWS
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
    )
    return {
        "table_count": len(result),
        "tables": [
            {
                "name": r["TABLE_NAME"],
                "engine": r["ENGINE"],
                "table_comment": r["TABLE_COMMENT"] or "",
                "row_estimate": r["TABLE_ROWS"] or 0,
            }
            for r in result
        ],
    }


def list_views():
    result = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME AS view_name, VIEW_DEFINITION
        FROM information_schema.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME
        """
    )
    return {
        "view_count": len(result),
        "views": [{"name": r["view_name"], "definition": r["VIEW_DEFINITION"]} for r in result],
    }


def list_stored_procedures():
    result = MySQLSimulator.execute_query(
        """
        SELECT ROUTINE_NAME, ROUTINE_DEFINITION
        FROM information_schema.ROUTINES
        WHERE ROUTINE_SCHEMA = DATABASE()
          AND ROUTINE_TYPE = 'PROCEDURE'
        ORDER BY ROUTINE_NAME
        """
    )
    return {
        "procedure_count": len(result),
        "procedures": [{"name": r["ROUTINE_NAME"], "definition": r["ROUTINE_DEFINITION"]} for r in result],
    }


def find_orm_configs(path: str = "/app/data/orm"):
    if not os.path.exists(path):
        local_path = os.path.join(os.getcwd(), "data", "orm")
        path = local_path if os.path.exists(local_path) else path
    if not os.path.exists(path):
        return {"file_count": 0, "files": [], "error": f"Path {path} not found"}

    files = []
    for file_name in sorted(os.listdir(path)):
        if file_name.endswith(".xml"):
            filepath = os.path.join(path, file_name)
            with open(filepath, "r", encoding="utf-8") as fh:
                files.append({"path": filepath, "content": fh.read()})
    return {"file_count": len(files), "files": files}


def list_triggers():
    result = MySQLSimulator.execute_query(
        """
        SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, ACTION_TIMING, ACTION_STATEMENT
        FROM information_schema.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE()
        ORDER BY TRIGGER_NAME
        """
    )
    return {
        "trigger_count": len(result),
        "triggers": [
            {
                "name": r["TRIGGER_NAME"],
                "event": f"{r['ACTION_TIMING']} {r['EVENT_MANIPULATION']}",
                "table": r["EVENT_OBJECT_TABLE"],
                "definition": r["ACTION_STATEMENT"],
            }
            for r in result
        ],
    }


def register_all(registry: ToolRegistry):
    registry.register("connect_database", connect_database, "Test database connection", {"type": "object"})
    registry.register("list_tables", list_tables, "List base tables", {"type": "object"})
    registry.register("list_views", list_views, "List views", {"type": "object"})
    registry.register("list_stored_procedures", list_stored_procedures, "List stored procedures", {"type": "object"})
    registry.register(
        "find_orm_configs",
        find_orm_configs,
        "Find ORM XML files",
        {"type": "object", "properties": {"path": {"type": "string", "default": "/app/data/orm"}}},
    )
    registry.register("list_triggers", list_triggers, "List triggers", {"type": "object"})

