"""Shared retry and public-error classification policies."""

from __future__ import annotations

from backend.agent.runtime.contracts import AgentError
from backend.agent.runtime.redaction import redact_value


RETRYABLE_CATEGORIES = {"provider", "rate_limit", "timeout"}


def is_retryable(error: AgentError) -> bool:
    return error.retryable and error.category in RETRYABLE_CATEGORIES


def public_error(
    *,
    code: str,
    category: str,
    message: str,
    source: str,
    retryable: bool = False,
    details: dict | None = None,
    cause_span_id: str | None = None,
) -> AgentError:
    return AgentError(
        code=code,
        category=category,
        message=str(redact_value(message)),
        retryable=retryable,
        source=source,
        details=redact_value(details or {}),
        cause_span_id=cause_span_id,
    )
