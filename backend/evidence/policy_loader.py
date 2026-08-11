"""Load one immutable fusion/calibration policy for replayable online scoring."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.evidence.calibration import IdentityCalibrator, IsotonicCalibrator, PlattCalibrator, ProbabilityCalibrator
from backend.evidence.contracts import CalibrationArtifact, ThresholdPolicy


@dataclass(frozen=True)
class FusionPolicyBundle:
    fusion_version: str
    feature_schema_hash: str
    threshold_policy: ThresholdPolicy
    calibrator: ProbabilityCalibrator
    coefficients: dict[str, float]
    prior_probability: float


def load_fusion_policy(path: str | Path, *, calibration_enabled: bool, feature_schema_path: str | Path | None = None) -> FusionPolicyBundle:
    payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    if feature_schema_path is not None:
        feature_schema = json.loads(Path(feature_schema_path).read_text(encoding="utf-8"))
        if str(feature_schema.get("version")) != str(payload.get("feature_schema_hash")):
            raise ValueError("fusion feature schema version does not match policy")
    threshold = ThresholdPolicy.model_validate(payload["threshold_policy"])
    calibration = dict(payload.get("calibration") or {})
    calibrator: ProbabilityCalibrator = IdentityCalibrator()
    if calibration_enabled and bool(calibration.get("validated", False)):
        algorithm = str(calibration.get("algorithm") or "identity")
        version = str(calibration.get("version") or "identity-v1")
        parameters = dict(calibration.get("parameters") or {})
        if algorithm == "platt":
            calibrator = PlattCalibrator(
                version=version,
                slope=float(parameters["slope"]),
                intercept=float(parameters["intercept"]),
            )
        elif algorithm == "isotonic":
            calibrator = IsotonicCalibrator(
                version=version,
                boundaries=[float(value) for value in parameters["boundaries"]],
                values=[float(value) for value in parameters["values"]],
            )
        elif algorithm != "identity":
            raise ValueError(f"unsupported configured calibration algorithm: {algorithm}")
    return FusionPolicyBundle(
        fusion_version=str(payload["fusion_version"]),
        feature_schema_hash=str(payload["feature_schema_hash"]),
        threshold_policy=threshold,
        calibrator=calibrator,
        coefficients={key: float(value) for key, value in dict(payload.get("coefficients") or {}).items()},
        prior_probability=float(payload.get("prior_probability", 0.18)),
    )


def calibration_artifact_from_policy(path: str | Path, *, git_sha: str) -> CalibrationArtifact:
    payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    calibration = dict(payload.get("calibration") or {})
    artifact_payload = {
        "calibration_version": str(calibration.get("version") or "identity-v1"),
        "fusion_version": str(payload["fusion_version"]),
        "feature_schema_hash": str(payload["feature_schema_hash"]),
        "dataset_version": str(calibration.get("dataset_version") or "unvalidated"),
        "split": "calibration",
        "git_sha": str(calibration.get("git_sha") or git_sha),
        "algorithm": str(calibration.get("algorithm") or "identity"),
        "parameters": dict(calibration.get("parameters") or {}),
        "metrics": {"validated": float(bool(calibration.get("validated", False)))},
        "created_at": datetime.fromisoformat(str(calibration.get("created_at") or "2026-08-11T00:00:00+00:00").replace("Z", "+00:00")),
    }
    canonical = json.dumps(artifact_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    artifact_payload["content_hash"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return CalibrationArtifact.model_validate(artifact_payload)
