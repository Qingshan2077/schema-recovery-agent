"""Question-answering tools for schema chat."""

from __future__ import annotations

from backend.agent.memory.schema_memory import SchemaMemory
from backend.config import Config
from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


def query_table_columns(table_name: str) -> dict:
    rows = MySQLSimulator.execute_query(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
               COLUMN_KEY, COLUMN_DEFAULT, COLUMN_COMMENT, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    return {
        "table": table_name,
        "columns": [
            {
                "name": row["COLUMN_NAME"],
                "type": row["COLUMN_TYPE"],
                "nullable": row["IS_NULLABLE"] == "YES",
                "key": row["COLUMN_KEY"] or "",
                "default": row["COLUMN_DEFAULT"],
                "comment": row["COLUMN_COMMENT"] or "",
                "extra": row["EXTRA"] or "",
            }
            for row in rows
        ],
        "column_count": len(rows),
    }


def query_table_metadata(table_name: str) -> dict:
    rows = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, ENGINE, TABLE_ROWS, TABLE_COMMENT, CREATE_TIME, UPDATE_TIME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    if not rows:
        return {"error": f"Table '{table_name}' not found"}
    row = rows[0]
    return {
        "table": row["TABLE_NAME"],
        "engine": row["ENGINE"],
        "estimated_rows": row["TABLE_ROWS"] or 0,
        "comment": row["TABLE_COMMENT"] or "",
        "created_at": str(row["CREATE_TIME"] or ""),
        "updated_at": str(row["UPDATE_TIME"] or ""),
    }


def query_saved_relations(source_table: str | None = None, target_table: str | None = None) -> dict:
    relations = SchemaMemory().query_similar_relations(source_table, target_table)
    return {"relation_count": len(relations), "relations": relations}


def database_overview() -> dict:
    tables = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
    )
    history = SchemaMemory().get_history(limit=1)
    latest = history[0] if history else {}
    return {
        "database": Config.DB_NAME,
        "table_count": len(tables),
        "tables": [
            {
                "name": row["TABLE_NAME"],
                "row_estimate": row["TABLE_ROWS"] or 0,
                "comment": row["TABLE_COMMENT"] or "",
            }
            for row in tables
        ],
        "latest_analysis": latest,
    }


def register_all(registry: ToolRegistry):
    registry.register(
        "query_table_columns",
        query_table_columns,
        "Query table columns for schema Q&A",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
    )
    registry.register(
        "query_table_metadata",
        query_table_metadata,
        "Query table metadata for schema Q&A",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"]},
    )
    registry.register(
        "query_saved_relations",
        query_saved_relations,
        "Query persisted discovered relations",
        {
            "type": "object",
            "properties": {
                "source_table": {"type": "string"},
                "target_table": {"type": "string"},
            },
        },
    )
    registry.register("database_overview", database_overview, "Summarize database inventory and latest analysis", {"type": "object"})
