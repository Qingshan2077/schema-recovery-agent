"""Production-contract eval executor backed by immutable in-memory catalog fixtures."""

from __future__ import annotations

from typing import Any

from backend.agent.qa import QAAgent
from backend.agent.runtime import RuntimeContainer
from backend.agent.runtime.tracing import InMemoryEventSink
from backend.core.identity import RunIdentity, stable_id
from backend.eval_v2.contracts import EvalCase, EvalRunManifest
from backend.observability.tracing import TraceEventSink, TraceRecorder


class _CompositeSink:
    def __init__(self, *sinks: Any):
        self.sinks = sinks

    async def emit(self, event: Any) -> None:
        for sink in self.sinks:
            await sink.emit(event)


class FixtureCaseExecutor:
    """Run QA cases through the real planner/verifier with fixture-only tools.

    The fixture runtime copies production ToolSpecs and allowlists, replacing only
    read executors. This evaluates model/tool policy behavior without accessing or
    polluting a configured database, memory store or monitor.
    """

    def __init__(self, *, runtime: RuntimeContainer, traces: TraceRecorder):
        self.runtime = runtime
        self.traces = traces
        self._active_namespaces: set[str] = set()

    async def execute(self, case: EvalCase, *, namespace: str, manifest: EvalRunManifest) -> dict[str, Any]:
        if namespace in self._active_namespaces:
            raise RuntimeError("eval_namespace_already_active")
        self._active_namespaces.add(namespace)
        if case.task_type != "qa":
            return {
                "status": "blocked",
                "case_id": case.case_id,
                "reason": "fixture_executor_supports_qa_only",
                "trace_complete": True,
            }
        fixture = dict(case.input.get("fixture") or {})
        calls: list[dict[str, Any]] = []
        isolated_tools = self.runtime.tool_runtime.fork(
            executor_overrides=_fixture_executors(fixture, calls),
        )
        qa = QAAgent(
            model_gateway=self.runtime.model_gateway,
            tool_runtime=isolated_tools,
        )
        identity = RunIdentity.create(thread_id=stable_id("thread", namespace))
        events = InMemoryEventSink()
        context = self.runtime.new_context(
            identity,
            agent_id="eval.qa",
            event_sink=_CompositeSink(events, TraceEventSink(self.traces)),
        )
        result = await qa.run(
            question=str(case.input.get("question") or ""),
            messages=list(case.input.get("messages") or []),
            run_context=context,
        )
        output = result.output
        return {
            "status": result.status.value,
            "case_id": case.case_id,
            "trace_id": identity.trace_id,
            "trace_complete": "runtime_event_sink_unavailable" not in context.audit_warnings,
            "output": output,
            "answer": output.get("answer"),
            "intent": output.get("intent"),
            "entities": [item.get("canonical_name") for item in output.get("entities", []) if item.get("canonical_name")],
            "citations": output.get("citations", []),
            "citation_coverage": output.get("citation_coverage", 0.0),
            "tool_calls": calls,
            "structured_output_valid": result.status.value not in {"failed"},
            "degraded": result.status.value == "degraded",
            "events": [item.model_dump(mode="json") for item in events.events],
        }

    async def cleanup(self, namespace: str) -> dict[str, Any]:
        existed = namespace in self._active_namespaces
        self._active_namespaces.discard(namespace)
        return {"namespace": namespace, "cleaned": existed, "leaked": namespace in self._active_namespaces}


def _fixture_executors(fixture: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    database = str(fixture.get("database") or "eval_fixture")
    schema = str(fixture.get("schema") or database)
    version = stable_id("snapshot", "eval", fixture)
    tables = dict(fixture.get("tables") or {})
    relations = list(fixture.get("relations") or [])

    def record(name: str, arguments: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        calls.append({"name": name, "arguments": arguments})
        return output

    def list_tables() -> dict[str, Any]:
        values = [
            {
                "entity_id": stable_id("catalog", database, schema, "table", name),
                "database": database,
                "schema_name": schema,
                "name": name,
                "kind": str(value.get("kind") or "table"),
                "aliases": list(value.get("aliases") or []),
                "row_estimate": int(value.get("row_estimate") or 0),
                "comment": str(value.get("comment") or ""),
            }
            for name, value in sorted(tables.items())
        ]
        return record("catalog.list_tables", {}, {"database": database, "catalog_version": version, "tables": values, "table_count": len(values)})

    def table_columns(table_name: str) -> dict[str, Any]:
        value = dict(tables.get(table_name) or {})
        columns = []
        for ordinal, column in enumerate(value.get("columns") or [], start=1):
            item = dict(column)
            columns.append({
                "ordinal": int(item.get("ordinal") or ordinal),
                "name": str(item["name"]),
                "data_type": str(item.get("data_type") or "varchar"),
                "nullable": bool(item.get("nullable", True)),
                "key": str(item.get("key") or ""),
                "default": item.get("default"),
                "comment": str(item.get("comment") or ""),
                "extra": str(item.get("extra") or ""),
            })
        output = {"database": database, "catalog_version": version, "table_id": stable_id("catalog", database, schema, "table", table_name), "table": table_name, "exists": table_name in tables, "columns": columns, "column_count": len(columns)}
        return record("catalog.query_table_columns", {"table_name": table_name}, output)

    def table_metadata(table_name: str) -> dict[str, Any]:
        value = dict(tables.get(table_name) or {})
        metadata = dict(value.get("metadata") or {})
        output = {"database": database, "catalog_version": version, "table_id": stable_id("catalog", database, schema, "table", table_name), "table": table_name, "exists": table_name in tables, "engine": str(metadata.get("engine") or ""), "estimated_rows": int(metadata.get("estimated_rows") or 0), "comment": str(value.get("comment") or ""), "created_at": str(metadata.get("created_at") or ""), "updated_at": str(metadata.get("updated_at") or "")}
        return record("catalog.query_table_metadata", {"table_name": table_name}, output)

    def indexes(table_name: str) -> dict[str, Any]:
        values = list(dict(tables.get(table_name) or {}).get("indexes") or [])
        return record("catalog.query_indexes", {"table_name": table_name}, {"database": database, "catalog_version": version, "table_id": stable_id("catalog", database, schema, "table", table_name), "table": table_name, "indexes": values, "index_count": len(values)})

    def relation_query(source_table: str | None = None, target_table: str | None = None) -> dict[str, Any]:
        values = [item for item in relations if (not source_table or item.get("source_table") == source_table) and (not target_table or item.get("target_table") == target_table)]
        return record("evidence.query_relations", {"source_table": source_table, "target_table": target_table}, {"database": database, "catalog_version": version, "relations": values, "relation_count": len(values)})

    def analysis_status() -> dict[str, Any]:
        return record("analysis.get_status", {}, {"database": database, "catalog_version": version, "available": False, "latest_analysis": {}})

    return {
        "catalog.list_tables": list_tables,
        "catalog.query_table_columns": table_columns,
        "catalog.query_table_metadata": table_metadata,
        "catalog.query_indexes": indexes,
        "evidence.query_relations": relation_query,
        "analysis.get_status": analysis_status,
    }
