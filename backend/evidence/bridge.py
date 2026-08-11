"""Explicit compatibility conversion from Phase 3 ledger objects to Phase 5 contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.agent.memory.contracts import MemoryNamespace
from backend.agent.runtime.hybrid_contracts import EvidenceItem as LegacyEvidenceItem
from backend.agent.runtime.hybrid_contracts import RelationCandidate
from backend.core.identity import stable_id
from backend.evidence.contracts import EvidenceItem, RelationCandidateVersion


def upgrade_evidence(
    item: LegacyEvidenceItem,
    *,
    namespace: MemoryNamespace,
    run_id: str,
) -> EvidenceItem:
    locator = dict(item.source_locator)
    return EvidenceItem(
        evidence_id=item.evidence_id,
        namespace=namespace,
        snapshot_id=item.snapshot_id,
        claim_key=item.claim_key,
        relation_id=item.relation_id,
        source_type=item.source_type,
        producer=item.producer,
        producer_version=str(locator.get("producer_version") or item.schema_version),
        polarity=item.polarity,
        strength=item.strength,
        reliability=item.reliability,
        source_uri=item.source_uri,
        source_locator=locator,
        artifact_hash=str(locator.get("artifact_hash")) if locator.get("artifact_hash") else None,
        excerpt_hash=str(locator.get("excerpt_hash")) if locator.get("excerpt_hash") else None,
        summary=item.summary,
        root_fact_id=str(locator.get("root_fact_id") or item.correlation_key),
        correlation_group=item.correlation_key,
        tool_call_id=item.tool_call_id,
        trace_id=item.trace_id,
        span_id=str(locator.get("span_id") or stable_id("span", item.trace_id, item.evidence_id)),
        model_profile=str(locator.get("model_profile")) if locator.get("model_profile") else None,
        prompt_version=str(locator.get("prompt_version")) if locator.get("prompt_version") else None,
        memory_id=(
            str(locator.get("memory_id") or stable_id("memory", item.evidence_id))
            if item.source_type == "memory" else None
        ),
        created_by_run_id=run_id,
        created_at=datetime.now(timezone.utc),
    )


def relation_template(
    candidate: RelationCandidate,
    *,
    namespace: MemoryNamespace,
    run_id: str,
    feature_schema_hash: str,
) -> RelationCandidateVersion:
    return RelationCandidateVersion(
        relation_id=candidate.relation_id,
        version=1,
        namespace=namespace,
        claim_key=candidate.claim_key,
        source_table_id=candidate.source_table,
        source_column_ids=candidate.source_columns,
        target_table_id=candidate.target_table,
        target_column_ids=candidate.target_columns,
        cardinality=candidate.cardinality,
        status="proposed",
        evidence_ids=candidate.evidence_ids,
        alternative_relation_ids=candidate.alternatives,
        validation_flags=candidate.validation_flags,
        feature_schema_hash=feature_schema_hash,
        raw_score=0,
        raw_probability=0,
        calibrated_probability=0,
        confidence_band="low",
        fusion_version="pending",
        calibration_version="pending",
        threshold_policy_version="pending",
        created_by_run_id=run_id,
        created_at=datetime.now(timezone.utc),
    )


def namespace_from_context(context: dict[str, Any], unit_snapshot_id: str, run_id: str) -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id=str(context.get("tenant_id") or "default"),
        project_id=str(context.get("project_id") or "default"),
        connection_id=str(context.get("connection_id") or context.get("database_fingerprint") or "default"),
        database_name=str(context.get("database_name") or "default"),
        schema_name=str(context.get("schema_name") or "default"),
        snapshot_id=unit_snapshot_id,
        thread_id=context.get("thread_id"),
        run_id=run_id,
    )
