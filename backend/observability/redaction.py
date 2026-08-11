"""Allowlist tracing attributes and remove credentials/connection material."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from backend.observability.semantic_attributes import ALLOWED_ATTRIBUTES


SECRET_PATTERN = re.compile(r"(?i)(password|api[_-]?key|authorization|token|secret|dsn|connection[_-]?string)")


def redact_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key, value in attributes.items():
        if key not in ALLOWED_ATTRIBUTES or SECRET_PATTERN.search(key):
            continue
        if key == "db.namespace_hash" and not str(value).startswith("sha256:"):
            value = "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()
        output[key] = _bounded(value)
    output.setdefault("redaction.level", "metadata_only")
    output.setdefault("payload.stored", False)
    return output


def _bounded(value: Any) -> Any:
    if isinstance(value, str): return value[:500]
    if isinstance(value, list): return [str(item)[:128] for item in value[:100]]
    if isinstance(value, (int, float, bool)) or value is None: return value
    return str(value)[:500]
