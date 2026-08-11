"""Phase 4 run/control/event API."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = "default"
    connection_id: str = "default"
    tenant_id: str = "default"
    database_name: str = "default"
    schema_name: str = "default"
    thread_id: str | None = None
    session_id: str | None = None
    engine: str | None = None
    execute: bool = True


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interrupt_id: str
    request_id: str
    decision: Any
    payload_hash: str
    actor_id: str
    actor_role: str


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    reason: str = Field(min_length=1, max_length=1000)
    actor_id: str | None = None


def create_run_router(service_provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["recovery-runs"])

    @router.post("")
    async def create_run(request: RunCreateRequest) -> dict[str, Any]:
        try:
            service = service_provider()
            state = service.create_run(
                project_id=request.project_id, connection_id=request.connection_id,
                tenant_id=request.tenant_id, database_name=request.database_name,
                schema_name=request.schema_name,
                thread_id=request.thread_id, session_id=request.session_id, engine=request.engine,
            )
            return await service.execute(state.run_id) if request.execute else service.get_run(state.run_id)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        try:
            return service_provider().get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @router.get("/{run_id}/events")
    async def get_events(
        run_id: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=1000, ge=1, le=5000),
    ) -> dict[str, Any]:
        try:
            events = service_provider().get_events(run_id, after_sequence=after_sequence, limit=limit)
            return {
                "run_id": run_id,
                "after_sequence": after_sequence,
                "next_sequence": max(
                    [int(item.get("sequence", after_sequence)) for item in events]
                    or [after_sequence]
                ),
                "events": events,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @router.post("/{run_id}/resume")
    async def resume(run_id: str, request: ResumeRequest) -> dict[str, Any]:
        try:
            return await service_provider().resume(run_id, **request.model_dump())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/{run_id}/cancel")
    async def cancel(run_id: str, request: CancelRequest) -> dict[str, Any]:
        try:
            return service_provider().cancel(run_id, **request.model_dump())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
