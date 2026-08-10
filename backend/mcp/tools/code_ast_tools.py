"""Agent-ready SQL lineage parser tool."""

from __future__ import annotations

from backend.mcp.tool_registry import ToolRegistry
from backend.parsers.sql.base import SQLParseResult
from backend.parsers.sql.registry import SQLParserRegistry


def parse_sql_asset(sql: str, dialect: str, source_uri: str, asset_kind: str) -> dict:
    return SQLParserRegistry().parse(
        sql,
        dialect=dialect,
        source_uri=source_uri,
        asset_kind=asset_kind,
    ).model_dump(mode="json")


def register_all(registry: ToolRegistry) -> None:
    registry.register(
        "recovery.parse_sql_asset",
        parse_sql_asset,
        "Parse SQL with a dialect-aware tokenized parser and low-reliability fallback",
        {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "dialect": {"type": "string"},
                "source_uri": {"type": "string"},
                "asset_kind": {"type": "string", "enum": ["view", "procedure", "trigger", "query"]},
            },
            "required": ["sql", "dialect", "source_uri", "asset_kind"],
            "additionalProperties": False,
        },
        output_model=SQLParseResult,
        capability="sql_ast:read",
        side_effect="none",
        approval_policy="never",
        idempotent=True,
        ready_for_agent=True,
        sensitivity="internal",
    )
