"""Base worker with Phase 1 runtime injection and an explicit legacy bridge."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.agent.runtime.contracts import ToolCallRequest
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.core.identity import new_id
from backend.mcp.tool_registry import ToolRegistry


class BaseWorker(ABC):
    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        run_context: RunContext | None = None,
        tool_runtime: ToolRuntime | None = None,
        model_gateway: ModelGateway | None = None,
    ):
        self.tool_registry = tool_registry
        self.tool_runtime = tool_runtime or tool_registry.runtime
        self.model_gateway = model_gateway
        self.run_context = run_context
        self._approved_operation_id: str | None = None
        self._call_log: list[dict[str, Any]] = []

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        pass

    def configure_runtime(
        self,
        *,
        run_context: RunContext,
        tool_runtime: ToolRuntime | None = None,
        model_gateway: ModelGateway | None = None,
    ) -> None:
        self.run_context = run_context.for_agent(self.worker_id)
        if tool_runtime is not None:
            self.tool_runtime = tool_runtime
        if model_gateway is not None:
            self.model_gateway = model_gateway

    def call_tool(self, name: str, **kwargs: Any) -> Any:
        if self.run_context is None:
            spec = self.tool_registry.get_spec(name)
            side_effecting = spec.side_effect in {"write", "ddl"}
            operation_id = self._approved_operation_id if side_effecting else None
            self._approved_operation_id = None
            result = self.tool_registry.execute_legacy(
                name,
                kwargs,
                approved=operation_id is not None,
                operation_id=operation_id,
            )
            call_id = new_id("tool_call")
            self._call_log.append(
                {
                    "tool_call_id": call_id,
                    "tool": name,
                    "tool_version": spec.version,
                    "params": _safe_params(kwargs),
                    "result_summary": _safe_summary(result),
                    "compatibility_mode": "legacy_registry",
                }
            )
            return result

        spec = self.tool_registry.get_spec(name)
        side_effecting = spec.side_effect in {"write", "ddl"}
        operation_id = self._approved_operation_id if side_effecting else None
        self._approved_operation_id = None
        tool_call_id = new_id("tool_call")
        request = ToolCallRequest(
            tool_call_id=tool_call_id,
            tool_name=name,
            arguments=kwargs,
            caller_agent=self.worker_id,
            run_id=self.run_context.run_id,
            trace_id=self.run_context.trace_id,
            parent_span_id=self.run_context.parent_span_id or new_id("span"),
            operation_id=operation_id,
            approved=operation_id is not None,
        )
        result = self.tool_runtime.execute_sync(request, self.run_context, allow_legacy=True)
        self._call_log.append(
            {
                "tool_call_id": result.tool_call_id,
                "tool": name,
                "tool_version": spec.version,
                "params": _safe_params(kwargs),
                "status": result.status,
                "output_hash": result.output_hash,
                "artifact_uri": result.artifact_uri,
                "result_summary": _safe_summary(result.output),
            }
        )
        if result.status != "success":
            raise RuntimeError(result.error.message if result.error else "Tool execution failed")
        return result.output or {}

    def approve_next_tool_call(self) -> str:
        """Record a one-shot approval token after the business guard has confirmed it."""

        if self.worker_id != "dba":
            raise PermissionError("Only the DBA compatibility worker may approve a side-effecting call")
        self._approved_operation_id = new_id("artifact")
        return self._approved_operation_id

    def get_call_log(self) -> list[dict[str, Any]]:
        return list(self._call_log)

    def reset_call_log(self) -> None:
        self._call_log.clear()

    @property
    def worker_id(self) -> str:
        return self.__class__.__name__.replace("Worker", "").lower()


def _safe_params(value: dict[str, Any]) -> dict[str, Any]:
    from backend.agent.runtime.redaction import redact_value

    return redact_value(value)


def _safe_summary(result: Any) -> str:
    from backend.agent.runtime.redaction import redact_value

    return str(redact_value(result))[:200]
