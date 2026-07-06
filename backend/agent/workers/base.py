"""Base worker class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.mcp.tool_registry import ToolRegistry


class BaseWorker(ABC):
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self._call_log: list[dict] = []

    @abstractmethod
    def run(self, context: dict) -> dict:
        pass

    def call_tool(self, name: str, **kwargs) -> Any:
        result = self.tool_registry.execute(name, **kwargs)
        self._call_log.append({"tool": name, "params": kwargs, "result_summary": str(result)[:200]})
        return result

    def get_call_log(self) -> list[dict]:
        return self._call_log

    @property
    def worker_id(self) -> str:
        return self.__class__.__name__.replace("Worker", "").lower()

