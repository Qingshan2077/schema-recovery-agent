"""Dialect-aware SQL parser contracts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract


class SourceLocator(StrictContract):
    source_uri: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    line: int = Field(ge=1)
    fragment_hash: str


class SQLLineageFact(StrictContract):
    fact_kind: Literal["join", "cte", "subquery", "trigger", "update_join", "table_ref", "unresolved"]
    left_table: str | None = None
    left_column: str | None = None
    right_table: str | None = None
    right_column: str | None = None
    referenced_tables: list[str] = Field(default_factory=list)
    locator: SourceLocator
    parser: str
    parser_version: str
    reliability: float = Field(ge=0, le=1)
    unresolved_reason: str | None = None


class SQLParseResult(StrictContract):
    dialect: str
    parser: str
    parser_version: str
    facts: list[SQLLineageFact]
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    source_hash: str


class SQLParser(Protocol):
    name: str
    version: str
    dialects: set[str]

    def parse(self, sql: str, *, dialect: str, source_uri: str, asset_kind: str) -> SQLParseResult: ...
