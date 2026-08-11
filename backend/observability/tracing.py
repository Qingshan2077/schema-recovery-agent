"""Small vendor-neutral trace recorder with W3C context and non-blocking exporters."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Protocol

from backend.core.identity import new_id
from backend.observability.redaction import redact_attributes


_current_span: ContextVar["TraceSpan | None"] = ContextVar("current_trace_span", default=None)


class SpanExporter(Protocol):
    def export(self, span: "TraceSpan") -> None: ...


class TraceSpan:
    def __init__(self, recorder: "TraceRecorder", *, name: str, trace_id: str, span_id: str, parent_span_id: str | None, attributes: dict[str, Any]):
        self.recorder = recorder
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.attributes = redact_attributes(attributes)
        self.started_at = datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.status = "running"
        self.error_type: str | None = None

    def set(self, **attributes: Any) -> None:
        self.attributes.update(redact_attributes(attributes))

    def end(self, *, status: str = "completed", error_type: str | None = None) -> None:
        if self.ended_at is not None: return
        self.ended_at = datetime.now(timezone.utc)
        self.status = _canonical_trace_status(status)
        self.error_type = error_type
        self.attributes["duration_ms"] = (self.ended_at - self.started_at).total_seconds() * 1000
        self.attributes["status"] = self.status
        if error_type: self.attributes["error.type"] = error_type
        self.recorder.record(self)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_schema_version": "1.0", "name": self.name, "trace_id": self.trace_id,
            "span_id": self.span_id, "parent_span_id": self.parent_span_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status, "attributes": self.attributes,
        }


class TraceRecorder:
    def __init__(self, db_path: str | Path, exporters: list[SpanExporter] | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.exporters = exporters or []
        self.dropped_spans = 0
        self._migrate()

    @contextmanager
    def span(self, name: str, *, trace_id: str | None = None, parent_span_id: str | None = None, attributes: dict[str, Any] | None = None) -> Iterator[TraceSpan]:
        parent = _current_span.get()
        value = TraceSpan(
            self, name=name, trace_id=trace_id or (parent.trace_id if parent else _trace_id()),
            span_id=new_id("span"), parent_span_id=parent_span_id or (parent.span_id if parent else None),
            attributes=attributes or {},
        )
        token = _current_span.set(value)
        try:
            yield value
        except Exception as exc:
            value.end(status="failed", error_type=type(exc).__name__)
            raise
        else:
            value.end()
        finally:
            _current_span.reset(token)

    def record(self, span: TraceSpan) -> None:
        payload = span.as_dict()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """INSERT INTO trace_spans VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(span_id) DO UPDATE SET
                     parent_span_id=COALESCE(excluded.parent_span_id, trace_spans.parent_span_id),
                     name=excluded.name, status=excluded.status,
                     ended_at=COALESCE(excluded.ended_at, trace_spans.ended_at),
                     payload_json=excluded.payload_json""",
                (span.trace_id, span.span_id, span.parent_span_id, span.name, span.status,
                 span.started_at.isoformat(), span.ended_at.isoformat() if span.ended_at else None,
                 json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)),
            )
        for exporter in self.exporters:
            try: exporter.export(span)
            except Exception: self.dropped_spans += 1

    def record_event(self, event: Any) -> None:
        """Project a typed runtime/workflow event into the common span store.

        Started/completed events intentionally share their supplied span_id, so the
        completion upserts the open span instead of creating a disconnected trace.
        """
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
        event_type = str(payload.get("event_type") or payload.get("type") or "runtime.event")
        name = event_type.rsplit(".", 1)[0] if "." in event_type else event_type
        event_payload = dict(payload.get("payload") or {})
        usage = dict(payload.get("usage") or {})
        span = TraceSpan(
            self,
            name=name,
            trace_id=str(payload["trace_id"]),
            span_id=str(payload.get("span_id") or new_id("span")),
            parent_span_id=payload.get("parent_span_id"),
            attributes={
                "event.type": event_type,
                "event.sequence": payload.get("sequence"),
                "run.id": payload.get("run_id"),
                "thread.id": payload.get("thread_id") or payload.get("session_id"),
                "agent.id": payload.get("agent_id"),
                "node.id": payload.get("node_id"),
                "attempt": payload.get("attempt", 1),
                "tool.name": event_payload.get("tool"),
                "tool.version": event_payload.get("version"),
                "tool.call_id": event_payload.get("tool_call_id"),
                "model.profile": event_payload.get("profile"),
                "model.id": event_payload.get("model"),
                "prompt.version": event_payload.get("prompt_version"),
                "prompt.hash": event_payload.get("prompt_hash"),
                "snapshot.id": event_payload.get("snapshot_id"),
                "relation.id": event_payload.get("relation_id"),
                "evidence.ids": event_payload.get("evidence_ids"),
                "memory.ids": event_payload.get("memory_ids"),
                "input.tokens": usage.get("input_tokens"),
                "output.tokens": usage.get("output_tokens"),
                "cost.estimate": usage.get("estimated_cost_usd"),
                "redaction.level": dict(payload.get("redaction") or {}).get("level", "metadata_only"),
                "payload.stored": False,
            },
        )
        existing = self._span_payload(span.span_id)
        if existing is not None:
            span.started_at = datetime.fromisoformat(existing["started_at"])
            span.parent_span_id = span.parent_span_id or existing.get("parent_span_id")
            span.attributes = {
                **dict(existing.get("attributes") or {}),
                **span.attributes,
            }
        status = _canonical_trace_status(str(payload.get("status") or "running"))
        if event_type.endswith((".started", ".required", ".paused")) or status in {"queued", "running", "waiting_approval"}:
            span.status = status
            self.record(span)
            return
        span.end(status=status, error_type="runtime_failure" if status in {"failed", "blocked", "canceled"} else None)

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT payload_json FROM trace_spans WHERE trace_id=? ORDER BY started_at, span_id", (trace_id,)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def _span_payload(self, span_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM trace_spans WHERE span_id=?", (span_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _migrate(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS trace_spans(
              trace_id TEXT NOT NULL, span_id TEXT PRIMARY KEY, parent_span_id TEXT, name TEXT NOT NULL,
              status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, payload_json TEXT NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_trace_lookup ON trace_spans(trace_id, started_at)")


def parse_traceparent(value: str | None) -> tuple[str | None, str | None]:
    if not value: return None, None
    parts = value.split("-")
    if len(parts) != 4 or parts[0] != "00" or len(parts[1]) != 32 or len(parts[2]) != 16: return None, None
    return f"trc_{parts[1]}", f"spn_{parts[2]}"


def traceparent(trace_id: str, span_id: str) -> str:
    return f"00-{_hex(trace_id, 32)}-{_hex(span_id, 16)}-01"


class TraceEventSink:
    def __init__(self, recorder: TraceRecorder):
        self.recorder = recorder

    async def emit(self, event: Any) -> None:
        self.recorder.record_event(event)


def _hex(value: str, length: int) -> str:
    raw = value.split("_", 1)[-1]
    return raw[:length] if len(raw) >= length and all(char in "0123456789abcdef" for char in raw.lower()) else hashlib.sha256(value.encode()).hexdigest()[:length]


def _canonical_trace_status(value: str) -> str:
    return {
        "ok": "completed",
        "success": "completed",
        "complete": "completed",
        "error": "failed",
        "failure": "failed",
        "cancelled": "canceled",
    }.get(value.casefold(), value.casefold())


def _trace_id() -> str:
    return "trc_" + hashlib.sha256(new_id("trace").encode()).hexdigest()[:32]
