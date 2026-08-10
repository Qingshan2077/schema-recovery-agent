"""Detect and dispatch ORM assets without forcing them through the wrong parser."""

from __future__ import annotations

from backend.parsers.orm.base import ORMAsset, ORMExtractionResult
from backend.parsers.orm.jpa import JPAAdapter
from backend.parsers.orm.mybatis import MyBatisAdapter


class ORMAdapterRegistry:
    def __init__(self):
        self._adapters = [MyBatisAdapter(), JPAAdapter()]

    def detect(self, asset: ORMAsset) -> tuple[str, float]:
        ranked = sorted(
            ((adapter.detect(asset), adapter) for adapter in self._adapters),
            key=lambda item: (-item[0], item[1].framework),
        )
        score, adapter = ranked[0]
        return (adapter.framework, score) if score > 0 else ("unsupported", 0.0)

    def extract(self, asset: ORMAsset) -> ORMExtractionResult:
        framework, score = self.detect(asset)
        if score == 0:
            return ORMExtractionResult(
                framework="unsupported",
                adapter_version="1.0.0",
                supported=False,
                warnings=["unsupported_orm_asset"],
                missing_capabilities=["orm_adapter"],
            )
        adapter = next(item for item in self._adapters if item.framework == framework)
        return adapter.extract(asset)
