"""The sole merge point for sequential and concurrent state patches."""

from __future__ import annotations

from backend.agent.runtime.contracts import RuntimeUsage
from backend.workflow.contracts import RecoveryStateV2, StatePatch
from backend.workflow.state_machine import RecoveryStateMachine


class StateVersionConflict(RuntimeError):
    pass


def apply_patch(state: RecoveryStateV2, patch: StatePatch) -> RecoveryStateV2:
    if patch.expected_version is not None and patch.expected_version != state.version:
        raise StateVersionConflict(f"expected state version {patch.expected_version}, found {state.version}")
    update = state.model_dump(mode="python")
    if patch.active_engine is not None:
        update["active_engine"] = patch.active_engine
    if patch.status is not None:
        update["status"] = RecoveryStateMachine.transition(state.status, patch.status)
    for field in ("phase", "snapshot_id", "database_fingerprint", "work_plan_ref", "result_ref", "evidence_round", "last_event_sequence"):
        value = getattr(patch, field)
        if value is not None:
            update[field] = value
    pending = {item.work_unit_id: item for item in state.pending_work_units}
    for work_unit_id in patch.pending_work_unit_ids_remove:
        pending.pop(work_unit_id, None)
    for item in patch.pending_work_units_add:
        pending.setdefault(item.work_unit_id, item)
    update["pending_work_units"] = list(pending.values())
    update["engine_history"] = list(state.engine_history) + patch.engine_history_add
    for target, additions in (
        ("completed_stage_keys", patch.completed_stage_keys_add),
        ("artifact_ids", patch.artifact_ids_add),
        ("evidence_ids", patch.evidence_ids_add),
        ("relation_ids", patch.relation_ids_add),
    ):
        update[target] = list(dict.fromkeys(list(update[target]) + additions))
    update["attempts"] = dict(state.attempts)
    for key, attempt in patch.attempts_merge.items():
        update["attempts"][key] = max(int(update["attempts"].get(key, 0)), int(attempt))
    update["output_refs"] = {**state.output_refs, **patch.output_refs_merge}
    update["errors"] = list(state.errors) + patch.errors_add
    update["budget"] = _add_usage(state.budget, patch.usage_delta)
    if patch.clear_interrupt:
        update["pending_interrupt"] = None
    elif patch.pending_interrupt is not None:
        update["pending_interrupt"] = patch.pending_interrupt
    if patch.cancellation is not None:
        update["cancellation"] = patch.cancellation
    update["version"] = state.version + 1
    return RecoveryStateV2.model_validate(update)


def merge_patches(patches: list[StatePatch]) -> StatePatch:
    merged = StatePatch()
    for patch in patches:
        data = merged.model_dump(mode="python")
        for field in (
            "engine_history_add", "pending_work_units_add", "pending_work_unit_ids_remove", "completed_stage_keys_add",
            "artifact_ids_add", "evidence_ids_add", "relation_ids_add", "errors_add",
        ):
            data[field] = list(data[field]) + list(getattr(patch, field))
        attempt_keys = set(data["attempts_merge"]) | set(patch.attempts_merge)
        data["attempts_merge"] = {
            key: max(
                int(data["attempts_merge"].get(key, 0)),
                int(patch.attempts_merge.get(key, 0)),
            )
            for key in attempt_keys
        }
        output_refs = dict(data["output_refs_merge"])
        for key, value in patch.output_refs_merge.items():
            if key in output_refs and output_refs[key] != value:
                raise StateVersionConflict(f"parallel output ref conflict for {key}")
            output_refs[key] = value
        data["output_refs_merge"] = output_refs
        data["usage_delta"] = _add_usage(merged.usage_delta, patch.usage_delta)
        for field in (
            "active_engine", "phase", "snapshot_id", "database_fingerprint",
            "work_plan_ref", "evidence_round", "pending_interrupt", "cancellation",
            "result_ref", "last_event_sequence",
        ):
            value = getattr(patch, field)
            if value is not None:
                data[field] = value
        data["status"] = _stronger_status(data.get("status"), patch.status)
        data["clear_interrupt"] = data["clear_interrupt"] or patch.clear_interrupt
        merged = StatePatch.model_validate(data)
    return merged


def _add_usage(left: RuntimeUsage, right: RuntimeUsage) -> RuntimeUsage:
    return RuntimeUsage(
        model_calls=left.model_calls + right.model_calls,
        tool_calls=left.tool_calls + right.tool_calls,
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cost_usd=left.cost_usd + right.cost_usd,
        loop_iterations=left.loop_iterations + right.loop_iterations,
    )


def _stronger_status(left: str | None, right: str | None) -> str | None:
    priority = {
        None: 0,
        "queued": 1,
        "running": 2,
        "waiting_approval": 3,
        "partial": 4,
        "degraded": 5,
        "blocked": 6,
        "failed": 7,
        "canceled": 8,
        "completed": 9,
        "expired": 10,
    }
    return right if priority[right] > priority[left] else left
