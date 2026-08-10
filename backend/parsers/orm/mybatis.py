"""MyBatis XML relation adapter."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from backend.parsers.orm.base import ORMAsset, ORMExtractionResult, ORMRelationFact


class MyBatisAdapter:
    framework = "mybatis"
    version = "1.0.0"

    def detect(self, asset: ORMAsset) -> float:
        content = asset.content.casefold()
        return 1.0 if "<mapper" in content else 0.0

    def extract(self, asset: ORMAsset) -> ORMExtractionResult:
        relations: list[ORMRelationFact] = []
        try:
            root = ET.fromstring(asset.content)
        except ET.ParseError:
            return ORMExtractionResult(
                framework=self.framework,
                adapter_version=self.version,
                supported=True,
                warnings=["invalid_xml"],
                missing_capabilities=["well_formed_xml"],
            )
        namespace = root.attrib.get("namespace", "unknown")
        source_entity = namespace.split(".")[-1].removesuffix("Mapper")
        source_table = _snake(source_entity)
        for tag, cardinality in (("association", "N:1"), ("collection", "1:N")):
            for element in root.iter(tag):
                target = element.attrib.get("javaType") or element.attrib.get("ofType") or "unknown"
                column = element.attrib.get("column", "")
                relations.append(
                    ORMRelationFact(
                        framework=self.framework,
                        source_entity=source_entity,
                        source_table=source_table,
                        source_columns=[column] if column else [],
                        target_entity=target.split(".")[-1],
                        target_table=_snake(target.split(".")[-1]),
                        target_columns=["id"] if column else [],
                        cardinality=cardinality,
                        explicit_mapping=True,
                        source_locator={"source_uri": asset.source_uri, "tag": tag, "property": element.attrib.get("property", "")},
                        reliability=0.9,
                    )
                )
        return ORMExtractionResult(
            framework=self.framework,
            adapter_version=self.version,
            supported=True,
            relations=relations,
            entities=[{"entity": source_entity, "table": source_table, "namespace": namespace}],
        )


def _snake(value: str) -> str:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).casefold()
    return normalized if normalized.endswith("s") else f"{normalized}s"
