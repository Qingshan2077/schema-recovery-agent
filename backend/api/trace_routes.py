from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from backend.config import Config


def create_trace_router(provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/v2/traces", tags=["traces"])

    @router.get("/{trace_id}")
    async def get_trace(trace_id: str) -> dict:
        if not Config.OTEL_ENABLED: raise HTTPException(status_code=404, detail="tracing_disabled")
        spans = provider().get_trace(trace_id)
        if not spans: raise HTTPException(status_code=404, detail="trace_not_found")
        return {"trace_id": trace_id, "trace_schema_version": "1.0", "spans": spans, "dropped_spans": provider().dropped_spans}

    return router
