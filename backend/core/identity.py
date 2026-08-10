"""Canonical identifiers for conversations, runs, traces, and artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IdKind = Literal[
    "thread",
    "run",
    "trace",
    "span",
    "event",
    "tool_call",
    "artifact",
    "evidence",
    "relation",
    "snapshot",
]

_PREFIXES: dict[IdKind, str] = {
    "thread": "thr",
    "run": "run",
    "trace": "trc",
    "span": "spn",
    "event": "evt",
    "tool_call": "tcall",
    "artifact": "art",
    "evidence": "evd",
    "relation": "rel",
    "snapshot": "snp",
}


def new_id(kind: IdKind) -> str:
    """Return an opaque, prefixed identifier suitable for public contracts."""

    return f"{_PREFIXES[kind]}_{uuid.uuid4().hex}"


def stable_id(kind: IdKind, *components: Any) -> str:
    """Return a deterministic identifier for a normalized business identity."""

    payload = json.dumps(components, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{_PREFIXES[kind]}_{digest}"


class RunIdentity(BaseModel):
    """Immutable identity shared by every layer participating in one run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    trace_id: str
    thread_id: str | None = None
    parent_run_id: str | None = None
    attempt: int = Field(default=1, ge=1)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_prefix(value, "run")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return _validate_prefix(value, "trc")

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id(cls, value: str | None) -> str | None:
        return _validate_prefix(value, "thr") if value else value

    @field_validator("parent_run_id")
    @classmethod
    def validate_parent_run_id(cls, value: str | None) -> str | None:
        return _validate_prefix(value, "run") if value else value

    @classmethod
    def create(
        cls,
        *,
        thread_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> "RunIdentity":
        return cls(
            run_id=new_id("run"),
            trace_id=new_id("trace"),
            thread_id=thread_id,
            parent_run_id=parent_run_id,
        )

    def next_attempt(self) -> "RunIdentity":
        """Retry the same business run while preserving its trace identity."""

        return self.model_copy(update={"attempt": self.attempt + 1})

    def as_context(self) -> dict[str, str | int | None]:
        return self.model_dump()


class LegacyIdMapping(BaseModel):
    """Explicit compatibility mapping; callers must state the entity type."""

    legacy_session_id: str
    entity_type: Literal["thread", "run"]
    canonical_id: str


def map_legacy_session_id(
    legacy_session_id: str,
    *,
    entity_type: Literal["thread", "run"],
) -> LegacyIdMapping:
    """Map a legacy ID without inferring meaning from its text prefix."""

    canonical_id = new_id(entity_type)
    return LegacyIdMapping(
        legacy_session_id=legacy_session_id,
        entity_type=entity_type,
        canonical_id=canonical_id,
    )


def canonicalize_legacy_id(
    value: str | None,
    *,
    entity_type: Literal["thread", "run"],
) -> str:
    """Reuse a valid canonical ID or explicitly map the supplied legacy ID."""

    if not value:
        return new_id(entity_type)
    expected_prefix = _PREFIXES[entity_type]
    try:
        return _validate_prefix(value, expected_prefix)
    except ValueError:
        return map_legacy_session_id(value, entity_type=entity_type).canonical_id


def _validate_prefix(value: str, expected: str) -> str:
    if not value.startswith(f"{expected}_") or len(value) <= len(expected) + 1:
        raise ValueError(f"identifier must use the {expected}_ prefix")
    return value
