"""Portable schema recovery workflow surface."""

from backend.workflow.contracts import RecoveryStateV2, StatePatch, WorkflowDefinition
from backend.workflow.definition import schema_recovery_v2
from backend.workflow.parity import normalize_outcome, parity_diff
from backend.workflow.reducer import apply_patch, merge_patches
from backend.workflow.result_builder import WorkflowResultBuilder
from backend.workflow.stage import RecoveryStage
from backend.workflow.stage_registry import StageRegistry
from backend.workflow.state_machine import RecoveryStateMachine

__all__ = [
    "RecoveryStage", "RecoveryStateV2", "RecoveryStateMachine", "StageRegistry", "StatePatch",
    "WorkflowDefinition", "WorkflowResultBuilder", "apply_patch", "merge_patches",
    "normalize_outcome", "parity_diff",
    "schema_recovery_v2",
]
