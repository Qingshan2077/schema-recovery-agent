"""Deterministic catalog entity resolution; fuzzy matches never auto-select."""

from __future__ import annotations

from difflib import SequenceMatcher
import unicodedata

from backend.agent.qa.contracts import CatalogEntity, EntityMention, SchemaEntityRef

_FOCUS_PRONOUNS = {"它", "这个表", "该表", "上一个表", "it", "this table", "that table"}


class EntityResolver:
    def __init__(self, *, fuzzy_threshold: float = 0.68):
        self.fuzzy_threshold = fuzzy_threshold

    def resolve(
        self,
        mentions: list[EntityMention],
        inventory: list[CatalogEntity],
        *,
        focus: list[CatalogEntity] | None = None,
    ) -> list[SchemaEntityRef]:
        return [self._resolve_one(item, inventory, focus or []) for item in mentions]

    def _resolve_one(
        self,
        mention: EntityMention,
        inventory: list[CatalogEntity],
        focus: list[CatalogEntity],
    ) -> SchemaEntityRef:
        raw_mention = _normalize(mention.mention)
        if raw_mention.casefold() in _FOCUS_PRONOUNS and focus:
            return _resolved(mention, focus[0], "focus")
        needle = _catalog_token(mention.mention)

        exact = [entity for entity in inventory if _normalize(entity.name) == needle]
        if len(exact) == 1:
            return _resolved(mention, exact[0], "exact")
        if len(exact) > 1:
            return _ambiguous(mention, exact, "exact")

        folded = needle.casefold()
        casefold = [entity for entity in inventory if _normalize(entity.name).casefold() == folded]
        if len(casefold) == 1:
            return _resolved(mention, casefold[0], "casefold")
        if len(casefold) > 1:
            return _ambiguous(mention, casefold, "casefold")

        aliases = [
            entity
            for entity in inventory
            if any(_normalize(alias).casefold() == folded for alias in entity.aliases)
        ]
        if len(aliases) == 1:
            return _resolved(mention, aliases[0], "alias")
        if len(aliases) > 1:
            return _ambiguous(mention, aliases, "alias")

        ranked = sorted(
            (
                (SequenceMatcher(None, folded, _normalize(entity.name).casefold()).ratio(), entity)
                for entity in inventory
            ),
            key=lambda pair: (-pair[0], pair[1].name),
        )
        fuzzy = [entity for score, entity in ranked if score >= self.fuzzy_threshold][:5]
        if fuzzy:
            return SchemaEntityRef(
                mention=mention.mention,
                status="ambiguous" if len(fuzzy) > 1 else "not_found",
                kind=mention.kind,
                resolution_method="fuzzy",
                candidates=fuzzy,
            )
        return SchemaEntityRef(mention=mention.mention, status="not_found", kind=mention.kind)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().strip("`'\"")


def _catalog_token(value: str) -> str:
    normalized = _normalize(value)
    if normalized.endswith("表") and len(normalized) > 1:
        normalized = normalized[:-1].strip()
    if normalized.casefold().startswith("table "):
        normalized = normalized[6:].strip()
    return normalized


def _resolved(mention: EntityMention, entity: CatalogEntity, method: str) -> SchemaEntityRef:
    return SchemaEntityRef(
        mention=mention.mention,
        status="resolved",
        entity_id=entity.entity_id,
        database=entity.database,
        schema_name=entity.schema_name,
        canonical_name=entity.name,
        kind=mention.kind,
        resolution_method=method,
    )


def _ambiguous(mention: EntityMention, entities: list[CatalogEntity], method: str) -> SchemaEntityRef:
    return SchemaEntityRef(
        mention=mention.mention,
        status="ambiguous",
        kind=mention.kind,
        resolution_method=method,
        candidates=entities[:8],
    )


CatalogResolver = EntityResolver
