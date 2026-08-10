"""Low-reliability fallback for SQL fragments rejected by the primary parser."""

from __future__ import annotations

import hashlib
import re

from backend.parsers.sql.base import SQLLineageFact, SQLParseResult, SourceLocator


class RegexFallbackParser:
    name = "regex_fallback"
    version = "1.0.0"
    dialects = {"*"}

    def parse(self, sql: str, *, dialect: str, source_uri: str, asset_kind: str) -> SQLParseResult:
        facts: list[SQLLineageFact] = []
        for match in re.finditer(r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", sql):
            fragment = match.group(0)
            facts.append(
                SQLLineageFact(
                    fact_kind="join",
                    left_table=match.group(1).casefold(),
                    left_column=match.group(2).casefold(),
                    right_table=match.group(3).casefold(),
                    right_column=match.group(4).casefold(),
                    referenced_tables=[match.group(1).casefold(), match.group(3).casefold()],
                    locator=SourceLocator(
                        source_uri=source_uri,
                        start_offset=match.start(),
                        end_offset=match.end(),
                        line=sql.count("\n", 0, match.start()) + 1,
                        fragment_hash=hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
                    ),
                    parser=self.name,
                    parser_version=self.version,
                    reliability=0.45,
                    unresolved_reason="regex_fallback_requires_verification",
                )
            )
        return SQLParseResult(
            dialect=dialect,
            parser=self.name,
            parser_version=self.version,
            facts=facts,
            warnings=["low_reliability_regex_fallback"],
            fallback_used=True,
            source_hash=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        )
