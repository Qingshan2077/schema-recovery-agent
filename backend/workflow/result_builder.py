"""One final result adapter shared by manual, LangGraph, and v1 facade."""

from __future__ import annotations

from typing import Any, Protocol

from backend.workflow.contracts import RecoveryStateV2


class ArtifactReader(Protocol):
    def get_json(self, artifact_id: str) -> dict[str, Any] | None: ...


class WorkflowResultBuilder:
    def __init__(self, artifacts: ArtifactReader):
        self.artifacts = artifacts

    def build(self, state: RecoveryStateV2) -> dict[str, Any]:
        result = self.artifacts.get_json(state.result_ref) if state.result_ref else None
        survey_ref = state.output_refs.get("survey_result")
        survey_result = self.artifacts.get_json(survey_ref) if survey_ref else None
        steps = _steps(state, self.artifacts)
        payload: dict[str, Any] = {
            "session_id": state.session_id,
            "run_id": state.run_id,
            "trace_id": state.trace_id,
            "thread_id": state.thread_id,
            "status": state.status,
            "run_status": state.status,
            "workflow_status": state.status,
            "legacy_status": _legacy_status(state.status),
            "workflow_version": state.workflow_version,
            "state_schema_version": state.state_schema_version,
            "active_engine": state.active_engine,
            "snapshot_id": state.snapshot_id,
            "database_fingerprint": state.database_fingerprint,
            "artifact_ids": state.artifact_ids,
            "evidence_ids": state.evidence_ids,
            "relation_ids": state.relation_ids,
            "result_ref": state.result_ref,
            "budget": state.budget.model_dump(mode="json"),
            "deadline_at": state.deadline_at.isoformat() if state.deadline_at else None,
            "errors": [item.model_dump(mode="json") for item in state.errors],
            "error": state.errors[-1].message if state.errors else None,
            "capability_gaps": [item.model_dump(mode="json") for item in state.errors],
            "engine_history": [item.model_dump(mode="json") for item in state.engine_history],
            "steps": steps,
            "total_steps": len(steps),
            "graph": {
                "engine": state.active_engine,
                "completed_workers": [step["worker"] for step in steps],
                "errors": [item.code for item in state.errors],
            },
        }
        if survey_result:
            payload["survey_result"] = _public_survey_result(survey_result)
        if result:
            merge_result = dict(result.get("merge_result", result))
            _normalize_merge_summary(merge_result)
            payload["merge_result"] = merge_result
            payload["er_diagram"] = result.get("er_diagram") or _er_diagram(
                merge_result, survey_result,
            )
        if state.pending_interrupt:
            payload["pending_interrupt"] = state.pending_interrupt.model_dump(mode="json")
        return payload


def _legacy_status(status: str) -> str:
    return {
        "completed": "success", "failed": "error", "canceled": "cancelled",
        "waiting_approval": "blocked", "expired": "blocked", "queued": "blocked", "running": "blocked",
    }.get(status, status)


def _steps(state: RecoveryStateV2, artifacts: ArtifactReader) -> list[dict[str, Any]]:
    ordering = {
        "survey": 1, "memory_retrieve": 2, "column": 3, "name": 4,
        "code": 5, "orm": 6, "memory_verify": 7, "merge": 8,
        "memory_consolidate": 9,
    }
    steps: list[dict[str, Any]] = []
    for key in state.completed_stage_keys:
        parts = key.split(":")
        if len(parts) < 3:
            continue
        stage_id, work_unit_id, status = parts[0], parts[1], parts[-1]
        worker = stage_id.removeprefix("recovery.").replace("memory.", "memory_")
        output_ref = (
            state.output_refs.get(f"{worker}_result:{work_unit_id}")
            or state.output_refs.get(f"{worker}_result")
        )
        output = artifacts.get_json(output_ref) if output_ref else None
        steps.append({
            "step": ordering.get(worker, 100 + len(steps)),
            "worker": worker,
            "status": status,
            "duration_ms": 0,
            "tool_calls": [
                {"tool_call_id": tool_call_id, "tool": "recorded_tool_call"}
                for tool_call_id in (output or {}).get("tool_call_ids", [])
            ],
            "output": output,
        })
    return sorted(steps, key=lambda item: (item["step"], item["worker"]))


def _normalize_merge_summary(merge_result: dict[str, Any]) -> None:
    high = list(merge_result.get("high_confidence_relations") or [])
    medium = list(merge_result.get("medium_confidence_relations") or [])
    low = list(merge_result.get("low_confidence_relations") or [])
    merge_result.setdefault("summary", {
        "total_relations": len(high) + len(medium) + len(low),
        "high_confidence": len(high),
        "medium_confidence": len(medium),
        "low_confidence": len(low),
    })


def _public_survey_result(survey_result: dict[str, Any]) -> dict[str, Any]:
    """Expose inventory totals without duplicating SQL or ORM source bodies."""

    return {
        "status": survey_result.get("status"),
        "summary": dict(survey_result.get("summary") or {}),
        "server_info": dict(survey_result.get("server_info") or {}),
        "tables": {
            "count": (survey_result.get("tables") or {}).get("count", 0),
            "list": list((survey_result.get("tables") or {}).get("list") or []),
        },
        "views": {"count": (survey_result.get("views") or {}).get("count", 0)},
        "stored_procedures": {
            "count": (survey_result.get("stored_procedures") or {}).get("count", 0),
        },
        "triggers": {"count": (survey_result.get("triggers") or {}).get("count", 0)},
        "orm_files": {"count": (survey_result.get("orm_files") or {}).get("count", 0)},
    }


def _er_diagram(
    merge_result: dict[str, Any], survey_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    survey = survey_result or {}
    for item in survey.get("schema_catalog") or []:
        table_name = str(item.get("name") or "")
        if table_name:
            tables.setdefault(table_name, {"relations": [], "relation_count": 0})
    for table_name in (survey.get("tables") or {}).get("list") or []:
        normalized = str(table_name or "")
        if normalized:
            tables.setdefault(normalized, {"relations": [], "relation_count": 0})
    relations = [
        relation
        for band in ("high_confidence_relations", "medium_confidence_relations", "low_confidence_relations")
        for relation in merge_result.get(band, [])
    ]
    for relation in relations:
        source = str(relation.get("source_table") or "")
        target = str(relation.get("target_table") or "")
        if not source or not target:
            continue
        source_node = tables.setdefault(source, {"relations": [], "relation_count": 0})
        tables.setdefault(target, {"relations": [], "relation_count": 0})
        source_node["relations"].append({
            "type": "has",
            "target": target,
            "via": str(relation.get("fk_column") or ""),
            "confidence": float(relation.get("fused_confidence") or 0.0),
        })
        source_node["relation_count"] += 1
    return {"table_count": len(tables), "tables": tables}
