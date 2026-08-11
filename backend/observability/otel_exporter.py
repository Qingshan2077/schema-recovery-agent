"""Optional OpenTelemetry SDK bridge for the vendor-neutral local span model."""

from __future__ import annotations

from typing import Any


class OpenTelemetrySpanExporter:
    def __init__(self, *, endpoint: str, service_name: str):
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer("schema-recovery-agent")

    def export(self, span: Any) -> None:
        if span.ended_at is None:
            return
        attributes = _flatten({
            **span.attributes,
            "schema_agent.trace_id": span.trace_id,
            "schema_agent.span_id": span.span_id,
            "schema_agent.parent_span_id": span.parent_span_id or "",
        })
        otel_span = self.tracer.start_span(
            span.name,
            start_time=int(span.started_at.timestamp() * 1_000_000_000),
            attributes=attributes,
        )
        otel_span.end(end_time=int(span.ended_at.timestamp() * 1_000_000_000))


def _flatten(values: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(_flatten(value, name))
        elif isinstance(value, (str, bool, int, float)):
            result[name] = value
        elif value is not None:
            result[name] = str(value)
    return result
