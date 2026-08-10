"""Process-local run registry used for reconnecting to an existing Phase 0 run."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.core.identity import RunIdentity
from backend.core.status import RunStatus, coerce_run_status


class RunStore:
    """Thread-safe process memory store; durable checkpoints arrive in Phase 4."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def start(self, identity: RunIdentity, *, engine: str | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        record = {
            **identity.model_dump(),
            "session_id": identity.run_id,
            "status": RunStatus.RUNNING.value,
            "engine": engine,
            "created_at": now,
            "updated_at": now,
            "last_sequence": 0,
            "result": None,
        }
        with self._lock:
            existing = self._records.get(identity.run_id)
            if existing:
                if identity.attempt > int(existing.get("attempt", 1)):
                    existing.update(
                        {
                            **identity.model_dump(),
                            "status": RunStatus.RUNNING.value,
                            "engine": engine,
                            "updated_at": now,
                            "result": None,
                        }
                    )
                return deepcopy(existing)
            self._records[identity.run_id] = record
        return deepcopy(record)

    def record_sequence(self, run_id: str, sequence: int) -> None:
        with self._lock:
            record = self._records.get(run_id)
            if not record:
                return
            record["last_sequence"] = max(int(record.get("last_sequence", 0)), sequence)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()

    def complete(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        status = coerce_run_status(result.get("run_status") or result.get("status") or RunStatus.ERROR.value)
        with self._lock:
            record = self._records.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "session_id": run_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_sequence": 0,
                },
            )
            record["status"] = status.value
            record["result"] = deepcopy(result)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            return deepcopy(record)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(run_id)
            return deepcopy(record) if record else None
