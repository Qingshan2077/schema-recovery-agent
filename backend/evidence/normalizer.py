"""Canonical relation claims, locators and immutable evidence dedupe keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.agent.memory.contracts import MemoryNamespace
from backend.core.identity import stable_id


def canonical_claim_key(
    namespace: MemoryNamespace,
    *,
    source_table_id: str,
    source_column_ids: list[str],
    target_table_id: str,
    target_column_ids: list[str],
    cardinality: str,
) -> str:
    namespace.require_l2()
    payload = {
        "namespace": namespace.project_key(),
        "source_table_id": source_table_id,
        "source_column_ids": list(source_column_ids),
        "target_table_id": target_table_id,
        "target_column_ids": list(target_column_ids),
        "cardinality": cardinality,
    }
    return f"claim_{_hash(payload)}"


def relation_id_for_claim(claim_key: str) -> str:
    return stable_id("relation", claim_key)


def evidence_dedupe_key(
    *,
    excerpt_hash: str | None,
    source_locator: dict[str, Any],
    claim_key: str,
    producer_version: str,
) -> str:
    return _hash({
        "excerpt_hash": excerpt_hash,
        "source_locator": normalize_locator(source_locator),
        "claim_key": claim_key,
        "producer_version": producer_version,
    })


def normalize_locator(locator: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _normalize_value(value)
        for key, value in sorted(locator.items(), key=lambda item: str(item[0]))
    }


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return normalize_locator(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
