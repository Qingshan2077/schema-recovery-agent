"""Manifest construction from explicit, sanitized version inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.eval_v2.contracts import DatasetManifest, EvalCreateRequest, EvalRunManifest
from backend.eval_v2.hashing import content_hash


def build_manifest(
    eval_run_id: str, request: EvalCreateRequest, dataset: DatasetManifest, cases: list,
    *, versions: dict[str, Any], git_sha: str, dirty_worktree: bool,
) -> EvalRunManifest:
    case_ids = sorted(case.case_id for case in cases)
    return EvalRunManifest(
        eval_run_id=eval_run_id, git_sha=git_sha, dirty_worktree=dirty_worktree,
        dataset_id=dataset.dataset_id, dataset_version=dataset.version,
        dataset_hash=dataset.content_hash, split=request.split,
        case_ids_hash=content_hash(case_ids), snapshot_hashes={}, engine=request.engine,
        model_profiles=dict(versions.get("model_profiles") or {}),
        provider_versions=dict(versions.get("provider_versions") or {}),
        prompt_hashes=dict(versions.get("prompt_hashes") or {}),
        tool_versions=dict(versions.get("tool_versions") or {}),
        fusion_version=str(versions.get("fusion_version") or "unknown"),
        calibration_version=str(versions.get("calibration_version") or "unknown"),
        threshold_policy_version=str(versions.get("threshold_policy_version") or "unknown"),
        memory_mode=str(versions.get("memory_mode") or "isolated"),
        runtime_config_hash=content_hash(versions.get("runtime_config") or {}),
        seed=request.seed,
        determinism="deterministic" if request.seed is not None else "non_deterministic",
        mode=request.mode, gate_policy=request.gate_policy,
        started_at=datetime.now(timezone.utc),
    )
