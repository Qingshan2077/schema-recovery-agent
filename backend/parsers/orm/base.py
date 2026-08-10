"""ORM adapter contracts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from backend.agent.runtime.contracts import StrictContract


class ORMAsset(StrictContract):
    source_uri: str
    content: str
    language: str | None = None


class ORMRelationFact(StrictContract):
    framework: str
    source_entity: str
    source_table: str | None = None
    source_columns: list[str] = Field(default_factory=list)
    target_entity: str
    target_table: str | None = None
    target_columns: list[str] = Field(default_factory=list)
    cardinality: Literal["1:1", "1:N", "N:1", "N:N", "unknown"] = "unknown"
    mapped_by: str | None = None
    join_table: str | None = None
    explicit_mapping: bool = False
    source_locator: dict = Field(default_factory=dict)
    reliability: float = Field(ge=0, le=1)


class ORMExtractionResult(StrictContract):
    framework: str
    adapter_version: str
    supported: bool
    relations: list[ORMRelationFact] = Field(default_factory=list)
    entities: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)


class ORMAdapter(Protocol):
    framework: str
    version: str

    def detect(self, asset: ORMAsset) -> float: ...
    def extract(self, asset: ORMAsset) -> ORMExtractionResult: ...
