"""Engine-independent RecoveryStage protocol."""

from __future__ import annotations

from typing import Any, Protocol

from backend.agent.runtime.hybrid_contracts import StageResult, WorkUnit
from backend.workflow.contracts import StageCapabilities


class RecoveryStage(Protocol):
    """Serializable, idempotent, cancellation-aware unit of recovery work."""

    stage_id: str
    input_schema_version: str
    output_schema_version: str
    capabilities: StageCapabilities

    async def execute(
        self,
        state: dict[str, Any],
        unit: WorkUnit,
        context: dict[str, Any],
    ) -> StageResult: ...

    def cancel(self, reason: str) -> None: ...
