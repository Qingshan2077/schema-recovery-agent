"""Read-mostly Memory Inspector and governed feedback APIs."""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.agent.memory.contracts import MemoryFeedback, MemoryNamespace
from backend.config import Config


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    action: Literal["accept", "reject", "correct", "mark_stale", "comment", "undo"]
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)
    correction: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ForgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    actor_role: str
    reason: str = Field(min_length=1, max_length=2000)


class PromotionResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    actor_role: str
    approve: bool
    reason: str = Field(min_length=1, max_length=2000)


def create_memory_router(service_provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/memory", tags=["memory"])

    def enabled() -> Any:
        if not Config.MEMORY_INSPECTOR_ENABLED:
            raise HTTPException(status_code=404, detail="memory_inspector_disabled")
        return service_provider()

    @router.get("")
    async def list_memory(
        layer: Literal["l2", "l3"] | None = None,
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        x_trace_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        service = enabled()
        namespace = _active_namespace()
        return {
            "trace_id": x_trace_id,
            "namespace": namespace.model_dump(mode="json"),
            "items": service.list_memory(namespace, layer=layer, status=status, limit=limit),
        }

    @router.get("/promotions")
    async def list_promotions(status: str | None = None) -> dict[str, Any]:
        return {
            "items": [item.model_dump(mode="json") for item in enabled().list_promotions(status=status)]
        }

    @router.post("/promotions/{proposal_id}/resolve")
    async def resolve_promotion(proposal_id: str, request: PromotionResolutionRequest) -> dict[str, Any]:
        try:
            proposal, memory = enabled().resolve_global(
                proposal_id, actor_id=request.actor_id, actor_role=request.actor_role,
                approve=request.approve, reason=request.reason,
            )
            return {
                "proposal": proposal.model_dump(mode="json"),
                "memory": memory.model_dump(mode="json"),
            }
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.get("/{memory_id}")
    async def get_memory(memory_id: str) -> dict[str, Any]:
        try:
            item = enabled().get_memory(memory_id)
            _assert_active_namespace(item)
            return item
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory_not_found") from exc

    @router.post("/{memory_id}/feedback")
    async def feedback(memory_id: str, request: FeedbackRequest) -> dict[str, str]:
        item = enabled().get_memory(memory_id)
        _assert_active_namespace(item)
        feedback_id = enabled().submit_feedback(
            memory_id,
            version=request.version,
            feedback=MemoryFeedback(**request.model_dump(exclude={"version"})),
        )
        return {"feedback_id": feedback_id}

    @router.post("/{memory_id}/forget")
    async def forget(memory_id: str, request: ForgetRequest) -> dict[str, str]:
        if request.actor_role not in {"schema_reviewer", "data_owner", "admin"}:
            raise HTTPException(status_code=403, detail="forget_requires_data_owner")
        item = enabled().get_memory(memory_id)
        _assert_active_namespace(item)
        return {"forget_id": enabled().forget(memory_id, actor_id=request.actor_id, reason=request.reason)}

    return router


def _active_namespace() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id=Config.TENANT_ID,
        project_id=Config.PROJECT_ID,
        connection_id=f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
        database_name=Config.DB_NAME,
        schema_name=Config.DB_NAME,
        snapshot_id="inspector",
    )


def _assert_active_namespace(item: dict[str, Any]) -> None:
    raw = item.get("namespace")
    if raw is None:
        return
    namespace = MemoryNamespace.model_validate(raw)
    active = _active_namespace()
    if namespace.project_key() != active.project_key():
        raise HTTPException(status_code=404, detail="memory_not_found")
