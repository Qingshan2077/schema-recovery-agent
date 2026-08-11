"""Phase 5 evidence, relation-version and calibration inspection APIs."""

from __future__ import annotations

from typing import Any, Callable
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.agent.memory.contracts import MemoryNamespace
from backend.config import Config
from backend.core.identity import stable_id
from backend.evidence.contracts import EvidenceItem, HumanFeedback
from backend.evidence.fusion import VersionedFusionEngine
from backend.evidence.policy_loader import load_fusion_policy


class RelationFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous_version: int = Field(ge=1)
    action: str
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)
    correction: dict[str, Any] = Field(default_factory=dict)
    run_id: str
    trace_id: str


def create_evidence_router(repository_provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/evidence-ledger", tags=["evidence-ledger"])

    def repository() -> Any:
        if not Config.EVIDENCE_LEDGER_ENABLED:
            raise HTTPException(status_code=404, detail="evidence_ledger_disabled")
        return repository_provider()

    @router.get("/evidence")
    async def list_evidence(
        claim_key: str | None = None,
        relation_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        namespace = _active_namespace()
        items = repository().query_evidence(
            tenant_key=namespace.canonical_tenant_id,
            project_key=namespace.canonical_project_id,
            connection_key=namespace.canonical_connection_id,
            database_key=namespace.canonical_database_name,
            schema_key=namespace.canonical_schema_name,
            claim_key=claim_key, relation_id=relation_id, snapshot_id=snapshot_id,
        )
        return {"items": [item.model_dump(mode="json") for item in items]}

    @router.get("/evidence/{evidence_id}")
    async def get_evidence(evidence_id: str) -> dict[str, Any]:
        try:
            item = repository().get_evidence(evidence_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="evidence_not_found") from exc
        _assert_namespace(item.namespace)
        return item.model_dump(mode="json")

    @router.get("/relations")
    async def list_relations(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        keys = _active_namespace().project_key()
        items = repository().list_relations(
            tenant_key=keys[0], project_key=keys[1], connection_key=keys[2],
            database_key=keys[3], schema_key=keys[4], status=status, limit=limit,
        )
        return {"items": [item.model_dump(mode="json") for item in items]}

    @router.get("/relations/{relation_id}")
    async def get_relation(relation_id: str, version: int | None = None) -> dict[str, Any]:
        try:
            item = repository().get_relation(relation_id, version=version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="relation_not_found") from exc
        _assert_namespace(item.namespace)
        return item.model_dump(mode="json")

    @router.get("/relations/{relation_id}/versions")
    async def list_relation_versions(
        relation_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        try:
            items = repository().list_relation_versions(relation_id, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="relation_not_found") from exc
        for item in items:
            _assert_namespace(item.namespace)
        return {"items": [item.model_dump(mode="json") for item in items]}

    @router.post("/relations/{relation_id}/feedback")
    async def relation_feedback(relation_id: str, request: RelationFeedbackRequest) -> dict[str, Any]:
        if request.actor_role not in {"schema_reviewer", "data_owner", "admin"}:
            raise HTTPException(status_code=403, detail="relation_feedback_requires_reviewer")
        if request.action not in {"accept", "reject", "correct_target", "correct_cardinality", "mark_stale", "comment", "undo"}:
            raise HTTPException(status_code=400, detail="unsupported_feedback_action")
        repo = repository()
        current = repo.get_relation(relation_id)
        _assert_namespace(current.namespace)
        if current.version != request.previous_version:
            raise HTTPException(status_code=409, detail="relation_version_conflict")
        now = datetime.now(timezone.utc)
        feedback_id = stable_id("feedback", relation_id, request.previous_version, request.actor_id, request.action, request.reason)
        evidence_id = stable_id("evidence", feedback_id)
        polarity = "support" if request.action in {"accept", "correct_target", "correct_cardinality"} else "oppose" if request.action in {"reject", "mark_stale"} else "neutral"
        evidence = EvidenceItem(
            evidence_id=evidence_id, namespace=current.namespace,
            snapshot_id=current.namespace.snapshot_id or "", claim_key=current.claim_key,
            relation_id=relation_id, source_type="human", producer="relation_feedback",
            producer_version="1.0", polarity=polarity, strength=1.0, reliability=1.0,
            source_uri=None, source_locator={"actor_id": request.actor_id, "actor_role": request.actor_role},
            summary=request.reason, root_fact_id=stable_id("fact", feedback_id),
            correlation_group=f"human:{feedback_id}", trace_id=request.trace_id,
            span_id=stable_id("span", request.trace_id, feedback_id), created_by_run_id=request.run_id,
            created_at=now,
        )
        repo.append_evidence(evidence)
        feedback = HumanFeedback(
            feedback_id=feedback_id, relation_id=relation_id,
            previous_version=request.previous_version, action=request.action,
            actor_id=request.actor_id, actor_role=request.actor_role,
            reason=request.reason, correction=request.correction,
            trace_id=request.trace_id, created_at=now,
        )
        repo.append_feedback(feedback, evidence_id)
        template = current.model_copy(update={
            "target_table_id": request.correction.get("target_table_id", current.target_table_id),
            "target_column_ids": request.correction.get("target_column_ids", current.target_column_ids),
            "cardinality": request.correction.get("cardinality", current.cardinality),
            "evidence_ids": [*current.evidence_ids, evidence_id],
        })
        policy = load_fusion_policy(Config.FUSION_POLICY_PATH, calibration_enabled=Config.CALIBRATION_ENABLED, feature_schema_path=Config.FUSION_FEATURE_SCHEMA_PATH)
        fused = VersionedFusionEngine(
            fusion_version=policy.fusion_version, feature_schema_hash=policy.feature_schema_hash,
            threshold_policy=policy.threshold_policy, calibrator=policy.calibrator,
            coefficients=policy.coefficients, prior_probability=policy.prior_probability,
        ).fuse(template, repo.query_evidence(relation_id=relation_id), version=current.version + 1, run_id=request.run_id, now=now)
        status_by_action = {"accept": "accepted", "reject": "rejected", "correct_target": "corrected", "correct_cardinality": "corrected", "mark_stale": "stale"}
        updated = fused.relation.model_copy(update={"status": status_by_action.get(request.action, current.status)})
        repo.append_relation_version(updated)
        return {"feedback": feedback.model_dump(mode="json"), "evidence": evidence.model_dump(mode="json"), "relation": updated.model_dump(mode="json")}

    @router.get("/calibrations")
    async def list_calibrations(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        return {
            "items": [item.model_dump(mode="json") for item in repository().list_calibrations(limit=limit)]
        }

    @router.get("/calibrations/{version}")
    async def get_calibration(version: str) -> dict[str, Any]:
        try:
            return repository().get_calibration(version).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="calibration_not_found") from exc

    return router


def _active_namespace() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id=Config.TENANT_ID, project_id=Config.PROJECT_ID,
        connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
        database_name=Config.DB_NAME, schema_name=Config.DB_NAME, snapshot_id="inspector",
    )


def _assert_namespace(namespace: MemoryNamespace) -> None:
    if namespace.project_key() != _active_namespace().project_key():
        raise HTTPException(status_code=404, detail="resource_not_found")
