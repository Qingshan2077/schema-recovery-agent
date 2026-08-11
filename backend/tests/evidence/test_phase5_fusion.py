from datetime import datetime, timezone

from backend.agent.memory.contracts import MemoryNamespace
from backend.evidence.contracts import EvidenceItem, RelationCandidateVersion, ThresholdPolicy
from backend.evidence.fusion import VersionedFusionEngine


def ns() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id="tenant", project_id="project", connection_id="connection",
        database_name="database", schema_name="public", snapshot_id="snp_current",
    )


def evidence(evidence_id: str, root: str, source: str = "memory") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id, namespace=ns(), snapshot_id="snp_current",
        claim_key="claim", relation_id="rel_relation", source_type=source,
        producer="test", producer_version="1", polarity="support", strength=.99,
        reliability=.99, summary="support", root_fact_id=root,
        correlation_group=root, trace_id="trc_test", span_id="spn_test",
        memory_id="mem_prior" if source == "memory" else None,
        created_by_run_id="run_current", created_at=datetime.now(timezone.utc),
    )


def template() -> RelationCandidateVersion:
    return RelationCandidateVersion(
        relation_id="rel_relation", version=1, namespace=ns(), claim_key="claim",
        source_table_id="orders", source_column_ids=["user_id"],
        target_table_id="users", target_column_ids=["id"], cardinality="N:1",
        status="proposed", feature_schema_hash="schema-v1", raw_score=0,
        raw_probability=0, calibrated_probability=0, confidence_band="low",
        fusion_version="pending", calibration_version="pending",
        threshold_policy_version="pending", created_by_run_id="run_current",
        created_at=datetime.now(timezone.utc),
    )


def test_memory_only_and_single_root_cannot_be_high_confidence():
    engine = VersionedFusionEngine(
        fusion_version="fusion-v1", feature_schema_hash="schema-v1",
        threshold_policy=ThresholdPolicy(version="threshold-v1", high=.5, medium=.2),
        prior_probability=.9,
    )
    result = engine.fuse(
        template(), [evidence("evd_a", "fact_a"), evidence("evd_b", "fact_a")],
        version=1, run_id="run_current", now=datetime.now(timezone.utc),
    )
    assert result.relation.confidence_band == "medium"
    assert result.excluded_evidence_ids == ["evd_b"]


def test_independent_current_fact_allows_high_confidence():
    engine = VersionedFusionEngine(
        fusion_version="fusion-v1", feature_schema_hash="schema-v1",
        threshold_policy=ThresholdPolicy(version="threshold-v1", high=.5, medium=.2),
        prior_probability=.9,
    )
    result = engine.fuse(
        template(), [evidence("evd_a", "fact_a", "catalog"), evidence("evd_b", "fact_b", "orm")],
        version=1, run_id="run_current", now=datetime.now(timezone.utc),
    )
    assert result.relation.confidence_band == "high"
    assert result.independent_root_fact_ids == ["fact_a", "fact_b"]
