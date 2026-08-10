"""Grade tool choice, entity resolution, grounding and policy compliance."""

from __future__ import annotations

from math import sqrt
from typing import Any

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract


class QACaseOutcome(StrictContract):
    case_id: str
    expected_tools: list[str]
    actual_tools: list[str]
    expected_arguments: list[dict[str, Any]] = Field(default_factory=list)
    actual_arguments: list[dict[str, Any]] = Field(default_factory=list)
    expected_entities: list[str] = Field(default_factory=list)
    actual_entities: list[str] = Field(default_factory=list)
    claim_count: int = Field(ge=0)
    cited_claim_count: int = Field(ge=0)
    structured_output_valid: bool
    repaired: bool = False
    duration_ms: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class MetricValue(StrictContract):
    value: float = Field(ge=0, le=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    confidence_interval_95: tuple[float, float]


class QAGradeReport(StrictContract):
    sample_size: int = Field(ge=0)
    tool_selection_accuracy: MetricValue
    entity_resolution_accuracy: MetricValue
    citation_coverage: MetricValue
    structured_output_validity: MetricValue
    first_pass_validity: MetricValue
    repair_rate: MetricValue
    write_tool_violations: int = Field(ge=0)
    extra_tool_call_rate: float = Field(ge=0)
    average_tool_calls: float = Field(ge=0)
    p50_latency_ms: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0)


class QATrajectoryGrader:
    WRITE_MARKERS = ("execute_ddl", "create", "alter", "drop", "truncate", "write", "delete", "update")

    def grade(self, outcomes: list[QACaseOutcome]) -> QAGradeReport:
        count = len(outcomes)
        tool_correct = sum(
            self._tool_signature(item.expected_tools, item.expected_arguments)
            == self._tool_signature(item.actual_tools, item.actual_arguments)
            for item in outcomes
        )
        entity_cases = [item for item in outcomes if item.expected_entities]
        entity_correct = sum(item.expected_entities == item.actual_entities for item in entity_cases)
        claims = sum(item.claim_count for item in outcomes)
        cited = sum(item.cited_claim_count for item in outcomes)
        valid = sum(item.structured_output_valid for item in outcomes)
        first_pass = sum(item.structured_output_valid and not item.repaired for item in outcomes)
        repaired = sum(item.repaired for item in outcomes)
        extra_calls = sum(max(0, len(item.actual_tools) - len(item.expected_tools)) for item in outcomes)
        actual_calls = sum(len(item.actual_tools) for item in outcomes)
        latencies = sorted(item.duration_ms for item in outcomes)
        write_violations = sum(
            any(marker in tool.casefold() for marker in self.WRITE_MARKERS)
            for item in outcomes for tool in item.actual_tools
        )
        return QAGradeReport(
            sample_size=count,
            tool_selection_accuracy=_metric(tool_correct, count),
            entity_resolution_accuracy=_metric(entity_correct, len(entity_cases)),
            citation_coverage=_metric(cited, claims),
            structured_output_validity=_metric(valid, count),
            first_pass_validity=_metric(first_pass, count),
            repair_rate=_metric(repaired, count),
            write_tool_violations=write_violations,
            extra_tool_call_rate=extra_calls / max(actual_calls, 1),
            average_tool_calls=actual_calls / max(count, 1),
            p50_latency_ms=_percentile(latencies, 0.50),
            p95_latency_ms=_percentile(latencies, 0.95),
            total_input_tokens=sum(item.input_tokens for item in outcomes),
            total_output_tokens=sum(item.output_tokens for item in outcomes),
            total_cost_usd=round(sum(item.cost_usd for item in outcomes), 8),
        )

    @staticmethod
    def _tool_signature(tools: list[str], arguments: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return [(tool, repr(sorted((arguments[index] if index < len(arguments) else {}).items()))) for index, tool in enumerate(tools)]


def _metric(numerator: int, denominator: int) -> MetricValue:
    value = numerator / denominator if denominator else 0.0
    return MetricValue(value=value, numerator=numerator, denominator=denominator, confidence_interval_95=_wilson(numerator, denominator))


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def _percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * quantile)))
    return int(values[index])
