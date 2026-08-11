"""TTL, namespace authorization and anti-poisoning policies for memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from backend.agent.memory.contracts import GlobalMemoryItem, MemoryNamespace, RelationMemoryVersion


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class MemoryPolicyError(PermissionError):
    pass


class MemoryPolicy:
    def authorize_namespace(self, requested: MemoryNamespace, active: MemoryNamespace, *, layer: str) -> None:
        if requested.canonical_tenant_id != active.canonical_tenant_id:
            raise MemoryPolicyError("namespace_mismatch: tenant")
        if requested.canonical_project_id != active.canonical_project_id:
            raise MemoryPolicyError("namespace_mismatch: project")
        if layer == "l1" and requested.thread_id != active.thread_id:
            raise MemoryPolicyError("namespace_mismatch: thread")
        if layer == "l2" and requested.project_key() != active.project_key():
            raise MemoryPolicyError("namespace_mismatch: database/schema")

    @staticmethod
    def relation_is_retrievable(item: RelationMemoryVersion, *, include_stale: bool, current_run_id: str) -> bool:
        if item.created_by_run_id == current_run_id:
            return False
        if item.status == "stale" and not include_stale:
            return False
        return item.status in {"accepted", "corrected"} or (include_stale and item.status == "stale")

    @staticmethod
    def global_is_retrievable(
        item: GlobalMemoryItem,
        *,
        now: datetime,
        dialect: str | None,
        domain: str | None,
        current_run_id: str,
    ) -> bool:
        if item.lifecycle != "active":
            return False
        if item.created_by_run_id == current_run_id:
            return False
        if item.expires_at and item.expires_at <= now:
            return False
        if dialect and "*" not in item.dialects and dialect not in item.dialects:
            return False
        if domain and "*" not in item.domains and domain not in item.domains:
            return False
        return True

    @staticmethod
    def can_activate_global(*, actor_role: str, support_project_count: int, support_eval_count: int) -> bool:
        if actor_role in {"memory_admin", "schema_reviewer"}:
            return True
        return support_project_count >= 3 and support_eval_count >= 2

    @staticmethod
    def sanitize_summary(summary: str) -> str:
        forbidden = (
            "ignore previous", "system prompt", "developer message", "call tool",
            "execute sql", "override policy", "忽略之前", "系统提示", "执行工具",
        )
        sanitized = summary.strip()[:2000]
        lowered = sanitized.casefold()
        if any(token in lowered for token in forbidden):
            return "[untrusted memory text withheld; use structured fields and provenance only]"
        return sanitized
