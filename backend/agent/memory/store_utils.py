"""Serialization and namespace helpers shared by memory stores."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.agent.memory.contracts import MemoryNamespace


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def namespace_columns(namespace: MemoryNamespace, *, layer: str) -> tuple[str, str, str, str, str]:
    if layer == "l1":
        namespace.require_l1()
    elif layer == "l2":
        namespace.require_l2()
    return (
        namespace.canonical_tenant_id,
        namespace.canonical_project_id,
        namespace.canonical_connection_id or "",
        namespace.canonical_database_name or "",
        namespace.canonical_schema_name or "",
    )


def lexical_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = "".join(character if character.isalnum() else " " for character in value.casefold())
        tokens.update(item for item in normalized.split() if item)
    return tokens
