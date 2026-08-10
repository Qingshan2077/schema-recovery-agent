"""Authorized, validated, budgeted execution for local and future remote tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from time import perf_counter
from typing import Any, Protocol

from backend.agent.runtime.budget import BudgetExceededError
from backend.agent.runtime.contracts import ToolCallRequest, ToolCallResult, ToolSpec
from backend.agent.runtime.error_policy import public_error
from backend.agent.runtime.redaction import stable_hash, structural_summary
from backend.agent.runtime.run_context import RunContext, RuntimeCancelledError
from backend.agent.runtime.tracing import new_span_id


class ArtifactStore(Protocol):
    async def put(self, *, artifact_id: str, content: bytes, media_type: str) -> str: ...


class LocalArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    async def put(self, *, artifact_id: str, content: bytes, media_type: str) -> str:
        suffix = ".json" if media_type == "application/json" else ".bin"
        target = (self.root / f"{artifact_id}{suffix}").resolve()
        if target.parent != self.root:
            raise ValueError("Artifact path escapes configured root")
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)
        return target.as_uri()


class ToolRuntime:
    def __init__(
        self,
        *,
        allowlists: dict[str, set[str]] | None = None,
        artifact_store: ArtifactStore | None = None,
        enforcement: str = "enforce",
        max_argument_bytes: int = 262_144,
    ):
        if enforcement not in {"observe", "enforce"}:
            raise ValueError("Tool runtime enforcement must be observe or enforce")
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}
        self._allowlists = {agent: set(items) for agent, items in (allowlists or {}).items()}
        self.artifact_store = artifact_store
        self.enforcement = enforcement
        self.max_argument_bytes = max_argument_bytes

    def register(self, spec: ToolSpec, executor: Callable[..., Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = (spec, executor)

    def set_allowlist(self, agent_id: str, allowed: set[str]) -> None:
        self._allowlists[agent_id] = set(allowed)

    def execute_sync(
        self,
        request: ToolCallRequest,
        context: RunContext,
        *,
        allow_legacy: bool = False,
    ) -> ToolCallResult:
        """Explicit bridge for legacy synchronous workers during Phase 1."""

        factory = lambda: self.execute(request, context, allow_legacy=allow_legacy)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(factory())
        outcome: dict[str, Any] = {}

        def runner() -> None:
            try:
                outcome["result"] = asyncio.run(factory())
            except BaseException as exc:
                outcome["error"] = exc

        thread = Thread(target=runner, name="legacy-tool-runtime", daemon=True)
        thread.start()
        thread.join()
        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]

    def discover(self, caller_agent: str) -> list[dict[str, Any]]:
        discovered: list[dict[str, Any]] = []
        for name, (spec, _) in sorted(self._tools.items()):
            if not spec.ready_for_agent or spec.side_effect in {"write", "ddl"}:
                continue
            if not self._is_allowed(caller_agent, spec):
                continue
            discovered.append(
                {
                    "name": name,
                    "version": spec.version,
                    "description": spec.description,
                    "capability": spec.capability,
                    "side_effect": spec.side_effect,
                    "input_schema": spec.input_model.model_json_schema(),
                    "output_schema": spec.output_model.model_json_schema(),
                }
            )
        return discovered

    async def execute(
        self,
        request: ToolCallRequest,
        context: RunContext,
        *,
        allow_legacy: bool = False,
    ) -> ToolCallResult:
        started = perf_counter()
        span_id = new_span_id()
        attempts = 0
        try:
            context.ensure_identity(run_id=request.run_id, trace_id=request.trace_id)
            context.cancellation.raise_if_cancelled()
            spec, executor = self._lookup(request.tool_name)
            denial = self._authorization_denial(request, spec, allow_legacy=allow_legacy)
            if denial:
                await context.tracer.emit(
                    context=context,
                    event_type="guardrail.blocked",
                    status="blocked",
                    span_id=span_id,
                    parent_span_id=request.parent_span_id,
                    payload={
                        "tool_call_id": request.tool_call_id,
                        "tool": spec.name,
                        "reason": denial,
                        "side_effect": spec.side_effect,
                    },
                    security_required=True,
                )
                if self.enforcement == "enforce" or spec.side_effect in {"write", "ddl"}:
                    return _error_result(
                        request,
                        started,
                        attempts,
                        public_error(
                            code="tool_permission_denied",
                            category="permission",
                            message="Tool call was blocked by runtime policy",
                            source="tool_runtime",
                            details={"reason": denial, "tool": spec.name},
                            cause_span_id=span_id,
                        ),
                    )
            else:
                await context.tracer.emit(
                    context=context,
                    event_type="guardrail.passed",
                    status="success",
                    span_id=span_id,
                    parent_span_id=request.parent_span_id,
                    payload={"tool_call_id": request.tool_call_id, "tool": spec.name, "side_effect": spec.side_effect},
                    security_required=spec.side_effect in {"write", "ddl"},
                )
            argument_bytes = len(
                json.dumps(request.arguments, ensure_ascii=False, default=str).encode("utf-8")
            )
            if argument_bytes > self.max_argument_bytes:
                return _error_result(
                    request,
                    started,
                    attempts,
                    public_error(
                        code="tool_input_too_large",
                        category="validation",
                        message="Tool arguments exceed the runtime size limit",
                        source="tool_runtime",
                        details={"bytes": argument_bytes, "limit": self.max_argument_bytes},
                        cause_span_id=span_id,
                    ),
                )
            try:
                validated_input = spec.input_model.model_validate(request.arguments)
                arguments = validated_input.model_dump(exclude_none=True)
            except Exception:
                return _error_result(
                    request,
                    started,
                    attempts,
                    public_error(
                        code="tool_input_invalid",
                        category="validation",
                        message="Tool arguments failed strict validation",
                        source="tool_runtime",
                        cause_span_id=span_id,
                    ),
                )
            await context.tracer.emit(
                context=context,
                event_type="tool.started",
                status="running",
                span_id=span_id,
                parent_span_id=request.parent_span_id,
                payload={
                    "tool": spec.name,
                    "tool_call_id": request.tool_call_id,
                    "version": spec.version,
                    "arguments": structural_summary(arguments),
                    "side_effect": spec.side_effect,
                },
            )
            max_attempts = spec.max_retries + 1 if spec.idempotent and spec.side_effect in {"none", "read"} else 1
            last_error: Exception | None = None
            while attempts < max_attempts:
                attempts += 1
                context.cancellation.raise_if_cancelled()
                context.budget.reserve_tool()
                try:
                    raw_output = await asyncio.wait_for(
                        _invoke_executor(executor, arguments),
                        timeout=spec.timeout_seconds,
                    )
                    try:
                        validated_output = spec.output_model.model_validate(raw_output)
                    except Exception:
                        return await self._failed(
                            request=request,
                            context=context,
                            spec=spec,
                            span_id=span_id,
                            started=started,
                            attempts=attempts,
                            error=public_error(
                                code="tool_output_invalid",
                                category="tool",
                                message="Tool output failed strict validation",
                                source=spec.name,
                                cause_span_id=span_id,
                            ),
                        )
                    output = validated_output.model_dump(mode="json")
                    if "root" in output and len(output) == 1:
                        output = output["root"]
                    return await self._complete(
                        request=request,
                        context=context,
                        spec=spec,
                        span_id=span_id,
                        started=started,
                        attempts=attempts,
                        output=output,
                    )
                except TimeoutError as exc:
                    last_error = exc
                except (RuntimeCancelledError, asyncio.CancelledError):
                    raise
                except Exception as exc:
                    last_error = exc
                if attempts < max_attempts:
                    await asyncio.sleep(min(0.1 * (2 ** (attempts - 1)), 0.5))
            return await self._failed(
                request=request,
                context=context,
                spec=spec,
                span_id=span_id,
                started=started,
                attempts=attempts,
                error=public_error(
                    code="tool_timeout" if isinstance(last_error, TimeoutError) else "tool_execution_failed",
                    category="timeout" if isinstance(last_error, TimeoutError) else "tool",
                    message="Tool execution failed",
                    source=spec.name,
                    retryable=spec.idempotent and spec.side_effect in {"none", "read"},
                    cause_span_id=span_id,
                ),
            )
        except (RuntimeCancelledError, asyncio.CancelledError):
            return _error_result(
                request,
                started,
                attempts,
                public_error(
                    code="tool_cancelled",
                    category="cancelled",
                    message="Tool call was cancelled",
                    source="tool_runtime",
                    cause_span_id=span_id,
                ),
                status="cancelled",
            )
        except BudgetExceededError as exc:
            return _error_result(
                request,
                started,
                attempts,
                public_error(
                    code="runtime_budget_exhausted",
                    category="budget",
                    message="Tool call blocked by run budget",
                    source="budget_ledger",
                    details={"dimension": exc.dimension, "current": exc.current, "limit": exc.limit},
                    cause_span_id=span_id,
                ),
            )
        except (KeyError, ValueError) as exc:
            await context.tracer.emit(
                context=context,
                event_type="guardrail.blocked",
                status="blocked",
                span_id=span_id,
                parent_span_id=request.parent_span_id,
                payload={
                    "tool_call_id": request.tool_call_id,
                    "tool": request.tool_name,
                    "reason": "identity_or_tool_not_available",
                },
                security_required=True,
            )
            return _error_result(
                request,
                started,
                attempts,
                public_error(
                    code="tool_not_available",
                    category="validation",
                    message=str(exc),
                    source="tool_runtime",
                    cause_span_id=span_id,
                ),
            )
        except Exception:
            return _error_result(
                request,
                started,
                attempts,
                public_error(
                    code="tool_runtime_internal_error",
                    category="internal",
                    message="Tool runtime failed before producing a valid result",
                    source="tool_runtime",
                    cause_span_id=span_id,
                ),
            )

    async def _complete(
        self,
        *,
        request: ToolCallRequest,
        context: RunContext,
        spec: ToolSpec,
        span_id: str,
        started: float,
        attempts: int,
        output: dict[str, Any],
    ) -> ToolCallResult:
        serialized = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        output_hash = stable_hash(output)
        artifact_uri: str | None = None
        public_output: dict[str, Any] | None = context.redaction_policy.redact(output)
        if len(serialized) > spec.max_result_bytes or spec.sensitivity == "restricted":
            if self.artifact_store is None:
                return await self._failed(
                    request=request,
                    context=context,
                    spec=spec,
                    span_id=span_id,
                    started=started,
                    attempts=attempts,
                    error=public_error(
                        code="tool_artifact_store_required",
                        category="tool",
                        message="Tool result requires an artifact store",
                        source="tool_runtime",
                        cause_span_id=span_id,
                    ),
                )
            artifact_uri = await self.artifact_store.put(
                artifact_id=request.tool_call_id,
                content=serialized,
                media_type="application/json",
            )
            public_output = {
                "artifact": True,
                "sha256": output_hash,
                "bytes": len(serialized),
                "summary": structural_summary(output),
            }
        duration_ms = int((perf_counter() - started) * 1000)
        await context.tracer.emit(
            context=context,
            event_type="tool.completed",
            status="success",
            span_id=span_id,
            parent_span_id=request.parent_span_id,
            attempt=attempts,
            payload={
                "tool": spec.name,
                "tool_call_id": request.tool_call_id,
                "version": spec.version,
                "output_hash": output_hash,
                "artifact_uri": artifact_uri,
                "bytes": len(serialized),
                "duration_ms": duration_ms,
            },
        )
        await self._emit_usage(context, span_id)
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status="success",
            output=public_output,
            artifact_uri=artifact_uri,
            output_hash=output_hash,
            duration_ms=duration_ms,
            attempt_count=attempts,
        )

    async def _failed(
        self,
        *,
        request: ToolCallRequest,
        context: RunContext,
        spec: ToolSpec,
        span_id: str,
        started: float,
        attempts: int,
        error: Any,
    ) -> ToolCallResult:
        await context.tracer.emit(
            context=context,
            event_type="tool.failed",
            status="error",
            span_id=span_id,
            parent_span_id=request.parent_span_id,
            attempt=max(1, attempts),
            payload={
                "tool_call_id": request.tool_call_id,
                "tool": spec.name,
                "error_code": error.code,
                "category": error.category,
            },
        )
        await self._emit_usage(context, span_id)
        return _error_result(request, started, attempts, error)

    async def _emit_usage(self, context: RunContext, parent_span_id: str) -> None:
        await context.tracer.emit(
            context=context,
            event_type="usage.updated",
            status="success",
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            payload={"current": context.budget.snapshot().model_dump(mode="json"), "limits": context.budget.limits()},
        )

    def _lookup(self, name: str) -> tuple[ToolSpec, Callable[..., Any]]:
        if name not in self._tools:
            raise KeyError(f"Tool is not registered: {name}")
        return self._tools[name]

    def _authorization_denial(self, request: ToolCallRequest, spec: ToolSpec, *, allow_legacy: bool) -> str | None:
        if not allow_legacy and not spec.ready_for_agent:
            return "tool_not_ready_for_agent"
        if not allow_legacy and not self._is_allowed(request.caller_agent, spec):
            return "caller_not_allowlisted"
        if spec.side_effect in {"write", "ddl"}:
            if not request.approved:
                return "approval_required"
            if not request.operation_id:
                return "operation_id_required"
        if spec.approval_policy == "always" and not request.approved:
            return "approval_required"
        if spec.approval_policy == "conditional" and spec.side_effect != "none" and not request.approved:
            return "conditional_approval_required"
        return None

    def _is_allowed(self, caller_agent: str, spec: ToolSpec) -> bool:
        allowed = self._allowlists.get(caller_agent, set())
        return spec.name in allowed or spec.capability in allowed or "*" in allowed


async def _invoke_executor(executor: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(executor):
        return await executor(**arguments)
    return await asyncio.to_thread(executor, **arguments)


def _error_result(
    request: ToolCallRequest,
    started: float,
    attempts: int,
    error: Any,
    *,
    status: str = "error",
) -> ToolCallResult:
    return ToolCallResult(
        tool_call_id=request.tool_call_id,
        status=status,
        output=None,
        duration_ms=int((perf_counter() - started) * 1000),
        attempt_count=attempts,
        error=error,
    )
