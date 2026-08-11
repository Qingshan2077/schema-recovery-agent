"""Deterministic percentile bootstrap confidence intervals."""

from __future__ import annotations

import random
from typing import Callable


def bootstrap_ci(values: list[float], statistic: Callable[[list[float]], float], *, seed: int = 17, samples: int = 1000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    estimates = sorted(statistic([rng.choice(values) for _ in values]) for _ in range(samples))
    return estimates[int(samples * .025)], estimates[min(samples - 1, int(samples * .975))]
