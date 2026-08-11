"""Bounded hybrid memory retrieval with deterministic rerank and diversity."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Protocol

from backend.agent.memory.contracts import (
    GlobalMemoryItem,
    MemoryContextItem,
    MemoryContextPackage,
    MemoryRetrievalQuery,
    RelationMemoryVersion,
)
from backend.agent.memory.l2_store import L2MemoryStore
from backend.agent.memory.l3_store import L3MemoryStore
from backend.agent.memory.policy import MemoryPolicy
from backend.core.identity import stable_id


class VectorRetriever(Protocol):
    def search(self, query: MemoryRetrievalQuery) -> dict[str, float]: ...


class MemoryRetriever:
    def __init__(
        self,
        l2: L2MemoryStore,
        l3: L3MemoryStore,
        *,
        policy: MemoryPolicy,
        vector: VectorRetriever | None = None,
        vector_enabled: bool = False,
    ):
        self.l2 = l2
        self.l3 = l3
        self.policy = policy
        self.vector = vector
        self.vector_enabled = vector_enabled

    def retrieve(self, query: MemoryRetrievalQuery, *, now: datetime) -> MemoryContextPackage:
        query.namespace.require_l2()
        l2_matches = self.l2.query(
            query.namespace,
            current_run_id=query.current_run_id,
            object_ids=query.object_ids,
            query_text=query.query_text,
            include_stale=query.include_stale,
            limit=query.top_k * 2,
        )
        l3_matches = self.l3.query_active(
            query.namespace,
            current_run_id=query.current_run_id,
            query_text=query.query_text,
            limit=query.top_k,
        )
        vector_scores: dict[str, float] = {}
        degraded: list[str] = []
        if self.vector_enabled:
            if self.vector is not None:
                vector_scores = self.vector.search(query)

        candidates: list[MemoryContextItem] = []
        query_text = " ".join([query.query_text, *query.object_ids])
        for item, method, score in l2_matches:
            vector_score = vector_scores.get(item.memory_id)
            if self.vector_enabled and vector_score is None:
                vector_score = _local_vector_similarity(query_text, item.summary)
            final_score = max(score, vector_score or 0.0)
            candidates.append(self._l2_item(item, "vector" if final_score > score else method, final_score))
        for item, method, score in l3_matches:
            vector_score = vector_scores.get(item.memory_id)
            if self.vector_enabled and vector_score is None:
                vector_score = _local_vector_similarity(query_text, item.rule_summary)
            final_score = max(score, vector_score or 0.0)
            candidates.append(self._l3_item(item, "vector" if final_score > score else method, final_score))
        candidates.sort(key=lambda item: (-item.retrieval_score, item.layer, item.memory_id))

        selected: list[MemoryContextItem] = []
        discarded: dict[str, int] = {}
        consumed = 0
        relation_counts: dict[str, int] = {}
        root_counts: dict[str, int] = {}
        for item in candidates:
            if len(selected) >= query.top_k:
                _increment(discarded, "top_k")
                continue
            diversity_key = item.memory_id.split(":", 1)[0]
            if relation_counts.get(diversity_key, 0) >= 2:
                _increment(discarded, "diversity_relation")
                continue
            if item.root_fact_ids and all(root_counts.get(root, 0) >= 1 for root in item.root_fact_ids):
                _increment(discarded, "diversity_root_fact")
                continue
            if consumed + item.estimated_tokens > query.token_budget:
                _increment(discarded, "token_budget")
                continue
            selected.append(item)
            consumed += item.estimated_tokens
            relation_counts[diversity_key] = relation_counts.get(diversity_key, 0) + 1
            for root in item.root_fact_ids:
                root_counts[root] = root_counts.get(root, 0) + 1

        package_id = stable_id(
            "artifact", query.current_run_id, query.namespace.snapshot_id,
            [f"{item.memory_id}:{item.version}" for item in selected],
        )
        return MemoryContextPackage(
            package_id=package_id,
            namespace=query.namespace,
            query=query,
            items=selected,
            selected_count=len(selected),
            discarded_count=sum(discarded.values()),
            discarded_reasons=discarded,
            estimated_tokens=consumed,
            degraded=bool(degraded),
            degradation_reasons=degraded,
            created_at=now,
        )

    def _l2_item(self, item: RelationMemoryVersion, method: str, score: float) -> MemoryContextItem:
        freshness = "current" if item.namespace.snapshot_id == item.last_verified_snapshot_id else "inherited"
        return MemoryContextItem(
            memory_id=item.memory_id,
            version=item.version,
            layer="l2",
            retrieval_method=method,
            retrieval_score=min(1.0, score),
            namespace_match=True,
            freshness="stale" if item.status == "stale" else freshness,
            status=item.status,
            root_fact_ids=item.root_fact_ids,
            evidence_ids=item.evidence_ids,
            summary=self.policy.sanitize_summary(item.summary),
            verification_requirements=[
                "object_exists", "type_compatible", "target_candidate_key", "current_non_memory_evidence",
            ],
            source_run_id=item.created_by_run_id,
            estimated_tokens=_tokens(item.summary) + 64,
        )

    def _l3_item(self, item: GlobalMemoryItem, method: str, score: float) -> MemoryContextItem:
        return MemoryContextItem(
            memory_id=item.memory_id,
            version=item.version,
            layer="l3",
            retrieval_method=method,
            retrieval_score=min(1.0, score),
            namespace_match=True,
            freshness="current",
            status=item.lifecycle,
            summary=self.policy.sanitize_summary(item.rule_summary),
            verification_requirements=["scope_match", "dialect_match", "current_snapshot_evidence"],
            source_run_id=item.created_by_run_id,
            estimated_tokens=_tokens(item.rule_summary) + 48,
        )


def _tokens(value: str) -> int:
    return max(1, len(value.encode("utf-8")) // 4)


def _increment(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1


def _local_vector_similarity(left: str, right: str, *, dimensions: int = 128) -> float:
    """Deterministic hashed character n-gram cosine fallback.

    It is intentionally local and data-free: deployments can inject an embedding
    provider, while the default advanced path still provides semantic-ish fuzzy
    retrieval without silently disabling the vector leg.
    """
    def vector(value: str) -> list[float]:
        normalized = " ".join(value.casefold().split())
        if not normalized:
            return [0.0] * dimensions
        grams = [normalized[index:index + 3] for index in range(max(1, len(normalized) - 2))]
        result = [0.0] * dimensions
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % dimensions
            result[bucket] += -1.0 if digest[2] & 1 else 1.0
        return result

    a, b = vector(left), vector(right)
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
