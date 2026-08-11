"""Deterministic Phase 5 feature extraction with root-fact correlation control."""

from __future__ import annotations

from dataclasses import dataclass

from backend.evidence.contracts import EvidenceItem


SOURCE_FEATURES = (
    "catalog", "column_profile", "name_semantics", "sql_ast", "sql_llm",
    "orm", "memory", "human", "legacy_import",
)


@dataclass(frozen=True)
class FeatureExtraction:
    values: dict[str, float]
    included: list[EvidenceItem]
    excluded: list[EvidenceItem]
    independent_root_fact_ids: list[str]
    conflicts: list[str]


class EvidenceFeatureExtractor:
    """Collapse descendants and correlated observations before scoring."""

    def extract(self, evidence: list[EvidenceItem]) -> FeatureExtraction:
        live = [item for item in evidence if item.tombstoned_at is None and item.polarity != "neutral"]
        selected: dict[tuple[str, str, str], EvidenceItem] = {}
        excluded: list[EvidenceItem] = []
        for item in sorted(live, key=lambda row: (-row.strength * row.reliability, row.evidence_id)):
            key = (item.root_fact_id, item.correlation_group, item.polarity)
            if key in selected:
                excluded.append(item)
            else:
                selected[key] = item
        included = list(selected.values())
        values = {f"support_{source}": 0.0 for source in SOURCE_FEATURES}
        values.update({f"oppose_{source}": 0.0 for source in SOURCE_FEATURES})
        for item in included:
            values[f"{item.polarity}_{item.source_type}"] += item.strength * item.reliability
        roots = sorted({item.root_fact_id for item in included})
        support_roots = {item.root_fact_id for item in included if item.polarity == "support"}
        oppose_roots = {item.root_fact_id for item in included if item.polarity == "oppose"}
        non_memory_roots = {item.root_fact_id for item in included if item.source_type != "memory"}
        source_types = {item.source_type for item in included if item.polarity == "support"}
        conflicts = sorted(support_roots & oppose_roots)
        values.update({
            "independent_root_count": float(len(roots)),
            "support_root_count": float(len(support_roots)),
            "oppose_root_count": float(len(oppose_roots)),
            "non_memory_root_count": float(len(non_memory_roots)),
            "source_diversity": float(len(source_types)),
            "synergy_multi_source": 1.0 if len(source_types) >= 2 else 0.0,
            "conflict_root_count": float(len(conflicts)),
            "memory_only": 1.0 if included and not non_memory_roots else 0.0,
            "single_root": 1.0 if len(roots) <= 1 else 0.0,
        })
        return FeatureExtraction(values, included, excluded, roots, conflicts)
