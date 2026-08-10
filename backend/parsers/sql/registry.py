"""SQL parser registry with sqlparse-tokenized primary and regex fallback."""

from __future__ import annotations

import hashlib
import re

import sqlparse

from backend.parsers.sql.base import SQLLineageFact, SQLParseResult, SourceLocator
from backend.parsers.sql.fallback_regex import RegexFallbackParser


class SqlparseLineageParser:
    name = "sqlparse_lineage"
    version = "1.0.0"
    dialects = {"mysql", "postgresql", "sqlite", "generic"}

    def parse(self, sql: str, *, dialect: str, source_uri: str, asset_kind: str) -> SQLParseResult:
        statements = sqlparse.parse(sql)
        if not statements:
            return SQLParseResult(
                dialect=dialect,
                parser=self.name,
                parser_version=self.version,
                facts=[],
                warnings=["empty_or_unparseable_sql"],
                source_hash=_hash(sql),
            )
        normalized = " ".join(str(statement) for statement in statements)
        aliases = _aliases(normalized)
        ctes = _cte_names(normalized)
        facts: list[SQLLineageFact] = []
        join_pattern = re.compile(
            r"(?P<left>[`\w]+)\.(?P<left_col>[`\w]+)\s*=\s*(?P<right>[`\w]+)\.(?P<right_col>[`\w]+)",
            re.IGNORECASE,
        )
        for match in join_pattern.finditer(normalized):
            left_alias = _identifier(match.group("left"))
            right_alias = _identifier(match.group("right"))
            left = aliases.get(left_alias, left_alias)
            right = aliases.get(right_alias, right_alias)
            prefix = normalized[max(0, match.start() - 120):match.start()].casefold()
            kind = "update_join" if "update" in prefix else "join"
            if left in ctes or right in ctes:
                kind = "cte"
            if "select" in prefix and prefix.rfind("(") > prefix.rfind("join"):
                kind = "subquery"
            facts.append(
                SQLLineageFact(
                    fact_kind=kind,
                    left_table=left,
                    left_column=_identifier(match.group("left_col")),
                    right_table=right,
                    right_column=_identifier(match.group("right_col")),
                    referenced_tables=sorted({left, right}),
                    locator=_locator(normalized, match.start(), match.end(), source_uri),
                    parser=self.name,
                    parser_version=self.version,
                    reliability=0.92 if kind in {"join", "update_join"} else 0.82,
                )
            )
        if asset_kind == "trigger":
            for match in re.finditer(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+`?(\w+)`?", normalized, re.IGNORECASE):
                table = _identifier(match.group(1))
                facts.append(
                    SQLLineageFact(
                        fact_kind="trigger",
                        referenced_tables=[table],
                        locator=_locator(normalized, match.start(), match.end(), source_uri),
                        parser=self.name,
                        parser_version=self.version,
                        reliability=0.85,
                        unresolved_reason="table_level_reference_without_column_pair",
                    )
                )
        warnings = [] if facts else ["no_lineage_facts_extracted"]
        return SQLParseResult(
            dialect=dialect,
            parser=self.name,
            parser_version=self.version,
            facts=facts,
            warnings=warnings,
            source_hash=_hash(sql),
        )


class SQLParserRegistry:
    def __init__(self):
        self._parsers = [SqlparseLineageParser()]
        self._fallback = RegexFallbackParser()

    def parse(self, sql: str, *, dialect: str, source_uri: str, asset_kind: str) -> SQLParseResult:
        normalized_dialect = dialect.casefold()
        parser = next((item for item in self._parsers if normalized_dialect in item.dialects), None)
        if parser is None:
            return self._fallback.parse(sql, dialect=dialect, source_uri=source_uri, asset_kind=asset_kind)
        result = parser.parse(sql, dialect=dialect, source_uri=source_uri, asset_kind=asset_kind)
        if result.facts:
            return result
        fallback = self._fallback.parse(sql, dialect=dialect, source_uri=source_uri, asset_kind=asset_kind)
        return fallback.model_copy(update={"warnings": result.warnings + fallback.warnings, "fallback_used": True})


def _aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in re.finditer(r"\b(?:FROM|JOIN|UPDATE)\s+`?(\w+)`?(?:\s+(?:AS\s+)?`?(\w+)`?)?", sql, re.IGNORECASE):
        table = _identifier(match.group(1))
        alias = _identifier(match.group(2) or table)
        if alias.upper() in {"ON", "WHERE", "SET", "JOIN", "LEFT", "RIGHT", "INNER"}:
            alias = table
        aliases[alias] = table
        aliases[table] = table
    return aliases


def _cte_names(sql: str) -> set[str]:
    return {_identifier(match.group(1)) for match in re.finditer(r"(?:\bWITH|,)\s*`?(\w+)`?\s+AS\s*\(", sql, re.IGNORECASE)}


def _identifier(value: str) -> str:
    return value.strip().strip("`").casefold()


def _locator(sql: str, start: int, end: int, source_uri: str) -> SourceLocator:
    fragment = sql[start:end]
    return SourceLocator(
        source_uri=source_uri,
        start_offset=start,
        end_offset=end,
        line=sql.count("\n", 0, start) + 1,
        fragment_hash=_hash(fragment),
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
