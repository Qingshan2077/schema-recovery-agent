"""Privacy-safe aggregate profiling tools for the Column hybrid stage."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract
from backend.config import Config
from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


class ColumnContract(StrictContract):
    name: str
    data_type: str
    nullable: bool
    primary_key: bool
    unique: bool


class TableContractOutput(StrictContract):
    database: str
    table: str
    exists: bool
    columns: list[ColumnContract]
    primary_key: list[str]
    candidate_keys: list[list[str]]


class ColumnProfileOutput(StrictContract):
    database: str
    table: str
    column: str
    row_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    null_ratio: float = Field(ge=0, le=1)
    uniqueness_ratio: float = Field(ge=0, le=1)
    privacy_mode: str = "aggregate_only"


class RelationshipProfileOutput(StrictContract):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    source_non_null_count: int = Field(ge=0)
    matched_count: int = Field(ge=0)
    orphan_count: int = Field(ge=0)
    overlap_ratio: float = Field(ge=0, le=1)
    orphan_ratio: float = Field(ge=0, le=1)
    privacy_mode: str = "aggregate_only"


def get_table_contract(table_name: str) -> dict[str, Any]:
    _validate_identifier(table_name)
    columns = MySQLSimulator.execute_query(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    indexes = MySQLSimulator.execute_query(
        """
        SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (table_name,),
    )
    unique_indexes: dict[str, list[str]] = {}
    for index in indexes:
        if int(index["NON_UNIQUE"]) == 0:
            unique_indexes.setdefault(str(index["INDEX_NAME"]), []).append(str(index["COLUMN_NAME"]))
    unique_columns = {item for values in unique_indexes.values() if len(values) == 1 for item in values}
    return {
        "database": Config.DB_NAME,
        "table": table_name,
        "exists": bool(columns),
        "columns": [
            {
                "name": row["COLUMN_NAME"],
                "data_type": row["COLUMN_TYPE"],
                "nullable": row["IS_NULLABLE"] == "YES",
                "primary_key": row["COLUMN_KEY"] == "PRI",
                "unique": row["COLUMN_NAME"] in unique_columns,
            }
            for row in columns
        ],
        "primary_key": [row["COLUMN_NAME"] for row in columns if row["COLUMN_KEY"] == "PRI"],
        "candidate_keys": list(unique_indexes.values()),
    }


def profile_column(table_name: str, column_name: str) -> dict[str, Any]:
    table, column = _assert_catalog_identifiers(table_name, column_name)
    rows = MySQLSimulator.execute_query(
        f"SELECT COUNT(*) AS row_count, SUM(`{column}` IS NULL) AS null_count, COUNT(DISTINCT `{column}`) AS distinct_count FROM `{table}`"
    )
    row = rows[0] if rows else {}
    row_count = int(row.get("row_count") or 0)
    null_count = int(row.get("null_count") or 0)
    distinct_count = int(row.get("distinct_count") or 0)
    non_null = max(row_count - null_count, 0)
    return {
        "database": Config.DB_NAME,
        "table": table_name,
        "column": column_name,
        "row_count": row_count,
        "null_count": null_count,
        "distinct_count": distinct_count,
        "null_ratio": null_count / max(row_count, 1),
        "uniqueness_ratio": distinct_count / max(non_null, 1),
        "privacy_mode": "aggregate_only",
    }


def profile_relationship(source_table: str, source_column: str, target_table: str, target_column: str) -> dict[str, Any]:
    source, source_col = _assert_catalog_identifiers(source_table, source_column)
    target, target_col = _assert_catalog_identifiers(target_table, target_column)
    rows = MySQLSimulator.execute_query(
        f"""SELECT
            COUNT(s.`{source_col}`) AS source_non_null_count,
            SUM(t.`{target_col}` IS NOT NULL) AS matched_count
        FROM `{source}` s
        LEFT JOIN `{target}` t ON s.`{source_col}` = t.`{target_col}`
        WHERE s.`{source_col}` IS NOT NULL"""
    )
    row = rows[0] if rows else {}
    source_count = int(row.get("source_non_null_count") or 0)
    matched = min(source_count, int(row.get("matched_count") or 0))
    orphan = max(source_count - matched, 0)
    return {
        "source_table": source_table,
        "source_column": source_column,
        "target_table": target_table,
        "target_column": target_column,
        "source_non_null_count": source_count,
        "matched_count": matched,
        "orphan_count": orphan,
        "overlap_ratio": matched / max(source_count, 1),
        "orphan_ratio": orphan / max(source_count, 1),
        "privacy_mode": "aggregate_only",
    }


def _assert_catalog_identifiers(table_name: str, column_name: str) -> tuple[str, str]:
    _validate_identifier(table_name)
    _validate_identifier(column_name)
    rows = MySQLSimulator.execute_query(
        "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table_name, column_name),
    )
    if not rows:
        raise ValueError("catalog identifier was not found in the active database")
    return table_name, column_name


def _validate_identifier(value: str) -> None:
    if not value or not value.replace("_", "a").isalnum():
        raise ValueError("identifier contains unsupported characters")


def register_all(registry: ToolRegistry) -> None:
    common = dict(side_effect="read", approval_policy="never", idempotent=True, ready_for_agent=True, sensitivity="internal")
    registry.register(
        "recovery.get_table_contract", get_table_contract, "Read table columns and candidate keys without row values",
        {"type": "object", "properties": {"table_name": {"type": "string"}}, "required": ["table_name"], "additionalProperties": False},
        output_model=TableContractOutput, capability="column_profile:read", **common,
    )
    registry.register(
        "recovery.profile_column", profile_column, "Return aggregate-only null and uniqueness statistics",
        {"type": "object", "properties": {"table_name": {"type": "string"}, "column_name": {"type": "string"}}, "required": ["table_name", "column_name"], "additionalProperties": False},
        output_model=ColumnProfileOutput, capability="column_profile:read", **common,
    )
    registry.register(
        "recovery.profile_relationship", profile_relationship, "Return aggregate-only overlap and orphan ratios",
        {"type": "object", "properties": {"source_table": {"type": "string"}, "source_column": {"type": "string"}, "target_table": {"type": "string"}, "target_column": {"type": "string"}}, "required": ["source_table", "source_column", "target_table", "target_column"], "additionalProperties": False},
        output_model=RelationshipProfileOutput, capability="column_profile:read", **common,
    )
