"""Provider-neutral request/response boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import Field

from backend.agent.runtime.contracts import ModelUsage, StrictContract


class ProviderRequest(StrictContract):
    model_call_id: str
    model: str
    rendered_prompt: str
    output_schema: dict[str, Any]
    temperature: float | None = None
    tool_specs: list[dict[str, Any]] = Field(default_factory=list)
    strict_schema: bool = False
    max_output_tokens: int | None = Field(default=None, gt=0)


class ProviderResponse(StrictContract):
    content: str
    response_id: str | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)
    finish_reason: str | None = None


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        category: str = "provider",
        retryable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.status_code = status_code


class ProviderAdapter(Protocol):
    name: str
    retry_safe: bool

    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]: ...
