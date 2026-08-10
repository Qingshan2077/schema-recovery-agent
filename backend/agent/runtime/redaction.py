"""Deterministic redaction and hashing for runtime audit data."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "connection_string",
    "credential",
    "db_password",
    "password",
    "passwd",
    "secret",
    "token",
}
_INLINE_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|password|passwd|secret|token)\s*[:=]\s*([^,}\s]+)"
)


@dataclass(frozen=True)
class RedactionPolicy:
    max_string_length: int = 1000
    replacement: str = "***"
    level: str = "metadata-only"

    def redact(self, value: Any) -> Any:
        return redact_value(value, policy=self)


def redact_value(value: Any, *, policy: RedactionPolicy | None = None) -> Any:
    policy = policy or RedactionPolicy()
    if isinstance(value, dict):
        return {
            str(key): policy.replacement
            if _is_sensitive_key(str(key))
            else redact_value(item, policy=policy)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item, policy=policy) for item in value]
    if isinstance(value, str):
        sanitized = _INLINE_SECRET.sub(lambda match: f"{match.group(1)}={policy.replacement}", value)
        if len(sanitized) > policy.max_string_length:
            return sanitized[: policy.max_string_length] + "…"
        return sanitized
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def structural_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "object", "keys": sorted(str(key) for key in value), "sha256": stable_hash(redact_value(value))}
    if isinstance(value, (list, tuple)):
        return {"type": "array", "items": len(value), "sha256": stable_hash(redact_value(value))}
    return {"type": type(value).__name__, "sha256": stable_hash(redact_value(value))}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_token") or normalized.endswith("_secret")
