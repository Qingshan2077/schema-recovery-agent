"""Versioned L3 global knowledge lifecycle and promotion proposal store."""

from __future__ import annotations

from datetime import datetime
import json

from backend.agent.memory.contracts import GlobalMemoryItem, MemoryNamespace, PromotionProposal
from backend.agent.memory.policy import Clock, MemoryPolicy, MemoryPolicyError, SystemClock
from backend.agent.memory.storage import MemoryItemNotFound, MemoryStoreConflict, SQLiteMemoryDatabase
from backend.agent.memory.store_utils import json_text, lexical_tokens, namespace_columns, payload_hash


class L3MemoryStore:
    def __init__(
        self,
        database: SQLiteMemoryDatabase,
        *,
        policy: MemoryPolicy | None = None,
        clock: Clock | None = None,
    ):
        self.database = database
        self.policy = policy or MemoryPolicy()
        self.clock = clock or SystemClock()

    def append(self, item: GlobalMemoryItem, *, namespace: MemoryNamespace) -> GlobalMemoryItem:
        keys = namespace_columns(namespace, layer="l3")
        payload = item.model_dump(mode="json")
        digest = payload_hash(payload)
        keywords = lexical_tokens(item.category, item.rule_summary, *item.scope, *item.dialects, *item.domains)
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM memory_item_versions WHERE memory_id=? AND version=?",
                (item.memory_id, item.version),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise MemoryStoreConflict("global memory version is immutable")
                return item
            current = connection.execute(
                "SELECT current_version FROM memory_items WHERE memory_id=?",
                (item.memory_id,),
            ).fetchone()
            expected = 1 if current is None else int(current["current_version"]) + 1
            if item.version != expected:
                raise MemoryStoreConflict(f"global memory version must be {expected}")
            if current is None:
                connection.execute(
                    "INSERT INTO memory_items VALUES (?, 'l3', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.memory_id, *keys, item.version, item.lifecycle,
                        item.created_by_run_id, item.effective_from.isoformat(),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE memory_items SET current_version=?, status=? WHERE memory_id=?",
                    (item.version, item.lifecycle, item.memory_id),
                )
            connection.execute(
                """INSERT INTO memory_item_versions VALUES(
                   ?, ?, 'l3', ?, ?, ?, ?, ?, NULL, ?, ?, ?, '[]', '[]', '[]', ?, ?, ?, ?, ?)""",
                (
                    item.memory_id, item.version, *keys, item.lifecycle,
                    item.rule_summary, json_text(sorted(keywords)), json_text(payload), digest,
                    item.created_by_run_id, item.effective_from.isoformat(), item.superseded_by,
                ),
            )
        return item

    def get(self, memory_id: str, *, version: int | None = None) -> GlobalMemoryItem:
        with self.database.connect() as connection:
            if version is None:
                row = connection.execute(
                    """SELECT v.payload_json FROM memory_item_versions v
                       JOIN memory_items i ON i.memory_id=v.memory_id AND i.current_version=v.version
                       WHERE v.memory_id=? AND v.layer='l3'""",
                    (memory_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload_json FROM memory_item_versions WHERE memory_id=? AND version=? AND layer='l3'",
                    (memory_id, version),
                ).fetchone()
        if row is None:
            raise MemoryItemNotFound(memory_id)
        return GlobalMemoryItem.model_validate_json(row["payload_json"])

    def query_active(
        self,
        namespace: MemoryNamespace,
        *,
        current_run_id: str,
        query_text: str,
        limit: int,
    ) -> list[tuple[GlobalMemoryItem, str, float]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT v.payload_json, v.keywords_json FROM memory_item_versions v
                   JOIN memory_items i ON i.memory_id=v.memory_id AND i.current_version=v.version
                   WHERE v.layer='l3' AND v.status='active' ORDER BY v.created_at DESC LIMIT ?""",
                (limit * 4,),
            ).fetchall()
        query_tokens = lexical_tokens(query_text)
        matches: list[tuple[GlobalMemoryItem, str, float]] = []
        for row in rows:
            item = GlobalMemoryItem.model_validate_json(row["payload_json"])
            if not self.policy.global_is_retrievable(
                item,
                now=self.clock.now(),
                dialect=namespace.dialect,
                domain=namespace.domain,
                current_run_id=current_run_id,
            ):
                continue
            tokens = set(json.loads(row["keywords_json"]))
            overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
            if not query_tokens or overlap > 0:
                matches.append((item, "lexical", min(0.8, 0.3 + overlap * 0.5)))
        return sorted(matches, key=lambda value: (-value[2], value[0].memory_id))[:limit]

    def append_proposal(self, proposal: PromotionProposal) -> PromotionProposal:
        payload = proposal.model_dump(mode="json")
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM memory_promotion_proposals WHERE proposal_id=?",
                (proposal.proposal_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash(payload):
                    raise MemoryStoreConflict("promotion proposal is immutable")
                return proposal
            connection.execute(
                "INSERT INTO memory_promotion_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.proposal_id, proposal.memory_id, proposal.source_version,
                    proposal.lifecycle, proposal.proposed_by_run_id, json_text(payload),
                    payload_hash(payload), proposal.expires_at.isoformat(),
                    proposal.created_at.isoformat(),
                    proposal.resolved_at.isoformat() if proposal.resolved_at else None,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> PromotionProposal:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM memory_promotion_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise MemoryItemNotFound(proposal_id)
        return PromotionProposal.model_validate_json(row["payload_json"])

    def resolve_proposal(
        self,
        proposal_id: str,
        *,
        actor_id: str,
        actor_role: str,
        approve: bool,
        reason: str,
    ) -> PromotionProposal:
        current = self.get_proposal(proposal_id)
        if current.lifecycle in {"active", "deprecated"}:
            return current
        if self.clock.now() >= current.expires_at:
            target = "deprecated"
        elif approve and self.policy.can_activate_global(
            actor_role=actor_role,
            support_project_count=len(set(current.support_project_ids)),
            support_eval_count=len(set(current.support_eval_ids)),
        ):
            target = "active"
        elif approve:
            raise MemoryPolicyError("promotion requires reviewer authority or cross-project evaluation support")
        else:
            target = "deprecated"
        updated = current.model_copy(update={
            "lifecycle": target,
            "reviewer_id": actor_id,
            "resolution_reason": reason,
            "resolved_at": self.clock.now(),
        })
        payload = updated.model_dump(mode="json")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """UPDATE memory_promotion_proposals SET lifecycle=?, payload_json=?, payload_hash=?, resolved_at=?
                   WHERE proposal_id=? AND lifecycle IN ('candidate', 'review')""",
                (
                    target, json_text(payload), payload_hash(payload),
                    updated.resolved_at.isoformat(), proposal_id,
                ),
            )
            if cursor.rowcount != 1:
                raise MemoryStoreConflict("promotion proposal changed concurrently")
        return updated
