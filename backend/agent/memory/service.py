"""Application service for the Phase 5 retrieve/verify/consolidate lifecycle."""

from __future__ import annotations

from datetime import timedelta
import hashlib
from typing import Any

from backend.agent.memory.contracts import (
    GlobalMemoryItem,
    MemoryContextPackage,
    MemoryFeedback,
    MemoryNamespace,
    MemoryRetrievalQuery,
    MemoryVerification,
    PromotionProposal,
    RelationMemoryVersion,
    ThreadMemoryRecord,
)
from backend.agent.memory.l1_store import L1MemoryStore
from backend.agent.memory.l2_store import L2MemoryStore
from backend.agent.memory.l3_store import L3MemoryStore
from backend.agent.memory.policy import Clock, MemoryPolicy, SystemClock
from backend.agent.memory.retrieval import MemoryRetriever, VectorRetriever
from backend.agent.memory.storage import MemoryItemNotFound, SQLiteMemoryDatabase
from backend.agent.memory.store_utils import json_text, payload_hash
from backend.agent.memory.verifier import MemoryVerifier
from backend.core.identity import stable_id
from backend.evidence.contracts import RelationCandidateVersion


class MemoryService:
    def __init__(
        self,
        db_path: str,
        *,
        policy: MemoryPolicy | None = None,
        clock: Clock | None = None,
        vector: VectorRetriever | None = None,
        vector_enabled: bool = False,
    ):
        self.clock = clock or SystemClock()
        self.policy = policy or MemoryPolicy()
        self.database = SQLiteMemoryDatabase(db_path)
        self.l1 = L1MemoryStore(self.database, clock=self.clock)
        self.l2 = L2MemoryStore(self.database, policy=self.policy)
        self.l3 = L3MemoryStore(self.database, policy=self.policy, clock=self.clock)
        self.retriever = MemoryRetriever(
            self.l2, self.l3, policy=self.policy, vector=vector,
            vector_enabled=vector_enabled,
        )
        self.verifier = MemoryVerifier(self.l2)

    def sync_thread(
        self,
        namespace: MemoryNamespace,
        state: dict[str, Any],
        *,
        status: str,
        active_ttl_days: int = 7,
        completed_ttl_days: int = 30,
    ) -> ThreadMemoryRecord:
        namespace.require_l1()
        current = self.l1.get(namespace)
        now = self.clock.now()
        record = ThreadMemoryRecord(
            memory_id=stable_id(
                "memory", namespace.canonical_tenant_id,
                namespace.canonical_project_id, namespace.thread_id,
            ),
            namespace=namespace,
            version=1 if current is None else current.version + 1,
            status=status,
            checkpoint_ref=(state.get("output_refs") or {}).get("checkpoint"),
            summary_ref=(state.get("output_refs") or {}).get("merge_result"),
            summary_provenance={
                "run_id": state.get("run_id"),
                "snapshot_id": state.get("snapshot_id"),
                "workflow_version": state.get("workflow_version"),
            },
            message_event_ids=list(current.message_event_ids if current else []),
            artifact_ids=list(state.get("artifact_ids") or []),
            temporary_relation_ids=list(state.get("relation_ids") or []),
            pending_approval_ref=(state.get("pending_interrupt") or {}).get("interrupt_id"),
            budget=dict(state.get("budget") or {}),
            last_event_sequence=int(state.get("last_event_sequence") or 0),
            expires_at=now + timedelta(
                days=completed_ttl_days if status == "completed" else active_ttl_days,
            ),
            created_at=current.created_at if current else now,
            updated_at=now,
        )
        return self.l1.upsert(record, expected_version=current.version if current else 0)

    def retrieve(self, query: MemoryRetrievalQuery) -> MemoryContextPackage:
        package = self.retriever.retrieve(query, now=self.clock.now())
        payload = package.model_dump(mode="json")
        selected = {(item.memory_id, item.version) for item in package.items}
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_context_packages VALUES (?, ?, ?, ?, ?, ?)",
                (
                    package.package_id, query.current_run_id, query.namespace.snapshot_id,
                    json_text(payload), payload_hash(payload), package.created_at.isoformat(),
                ),
            )
            for item in package.items:
                retrieval_id = stable_id(
                    "retrieval", package.package_id, item.memory_id, item.version,
                    item.retrieval_method,
                )
                connection.execute(
                    "INSERT OR IGNORE INTO memory_retrievals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        retrieval_id, query.current_run_id, item.memory_id, item.version,
                        item.layer, item.retrieval_method, item.retrieval_score,
                        int((item.memory_id, item.version) in selected), None,
                        package.created_at.isoformat(),
                    ),
                )
        return package

    def get_context_package(self, package_id: str) -> MemoryContextPackage:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM memory_context_packages WHERE package_id=?", (package_id,),
            ).fetchone()
        if row is None:
            raise MemoryItemNotFound(package_id)
        return MemoryContextPackage.model_validate_json(row["payload_json"])

    def list_memory(
        self, namespace: MemoryNamespace, *, layer: str | None = None,
        status: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        keys = namespace.project_key()
        clauses = [
            "tenant_key=?", "project_key=?", "connection_key=?",
            "database_key=?", "schema_key=?",
        ]
        params: list[Any] = list(keys)
        if layer:
            clauses.append("layer=?")
            params.append(layer)
        if status:
            clauses.append("status=?")
            params.append(status)
        params.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT memory_id, layer, current_version, status, created_by_run_id, created_at
                    FROM memory_items WHERE {' AND '.join(clauses)}
                    ORDER BY created_at DESC, memory_id LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_thread(self, namespace: MemoryNamespace) -> ThreadMemoryRecord | None:
        return self.l1.get(namespace)

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT layer FROM memory_items WHERE memory_id=?", (memory_id,),
            ).fetchone()
        if row is None:
            raise MemoryItemNotFound(memory_id)
        item = self.l2.get(memory_id) if row["layer"] == "l2" else self.l3.get(memory_id)
        return item.model_dump(mode="json")

    def list_promotions(self, *, status: str | None = None, limit: int = 100) -> list[PromotionProposal]:
        clauses = ["1=1"]
        params: list[Any] = []
        if status:
            clauses.append("lifecycle=?")
            params.append(status)
        params.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT payload_json FROM memory_promotion_proposals
                    WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [PromotionProposal.model_validate_json(row["payload_json"]) for row in rows]

    def verify(
        self,
        package_id: str,
        *,
        catalog: list[dict[str, Any]],
        current_evidence: list[dict[str, Any]],
    ) -> list[MemoryVerification]:
        package = self.get_context_package(package_id)
        results = self.verifier.verify(
            package, catalog=catalog, current_evidence=current_evidence, now=self.clock.now(),
        )
        with self.database.transaction() as connection:
            for item in results:
                connection.execute(
                    """INSERT OR IGNORE INTO memory_verifications VALUES(
                       ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.verification_id, item.run_id, item.memory_id, item.memory_version,
                        item.snapshot_id, item.outcome, json_text(item.reason_codes),
                        json_text(item.evidence_ids), item.verified_at.isoformat(),
                    ),
                )
        return results

    def consolidate_relation(
        self,
        relation: RelationCandidateVersion,
        *,
        verification: MemoryVerification | None = None,
        root_fact_ids: list[str] | None = None,
    ) -> RelationMemoryVersion | None:
        if relation.status not in {"accepted", "corrected"}:
            return None
        if verification is not None and verification.outcome != "verified":
            return None
        memory_id = stable_id("memory", relation.namespace.project_key(), relation.claim_key)
        try:
            current = self.l2.get(memory_id)
            if (
                current.created_by_run_id == relation.created_by_run_id
                and current.relation_id == relation.relation_id
                and current.evidence_ids == relation.evidence_ids
            ):
                return current
            version = current.version + 1
            first_seen = current.first_seen_snapshot_id
        except MemoryItemNotFound:
            version = 1
            first_seen = relation.namespace.snapshot_id or ""
        item = RelationMemoryVersion(
            memory_id=memory_id,
            relation_id=relation.relation_id,
            version=version,
            namespace=relation.namespace,
            source_table_id=relation.source_table_id,
            source_columns=relation.source_column_ids,
            target_table_id=relation.target_table_id,
            target_columns=relation.target_column_ids,
            cardinality=relation.cardinality,
            status=relation.status,
            evidence_ids=relation.evidence_ids,
            calibrated_probability=relation.calibrated_probability,
            calibration_version=relation.calibration_version,
            first_seen_snapshot_id=first_seen,
            last_verified_snapshot_id=relation.namespace.snapshot_id or "",
            created_by_run_id=relation.created_by_run_id,
            root_fact_ids=sorted(set(root_fact_ids or [])),
            source_object_ids=[
                relation.source_table_id, *relation.source_column_ids,
                relation.target_table_id, *relation.target_column_ids,
            ],
            summary=(
                f"{relation.source_table_id}({', '.join(relation.source_column_ids)}) -> "
                f"{relation.target_table_id}({', '.join(relation.target_column_ids)})"
            ),
            created_at=self.clock.now(),
        )
        return self.l2.append(item)

    def submit_feedback(
        self,
        memory_id: str,
        *,
        version: int,
        feedback: MemoryFeedback,
    ) -> str:
        self.l2.get(memory_id, version=version)
        feedback_id = stable_id("feedback", memory_id, version, feedback.request_id)
        payload = feedback.model_dump(mode="json")
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    feedback_id, memory_id, version, feedback.action, feedback.actor_id,
                    feedback.actor_role, _reason_hash(feedback.reason), json_text(payload),
                    self.clock.now().isoformat(),
                ),
            )
        return feedback_id

    def forget(self, memory_id: str, *, actor_id: str, reason: str) -> str:
        item = self.l2.get(memory_id)
        prior = item.model_dump(mode="json")
        forget_id = stable_id("feedback", "forget", memory_id, item.version, actor_id, reason)
        audit_hash = payload_hash({
            "memory_id": memory_id, "version": item.version,
            "relation_id": item.relation_id, "namespace": item.namespace.project_key(),
        })
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_forget_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    forget_id, memory_id, actor_id, _reason_hash(reason), payload_hash(prior),
                    audit_hash, self.clock.now().isoformat(),
                ),
            )
            connection.execute(
                "UPDATE memory_items SET status='forgotten' WHERE memory_id=?", (memory_id,),
            )
        return forget_id

    def propose_global(
        self,
        item: GlobalMemoryItem,
        *,
        namespace: MemoryNamespace,
        support_project_ids: list[str],
        support_eval_ids: list[str],
    ) -> PromotionProposal:
        candidate = item.model_copy(update={"lifecycle": "candidate"})
        self.l3.append(candidate, namespace=namespace)
        proposal = PromotionProposal(
            proposal_id=stable_id("promotion", item.memory_id, item.version),
            memory_id=item.memory_id,
            source_version=item.version,
            proposed_by_run_id=item.created_by_run_id or "offline",
            support_project_ids=support_project_ids,
            support_eval_ids=support_eval_ids,
            expires_at=self.clock.now() + timedelta(days=30),
            created_at=self.clock.now(),
        )
        return self.l3.append_proposal(proposal)

    def resolve_global(
        self,
        proposal_id: str,
        *,
        actor_id: str,
        actor_role: str,
        approve: bool,
        reason: str,
    ) -> tuple[PromotionProposal, GlobalMemoryItem]:
        proposal = self.l3.resolve_proposal(
            proposal_id, actor_id=actor_id, actor_role=actor_role,
            approve=approve, reason=reason,
        )
        source = self.l3.get(proposal.memory_id, version=proposal.source_version)
        lifecycle = "active" if proposal.lifecycle == "active" else "deprecated"
        promoted = source.model_copy(update={
            "version": self.l3.get(source.memory_id).version + 1,
            "lifecycle": lifecycle,
            "effective_from": self.clock.now(),
        })
        return proposal, self.l3.append(promoted, namespace=self._l3_namespace(source.memory_id))

    def _l3_namespace(self, memory_id: str) -> MemoryNamespace:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT tenant_key, project_key, connection_key, database_key, schema_key
                   FROM memory_items WHERE memory_id=? AND layer='l3'""",
                (memory_id,),
            ).fetchone()
        if row is None:
            raise MemoryItemNotFound(memory_id)
        return MemoryNamespace(
            tenant_id=row["tenant_key"], project_id=row["project_key"],
            connection_id=row["connection_key"], database_name=row["database_key"],
            schema_name=row["schema_key"], snapshot_id="global",
        )


def _reason_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
