"""Agent-ready, read-only catalog and evidence tools for schema QA."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from backend.agent.memory.schema_memory import SchemaMemory
from backend.agent.runtime.contracts import StrictContract
from backend.config import Config
from backend.core.identity import stable_id
from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


def _catalog_version() -> str:
    return stable_id("snapshot", Config.DB_HOST, Config.DB_PORT, Config.DB_NAME, "live-catalog")


def _table_id(name: str) -> str:
    return stable_id("catalog", Config.DB_NAME, Config.DB_NAME, "table", name)


class TableItem(StrictContract):
    entity_id: str
    database: str
    schema_name: str
    name: str
    kind: str = "table"
    aliases: list[str] = Field(default_factory=list)
    row_estimate: int = 0
    comment: str = ""


class ListTablesOutput(StrictContract):
    database: str
    catalog_version: str
    tables: list[TableItem]
    table_count: int = Field(ge=0)


class ColumnItem(StrictContract):
    ordinal: int = Field(ge=1)
    name: str
    data_type: str
    nullable: bool
    key: str = ""
    default: Any = None
    comment: str = ""
    extra: str = ""


class TableColumnsOutput(StrictContract):
    database: str
    catalog_version: str
    table_id: str
    table: str
    exists: bool
    columns: list[ColumnItem]
    column_count: int = Field(ge=0)


class TableMetadataOutput(StrictContract):
    database: str
    catalog_version: str
    table_id: str
    table: str
    exists: bool
    engine: str = ""
    estimated_rows: int = 0
    comment: str = ""
    created_at: str = ""
    updated_at: str = ""


class IndexItem(StrictContract):
    name: str
    unique: bool
    index_type: str
    columns: list[str]


class TableIndexesOutput(StrictContract):
    database: str
    catalog_version: str
    table_id: str
    table: str
    indexes: list[IndexItem]
    index_count: int = Field(ge=0)


class RelationItem(StrictContract):
    relation_id: str
    source_table: str
    fk_column: str
    target_table: str
    pk_column: str
    relation_type: str
    confidence: float = Field(ge=0, le=1)
    evidence_source: str = "schema_memory"


class RelationsOutput(StrictContract):
    database: str
    catalog_version: str
    relations: list[RelationItem]
    relation_count: int = Field(ge=0)


class AnalysisStatusOutput(StrictContract):
    database: str
    catalog_version: str
    available: bool
    latest_analysis: dict[str, Any]


def list_tables() -> dict[str, Any]:
    rows = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT, TABLE_TYPE
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY TABLE_NAME
        """
    )
    tables = [
        {
            "entity_id": _table_id(str(row["TABLE_NAME"])),
            "database": Config.DB_NAME,
            "schema_name": Config.DB_NAME,
            "name": str(row["TABLE_NAME"]),
            "kind": "view" if row.get("TABLE_TYPE") == "VIEW" else "table",
            "aliases": [],
            "row_estimate": int(row.get("TABLE_ROWS") or 0),
            "comment": str(row.get("TABLE_COMMENT") or ""),
        }
        for row in rows
    ]
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "tables": tables,
        "table_count": len(tables),
    }


def query_table_columns(table_name: str) -> dict[str, Any]:
    rows = MySQLSimulator.execute_query(
        """
        SELECT ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
               COLUMN_KEY, COLUMN_DEFAULT, COLUMN_COMMENT, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "table_id": _table_id(table_name),
        "table": table_name,
        "exists": bool(rows),
        "columns": [
            {
                "ordinal": int(row["ORDINAL_POSITION"]),
                "name": str(row["COLUMN_NAME"]),
                "data_type": str(row["COLUMN_TYPE"]),
                "nullable": row["IS_NULLABLE"] == "YES",
                "key": str(row.get("COLUMN_KEY") or ""),
                "default": row.get("COLUMN_DEFAULT"),
                "comment": str(row.get("COLUMN_COMMENT") or ""),
                "extra": str(row.get("EXTRA") or ""),
            }
            for row in rows
        ],
        "column_count": len(rows),
    }


def query_table_metadata(table_name: str) -> dict[str, Any]:
    rows = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, ENGINE, TABLE_ROWS, TABLE_COMMENT, CREATE_TIME, UPDATE_TIME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    row = rows[0] if rows else {}
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "table_id": _table_id(table_name),
        "table": table_name,
        "exists": bool(rows),
        "engine": str(row.get("ENGINE") or ""),
        "estimated_rows": int(row.get("TABLE_ROWS") or 0),
        "comment": str(row.get("TABLE_COMMENT") or ""),
        "created_at": str(row.get("CREATE_TIME") or ""),
        "updated_at": str(row.get("UPDATE_TIME") or ""),
    }


def query_indexes(table_name: str) -> dict[str, Any]:
    rows = MySQLSimulator.execute_query(
        """
        SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX, INDEX_TYPE
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (table_name,),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row["INDEX_NAME"])
        grouped.setdefault(
            name,
            {
                "name": name,
                "unique": int(row["NON_UNIQUE"]) == 0,
                "index_type": str(row.get("INDEX_TYPE") or ""),
                "columns": [],
            },
        )["columns"].append(str(row["COLUMN_NAME"]))
    indexes = list(grouped.values())
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "table_id": _table_id(table_name),
        "table": table_name,
        "indexes": indexes,
        "index_count": len(indexes),
    }


def query_relations(source_table: str | None = None, target_table: str | None = None) -> dict[str, Any]:
    rows = SchemaMemory().query_similar_relations(source_table, target_table)
    relations = []
    for row in rows:
        source = str(row.get("source_table") or "")
        target = str(row.get("target_table") or "")
        fk_column = str(row.get("fk_column") or "")
        pk_column = str(row.get("pk_column") or "id")
        relations.append(
            {
                "relation_id": str(row.get("relation_id") or stable_id("relation", source, fk_column, target, pk_column)),
                "source_table": source,
                "fk_column": fk_column,
                "target_table": target,
                "pk_column": pk_column,
                "relation_type": str(row.get("relation_type") or "N:1"),
                "confidence": max(0.0, min(1.0, float(row.get("confidence") or 0))),
                "evidence_source": "schema_memory",
            }
        )
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "relations": relations,
        "relation_count": len(relations),
    }


def get_analysis_status() -> dict[str, Any]:
    history = SchemaMemory().get_history(limit=1)
    return {
        "database": Config.DB_NAME,
        "catalog_version": _catalog_version(),
        "available": bool(history),
        "latest_analysis": history[0] if history else {},
    }


def register_all(registry: ToolRegistry) -> None:
    common = {
        "side_effect": "read",
        "approval_policy": "never",
        "idempotent": True,
        "ready_for_agent": True,
        "sensitivity": "internal",
        "max_retries": 1,
    }
    registry.register(
        "catalog.list_tables",
        list_tables,
        "List the visible database catalog using a stable entity identity.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        output_model=ListTablesOutput,
        capability="catalog:read",
        **common,
    )
    registry.register(
        "catalog.query_table_columns",
        query_table_columns,
        "Read ordered column facts for one exactly resolved table.",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"], "additionalProperties": False},
        output_model=TableColumnsOutput,
        capability="catalog:read",
        **common,
    )
    registry.register(
        "catalog.query_table_metadata",
        query_table_metadata,
        "Read metadata for one exactly resolved table.",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"], "additionalProperties": False},
        output_model=TableMetadataOutput,
        capability="catalog:read",
        **common,
    )
    registry.register(
        "catalog.query_indexes",
        query_indexes,
        "Read index facts for one exactly resolved table.",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"], "additionalProperties": False},
        output_model=TableIndexesOutput,
        capability="catalog:read",
        **common,
    )
    registry.register(
        "evidence.query_relations",
        query_relations,
        "Read persisted relation evidence, optionally filtered by exact table names.",
        {
            "type": "object",
            "properties": {"source_table": {"type": "string"}, "target_table": {"type": "string"}},
            "additionalProperties": False,
        },
        output_model=RelationsOutput,
        capability="evidence:read",
        **common,
    )
    registry.register(
        "analysis.get_status",
        get_analysis_status,
        "Read the latest persisted schema analysis status.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        output_model=AnalysisStatusOutput,
        capability="analysis:read",
        **common,
    )
