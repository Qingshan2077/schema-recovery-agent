"""Semantic parity normalization for Manual and LangGraph workflow outcomes."""

from __future__ import annotations

from typing import Any, Iterable

from backend.workflow.contracts import RecoveryStateV2, WorkflowEvent


VOLATILE_RESULT_FIELDS = {
    "active_engine", "engine_history", "last_event_sequence", "span_id",
    "timestamp", "created_at", "updated_at",
}


def normalize_outcome(
    state: RecoveryStateV2,
    *,
    result: dict[str, Any] | None = None,
    events: Iterable[WorkflowEvent] = (),
) -> dict[str, Any]:
    """Drop engine scheduling noise while retaining domain and budget semantics."""

    return {
        "status": state.status,
        "stage_causal_set": sorted(_stage_identity(item) for item in state.completed_stage_keys),
        "artifact_ids": sorted(state.artifact_ids),
        "evidence_ids": sorted(state.evidence_ids),
        "relation_ids": sorted(state.relation_ids),
        "evidence_round": state.evidence_round,
        "budget": state.budget.model_dump(mode="json"),
        "errors": sorted(
            (item.category, item.code, item.source, item.retryable)
            for item in state.errors
        ),
        "result": _normalize_value(result or {}),
        "event_causal_set": sorted(
            (item.type, item.node_id, item.attempt, item.status)
            for item in events
            if item.type not in {"heartbeat", "usage.updated", "checkpoint.created", "checkpoint.restored"}
        ),
    }


def parity_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, dict[str, Any]]:
    keys = sorted(set(left) | set(right))
    return {
        key: {"manual": left.get(key), "langgraph": right.get(key)}
        for key in keys
        if left.get(key) != right.get(key)
    }


def _stage_identity(value: str) -> str:
    parts = value.rsplit(":", 1)
    if len(parts) == 2 and parts[1] in {"completed", "success", "partial", "degraded", "blocked", "failed", "error", "canceled", "cancelled"}:
        return parts[0]
    return value


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_value(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_RESULT_FIELDS
        }
    if isinstance(value, list):
        normalized = [_normalize_value(item) for item in value]
        if all(not isinstance(item, (dict, list)) for item in normalized):
            return sorted(normalized, key=str)
        return normalized
    return value
