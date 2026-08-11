"""Controlled Eval v2 CLI; the case executor must be explicitly supplied by the environment."""
import argparse
import asyncio
import importlib
import os

from backend.config import Config
from backend.eval_v2.artifacts import EvalArtifactStore
from backend.eval_v2.contracts import EvalCreateRequest
from backend.eval_v2.registry import DatasetRegistry
from backend.eval_v2.service import EvalService
from backend.eval_v2.store import EvalStore
from backend.observability.tracing import TraceRecorder


def load_executor():
    spec = os.environ.get("EVAL_CASE_EXECUTOR", "")
    if ":" not in spec: raise RuntimeError("EVAL_CASE_EXECUTOR=module:factory is required")
    module, factory = spec.split(":", 1)
    return getattr(importlib.import_module(module), factory)()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--dataset", default=os.environ.get("EVAL_DATASET_ID", ""))
    parser.add_argument("--dataset-version", default=os.environ.get("EVAL_DATASET_VERSION", ""))
    parser.add_argument("--engine", default="manual")
    parser.add_argument("--gate", default="release-gate-v1")
    parser.add_argument("--enforce-gate", action="store_true")
    args = parser.parse_args()
    service = EvalService(registry=DatasetRegistry(Config.EVAL_DATASET_REGISTRY_PATH), store=EvalStore(Config.EVAL_V2_DB_PATH), artifacts=EvalArtifactStore(Config.EVAL_ARTIFACT_DIR), traces=TraceRecorder(Config.TRACE_DB_PATH), executor=load_executor())
    request = EvalCreateRequest(dataset_id=args.dataset, dataset_version=args.dataset_version, split=args.split, mode=args.mode, engine=args.engine, gate_policy=args.gate)
    record, cases = service.create(request, versions={"runtime_config": {"cli": True}}, git_sha=Config.DEPLOYMENT_GIT_SHA, dirty_worktree=Config.DEPLOYMENT_DIRTY_WORKTREE)
    final = await service.execute(record.eval_run_id, cases)
    report = service.report(record.eval_run_id)
    gate = report["gate-result.json"]
    print({"eval_run_id": final.eval_run_id, "status": final.status, "gate": gate["status"]})
    if args.enforce_gate and gate["status"] != "passed": raise SystemExit(2)


asyncio.run(main())
