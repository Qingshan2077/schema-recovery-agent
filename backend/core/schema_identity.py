"""Database fingerprints and immutable schema snapshot references."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.identity import stable_id


class SnapshotCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class SchemaSnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    database_fingerprint: str
    schema_names: list[str] = Field(default_factory=list)
    schema_hash: str
    captured_at: datetime
    capture_method: str
    completeness: SnapshotCompleteness = SnapshotCompleteness.UNKNOWN


def build_database_fingerprint(
    *,
    provider: str,
    dialect: str,
    instance_identity: str,
    database_name: str,
    schema_names: list[str] | tuple[str, ...],
    tenant_id: str = "default",
    project_id: str = "default",
) -> str:
    """Hash a normalized database identity without including credentials."""

    identity = {
        "provider": provider.strip().lower(),
        "dialect": dialect.strip().lower(),
        "instance_identity": instance_identity.strip().lower(),
        "database_name": database_name.strip().lower(),
        "schema_names": sorted({name.strip().lower() for name in schema_names if name.strip()}),
        "tenant_id": tenant_id.strip().lower(),
        "project_id": project_id.strip().lower(),
    }
    return _sha256(identity)


def compute_schema_hash(metadata: Any) -> str:
    return _sha256(_normalize_schema_value(metadata))


def create_snapshot_ref(
    *,
    database_fingerprint: str,
    schema_names: list[str],
    schema_metadata: Any,
    capture_method: str,
    completeness: SnapshotCompleteness | str = SnapshotCompleteness.UNKNOWN,
    captured_at: datetime | None = None,
) -> SchemaSnapshotRef:
    schema_hash = compute_schema_hash(schema_metadata)
    snapshot_id = stable_id("snapshot", database_fingerprint, schema_hash)
    return SchemaSnapshotRef(
        snapshot_id=snapshot_id,
        database_fingerprint=database_fingerprint,
        schema_names=sorted({name.lower() for name in schema_names}),
        schema_hash=schema_hash,
        captured_at=captured_at or datetime.now(timezone.utc),
        capture_method=capture_method,
        completeness=SnapshotCompleteness(completeness),
    )


def is_snapshot_stale(snapshot: SchemaSnapshotRef, current: SchemaSnapshotRef) -> bool:
    if snapshot.database_fingerprint != current.database_fingerprint:
        return True
    return snapshot.snapshot_id != current.snapshot_id or snapshot.schema_hash != current.schema_hash


def _normalize_schema_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _normalize_schema_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize_schema_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        normalized = [_normalize_schema_value(item) for item in value]
        if normalized and all(isinstance(item, dict) for item in normalized):
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
        return normalized
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
