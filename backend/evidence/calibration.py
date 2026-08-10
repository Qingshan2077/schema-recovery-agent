"""Version interface for future supervised confidence calibration."""

from __future__ import annotations

from typing import Protocol


class ProbabilityCalibrator(Protocol):
    version: str

    def calibrate(self, probability: float) -> float: ...


class IdentityCalibrator:
    version = "identity-v1"

    def calibrate(self, probability: float) -> float:
        return max(0.0, min(1.0, probability))
