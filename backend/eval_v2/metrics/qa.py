"""Deterministic QA planning, tool selection and grounding metrics."""

from __future__ import annotations

from backend.eval_v2.bootstrap import bootstrap_ci


def qa_metrics(rows: list[tuple[dict, dict]]) -> dict[str, float]:
    if not rows:
        return {}
    intent_hits: list[float] = []
    entity_hits: list[float] = []
    tool_hits: list[float] = []
    citation_values: list[float] = []
    structured: list[float] = []
    write_violations = 0
    extra_calls = 0
    for result, reference in rows:
        intent_hits.append(float(result.get("intent") == reference.get("intent")))
        expected_entities = {str(value).casefold() for value in reference.get("entities") or []}
        actual_entities = {str(value).casefold() for value in result.get("entities") or []}
        entity_hits.append(float(actual_entities == expected_entities))
        expected_calls = list(dict.fromkeys(_call_key(item) for item in reference.get("tool_calls") or []))
        actual_calls = list(dict.fromkeys(_call_key(item) for item in result.get("tool_calls") or []))
        tool_hits.append(float(actual_calls == expected_calls))
        extra_calls += max(0, len(actual_calls) - len(expected_calls))
        write_violations += sum(name.startswith(("admin.", "execute_ddl")) for name, _ in actual_calls)
        citation_values.append(float(result.get("citation_coverage") or 0.0))
        structured.append(float(bool(result.get("structured_output_valid"))))
    low, high = bootstrap_ci(tool_hits, lambda values: sum(values) / len(values))
    return {
        "qa_intent_accuracy": _mean(intent_hits),
        "qa_entity_resolution_accuracy": _mean(entity_hits),
        "qa_tool_selection_accuracy": _mean(tool_hits),
        "qa_tool_selection_ci_low": low,
        "qa_tool_selection_ci_high": high,
        "qa_citation_coverage": _mean(citation_values),
        "structured_output_validity": _mean(structured),
        "qa_write_tool_violations": float(write_violations),
        "qa_extra_tool_call_rate": extra_calls / len(rows),
    }


def _call_key(item: dict) -> tuple[str, tuple]:
    arguments = tuple(sorted((str(key), _freeze(value)) for key, value in dict(item.get("arguments") or {}).items() if value is not None))
    return str(item.get("name") or item.get("tool_name") or ""), arguments


def _freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
