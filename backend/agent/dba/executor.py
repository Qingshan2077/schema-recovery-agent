"""Privileged execution port isolated from the ordinary ToolRegistry."""

from __future__ import annotations

from typing import Protocol


class PrivilegedDDLAdapter(Protocol):
    def current_schema_hash(self, connection_id: str, targets: list[str]) -> str: ...
    def execute(self, connection_id: str, statements: list[str], *, statement_timeout_ms: int, lock_timeout_ms: int, idempotency_key: str) -> dict: ...
    def verify(self, connection_id: str, checks: list[dict]) -> dict: ...


class ExecutionUnavailable(PermissionError): pass
