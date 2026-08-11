"""Phase 3 contract tests. These tests are deterministic and offline."""

from __future__ import annotations

import asyncio

import pytest

from backend.agent.collectors.recovery_collectors import ColumnCollector
from backend.agent.critics import EvidenceRequestPolicy
from backend.agent.domain.relation_keys import build_claim_key, build_relation_id
from backend.agent.runtime.hybrid_contracts import (
    BudgetSlice,
    EvidenceItem,
    EvidenceRequest,
    RelationCandidate,
    WorkUnit,
)
from backend.agent.runtime.prompt_registry import PromptRegistry
from backend.evidence.fusion import EvidenceFusionEngine
from backend.evidence.repository import EvidenceIntegrityError, SQLiteEvidenceRepository
from backend.parsers.orm.base import ORMAsset
from backend.parsers.orm.registry import ORMAdapterRegistry
from backend.parsers.sql.registry import SQLParserRegistry


def _unit(worker: str = "column", *, snapshot_id: str = "snp_test", evidence_round: int = 0) -> WorkUnit:
    return WorkUnit(
        work_unit_id=f"wunit_{worker}",
        run_id="run_test",
        trace_id="trc_test",
        snapshot_id=snapshot_id,
        database_fingerprint="database_test",
        worker=worker,
        subject_refs=[],
        evidence_round=evidence_round,
        idempotency_key="1" * 64,
        budget_slice=BudgetSlice(max_model_calls=2, max_tool_calls=8),
    )


def _candidate(snapshot_id: str = "snp_test") -> RelationCandidate:
    claim = build_claim_key(
        project_id="project",
        connection_id="connection",
        schema_name="schema",
        snapshot_id=snapshot_id,
        source_table="orders",
        source_columns=["customer_id"],
        target_table="customers",
        target_columns=["id"],
    )
    return RelationCandidate(
        relation_id=build_relation_id(claim),
        claim_key=claim,
        source_table="orders",
        source_columns=["customer_id"],
        target_table="customers",
        target_columns=["id"],
        cardinality="N:1",
    )


def _evidence(
    candidate: RelationCandidate,
    evidence_id: str,
    *,
    polarity: str = "support",
    correlation_key: str = "correlation-a",
    strength: float = 0.9,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        snapshot_id="snp_test",
        database_fingerprint="database_test",
        claim_key=candidate.claim_key,
        relation_id=candidate.relation_id,
        source_type="column_profile",
        producer="column",
        polarity=polarity,
        strength=strength,
        reliability=0.9,
        summary="aggregate-only profile",
        trace_id="trc_test",
        correlation_key=correlation_key,
    )


def test_claim_key_is_snapshot_bound():
    first = _candidate("snp_first")
    second = _candidate("snp_second")

    assert first.claim_key != second.claim_key
    assert first.relation_id != second.relation_id


def test_evidence_ledger_is_idempotent_and_rejects_hash_conflict(tmp_path):
    repository = SQLiteEvidenceRepository(tmp_path / "evidence.db")
    candidate = _candidate()
    evidence = _evidence(candidate, "evd_same")

    assert repository.append_evidence(evidence) is True
    assert repository.append_evidence(evidence) is False

    changed = evidence.model_copy(update={"summary": "different immutable payload"})
    with pytest.raises(EvidenceIntegrityError):
        repository.append_evidence(changed)


def test_relation_candidate_events_preserve_revisions(tmp_path):
    repository = SQLiteEvidenceRepository(tmp_path / "relations.db")
    candidate = _candidate()
    revised = candidate.model_copy(update={"evidence_ids": ["evd_revision"]})

    assert repository.append_relation(candidate, snapshot_id="snp_test", producer="column") is True
    assert repository.append_relation(revised, snapshot_id="snp_test", producer="column") is True
    assert len(repository.query_relations(snapshot_id="snp_test")) == 2


def test_fusion_deduplicates_correlated_evidence_and_includes_negative_evidence():
    candidate = _candidate()
    items = [
        _evidence(candidate, "evd_support_strong", correlation_key="same", strength=0.95),
        _evidence(candidate, "evd_support_duplicate", correlation_key="same", strength=0.50),
        _evidence(candidate, "evd_oppose", polarity="oppose", correlation_key="independent", strength=1.0),
    ]

    fused = EvidenceFusionEngine().fuse(candidate, items)
    contributions = {item.evidence_id: item for item in fused.breakdown.contributions}

    assert contributions["evd_support_strong"].included is True
    assert contributions["evd_support_duplicate"].included is False
    assert contributions["evd_support_duplicate"].exclusion_reason == "correlated_duplicate"
    assert contributions["evd_oppose"].log_odds_delta < 0


class _PairLocalProfileRuntime:
    tool_call_ids: list[str] = []

    async def call(self, tool_name: str, **arguments):
        assert tool_name == "recovery.profile_relationship"
        if arguments["target_table"] == "user":
            return {"overlap_ratio": 0.90, "orphan_ratio": 0.10, "privacy_mode": "aggregate_only"}
        return {"overlap_ratio": 0.10, "orphan_ratio": 0.90, "privacy_mode": "aggregate_only"}


def test_column_candidates_do_not_accumulate_evidence_across_targets():
    context = {
        "survey_result": {
            "schema_catalog": [
                {"name": "events", "columns": [{"column_name": "user_id", "data_type": "int", "is_primary_key": False}]},
                {"name": "user", "columns": [{"column_name": "id", "data_type": "int", "is_primary_key": True}]},
                {"name": "users", "columns": [{"column_name": "id", "data_type": "int", "is_primary_key": True}]},
            ]
        }
    }

    collected = asyncio.run(ColumnCollector().collect(_unit(), context, _PairLocalProfileRuntime()))
    facts = {item["target_table"]: item for item in collected.content["candidate_facts"]}

    assert facts["user"]["polarity"] == "support"
    assert facts["users"]["polarity"] == "oppose"
    assert facts["user"]["strength"] == 0.90
    assert facts["users"]["strength"] == 0.90
    assert facts["user"]["claim_key"] != facts["users"]["claim_key"]


def test_sql_parser_preserves_cte_and_trigger_locators():
    parser = SQLParserRegistry()
    cte = parser.parse(
        "WITH recent AS (SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id) SELECT * FROM recent",
        dialect="mysql",
        source_uri="database://view/recent",
        asset_kind="view",
    )
    trigger = parser.parse(
        "CREATE TRIGGER x AFTER UPDATE ON orders FOR EACH ROW UPDATE customers c JOIN orders o ON c.id = o.customer_id SET c.name = c.name",
        dialect="mysql",
        source_uri="database://trigger/x",
        asset_kind="trigger",
    )

    assert cte.facts
    assert any(item.locator.fragment_hash for item in cte.facts)
    assert any(item.fact_kind in {"trigger", "update_join"} for item in trigger.facts)
    assert all(item.locator.source_uri for item in trigger.facts)


def test_orm_registry_supports_mybatis_jpa_and_typed_unsupported():
    registry = ORMAdapterRegistry()
    mybatis = registry.extract(ORMAsset(
        source_uri="mapper.xml",
        content='<mapper namespace="OrderMapper"><resultMap id="x"><association property="customer" javaType="Customer" column="customer_id"/></resultMap></mapper>',
    ))
    jpa = registry.extract(ORMAsset(
        source_uri="Order.java",
        content='@Entity @Table(name="orders") class Order { @ManyToOne @JoinColumn(name="customer_id") private Customer customer; }',
        language="java",
    ))
    unsupported = registry.extract(ORMAsset(source_uri="model.go", content="type Order struct {}", language="go"))

    assert mybatis.framework == "mybatis" and mybatis.relations[0].explicit_mapping
    assert jpa.framework == "jpa" and jpa.relations[0].source_columns == ["customer_id"]
    assert unsupported.supported is False
    assert unsupported.missing_capabilities == ["orm_adapter"]


def test_critic_policy_enforces_round_tool_budget_and_privacy():
    parent = _unit("merge", evidence_round=0)
    base = dict(
        request_id="req_test",
        claim_key="claim_test",
        target_worker="column",
        requested_fact="aggregate overlap ratio",
        subject_refs=["orders.customer_id", "customers.id"],
        allowed_tools=["recovery.profile_relationship"],
        reason="resolve ambiguity",
        expected_information_gain=0.8,
        estimated_budget=BudgetSlice(max_model_calls=0, max_tool_calls=2),
        round=1,
        dedupe_key="2" * 64,
    )
    policy = EvidenceRequestPolicy()

    authorized = EvidenceRequest(**base)
    assert policy.authorize(authorized, parent) == (True, None)
    child = policy.to_work_unit(authorized, parent)
    assert child.worker == "column"
    assert child.snapshot_id == parent.snapshot_id
    assert child.evidence_round == 1
    raw = EvidenceRequest(**{**base, "requested_fact": "return raw row sample values"})
    assert policy.authorize(raw, parent)[1] == "privacy_policy_rejected"
    wrong_tool = EvidenceRequest(**{**base, "allowed_tools": ["db.execute_ddl"]})
    assert policy.authorize(wrong_tool, parent)[1] == "tool_not_allowlisted"
    assert policy.authorize(EvidenceRequest(**base), parent, executed_dedupe_keys={"2" * 64})[1] == "duplicate_request"


def test_all_phase3_worker_prompts_are_immutable_and_registered():
    registry = PromptRegistry()
    registry.validate_all()

    for worker in ("survey", "column", "name", "code", "orm", "merge"):
        legacy = registry.get(f"worker.{worker}.reasoning", "1.0.0")
        active = registry.get(f"worker.{worker}.reasoning")
        assert legacy.status == "deprecated"
        assert active.semantic_version == "1.1.0"
        assert "memory_context" in active.input_schema["required"]
        assert "used_memory_ids" in active.output_schema["required"]
        assert active.output_schema["additionalProperties"] is False
        assert "probability" not in active.output_schema["properties"]


def test_evidence_identity_is_run_scoped_when_payload_contains_trace_provenance():
    from backend.agent.domain.catalog_resolver import RecoveryCatalogResolver
    from backend.agent.runtime.hybrid_contracts import ReasoningProposal, RelationCandidate
    from backend.agent.verifiers.worker_verifier import WorkerVerifier

    fact = {
        "claim_key": "claim_1",
        "source_type": "name_semantics",
        "polarity": "support",
        "strength": 0.7,
        "reliability": 0.8,
        "summary": "orders.user_id names users",
        "source_locator": {"table": "orders", "column": "user_id"},
        "correlation_seed": "name:orders:user_id",
    }
    candidate = RelationCandidate(
        relation_id="rel_1",
        claim_key="claim_1",
        source_table="orders",
        source_columns=["user_id"],
        target_table="users",
        target_columns=["id"],
    )
    catalog = RecoveryCatalogResolver(
        snapshot_id="snp_1",
        catalog=[
            {"name": "orders", "columns": [{"column_name": "user_id", "data_type": "int"}]},
            {"name": "users", "columns": [{"column_name": "id", "data_type": "int", "is_primary_key": True}]},
        ],
    )

    def evidence_for(run_id: str, trace_id: str):
        unit = _unit("name").model_copy(update={"run_id": run_id, "trace_id": trace_id})
        proposal = ReasoningProposal(
            proposal_id=f"prop_{run_id}", worker="name", snapshot_id=unit.snapshot_id,
            candidates=[candidate], decision_summary="grounded", model_profile="test",
            prompt_version="1.1.0",
        )
        return WorkerVerifier("name").verify(
            unit=unit,
            proposal=proposal,
            collector_content={"candidate_facts": [fact]},
            catalog=catalog,
            artifact_id="art_shared",
        ).evidence_items[0]

    first = evidence_for("run_first", "trc_first")
    second = evidence_for("run_second", "trc_second")

    assert first.evidence_id != second.evidence_id
    assert first.trace_id != second.trace_id
