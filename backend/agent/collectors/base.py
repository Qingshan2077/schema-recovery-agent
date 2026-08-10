"""Collector boundary and ToolRuntime-only invocation helper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.agent.runtime.contracts import ToolCallRequest
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.agent.runtime.hybrid_contracts import WorkUnit
from backend.core.identity import new_id


@dataclass
class CollectedFacts:
    content: dict[str, Any]
    legacy_output: dict[str, Any] = field(default_factory=dict)
    completeness: float = 1.0
    missing_capabilities: list[str] = field(default_factory=list)
    tool_call_ids: list[str] = field(default_factory=list)
    collector_version: str = "1.0.0"


class RecoveryCollector(Protocol):
    worker_id: str
    version: str

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: "CollectorRuntime") -> CollectedFacts: ...


class CollectorRuntime:
    def __init__(self, tool_runtime: ToolRuntime, run_context: RunContext, *, caller_agent: str):
        self.tool_runtime = tool_runtime
        self.run_context = run_context
        self.caller_agent = caller_agent
        self.tool_call_ids: list[str] = []

    async def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        request = ToolCallRequest(
            tool_call_id=new_id("tool_call"),
            tool_name=tool_name,
            arguments=arguments,
            caller_agent=self.caller_agent,
            run_id=self.run_context.run_id,
            trace_id=self.run_context.trace_id,
            parent_span_id=self.run_context.parent_span_id or new_id("span"),
        )
        result = await self.tool_runtime.execute(request, self.run_context.for_agent(self.caller_agent))
        self.tool_call_ids.append(result.tool_call_id)
        if result.status != "success" or result.output is None:
            code = result.error.code if result.error else "collector_tool_failed"
            raise RuntimeError(f"{tool_name} failed: {code}")
        return result.output
