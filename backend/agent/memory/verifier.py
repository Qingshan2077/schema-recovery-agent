"""Current-snapshot verification of retrieved memory hypotheses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.agent.memory.contracts import (
    MemoryContextPackage,
    MemoryVerification,
    RelationMemoryVersion,
)
from backend.agent.memory.l2_store import L2MemoryStore
from backend.core.identity import stable_id


class MemoryVerifier:
    def __init__(self, l2: L2MemoryStore):
        self.l2 = l2

    def verify(
        self,
        package: MemoryContextPackage,
        *,
        catalog: list[dict[str, Any]],
        current_evidence: list[dict[str, Any]],
        now: datetime,
    ) -> list[MemoryVerification]:
        table_index = _catalog_index(catalog)
        current_roots = {
            str(item.get("root_fact_id") or item.get("correlation_group") or item.get("correlation_key") or "")
            for item in current_evidence
            if str(item.get("source_type") or "") != "memory"
        }
        results: list[MemoryVerification] = []
        for context_item in package.items:
            reason_codes: list[str] = []
            evidence_ids: list[str] = []
            if context_item.layer == "l3":
                outcome = "insufficient"
                reason_codes = ["global_pattern_requires_candidate_binding"]
            else:
                relation = self.l2.get(context_item.memory_id, version=context_item.version)
                outcome, reason_codes = _verify_relation(
                    relation,
                    table_index=table_index,
                    current_snapshot_id=package.namespace.snapshot_id or "",
                    current_roots=current_roots,
                )
                evidence_ids = relation.evidence_ids
            results.append(MemoryVerification(
                verification_id=stable_id(
                    "verification", package.query.current_run_id, context_item.memory_id,
                    context_item.version, package.namespace.snapshot_id,
                ),
                run_id=package.query.current_run_id,
                memory_id=context_item.memory_id,
                memory_version=context_item.version,
                snapshot_id=package.namespace.snapshot_id or "",
                outcome=outcome,
                reason_codes=reason_codes,
                evidence_ids=evidence_ids,
                verified_at=now,
            ))
        return results


def _verify_relation(
    relation: RelationMemoryVersion,
    *,
    table_index: dict[str, dict[str, Any]],
    current_snapshot_id: str,
    current_roots: set[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    source = table_index.get(relation.source_table_id.casefold())
    target = table_index.get(relation.target_table_id.casefold())
    if source is None or target is None:
        return "stale", ["source_table_missing" if source is None else "target_table_missing"]
    source_columns = source["columns"]
    target_columns = target["columns"]
    missing_source = [name for name in relation.source_columns if name.casefold() not in source_columns]
    missing_target = [name for name in relation.target_columns if name.casefold() not in target_columns]
    if missing_source or missing_target:
        return "stale", [
            *(f"source_column_missing:{name}" for name in missing_source),
            *(f"target_column_missing:{name}" for name in missing_target),
        ]
    for source_name, target_name in zip(relation.source_columns, relation.target_columns):
        source_type = source_columns[source_name.casefold()].get("type")
        target_type = target_columns[target_name.casefold()].get("type")
        if source_type and target_type and not _compatible_type(str(source_type), str(target_type)):
            reasons.append(f"type_mismatch:{source_name}:{target_name}")
    if reasons:
        return "rejected", reasons
    target_unique = target.get("unique_columns", set())
    if not all(name.casefold() in target_unique for name in relation.target_columns):
        reasons.append("target_not_candidate_key")
    if relation.last_verified_snapshot_id != current_snapshot_id:
        reasons.append("snapshot_changed")
    if not set(relation.root_fact_ids).intersection(current_roots):
        reasons.append("current_non_memory_evidence_missing")
    if "snapshot_changed" in reasons or "current_non_memory_evidence_missing" in reasons:
        return "insufficient", reasons
    if "target_not_candidate_key" in reasons and relation.cardinality not in {"N:N", "unknown"}:
        return "rejected", reasons
    return "verified", reasons or ["current_snapshot_verified"]


def _catalog_index(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for table in catalog:
        table_name = str(table.get("table_id") or table.get("table_name") or table.get("name") or "")
        if not table_name:
            continue
        columns: dict[str, dict[str, Any]] = {}
        unique_columns: set[str] = set()
        for column in table.get("columns") or []:
            name = str(column.get("column_id") or column.get("column_name") or column.get("name") or "")
            if not name:
                continue
            columns[name.casefold()] = {
                "type": column.get("data_type") or column.get("type"),
                "nullable": column.get("nullable") or column.get("is_nullable"),
            }
            if column.get("primary_key") or column.get("is_primary") or column.get("unique"):
                unique_columns.add(name.casefold())
        for index_item in table.get("indexes") or []:
            if index_item.get("unique") or index_item.get("is_unique"):
                unique_columns.update(str(item).casefold() for item in index_item.get("columns") or [])
        index[table_name.casefold()] = {
            "columns": columns,
            "unique_columns": unique_columns,
        }
    return index


def _compatible_type(left: str, right: str) -> bool:
    def family(value: str) -> str:
        normalized = value.casefold()
        if any(token in normalized for token in ("int", "serial", "number", "decimal", "numeric")):
            return "number"
        if any(token in normalized for token in ("char", "text", "uuid", "enum")):
            return "text"
        if any(token in normalized for token in ("date", "time")):
            return "time"
        if "bool" in normalized or "bit" in normalized:
            return "boolean"
        return normalized.split("(", 1)[0]

    return family(left) == family(right)
