"""Legacy-compatible registration and discovery facade over ToolRuntime."""

from __future__ import annotations

import inspect
import warnings
from typing import Any, Callable, get_type_hints

from pydantic import BaseModel, ConfigDict, RootModel, create_model

from backend.agent.runtime.contracts import RunBudget, ToolCallRequest, ToolSpec
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.core.identity import RunIdentity, new_id


class LegacyToolOutput(RootModel[dict[str, Any]]):
    pass


class LegacyToolSpecAdapter:
    """Create an explicit minimum ToolSpec for a legacy registration."""

    @staticmethod
    def adapt(
        *,
        name: str,
        fn: Callable[..., Any],
        description: str,
        input_schema: dict[str, Any],
        output_model: type[BaseModel] | None,
        capability: str | None,
        side_effect: str | None,
        approval_policy: str | None,
        idempotent: bool | None,
        timeout_seconds: float,
        max_result_bytes: int,
        sensitivity: str,
        ready_for_agent: bool,
        max_retries: int,
    ) -> ToolSpec:
        inferred_side_effect = side_effect or ("ddl" if name == "execute_ddl" else "read")
        return ToolSpec(
            name=name,
            version="1.0.0",
            description=description,
            input_model=_legacy_input_model(name, fn, input_schema),
            output_model=output_model or LegacyToolOutput,
            capability=capability or f"tool:{name}",
            side_effect=inferred_side_effect,
            approval_policy=approval_policy or ("always" if inferred_side_effect in {"write", "ddl"} else "never"),
            idempotent=(inferred_side_effect in {"none", "read"}) if idempotent is None else idempotent,
            timeout_seconds=timeout_seconds,
            max_result_bytes=max_result_bytes,
            sensitivity=sensitivity,
            ready_for_agent=ready_for_agent and output_model is not None,
            max_retries=max_retries,
        )


class ToolRegistry:
    """Compatibility layer; new agents must depend on ``ToolRuntime`` directly."""

    def __init__(self, runtime: ToolRuntime | None = None) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self.runtime = runtime or ToolRuntime(enforcement="enforce")

    def clear(self) -> None:
        """Test-only compatibility hook."""

        self._tools.clear()
        self.runtime = ToolRuntime(enforcement=self.runtime.enforcement)

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        *,
        output_model: type[BaseModel] | None = None,
        capability: str | None = None,
        side_effect: str | None = None,
        approval_policy: str | None = None,
        idempotent: bool | None = None,
        timeout_seconds: float = 30.0,
        max_result_bytes: int = 256_000,
        sensitivity: str = "internal",
        ready_for_agent: bool = False,
        max_retries: int = 1,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        spec = LegacyToolSpecAdapter.adapt(
            name=name,
            fn=fn,
            description=description,
            input_schema=input_schema or {},
            output_model=output_model,
            capability=capability,
            side_effect=side_effect,
            approval_policy=approval_policy,
            idempotent=idempotent,
            timeout_seconds=timeout_seconds,
            max_result_bytes=max_result_bytes,
            sensitivity=sensitivity,
            ready_for_agent=ready_for_agent,
            max_retries=max_retries,
        )
        self._tools[name] = {"fn": fn, "spec": spec, "legacy_input_schema": input_schema or {}}
        self.runtime.register(spec, fn)

    def execute(self, name: str, **kwargs: Any) -> Any:
        warnings.warn(
            "ToolRegistry.execute() is deprecated; inject ToolRuntime into new agents",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.execute_legacy(name, kwargs)

    def execute_legacy(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        approved: bool = False,
        operation_id: str | None = None,
    ) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not registered. Available: {list(self._tools.keys())}")
        identity = RunIdentity.create()
        context = RunContext.from_identity(identity, agent_id="legacy_registry", budget=_legacy_budget())
        spec: ToolSpec = self._tools[name]["spec"]
        request = ToolCallRequest(
            tool_call_id=new_id("tool_call"),
            tool_name=name,
            arguments=arguments,
            caller_agent="legacy_registry",
            run_id=identity.run_id,
            trace_id=identity.trace_id,
            parent_span_id=new_id("span"),
            approved=approved,
            operation_id=operation_id,
        )
        result = self.runtime.execute_sync(request, context, allow_legacy=True)
        if result.status != "success":
            raise RuntimeError(result.error.message if result.error else "Tool execution failed")
        return result.output

    def get_spec(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]["spec"]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": meta["spec"].description,
                "input_schema": meta["spec"].input_model.model_json_schema(),
                "output_schema": meta["spec"].output_model.model_json_schema(),
                "version": meta["spec"].version,
                "capability": meta["spec"].capability,
                "side_effect": meta["spec"].side_effect,
                "sensitivity": meta["spec"].sensitivity,
                "ready_for_agent": meta["spec"].ready_for_agent,
            }
            for name, meta in sorted(self._tools.items())
        ]


def _legacy_input_model(name: str, fn: Callable[..., Any], schema: dict[str, Any]) -> type[BaseModel]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    try:
        hints = get_type_hints(fn)
    except (NameError, TypeError):
        hints = {}
    fields: dict[str, tuple[Any, Any]] = {}
    for parameter_name, parameter in inspect.signature(fn).parameters.items():
        annotation = hints.get(parameter_name, _schema_type(properties.get(parameter_name, {})))
        if annotation is inspect.Parameter.empty:
            annotation = Any
        if parameter.default is not inspect.Parameter.empty:
            default = parameter.default
        elif parameter_name in required or not properties:
            default = ...
        else:
            default = None
            annotation = annotation | None if isinstance(annotation, type) else Any
        fields[parameter_name] = (annotation, default)
    return create_model(
        f"{''.join(part.title() for part in name.split('_'))}LegacyInput",
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )


def _schema_type(schema: dict[str, Any]) -> Any:
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list[Any],
        "object": dict[str, Any],
    }.get(schema.get("type"), Any)


def _legacy_budget() -> RunBudget:
    return RunBudget(
        max_model_calls=1,
        max_tool_calls=10,
        max_input_tokens=1,
        max_output_tokens=1,
        max_cost_usd=None,
        max_loop_iterations=1,
    )
