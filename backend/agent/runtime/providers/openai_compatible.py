"""OpenAI-compatible provider adapter; SDK objects never cross this module."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from backend.agent.runtime.contracts import ModelUsage
from backend.agent.runtime.providers.base import ProviderError, ProviderRequest, ProviderResponse


class OpenAICompatibleProvider:
    name = "openai_compatible"
    retry_safe = True

    def __init__(self, *, api_key: str, base_url: str, request_headers: dict[str, str] | None = None):
        self._api_key = api_key
        self._base_url = base_url
        self._request_headers = dict(request_headers or {})

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        if not self._api_key:
            raise ProviderError("provider_credentials_missing", category="provider", retryable=False)
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                default_headers=self._request_headers or None,
            )
            response_format: dict[str, Any]
            if request.strict_schema:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agent_runtime_output",
                        "strict": True,
                        "schema": request.output_schema,
                    },
                }
            else:
                response_format = {"type": "json_object"}
            response = await client.chat.completions.create(
                model=request.model,
                messages=[{"role": "user", "content": request.rendered_prompt}],
                temperature=request.temperature,
                response_format=response_format,
                max_tokens=request.max_output_tokens,
            )
            choice = response.choices[0]
            usage = response.usage
            return ProviderResponse(
                content=choice.message.content or "",
                response_id=response.id,
                finish_reason=choice.finish_reason,
                usage=ModelUsage(
                    input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                    cost_usd=Decimal("0"),
                ),
            )
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            raise _classify_sdk_error(exc) from None

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        if not self._api_key:
            raise ProviderError("provider_credentials_missing", category="provider", retryable=False)
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                default_headers=self._request_headers or None,
            )
            stream = await client.chat.completions.create(
                model=request.model,
                messages=[{"role": "user", "content": request.rendered_prompt}],
                temperature=request.temperature,
                stream=True,
                max_tokens=request.max_output_tokens,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise _classify_sdk_error(exc) from None


def _classify_sdk_error(exc: Exception) -> ProviderError:
    status_code = getattr(exc, "status_code", None)
    class_name = exc.__class__.__name__.lower()
    if status_code == 429 or "ratelimit" in class_name:
        return ProviderError("provider_rate_limit", category="rate_limit", retryable=True, status_code=429)
    if status_code in {500, 502, 503, 504}:
        return ProviderError("provider_server_error", retryable=True, status_code=status_code)
    if status_code in {401, 403} or "authentication" in class_name or "permission" in class_name:
        return ProviderError("provider_authentication_failed", retryable=False, status_code=status_code)
    if "timeout" in class_name:
        return ProviderError("provider_timeout", category="timeout", retryable=True, status_code=status_code)
    if "connection" in class_name:
        return ProviderError("provider_connection_error", retryable=True, status_code=status_code)
    return ProviderError("provider_request_failed", retryable=False, status_code=status_code)
