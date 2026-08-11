"""Server-owned DDL planning and approval API."""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.agent.dba.contracts import ActorContext
from backend.agent.dba.operation_store import OperationConflict
from backend.config import Config
from backend.core.identity import new_id


class OperationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: str = Field(min_length=1, max_length=10000)
    dialect: Literal["mysql", "postgresql"] = "mysql"
    thread_id: str | None = None
    run_id: str | None = None
    snapshot_id: str = "snp_unknown"
    snapshot_hash: str = "sha256:unknown"


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    decision: Literal["approve", "reject", "request_changes"]
    reason: str = Field(min_length=1, max_length=2000)
    acknowledged_hash: str
    request_id: str


def create_dba_router(provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["dba-approvals"])

    def service():
        if not Config.DBA_V2_ENABLED: raise HTTPException(status_code=404, detail="dba_v2_disabled")
        return provider()

    @router.post("/dba/operations", status_code=status.HTTP_202_ACCEPTED)
    async def create_operation(body: OperationCreateRequest, request: Request) -> dict[str, Any]:
        if not Config.DBA_PLAN_ENABLED: raise HTTPException(status_code=403, detail="dba_planning_disabled")
        actor = _actor(request)
        try:
            operation = await service().create_operation(
                body.request, actor=actor,
                connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
                thread_id=body.thread_id or new_id("thread"), run_id=body.run_id or new_id("run"),
                dialect=body.dialect, snapshot_id=body.snapshot_id, snapshot_hash=body.snapshot_hash,
            )
            return _project(operation, actor)
        except PermissionError as exc: raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/dba/operations/{operation_id}")
    async def get_operation(operation_id: str, request: Request) -> dict[str, Any]:
        actor = _actor(request)
        try: return _project(service()._authorized(operation_id, actor), actor)
        except KeyError as exc: raise HTTPException(status_code=404, detail="operation_not_found") from exc

    @router.get("/approvals")
    async def approvals(request: Request, state: str | None = None, risk: str | None = None, environment: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        actor = _actor(request)
        rows = service().store.list(tenant_id=actor.tenant_id, project_id=actor.project_id, status=state, risk=risk, environment=environment, limit=limit)
        return {"items": [_project(item, actor) for item in rows], "capabilities": actor.capabilities}

    @router.get("/approvals/{operation_id}")
    async def approval_detail(operation_id: str, request: Request) -> dict[str, Any]:
        actor = _actor(request)
        try: return _project(service()._authorized(operation_id, actor), actor)
        except KeyError as exc: raise HTTPException(status_code=404, detail="operation_not_found") from exc

    @router.post("/approvals/{operation_id}/resolve")
    async def resolve(operation_id: str, body: DecisionRequest, request: Request) -> dict[str, Any]:
        actor = _actor(request)
        try:
            return _project(service().resolve(operation_id, expected_version=body.expected_version, decision=body.decision, reason=body.reason, acknowledged_hash=body.acknowledged_hash, request_id=body.request_id, actor=actor), actor)
        except PermissionError as exc: raise HTTPException(status_code=403, detail=str(exc)) from exc
        except OperationConflict as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/approvals/{operation_id}/audit")
    async def audit(operation_id: str, request: Request) -> dict[str, Any]:
        actor = _actor(request); service()._authorized(operation_id, actor)
        return {"items": service().store.audit(operation_id)}

    return router


def _actor(request: Request) -> ActorContext:
    raw = getattr(request.state, "actor", None)
    if raw is None:
        return ActorContext(actor_id="local-anonymous", roles=["viewer"], tenant_id=Config.TENANT_ID, project_id=Config.PROJECT_ID, environment="dev", capabilities=["dba_view"])
    return ActorContext.model_validate(raw)


def _project(operation, actor: ActorContext) -> dict[str, Any]:
    payload = operation.model_dump(mode="json")
    if "dba_view_sql" not in actor.capabilities:
        payload["normalized_sql"] = []
        payload["normalized_ast"] = {"redacted": True}
    payload["capabilities"] = {
        "approve": any(role in actor.roles for role in ("dba_approver", "security_approver")),
        "view_sql": "dba_view_sql" in actor.capabilities,
        "execute": False,
    }
    return payload
