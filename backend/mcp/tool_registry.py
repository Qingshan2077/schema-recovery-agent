"""Tool registry for MCP-style local tools."""

from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """In-process registry used by workers to execute named tools."""

    _tools: dict[str, dict] = {}

    @classmethod
    def clear(cls) -> None:
        cls._tools = {}

    @classmethod
    def register(
        cls,
        name: str,
        fn: Callable,
        description: str = "",
        input_schema: dict | None = None,
    ) -> None:
        cls._tools[name] = {
            "fn": fn,
            "description": description,
            "input_schema": input_schema or {},
        }

    @classmethod
    def execute(cls, name: str, **kwargs) -> Any:
        if name not in cls._tools:
            raise ValueError(f"Tool '{name}' not registered. Available: {list(cls._tools.keys())}")
        return cls._tools[name]["fn"](**kwargs)

    @classmethod
    def list_tools(cls) -> list[dict]:
        return [
            {
                "name": name,
                "description": meta["description"],
                "input_schema": meta["input_schema"],
            }
            for name, meta in sorted(cls._tools.items())
        ]

