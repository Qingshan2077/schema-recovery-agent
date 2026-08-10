"""Bounded, source-labelled construction of provider input."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.agent.runtime.redaction import RedactionPolicy


@dataclass(frozen=True)
class BuiltContext:
    values: dict[str, Any]
    estimated_tokens: int
    trimmed_fields: tuple[str, ...]
    redaction_level: str
    source_labels: dict[str, str]


class ContextBuilder:
    def __init__(self, *, max_bytes: int = 100_000, redaction_policy: RedactionPolicy | None = None):
        self.max_bytes = max_bytes
        self.redaction_policy = redaction_policy or RedactionPolicy()

    def build(self, values: dict[str, Any]) -> BuiltContext:
        redacted = self.redaction_policy.redact(values)
        trimmed: list[str] = []
        bounded: dict[str, Any] = {}
        consumed = 0
        for key, value in redacted.items():
            encoded = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            remaining = self.max_bytes - consumed
            if remaining <= 0:
                trimmed.append(key)
                continue
            if len(encoded) > remaining:
                bounded[key] = {"untrusted_data_omitted": True, "original_bytes": len(encoded)}
                consumed += len(json.dumps(bounded[key]).encode("utf-8"))
                trimmed.append(key)
                continue
            bounded[key] = value
            consumed += len(encoded)
        return BuiltContext(
            values=bounded,
            estimated_tokens=max(1, consumed // 4),
            trimmed_fields=tuple(trimmed),
            redaction_level=self.redaction_policy.level,
            source_labels={key: "runtime_input:untrusted" for key in bounded},
        )
