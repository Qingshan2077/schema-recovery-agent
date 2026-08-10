"""Provider-neutral model gateway with strict output, budget, retry, and trace controls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from threading import Thread
from typing import Any

from backend.agent.runtime.budget import BudgetExceededError
from backend.agent.runtime.context_builder import ContextBuilder
from backend.agent.runtime.contracts import ModelEvent, ModelRequest, ModelResult, ModelUsage
from backend.agent.runtime.error_policy import public_error
from backend.agent.runtime.model_profiles import CapabilityError, ModelProfileRegistry
from backend.agent.runtime.prompt_registry import PromptRegistry, PromptRegistryError, RenderedPrompt
from backend.agent.runtime.providers.base import ProviderAdapter, ProviderError, ProviderRequest, ProviderResponse
from backend.agent.runtime.redaction import stable_hash
from backend.agent.runtime.run_context import RunContext, RuntimeCancelledError
from backend.agent.runtime.structured_output import StructuredOutputError, parse_and_validate, repair_instruction
from backend.agent.runtime.tracing import new_span_id
from backend.core.identity import new_id


class ModelGateway:
    """The only application-facing entry point for model inference."""

    def __init__(
        self,
        *,
        profiles: ModelProfileRegistry,
        prompts: PromptRegistry,
        providers: dict[str, ProviderAdapter],
        context_builder: ContextBuilder | None = None,
        repair_enabled: bool = True,
    ):
        self.profiles = profiles
        self.prompts = prompts
        self.providers = dict(providers)
        self.context_builder = context_builder or ContextBuilder()
        self.repair_enabled = repair_enabled

    async def generate_structured(self, request: ModelRequest, context: RunContext) -> ModelResult:
        model_call_id = new_id("model_call")
        attempts = 0
        usage = ModelUsage()
        try:
            context.cancellation.raise_if_cancelled()
            profile = self.profiles.get(request.profile)
            provider = self._provider(profile.provider)
            built = self.context_builder.build(request.input)
            rendered = self.prompts.render(request.prompt_id, request.prompt_version, built.values)
            if stable_hash(rendered.output_schema) != stable_hash(request.output_schema):
                raise PromptRegistryError("Request output schema does not match the immutable prompt snapshot")
            degraded_reasons = self.profiles.validate_capabilities(
                profile.name,
                rendered.required_capabilities,
                allow_local_schema_validation=True,
            )
            if request.tool_specs and not profile.capabilities.supports_tools:
                raise CapabilityError(f"Profile '{profile.name}' does not support tools")
            response, call_attempts, call_usage = await self._invoke(
                provider=provider,
                profile=profile,
                rendered_prompt=rendered.content,
                output_schema=request.output_schema,
                model_call_id=model_call_id,
                context=context,
                estimated_input_tokens=built.estimated_tokens,
                max_output_tokens=_max_output_tokens(request),
                tool_specs=request.tool_specs,
                prompt_version=rendered.version,
                prompt_hash=rendered.sha256,
            )
            attempts += call_attempts
            usage = _add_usage(usage, call_usage)
            try:
                parsed = parse_and_validate(response.content, request.output_schema).value
            except StructuredOutputError as validation_error:
                if self.repair_enabled:
                    repaired = await self._repair(
                        original=response.content,
                        validation_error=validation_error,
                        provider=provider,
                        profile=profile,
                        output_schema=request.output_schema,
                        model_call_id=model_call_id,
                        context=context,
                        max_output_tokens=_max_output_tokens(request),
                        prompt_version=rendered.version,
                    )
                    attempts += repaired[1]
                    usage = _add_usage(usage, repaired[2])
                    if repaired[0] is not None:
                        return await self._completed_result(
                            context=context,
                            model_call_id=model_call_id,
                            profile=profile,
                            response=repaired[0],
                            parsed=repaired[3],
                            usage=usage,
                            attempts=attempts,
                            rendered=rendered,
                            repaired=True,
                            degradation_reasons=degraded_reasons,
                        )
                fallback = await self._try_fallback(
                    request=request,
                    context=context,
                    rendered=rendered,
                    model_call_id=model_call_id,
                    estimated_input_tokens=built.estimated_tokens,
                )
                if fallback is not None:
                    fallback.attempt_count += attempts
                    fallback.usage = _add_usage(usage, fallback.usage)
                    return fallback
                error = public_error(
                    code=validation_error.code,
                    category="validation",
                    message="Model output failed strict schema validation",
                    source="structured_output",
                    details={"path": validation_error.path},
                )
                return await self._failed_result(
                    context=context,
                    model_call_id=model_call_id,
                    model=profile.model,
                    provider=profile.provider,
                    attempts=attempts,
                    usage=usage,
                    error=error,
                    prompt_hash=rendered.sha256,
                )
            return await self._completed_result(
                context=context,
                model_call_id=model_call_id,
                profile=profile,
                response=response,
                parsed=parsed,
                usage=usage,
                attempts=attempts,
                rendered=rendered,
                degradation_reasons=degraded_reasons,
            )
        except asyncio.CancelledError:
            error = public_error(
                code="model_cancelled",
                category="cancelled",
                message="Model call was cancelled",
                source="model_gateway",
            )
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
                status="cancelled",
            )
        except RuntimeCancelledError as exc:
            error = public_error(
                code="model_cancelled",
                category="cancelled",
                message=str(exc),
                source="model_gateway",
            )
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
                status="cancelled",
            )
        except BudgetExceededError as exc:
            error = public_error(
                code="runtime_budget_exhausted",
                category="budget",
                message="Model call blocked by run budget",
                source="budget_ledger",
                details={"dimension": exc.dimension, "current": exc.current, "limit": exc.limit},
            )
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
            )
        except (CapabilityError, PromptRegistryError, ValueError) as exc:
            error = public_error(
                code="runtime_configuration_invalid",
                category="validation",
                message=str(exc),
                source="model_gateway",
            )
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
            )
        except ProviderError as exc:
            error = _provider_agent_error(exc)
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
            )
        except Exception:
            error = public_error(
                code="model_runtime_internal_error",
                category="internal",
                message="Model runtime failed before producing a valid result",
                source="model_gateway",
            )
            return await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=request.profile,
                provider="unknown",
                attempts=attempts,
                usage=usage,
                error=error,
            )

    def generate_structured_sync(self, request: ModelRequest, context: RunContext) -> ModelResult:
        """Compatibility bridge for the synchronous evaluation facade."""

        factory = lambda: self.generate_structured(request, context)
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

        thread = Thread(target=runner, name="legacy-model-gateway", daemon=True)
        thread.start()
        thread.join()
        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]

    async def stream_text(self, request: ModelRequest, context: RunContext) -> AsyncIterator[ModelEvent]:
        model_call_id = new_id("model_call")
        model_name = request.profile
        provider_name = "unknown"
        usage = ModelUsage()
        try:
            context.cancellation.raise_if_cancelled()
            profile = self.profiles.get(request.profile)
            model_name = profile.model
            provider_name = profile.provider
            if not profile.capabilities.supports_streaming:
                raise CapabilityError(f"Profile '{profile.name}' does not support streaming")
            provider = self._provider(profile.provider)
            built = self.context_builder.build(request.input)
            rendered = self.prompts.render(request.prompt_id, request.prompt_version, built.values)
            if stable_hash(rendered.output_schema) != stable_hash(request.output_schema):
                raise PromptRegistryError("Request output schema does not match the immutable prompt snapshot")
            max_output_tokens = _max_output_tokens(request)
            reservation = context.budget.reserve_model(
                input_tokens=built.estimated_tokens,
                output_tokens=max_output_tokens,
            )
            span_id = new_span_id()
            await context.tracer.emit(
                context=context,
                event_type="model.started",
                status="running",
                span_id=span_id,
                parent_span_id=context.parent_span_id,
                payload={
                    "model_call_id": model_call_id,
                    "profile": profile.name,
                    "prompt_version": rendered.version,
                    "prompt_hash": rendered.sha256,
                    "schema_hash": stable_hash(request.output_schema),
                },
            )
            provider_request = ProviderRequest(
                model_call_id=model_call_id,
                model=profile.model,
                rendered_prompt=rendered.content,
                output_schema=request.output_schema,
                temperature=profile.temperature,
                strict_schema=False,
                max_output_tokens=max_output_tokens,
            )
            chunks: list[str] = []
            async with asyncio.timeout(profile.timeout_seconds):
                async for chunk in provider.stream(provider_request):
                    context.cancellation.raise_if_cancelled()
                    chunks.append(chunk)
                    yield ModelEvent(event="delta", model_call_id=model_call_id, text=chunk)
            estimated_output = max(0, len("".join(chunks)) // 4)
            context.budget.settle_model(
                reservation,
                actual_input_tokens=built.estimated_tokens,
                actual_output_tokens=estimated_output,
            )
            usage = ModelUsage(input_tokens=built.estimated_tokens, output_tokens=estimated_output)
            result = ModelResult(
                status="success",
                parsed={"text": "".join(chunks)},
                model=profile.model,
                provider=profile.provider,
                attempt_count=1,
                model_call_id=model_call_id,
                prompt_hash=rendered.sha256,
                usage=usage,
            )
            await context.tracer.emit(
                context=context,
                event_type="model.completed",
                status="success",
                span_id=span_id,
                parent_span_id=context.parent_span_id,
                payload={
                    "model_call_id": model_call_id,
                    "model": profile.model,
                    "provider": profile.provider,
                    "streaming": True,
                },
            )
            yield ModelEvent(event="completed", model_call_id=model_call_id, result=result)
        except (asyncio.CancelledError, RuntimeCancelledError):
            error = public_error(
                code="model_cancelled", category="cancelled", message="Model stream was cancelled", source="model_gateway"
            )
            result = await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=model_name,
                provider=provider_name,
                attempts=1,
                usage=usage,
                error=error,
                status="cancelled",
            )
            yield ModelEvent(event="failed", model_call_id=model_call_id, result=result)
        except BudgetExceededError as exc:
            error = public_error(
                code="runtime_budget_exhausted",
                category="budget",
                message="Model stream blocked by run budget",
                source="budget_ledger",
                details={"dimension": exc.dimension, "current": exc.current, "limit": exc.limit},
            )
            result = await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=model_name,
                provider=provider_name,
                attempts=0,
                usage=usage,
                error=error,
            )
            yield ModelEvent(event="failed", model_call_id=model_call_id, result=result)
        except (ProviderError, CapabilityError, PromptRegistryError, TimeoutError, ValueError) as exc:
            if isinstance(exc, ProviderError):
                error = _provider_agent_error(exc)
            elif isinstance(exc, TimeoutError):
                error = public_error(
                    code="provider_timeout",
                    category="timeout",
                    message="Model stream timed out",
                    source="model_gateway",
                    retryable=True,
                )
            else:
                error = public_error(
                    code="runtime_configuration_invalid",
                    category="validation",
                    message=str(exc),
                    source="model_gateway",
                )
            result = await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=model_name,
                provider=provider_name,
                attempts=1,
                usage=usage,
                error=error,
            )
            yield ModelEvent(event="failed", model_call_id=model_call_id, result=result)
        except Exception:
            error = public_error(
                code="model_runtime_internal_error",
                category="internal",
                message="Model stream failed inside the runtime",
                source="model_gateway",
            )
            result = await self._failed_result(
                context=context,
                model_call_id=model_call_id,
                model=model_name,
                provider=provider_name,
                attempts=1,
                usage=usage,
                error=error,
            )
            yield ModelEvent(event="failed", model_call_id=model_call_id, result=result)

    async def _invoke(
        self,
        *,
        provider: ProviderAdapter,
        profile: Any,
        rendered_prompt: str,
        output_schema: dict[str, Any],
        model_call_id: str,
        context: RunContext,
        estimated_input_tokens: int,
        max_output_tokens: int,
        tool_specs: list[str],
        prompt_version: str,
        prompt_hash: str,
    ) -> tuple[ProviderResponse, int, ModelUsage]:
        attempts = 0
        total_usage = ModelUsage()
        max_attempts = profile.max_retries + 1
        last_error: ProviderError | None = None
        while attempts < max_attempts:
            attempts += 1
            context.cancellation.raise_if_cancelled()
            reservation = context.budget.reserve_model(
                input_tokens=estimated_input_tokens,
                output_tokens=max_output_tokens,
            )
            span_id = new_span_id()
            await context.tracer.emit(
                context=context,
                event_type="model.started",
                status="running",
                span_id=span_id,
                parent_span_id=context.parent_span_id,
                attempt=attempts,
                payload={
                    "profile": profile.name,
                    "prompt_version": prompt_version,
                    "prompt_hash": prompt_hash,
                    "schema_hash": stable_hash(output_schema),
                    "tool_names": tool_specs,
                    "model_call_id": model_call_id,
                },
            )
            provider_request = ProviderRequest(
                model_call_id=model_call_id,
                model=profile.model,
                rendered_prompt=rendered_prompt,
                output_schema=output_schema,
                temperature=profile.temperature,
                tool_specs=[{"name": name} for name in tool_specs],
                strict_schema=profile.capabilities.supports_strict_schema,
                max_output_tokens=max_output_tokens,
            )
            try:
                response = await asyncio.wait_for(
                    provider.complete(provider_request),
                    timeout=profile.timeout_seconds,
                )
                context.budget.settle_model(
                    reservation,
                    actual_input_tokens=response.usage.input_tokens,
                    actual_output_tokens=response.usage.output_tokens,
                    actual_cost_usd=response.usage.cost_usd,
                )
                total_usage = _add_usage(total_usage, response.usage)
                return response, attempts, total_usage
            except TimeoutError:
                last_error = ProviderError("provider_timeout", category="timeout", retryable=True)
            except ProviderError as exc:
                last_error = exc
            await context.tracer.emit(
                context=context,
                event_type="model.failed",
                status="retrying" if last_error.retryable and attempts < max_attempts else "error",
                span_id=span_id,
                parent_span_id=context.parent_span_id,
                attempt=attempts,
                payload={
                    "model_call_id": model_call_id,
                    "error_code": last_error.code,
                    "retryable": last_error.retryable,
                },
            )
            if not last_error.retryable or not provider.retry_safe or attempts >= max_attempts:
                raise last_error
            await asyncio.sleep(min(0.25 * (2 ** (attempts - 1)), 1.0))
        raise last_error or ProviderError("provider_request_failed")

    async def _repair(
        self,
        *,
        original: str,
        validation_error: StructuredOutputError,
        provider: ProviderAdapter,
        profile: Any,
        output_schema: dict[str, Any],
        model_call_id: str,
        context: RunContext,
        max_output_tokens: int,
        prompt_version: str,
    ) -> tuple[ProviderResponse | None, int, ModelUsage, dict[str, Any] | None]:
        instruction = repair_instruction(validation_error, output_schema)
        repaired_prompt = instruction + "\n<invalid_output>\n" + str(context.redaction_policy.redact(original)) + "\n</invalid_output>"
        try:
            response, attempts, usage = await self._invoke(
                provider=provider,
                profile=profile,
                rendered_prompt=repaired_prompt,
                output_schema=output_schema,
                model_call_id=model_call_id,
                context=context,
                estimated_input_tokens=max(1, len(repaired_prompt) // 4),
                max_output_tokens=max_output_tokens,
                tool_specs=[],
                prompt_version=f"{prompt_version}+repair-v1",
                prompt_hash=stable_hash({"policy": "structured-output-repair-v1"}),
            )
            try:
                parsed = parse_and_validate(response.content, output_schema).value
            except StructuredOutputError:
                return None, attempts, usage, None
            return response, attempts, usage, parsed
        except (ProviderError, BudgetExceededError):
            return None, 0, ModelUsage(), None

    async def _try_fallback(
        self,
        *,
        request: ModelRequest,
        context: RunContext,
        rendered: RenderedPrompt,
        model_call_id: str,
        estimated_input_tokens: int,
    ) -> ModelResult | None:
        if not request.fallback_profile or request.fallback_profile == request.profile:
            return None
        try:
            profile = self.profiles.get(request.fallback_profile)
            provider = self._provider(profile.provider)
            response, attempts, usage = await self._invoke(
                provider=provider,
                profile=profile,
                rendered_prompt=rendered.content,
                output_schema=request.output_schema,
                model_call_id=model_call_id,
                context=context,
                estimated_input_tokens=estimated_input_tokens,
                max_output_tokens=_max_output_tokens(request),
                tool_specs=request.tool_specs,
                prompt_version=rendered.version,
                prompt_hash=rendered.sha256,
            )
            parsed = parse_and_validate(response.content, request.output_schema).value
            return await self._completed_result(
                context=context,
                model_call_id=model_call_id,
                profile=profile,
                response=response,
                parsed=parsed,
                usage=usage,
                attempts=attempts,
                rendered=rendered,
                fallback_used=True,
                degradation_reasons=[f"fallback_from:{request.profile}"],
            )
        except (ProviderError, StructuredOutputError, BudgetExceededError, CapabilityError):
            return None

    async def _completed_result(
        self,
        *,
        context: RunContext,
        model_call_id: str,
        profile: Any,
        response: ProviderResponse,
        parsed: dict[str, Any],
        usage: ModelUsage,
        attempts: int,
        rendered: RenderedPrompt,
        repaired: bool = False,
        fallback_used: bool = False,
        degradation_reasons: list[str] | None = None,
    ) -> ModelResult:
        reasons = list(degradation_reasons or [])
        reasons.extend(reason for reason in context.audit_warnings if reason not in reasons)
        status = "degraded" if fallback_used or reasons else "success"
        await context.tracer.emit(
            context=context,
            event_type="model.completed",
            status=status,
            span_id=new_span_id(),
            parent_span_id=context.parent_span_id,
            payload={
                "model": profile.model,
                "provider": profile.provider,
                "schema_valid": True,
                "response_hash": stable_hash(parsed),
                "repaired": repaired,
                "fallback_used": fallback_used,
                "prompt_hash": rendered.sha256,
                "model_call_id": model_call_id,
            },
        )
        await self._emit_usage(context)
        return ModelResult(
            status=status,
            parsed=parsed,
            response_id=response.response_id,
            model=profile.model,
            provider=profile.provider,
            usage=usage,
            attempt_count=attempts,
            model_call_id=model_call_id,
            prompt_hash=rendered.sha256,
            repaired=repaired,
            fallback_used=fallback_used,
            degradation_reasons=reasons,
        )

    async def _failed_result(
        self,
        *,
        context: RunContext,
        model_call_id: str,
        model: str,
        provider: str,
        attempts: int,
        usage: ModelUsage,
        error: Any,
        status: str = "error",
        prompt_hash: str | None = None,
    ) -> ModelResult:
        await context.tracer.emit(
            context=context,
            event_type="model.failed",
            status=status,
            span_id=new_span_id(),
            parent_span_id=context.parent_span_id,
            payload={
                "model_call_id": model_call_id,
                "error_code": error.code,
                "category": error.category,
                "retryable": error.retryable,
            },
        )
        await self._emit_usage(context)
        return ModelResult(
            status=status,
            parsed=None,
            model=model,
            provider=provider,
            usage=usage,
            attempt_count=attempts,
            model_call_id=model_call_id,
            error=error,
            prompt_hash=prompt_hash,
        )

    async def _emit_usage(self, context: RunContext) -> None:
        await context.tracer.emit(
            context=context,
            event_type="usage.updated",
            status="success",
            span_id=new_span_id(),
            parent_span_id=context.parent_span_id,
            payload={"current": context.budget.snapshot().model_dump(mode="json"), "limits": context.budget.limits()},
        )

    def _provider(self, name: str) -> ProviderAdapter:
        try:
            return self.providers[name]
        except KeyError as exc:
            raise CapabilityError(f"Provider adapter is not configured: {name}") from exc


def _max_output_tokens(request: ModelRequest) -> int:
    value = request.metadata.get("max_output_tokens", 2048)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("metadata.max_output_tokens must be a positive integer")
    return value


def _add_usage(left: ModelUsage, right: ModelUsage) -> ModelUsage:
    return ModelUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
        cost_usd=Decimal(left.cost_usd) + Decimal(right.cost_usd),
    )


def _provider_agent_error(error: ProviderError):
    return public_error(
        code=error.code,
        category=error.category,
        message="Model provider request failed",
        source="provider_adapter",
        retryable=error.retryable,
        details={"status_code": error.status_code} if error.status_code else {},
    )
