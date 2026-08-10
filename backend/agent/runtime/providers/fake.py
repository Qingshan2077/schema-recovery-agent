"""Deterministic, offline provider with explicit fault injection."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from backend.agent.runtime.contracts import ModelUsage, StrictContract
from backend.agent.runtime.providers.base import ProviderError, ProviderRequest, ProviderResponse


class FakeScenario(StrictContract):
    kind: Literal["success", "bad_json", "schema_mismatch", "timeout", "rate_limit", "server_error", "cancelled"]
    output: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)
    response_id: str | None = "fake_response"


class FakeProvider:
    name = "fake"
    retry_safe = True

    def __init__(self, scenarios: Iterable[FakeScenario | dict[str, Any]] | None = None):
        configured = scenarios or [FakeScenario(kind="success", output={})]
        self._scenarios = deque(
            item if isinstance(item, FakeScenario) else FakeScenario.model_validate(item)
            for item in configured
        )
        self.calls: list[ProviderRequest] = []

    @classmethod
    def from_fixture(cls, path: str | Path) -> "FakeProvider":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Fake provider fixture must be a JSON array")
        return cls(raw)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        scenario = self._scenarios.popleft() if self._scenarios else FakeScenario(kind="success", output={})
        if scenario.kind == "timeout":
            raise ProviderError("provider_timeout", category="timeout", retryable=True)
        if scenario.kind == "rate_limit":
            raise ProviderError("provider_rate_limit", category="rate_limit", retryable=True, status_code=429)
        if scenario.kind == "server_error":
            raise ProviderError("provider_server_error", retryable=True, status_code=503)
        if scenario.kind == "cancelled":
            raise asyncio.CancelledError()
        if scenario.kind == "bad_json":
            content = scenario.content or "not-json"
        elif scenario.kind == "schema_mismatch":
            content = scenario.content or json.dumps({"unexpected": True})
        else:
            content = scenario.content or json.dumps(scenario.output, ensure_ascii=False)
        return ProviderResponse(
            content=content,
            response_id=scenario.response_id,
            usage=scenario.usage,
            finish_reason="stop",
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        for chunk in _chunks(response.content, 16):
            yield chunk


def _chunks(value: str, size: int) -> Iterable[str]:
    for offset in range(0, len(value), size):
        yield value[offset : offset + size]
