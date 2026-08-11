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
from backend.eval_v2.case_executor import FixtureCaseExecutor
from backend.eval_v2.store import EvalStore
from backend.observability.tracing import TraceRecorder
from backend.agent.runtime import build_runtime_container
from backend.mcp.server import init_mcp_tools
from backend.evidence.policy_loader import load_fusion_policy


def load_executor(*, traces):
    spec = os.environ.get("EVAL_CASE_EXECUTOR", "")
    if ":" in spec:
        module, factory = spec.split(":", 1)
        return getattr(importlib.import_module(module), factory)()
    runtime = build_runtime_container(Config)
    init_mcp_tools(runtime.tool_runtime)
    return FixtureCaseExecutor(runtime=runtime, traces=traces)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--dataset", default=os.environ.get("EVAL_DATASET_ID", "schema-agent-qa-core"))
    parser.add_argument("--dataset-version", default=os.environ.get("EVAL_DATASET_VERSION", "1.0.0"))
    parser.add_argument("--engine", default="manual")
    parser.add_argument("--gate", default="release-gate-v1")
    parser.add_argument("--enforce-gate", action="store_true")
    args = parser.parse_args()
    traces = TraceRecorder(Config.TRACE_DB_PATH)
    service = EvalService(registry=DatasetRegistry(Config.EVAL_DATASET_REGISTRY_PATH), store=EvalStore(Config.EVAL_V2_DB_PATH), artifacts=EvalArtifactStore(Config.EVAL_ARTIFACT_DIR), traces=traces, executor=load_executor(traces=traces))
    request = EvalCreateRequest(dataset_id=args.dataset, dataset_version=args.dataset_version, split=args.split, mode=args.mode, engine=args.engine, gate_policy=args.gate)
    fusion = load_fusion_policy(Config.FUSION_POLICY_PATH, calibration_enabled=Config.CALIBRATION_ENABLED, feature_schema_path=Config.FUSION_FEATURE_SCHEMA_PATH)
    versions = {
        **service.runtime_versions(),
        "fusion_version": fusion.fusion_version,
        "calibration_version": fusion.calibrator.version,
        "threshold_policy_version": fusion.threshold_policy.version,
        "memory_mode": "isolated",
        "runtime_config": {
            "cli": True, "engine": args.engine, "workflow": Config.WORKFLOW_VERSION,
            "state_schema": Config.STATE_SCHEMA_VERSION,
            "tool_policy": Config.TOOL_RUNTIME_ENFORCEMENT,
        },
    }
    record, cases = service.create(request, versions=versions, git_sha=Config.DEPLOYMENT_GIT_SHA, dirty_worktree=Config.DEPLOYMENT_DIRTY_WORKTREE)
    final = await service.execute(record.eval_run_id, cases)
    report = service.report(record.eval_run_id)
    gate = report["gate-result.json"]
    print({"eval_run_id": final.eval_run_id, "status": final.status, "gate": gate["status"]})
    if args.enforce_gate and gate["status"] != "passed": raise SystemExit(2)


asyncio.run(main())
