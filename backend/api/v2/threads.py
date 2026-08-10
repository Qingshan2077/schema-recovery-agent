"""Persistent conversation, event and cancellation endpoints."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from backend.chat.contracts import CreateThreadRequest, PostMessageRequest
from backend.chat.service import ChatService


def create_chat_router(service_provider: Callable[[], ChatService]) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["chat-v2"])

    @router.post("/threads", status_code=status.HTTP_201_CREATED)
    async def create_thread(request: CreateThreadRequest) -> dict:
        return service_provider().repository.create_thread(owner_id="local", title=request.title).model_dump(mode="json")

    @router.get("/threads/{thread_id}")
    async def get_thread(thread_id: str) -> dict:
        thread = service_provider().repository.get_thread(thread_id, owner_id="local")
        if thread is None:
            raise HTTPException(status_code=404, detail="thread_not_found")
        return thread.model_dump(mode="json")

    @router.post("/threads/{thread_id}/messages", status_code=status.HTTP_202_ACCEPTED)
    async def post_message(thread_id: str, request: PostMessageRequest, background: BackgroundTasks) -> dict:
        service = service_provider()
        try:
            started = service.start_message(
                thread_id=thread_id,
                owner_id="local",
                content=request.content,
                idempotency_key=request.idempotency_key,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="thread_not_found") from None
        if not started.reused:
            background.add_task(service.execute, started, owner_id="local")
        return started.model_dump(mode="json")

    @router.get("/threads/{thread_id}/events")
    async def get_events(
        thread_id: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        try:
            page = service_provider().repository.get_events(thread_id, owner_id="local", after_sequence=after_sequence, limit=limit)
        except KeyError:
            raise HTTPException(status_code=404, detail="thread_not_found") from None
        return page.model_dump(mode="json")

    @router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    async def cancel_qa_run(run_id: str) -> dict:
        if not service_provider().cancel(run_id, owner_id="local"):
            raise HTTPException(status_code=409, detail="run_not_running")
        return {"run_id": run_id, "cancel_requested": True}

    return router
