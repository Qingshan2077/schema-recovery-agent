"""Tool registry for MCP-style local tools."""

from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """In-process registry used by workers to execute named tools."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def clear(self) -> None:
        self._tools.clear()

    def register(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        input_schema: dict | None = None,
    ) -> None:
        self._tools[name] = {
            "fn": fn,
            "description": description,
            "input_schema": input_schema or {},
        }

    def execute(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not registered. Available: {list(self._tools.keys())}")
        return self._tools[name]["fn"](**kwargs)

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": meta["description"],
                "input_schema": meta["input_schema"],
            }
            for name, meta in sorted(self._tools.items())
        ]
