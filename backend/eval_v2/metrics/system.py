def rate_metric(rows: list[dict], field: str, expected=True) -> float:
    return sum(row.get(field) == expected for row in rows) / len(rows) if rows else 0.0


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile_value))]
