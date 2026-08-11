"""ECE, adaptive ECE, Brier and negative log likelihood."""

from __future__ import annotations

from math import log


def calibration_metrics(probabilities: list[float], labels: list[int], *, bins: int = 10) -> dict[str, float]:
    if len(probabilities) != len(labels) or not probabilities:
        return {"calibration_ece": 0.0, "calibration_adaptive_ece": 0.0, "calibration_brier": 0.0, "calibration_nll": 0.0}
    pairs = [(min(max(float(p), 1e-9), 1 - 1e-9), int(y)) for p, y in zip(probabilities, labels)]
    ece = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        bucket = [pair for pair in pairs if lower <= pair[0] < upper or (index == bins - 1 and pair[0] == 1)]
        if bucket:
            ece += len(bucket) / len(pairs) * abs(sum(p for p, _ in bucket) / len(bucket) - sum(y for _, y in bucket) / len(bucket))
    ordered = sorted(pairs)
    adaptive = 0.0
    width = max(1, len(ordered) // bins)
    for start in range(0, len(ordered), width):
        bucket = ordered[start:start + width]
        adaptive += len(bucket) / len(pairs) * abs(sum(p for p, _ in bucket) / len(bucket) - sum(y for _, y in bucket) / len(bucket))
    return {
        "calibration_ece": ece,
        "calibration_adaptive_ece": adaptive,
        "calibration_brier": sum((p - y) ** 2 for p, y in pairs) / len(pairs),
        "calibration_nll": -sum(y * log(p) + (1 - y) * log(1 - p) for p, y in pairs) / len(pairs),
    }
