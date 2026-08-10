"""Snapshot-bound catalog validation used by every verifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.agent.runtime.hybrid_contracts import RelationCandidate


@dataclass(frozen=True)
class CatalogColumn:
    table: str
    name: str
    data_type: str
    nullable: bool
    primary_key: bool
    unique: bool


class RecoveryCatalogResolver:
    def __init__(self, *, snapshot_id: str, catalog: list[dict[str, Any]]):
        self.snapshot_id = snapshot_id
        self._tables: dict[str, dict[str, CatalogColumn]] = {}
        for table in catalog:
            table_name = str(table.get("name") or "").casefold()
            if not table_name:
                continue
            columns: dict[str, CatalogColumn] = {}
            for raw in table.get("columns", []):
                name = str(raw.get("column_name") or raw.get("name") or "").casefold()
                if not name:
                    continue
                columns[name] = CatalogColumn(
                    table=table_name,
                    name=name,
                    data_type=str(raw.get("data_type") or raw.get("type") or "unknown").casefold(),
                    nullable=bool(raw.get("is_nullable", raw.get("nullable", True))),
                    primary_key=bool(raw.get("is_primary_key", raw.get("key") == "PRI")),
                    unique=bool(
                        raw.get("is_unique")
                        or raw.get("unique")
                        or raw.get("is_primary_key")
                        or raw.get("key") in {"PRI", "UNI"}
                    ),
                )
            self._tables[table_name] = columns

    def has_table(self, table: str) -> bool:
        return table.casefold() in self._tables

    def has_column(self, table: str, column: str) -> bool:
        return column.casefold() in self._tables.get(table.casefold(), {})

    def column(self, table: str, column: str) -> CatalogColumn | None:
        return self._tables.get(table.casefold(), {}).get(column.casefold())

    def type_compatible(self, left: CatalogColumn, right: CatalogColumn) -> bool:
        return _type_family(left.data_type) == _type_family(right.data_type)

    def validate_candidate(self, candidate: RelationCandidate) -> list[str]:
        flags: list[str] = []
        if not self.has_table(candidate.source_table):
            flags.append("missing_source_table")
        if not self.has_table(candidate.target_table):
            flags.append("missing_target_table")
        for column in candidate.source_columns:
            if not self.has_column(candidate.source_table, column):
                flags.append(f"missing_source_column:{column}")
        for column in candidate.target_columns:
            if not self.has_column(candidate.target_table, column):
                flags.append(f"missing_target_column:{column}")
        for source, target in zip(candidate.source_columns, candidate.target_columns):
            left = self.column(candidate.source_table, source)
            right = self.column(candidate.target_table, target)
            if left and right and not self.type_compatible(left, right):
                flags.append(f"type_mismatch:{source}:{target}")
            if right and not right.unique:
                flags.append(f"target_not_unique:{target}")
        if candidate.source_table.casefold() == candidate.target_table.casefold():
            flags.append("self_reference")
        return flags


def _type_family(data_type: str) -> str:
    normalized = data_type.casefold()
    families = {
        "integer": ("int", "serial", "bit"),
        "decimal": ("decimal", "numeric", "float", "double", "real"),
        "text": ("char", "text", "enum", "set"),
        "binary": ("binary", "blob"),
        "temporal": ("date", "time", "year"),
        "json": ("json",),
        "uuid": ("uuid",),
    }
    for family, markers in families.items():
        if any(marker in normalized for marker in markers):
            return family
    return normalized.split("(", 1)[0]
