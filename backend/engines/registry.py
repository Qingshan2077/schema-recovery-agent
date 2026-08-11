"""Engine selection and immutable per-run assignment."""

from __future__ import annotations

from typing import Any


class EngineRegistry:
    def __init__(self, engines: dict[str, Any]):
        self.engines = dict(engines)

    def get(self, name: str):
        normalized = {"manual_v2": "manual", "langgraph_v2": "langgraph"}.get(name, name)
        if normalized not in self.engines:
            raise ValueError(f"recovery engine is unavailable: {name}")
        return self.engines[normalized]

    def capabilities(self) -> dict[str, Any]:
        return {
            name: engine.capability_check() if hasattr(engine, "capability_check") else {"available": True}
            for name, engine in self.engines.items()
        }
