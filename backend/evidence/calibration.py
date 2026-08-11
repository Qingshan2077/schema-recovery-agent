"""Versioned probability calibration used by the Phase 5 fusion pipeline."""

from __future__ import annotations

from bisect import bisect_right
from math import exp, log
from typing import Any, Protocol

from backend.evidence.contracts import CalibrationArtifact


class ProbabilityCalibrator(Protocol):
    version: str

    def calibrate(self, probability: float) -> float: ...


class IdentityCalibrator:
    version = "identity-v1"

    def calibrate(self, probability: float) -> float:
        return max(0.0, min(1.0, probability))


class PlattCalibrator:
    """Apply an offline-fitted sigmoid without learning from online traffic."""

    def __init__(self, *, version: str, slope: float, intercept: float):
        self.version = version
        self.slope = slope
        self.intercept = intercept

    def calibrate(self, probability: float) -> float:
        bounded = min(max(probability, 1e-9), 1 - 1e-9)
        logit = log(bounded / (1 - bounded))
        value = self.slope * logit + self.intercept
        return 1 / (1 + exp(-value)) if value >= 0 else exp(value) / (1 + exp(value))


class IsotonicCalibrator:
    def __init__(self, *, version: str, boundaries: list[float], values: list[float]):
        if not boundaries or len(boundaries) != len(values):
            raise ValueError("isotonic boundaries and values must be non-empty and aligned")
        if boundaries != sorted(boundaries) or values != sorted(values):
            raise ValueError("isotonic calibration points must be monotonic")
        self.version = version
        self.boundaries = boundaries
        self.values = values

    def calibrate(self, probability: float) -> float:
        index = min(bisect_right(self.boundaries, probability), len(self.values) - 1)
        return max(0.0, min(1.0, self.values[index]))


def calibrator_from_artifact(artifact: CalibrationArtifact) -> ProbabilityCalibrator:
    parameters: dict[str, Any] = artifact.parameters
    if artifact.algorithm == "identity":
        calibrator = IdentityCalibrator()
        calibrator.version = artifact.calibration_version
        return calibrator
    if artifact.algorithm == "platt":
        return PlattCalibrator(
            version=artifact.calibration_version,
            slope=float(parameters["slope"]),
            intercept=float(parameters["intercept"]),
        )
    if artifact.algorithm == "isotonic":
        return IsotonicCalibrator(
            version=artifact.calibration_version,
            boundaries=[float(value) for value in parameters["boundaries"]],
            values=[float(value) for value in parameters["values"]],
        )
    raise ValueError(f"unsupported calibration algorithm: {artifact.algorithm}")
