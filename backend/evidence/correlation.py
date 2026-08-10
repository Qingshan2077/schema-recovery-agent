"""Correlation clustering prevents repeated observations from double counting."""

from __future__ import annotations

from backend.agent.runtime.hybrid_contracts import EvidenceItem


def select_independent_evidence(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    selected: dict[str, EvidenceItem] = {}
    discarded: list[EvidenceItem] = []
    for item in sorted(items, key=lambda value: (-value.reliability * value.strength, value.evidence_id)):
        existing = selected.get(item.correlation_key)
        if existing is None:
            selected[item.correlation_key] = item
        else:
            discarded.append(item)
    return list(selected.values()), discarded
