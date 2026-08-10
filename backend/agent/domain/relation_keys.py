"""Namespace-safe stable identities for relation claims."""

from __future__ import annotations

import hashlib
import json

from backend.core.identity import stable_id


def normalize_columns(columns: list[str]) -> tuple[str, ...]:
    return tuple(column.strip().strip("`").casefold() for column in columns)


def build_claim_key(
    *,
    project_id: str,
    connection_id: str,
    schema_name: str,
    snapshot_id: str,
    source_table: str,
    source_columns: list[str],
    target_table: str,
    target_columns: list[str],
) -> str:
    namespace = {
        "project": project_id.casefold(),
        "connection": connection_id.casefold(),
        "schema": schema_name.casefold(),
        "snapshot": snapshot_id,
        "source": [source_table.casefold(), normalize_columns(source_columns)],
        "target": [target_table.casefold(), normalize_columns(target_columns)],
    }
    digest = hashlib.sha256(
        json.dumps(namespace, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"claim_{digest}"


def build_relation_id(claim_key: str) -> str:
    return stable_id("relation", claim_key)


def build_correlation_key(
    *,
    source_type: str,
    producer: str,
    artifact_id: str | None,
    source_uri: str | None,
    source_locator: dict,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "source_type": source_type,
                "producer": producer,
                "artifact_id": artifact_id,
                "source_uri": source_uri,
                "locator": source_locator,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
