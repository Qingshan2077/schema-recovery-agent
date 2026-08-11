"""Same-run LangGraph-to-manual takeover coordinator."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.persistence.event_log import SQLiteEventLog
from backend.persistence.run_repository import SQLiteRunRepository
from backend.workflow.contracts import EngineTransition, RecoveryStateV2
from backend.workflow.contracts import StatePatch
from backend.workflow.reducer import apply_patch


class FallbackRejected(RuntimeError):
    pass


class FallbackCoordinator:
    def __init__(self, runs: SQLiteRunRepository, events: SQLiteEventLog, *, max_fallbacks: int = 1):
        self.runs = runs
        self.events = events
        self.max_fallbacks = max_fallbacks

    def takeover(self, state: RecoveryStateV2, *, reason: str, in_flight_known_safe: bool) -> RecoveryStateV2:
        if state.active_engine != "langgraph":
            raise FallbackRejected("only an active LangGraph run can fall back")
        fallback_count = sum(item.to_engine == "manual" for item in state.engine_history)
        if fallback_count >= self.max_fallbacks:
            raise FallbackRejected("automatic fallback limit reached")
        if not in_flight_known_safe:
            raise FallbackRejected("in-flight side effect requires reconciliation")
        started = self.events.append(state, "run.fallback_started", status=state.status, node_id=state.phase, payload={"reason": reason})
        transition = EngineTransition(
            from_engine="langgraph", to_engine="manual", reason=reason,
            sequence=started.sequence, changed_at=datetime.now(timezone.utc),
        )
        next_state = apply_patch(state, StatePatch(
            active_engine="manual",
            engine_history_add=[transition],
            last_event_sequence=started.sequence,
            expected_version=state.version,
        ))
        self.runs.save(next_state, expected_version=state.version)
        changed = self.events.append(
            next_state, "run.engine_changed", status=next_state.status, node_id=next_state.phase,
            payload={"from": "langgraph", "to": "manual"},
        )
        committed = apply_patch(next_state, StatePatch(
            last_event_sequence=changed.sequence,
            expected_version=next_state.version,
        ))
        return self.runs.save(committed, expected_version=next_state.version)
