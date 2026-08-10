"""Base worker class."""

from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any

from backend.core.identity import new_id
from backend.mcp.tool_registry import ToolRegistry


class BaseWorker(ABC):
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self._call_log: list[dict] = []

    @abstractmethod
    def run(self, context: dict) -> dict:
        pass

    def call_tool(self, name: str, **kwargs) -> Any:
        tool_call_id = new_id("tool_call")
        result = self.tool_registry.execute(name, **kwargs)
        self._call_log.append(
            {
                "tool_call_id": tool_call_id,
                "tool": name,
                "params": _redact(kwargs),
                "result_summary": _safe_summary(result),
            }
        )
        return result

    def get_call_log(self) -> list[dict]:
        return list(self._call_log)

    def reset_call_log(self) -> None:
        """Start a fresh call log for every worker execution attempt."""

        self._call_log.clear()

    @property
    def worker_id(self) -> str:
        return self.__class__.__name__.replace("Worker", "").lower()


_SENSITIVE_KEYS = {"password", "passwd", "token", "secret", "api_key", "authorization", "connection_string"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if str(key).lower() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def _safe_summary(result: Any) -> str:
    summary = str(_redact(result))[:200]
    return re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^,}\s]+",
        r"\1=***",
        summary,
    )
