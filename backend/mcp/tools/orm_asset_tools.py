"""Agent-ready ORM adapter registry tools."""

from __future__ import annotations

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract
from backend.mcp.tool_registry import ToolRegistry
from backend.parsers.orm.base import ORMAsset, ORMExtractionResult
from backend.parsers.orm.registry import ORMAdapterRegistry


class ORMDetectionOutput(StrictContract):
    framework: str
    confidence: float = Field(ge=0, le=1)
    supported: bool


def detect_orm_asset(source_uri: str, content: str, language: str | None = None) -> dict:
    framework, confidence = ORMAdapterRegistry().detect(
        ORMAsset(source_uri=source_uri, content=content, language=language)
    )
    return {"framework": framework, "confidence": confidence, "supported": framework != "unsupported"}


def extract_orm_asset(source_uri: str, content: str, language: str | None = None) -> dict:
    return ORMAdapterRegistry().extract(
        ORMAsset(source_uri=source_uri, content=content, language=language)
    ).model_dump(mode="json")


def register_all(registry: ToolRegistry) -> None:
    schema = {
        "type": "object",
        "properties": {
            "source_uri": {"type": "string"},
            "content": {"type": "string"},
            "language": {"type": "string"},
        },
        "required": ["source_uri", "content"],
        "additionalProperties": False,
    }
    common = dict(side_effect="none", approval_policy="never", idempotent=True, ready_for_agent=True, sensitivity="internal")
    registry.register(
        "recovery.detect_orm_asset", detect_orm_asset, "Detect an ORM framework before parsing",
        schema, output_model=ORMDetectionOutput, capability="orm_asset:read", **common,
    )
    registry.register(
        "recovery.extract_orm_asset", extract_orm_asset, "Extract normalized ORM relation facts through the detected adapter",
        schema, output_model=ORMExtractionResult, capability="orm_asset:read", **common,
    )
