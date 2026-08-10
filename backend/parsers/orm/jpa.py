"""JPA/Hibernate annotation adapter with source locators."""

from __future__ import annotations

import re

from backend.parsers.orm.base import ORMAsset, ORMExtractionResult, ORMRelationFact


class JPAAdapter:
    framework = "jpa"
    version = "1.0.0"

    def detect(self, asset: ORMAsset) -> float:
        content = asset.content
        return 0.95 if "@Entity" in content or "@ManyToOne" in content or "@OneToMany" in content else 0.0

    def extract(self, asset: ORMAsset) -> ORMExtractionResult:
        entity_match = re.search(r"\bclass\s+(\w+)", asset.content)
        entity = entity_match.group(1) if entity_match else "UnknownEntity"
        table_match = re.search(r"@Table\s*\(\s*name\s*=\s*\"([^\"]+)\"", asset.content)
        table = table_match.group(1) if table_match else _snake(entity)
        relation_pattern = re.compile(
            r"@(?P<kind>ManyToOne|OneToMany|OneToOne|ManyToMany)(?P<args>\([^)]*\))?"
            r"(?P<middle>(?:\s*@\w+(?:\([^)]*\))?)*)\s*(?:private|protected|public)\s+"
            r"(?:List<|Set<|Collection<)?(?P<target>\w+)>?\s+(?P<field>\w+)",
            re.MULTILINE,
        )
        relations: list[ORMRelationFact] = []
        cardinalities = {"ManyToOne": "N:1", "OneToMany": "1:N", "OneToOne": "1:1", "ManyToMany": "N:N"}
        for match in relation_pattern.finditer(asset.content):
            annotations = f"{match.group('args') or ''}{match.group('middle') or ''}"
            join = re.search(r"@JoinColumn\s*\(\s*name\s*=\s*\"([^\"]+)\"", annotations)
            mapped = re.search(r"mappedBy\s*=\s*\"([^\"]+)\"", annotations)
            join_table = re.search(r"@JoinTable\s*\(\s*name\s*=\s*\"([^\"]+)\"", annotations)
            relations.append(
                ORMRelationFact(
                    framework=self.framework,
                    source_entity=entity,
                    source_table=table,
                    source_columns=[join.group(1)] if join else [],
                    target_entity=match.group("target"),
                    target_table=_snake(match.group("target")),
                    target_columns=["id"] if join else [],
                    cardinality=cardinalities[match.group("kind")],
                    mapped_by=mapped.group(1) if mapped else None,
                    join_table=join_table.group(1) if join_table else None,
                    explicit_mapping=bool(join or mapped or join_table),
                    source_locator={
                        "source_uri": asset.source_uri,
                        "line": asset.content.count("\n", 0, match.start()) + 1,
                        "field": match.group("field"),
                    },
                    reliability=0.95 if join else 0.72,
                )
            )
        return ORMExtractionResult(
            framework=self.framework,
            adapter_version=self.version,
            supported=True,
            relations=relations,
            entities=[{"entity": entity, "table": table}],
        )


def _snake(value: str) -> str:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).casefold()
    return normalized if normalized.endswith("s") else f"{normalized}s"
