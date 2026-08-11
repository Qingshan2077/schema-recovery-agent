"""Conservative SQL parser boundary: unsupported or ambiguous DDL is blocked."""

from __future__ import annotations

import re
import sqlparse


class DDLValidationError(ValueError):
    pass


ALLOWED = {"CREATE", "ALTER", "DROP", "RENAME"}


def validate_and_normalize(statements: list[str], *, dialect: str) -> tuple[list[str], dict]:
    normalized = []
    ast_statements = []
    for raw in statements:
        parsed = [item for item in sqlparse.parse(raw) if str(item).strip()]
        if len(parsed) != 1: raise DDLValidationError("multiple_or_empty_statements")
        statement = parsed[0]
        kind = statement.get_type().upper()
        if kind not in ALLOWED: raise DDLValidationError(f"unsupported_ddl:{kind}")
        canonical = sqlparse.format(str(statement).strip().rstrip(";"), keyword_case="upper", strip_comments=True, reindent=False)
        if ";" in canonical: raise DDLValidationError("multiple_statements")
        targets = _targets(canonical)
        if not targets: raise DDLValidationError("target_object_unresolved")
        normalized.append(canonical)
        ast_statements.append({"type": kind, "target_objects": targets, "canonical_sql_hash_input": canonical, "dialect": dialect})
    return normalized, {"dialect": dialect, "statements": ast_statements}


def _targets(sql: str) -> list[str]:
    matches = re.findall(r"(?i)\b(?:TABLE|INDEX|VIEW)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?[`\"]?([A-Za-z_][A-Za-z0-9_.$]*)", sql)
    return list(dict.fromkeys(matches))
