"""Shared Stage registry; engines never construct or implement workers."""

from __future__ import annotations

from typing import Any

from backend.workflow.contracts import WorkflowDefinition
from backend.workflow.stage import RecoveryStage


class StageRegistryError(ValueError):
    pass


class StageRegistry:
    def __init__(self):
        self._stages: dict[str, RecoveryStage] = {}

    def register(self, stage: RecoveryStage) -> None:
        if stage.stage_id in self._stages:
            raise StageRegistryError(f"duplicate stage: {stage.stage_id}")
        self._stages[stage.stage_id] = stage

    def get(self, stage_id: str) -> RecoveryStage:
        try:
            return self._stages[stage_id]
        except KeyError as exc:
            raise StageRegistryError(f"stage is not registered: {stage_id}") from exc

    def validate_definition(self, definition: WorkflowDefinition) -> None:
        missing = sorted({node.stage_id for node in definition.nodes if node.stage_id and node.stage_id not in self._stages})
        if missing:
            raise StageRegistryError(f"workflow has missing stages: {', '.join(missing)}")

    def capabilities(self) -> dict[str, dict[str, Any]]:
        return {
            stage_id: {
                "input_schema_version": stage.input_schema_version,
                "output_schema_version": stage.output_schema_version,
                "capabilities": (
                    stage.capabilities.model_dump(mode="json")
                    if getattr(stage, "capabilities", None) is not None else None
                ),
            }
            for stage_id, stage in self._stages.items()
        }

    def cancel_all(self, reason: str) -> None:
        for stage in self._stages.values():
            cancel = getattr(stage, "cancel", None)
            if cancel is not None:
                cancel(reason)
