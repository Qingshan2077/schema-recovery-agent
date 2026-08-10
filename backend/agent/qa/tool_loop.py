"""Bounded, cached and policy-controlled QA tool executor."""

from __future__ import annotations

from backend.agent.qa.contracts import ToolExecution, ToolStep
from backend.agent.qa.errors import UnsafeQuestionError
from backend.agent.qa.policies import QAToolPolicy
from backend.agent.runtime.contracts import ToolCallRequest
from backend.agent.runtime.redaction import stable_hash
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.core.identity import new_id


class QAToolLoop:
    def __init__(self, runtime: ToolRuntime, policy: QAToolPolicy):
        self.runtime = runtime
        self.policy = policy
        self._cache: dict[str, dict[str, ToolExecution]] = {}
        self._call_counts: dict[str, int] = {}

    async def execute(self, steps: list[ToolStep], context: RunContext) -> list[ToolExecution]:
        self.policy.validate_steps(steps)
        executions: list[ToolExecution] = []
        run_cache = self._cache.setdefault(context.run_id, {})
        for step in steps:
            context.cancellation.raise_if_cancelled()
            cache_key = stable_hash({"tool": step.tool_name, "arguments": step.arguments})
            cached = run_cache.get(cache_key)
            if cached is not None:
                executions.append(cached.model_copy(update={"cached": True}))
                continue
            call_count = self._call_counts.get(context.run_id, 0)
            if call_count >= self.policy.max_calls:
                raise UnsafeQuestionError("QA run exceeded its total tool-call budget")
            self._call_counts[context.run_id] = call_count + 1
            request = ToolCallRequest(
                tool_call_id=new_id("tool_call"),
                tool_name=step.tool_name,
                arguments=step.arguments,
                caller_agent="qa",
                run_id=context.run_id,
                trace_id=context.trace_id,
                parent_span_id=context.parent_span_id or new_id("span"),
            )
            result = await self.runtime.execute(request, context.for_agent("qa.tool_loop"))
            execution = ToolExecution(
                tool_call_id=result.tool_call_id,
                tool_name=step.tool_name,
                arguments=step.arguments,
                status=result.status,
                output=result.output,
                output_hash=result.output_hash,
                error_code=result.error.code if result.error else None,
            )
            if result.status == "success":
                run_cache[cache_key] = execution
            executions.append(execution)
        return executions

    async def inventory(self, context: RunContext) -> ToolExecution:
        results = await self.execute(
            [ToolStep(tool_name="catalog.list_tables", arguments={}, purpose="resolve visible catalog entities", round=1)],
            context,
        )
        return results[0]

    def finish(self, run_id: str) -> None:
        self._cache.pop(run_id, None)
        self._call_counts.pop(run_id, None)


ReadOnlyToolLoop = QAToolLoop
