"""Asynchronous Eval v2 resources; every GET is side-effect free."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Response, status

from backend.config import Config
from backend.eval_v2.contracts import EvalCreateRequest


def create_eval_v2_router(provider: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/v2/evals", tags=["eval-v2"])

    def service():
        if not Config.EVAL_V2_ENABLED: raise HTTPException(status_code=404, detail="eval_v2_disabled")
        return provider()

    @router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(request: EvalCreateRequest, background: BackgroundTasks, response: Response) -> dict[str, Any]:
        try:
            record, cases = service().create(request, versions=_versions(), git_sha=Config.DEPLOYMENT_GIT_SHA, dirty_worktree=Config.DEPLOYMENT_DIRTY_WORKTREE)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background.add_task(service().execute, record.eval_run_id, cases)
        response.headers["Location"] = f"/api/v2/evals/runs/{record.eval_run_id}"
        return record.model_dump(mode="json")

    @router.get("/runs/{eval_run_id}")
    async def get_run(eval_run_id: str) -> dict[str, Any]:
        try: return service().store.get(eval_run_id).model_dump(mode="json")
        except KeyError as exc: raise HTTPException(status_code=404, detail="eval_run_not_found") from exc

    @router.get("/runs/{eval_run_id}/events")
    async def events(eval_run_id: str, after_sequence: int = Query(default=0, ge=0), limit: int = Query(default=1000, ge=1, le=5000)) -> dict[str, Any]:
        service().store.get(eval_run_id)
        rows = service().store.events(eval_run_id, after=after_sequence, limit=limit)
        return {"items": rows, "next_sequence": max([after_sequence, *[row["sequence"] for row in rows]])}

    @router.get("/runs/{eval_run_id}/report")
    async def report(eval_run_id: str) -> dict[str, Any]:
        try: return service().report(eval_run_id)
        except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/runs/{eval_run_id}/cancel")
    async def cancel(eval_run_id: str) -> dict[str, Any]:
        try: return service().cancel(eval_run_id).model_dump(mode="json")
        except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/baselines/{eval_run_id}/promote")
    async def promote(eval_run_id: str, gate: str, reason: str, x_actor_id: str = Header(), x_actor_role: str = Header()) -> dict[str, Any]:
        if x_actor_role not in {"quality_admin", "release_manager"}: raise HTTPException(status_code=403, detail="baseline_promotion_forbidden")
        try: return service().promote(eval_run_id, gate=gate, actor_id=x_actor_id, actor_role=x_actor_role, reason=reason).model_dump(mode="json")
        except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/baselines/current")
    async def baseline(gate: str) -> dict[str, Any]:
        value = service().store.current_baseline(gate)
        if value is None: raise HTTPException(status_code=404, detail="baseline_not_found")
        return value

    return router


def _versions() -> dict[str, Any]:
    return {
        "model_profiles": {"fast": Config.MODEL_FAST, "reasoning": Config.MODEL_REASONING, "judge": Config.MODEL_JUDGE},
        "fusion_version": Config.FUSION_MODEL_VERSION,
        "calibration_version": "configured",
        "threshold_policy_version": "configured",
        "memory_mode": "isolated",
        "runtime_config": {"engine": Config.RECOVERY_ENGINE, "workflow": Config.WORKFLOW_VERSION},
    }
