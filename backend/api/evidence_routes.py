"""Phase 5 evidence, relation-version and calibration inspection APIs."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from backend.agent.memory.contracts import MemoryNamespace
from backend.config import Config


def create_evidence_router(repository_provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/evidence-ledger", tags=["evidence-ledger"])

    def repository() -> Any:
        if not Config.MEMORY_INSPECTOR_ENABLED:
            raise HTTPException(status_code=404, detail="memory_inspector_disabled")
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
