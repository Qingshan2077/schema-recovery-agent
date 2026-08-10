"""Attach stable lineage identifiers to legacy merge output."""

from __future__ import annotations

from typing import Any

from backend.core.identity import stable_id


def attach_merge_lineage(
    merge_result: dict[str, Any],
    *,
    run_id: str,
    trace_id: str,
    database_fingerprint: str | None,
    snapshot_id: str | None,
) -> dict[str, Any]:
    database_namespace = database_fingerprint or "unknown_database"
    snapshot_namespace = snapshot_id or f"unknown_snapshot:{run_id}"
    merge_result["artifact_id"] = merge_result.get("artifact_id") or stable_id(
        "artifact", run_id, snapshot_namespace, "merge_result"
    )
    merge_result["run_id"] = run_id
    merge_result["trace_id"] = trace_id
    merge_result["database_fingerprint"] = database_fingerprint
    merge_result["snapshot_id"] = snapshot_id

    for relation in _all_relations(merge_result):
        relation_id = relation.get("relation_id") or stable_id(
            "relation",
            database_namespace,
            snapshot_namespace,
            str(relation.get("source_table", "")).lower(),
            str(relation.get("target_table", "")).lower(),
            str(relation.get("fk_column", "")).lower(),
            str(relation.get("pk_column", "")).lower(),
        )
        relation["relation_id"] = relation_id
        relation["run_id"] = run_id
        relation["trace_id"] = trace_id
        relation["database_fingerprint"] = database_fingerprint
        relation["snapshot_id"] = snapshot_id
        evidence_ids: list[str] = []
        for index, evidence in enumerate(relation.get("evidence_chain") or []):
            evidence_id = evidence.get("evidence_id") or stable_id(
                "evidence",
                relation_id,
                index,
                evidence.get("type"),
                evidence.get("detail"),
                evidence.get("strength"),
            )
            evidence["evidence_id"] = evidence_id
            evidence["run_id"] = run_id
            evidence["trace_id"] = trace_id
            evidence["snapshot_id"] = snapshot_id
            evidence_ids.append(evidence_id)
        relation["evidence_ids"] = evidence_ids
    return merge_result


def _all_relations(merge_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *merge_result.get("high_confidence_relations", []),
        *merge_result.get("medium_confidence_relations", []),
        *merge_result.get("low_confidence_relations", []),
    ]
