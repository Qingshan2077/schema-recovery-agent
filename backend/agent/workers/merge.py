"""MergeWorker implementation."""

from __future__ import annotations

from backend.agent.workers.base import BaseWorker


class MergeWorker(BaseWorker):
    SOURCE_WEIGHTS = {
        "sql_join": 0.40,
        "orm_association": 0.25,
        "orm_collection": 0.25,
        "column_name_suffix": 0.20,
        "primary_key_name_match": 0.20,
        "naming_convention_match": 0.18,
        "index_exists": 0.10,
        "naming_cross_table": 0.15,
        "explicit_fk_prefix": 0.25,
        "subquery_ref": 0.10,
    }
    HIGH_CONFIDENCE = 0.70
    MEDIUM_CONFIDENCE = 0.40
    SYNERGY_PER_EXTRA_SOURCE = 0.04
    MAX_SYNERGY = 0.12
    CONFLICT_PENALTY = 0.08

    def run(self, context: dict) -> dict:
        all_evidence = []
        for rel in context.get("code_result", {}).get("relations", []):
            all_evidence.append(self._normalize_evidence(rel))
        for rel in context.get("orm_result", {}).get("relations", []):
            all_evidence.append(self._normalize_evidence(rel))
        for rel in context.get("column_result", {}).get("potential_relations", []):
            for ev in rel.get("evidence", []):
                all_evidence.append(
                    self._normalize_evidence(
                        {
                            "source_table": rel["source_table"],
                            "target_table": rel["target_table"],
                            "fk_column": rel.get("fk_column", ""),
                            "pk_column": rel.get("pk_column", ""),
                            "confidence": min(rel.get("confidence", 0.5), 0.95),
                            "evidence": [ev],
                            "relation_type": ev.get("source", "column_analysis"),
                        }
                    )
                )
        for rel in context.get("name_result", {}).get("column_name_matches", {}).get("matches", []):
            for ev in rel.get("evidence", []):
                all_evidence.append(
                    self._normalize_evidence(
                        {
                            "source_table": rel["source_table"],
                            "target_table": rel["target_table"],
                            "fk_column": rel.get("fk_column", ""),
                            "pk_column": rel.get("pk_column", ""),
                            "confidence": rel.get("confidence", 0.5),
                            "evidence": [ev],
                            "relation_type": "naming_cross_table",
                        }
                    )
                )
        return self._fuse_evidence(all_evidence)

    def _normalize_evidence(self, rel: dict) -> dict:
        return {
            "source_table": rel.get("source_table", ""),
            "target_table": rel.get("target_table", ""),
            "fk_column": rel.get("fk_column", ""),
            "pk_column": rel.get("pk_column", ""),
            "raw_confidence": min(rel.get("confidence", rel.get("sub_confidence", 0.5)), 1.0),
            "evidence_list": rel.get("evidence", []),
            "relation_type": rel.get("relation_type", "unknown"),
            "source_file": rel.get("source_file", ""),
            "source_name": rel.get("source_name", ""),
        }

    def _fuse_evidence(self, all_evidence: list[dict]) -> dict:
        groups: dict[tuple[str, str, str, str], dict] = {}
        target_candidates: dict[tuple[str, str], set[str]] = {}
        for ev in all_evidence:
            key = (
                ev["source_table"].lower(),
                ev["target_table"].lower(),
                ev["fk_column"].lower(),
                ev["pk_column"].lower(),
            )
            if not key[0] or not key[2]:
                continue
            target_candidates.setdefault((key[0], key[2]), set()).add(key[1])
            groups.setdefault(
                key,
                {"source_table": key[0], "target_table": key[1], "fk_column": key[2], "pk_column": key[3], "evidences": []},
            )
            groups[key]["evidences"].append(ev)

        fused_relations = []
        for group in groups.values():
            conflicts = len(target_candidates.get((group["source_table"], group["fk_column"]), set())) - 1
            fused = self._fuse_single_group(group, conflicts=max(conflicts, 0))
            if fused:
                fused_relations.append(fused)
        fused_relations.sort(key=lambda x: x["fused_confidence"], reverse=True)

        high = [r for r in fused_relations if r["fused_confidence"] >= self.HIGH_CONFIDENCE]
        medium = [r for r in fused_relations if self.MEDIUM_CONFIDENCE <= r["fused_confidence"] < self.HIGH_CONFIDENCE]
        low = [r for r in fused_relations if r["fused_confidence"] < self.MEDIUM_CONFIDENCE]
        return {
            "status": "success",
            "summary": {
                "total_relations": len(fused_relations),
                "high_confidence": len(high),
                "medium_confidence": len(medium),
                "low_confidence": len(low),
            },
            "high_confidence_relations": high,
            "medium_confidence_relations": medium,
            "low_confidence_relations": low,
            "source_contributions": self._calculate_source_contributions(fused_relations),
            "evidence_detail": {},
        }

    def _fuse_single_group(self, group: dict, conflicts: int = 0) -> dict | None:
        weighted_sum = 0.0
        total_weight = 0.0
        evidence_details = []
        relation_type_counts = {}
        for ev in group["evidences"]:
            rel_type = ev.get("relation_type", "unknown")
            weight = self.SOURCE_WEIGHTS.get(rel_type, 0.10)
            weighted_sum += weight * ev.get("raw_confidence", 0.5)
            total_weight += weight
            relation_type_counts[rel_type] = relation_type_counts.get(rel_type, 0) + 1
            for item in ev.get("evidence_list", []):
                evidence_details.append(
                    {"type": rel_type, "weight": weight, "detail": item.get("detail", ""), "strength": item.get("strength", 0)}
                )
        if total_weight == 0:
            return None

        base_confidence = weighted_sum / total_weight
        source_count = len(relation_type_counts)
        synergy_bonus = min(max(source_count - 1, 0) * self.SYNERGY_PER_EXTRA_SOURCE, self.MAX_SYNERGY)
        conflict_penalty = conflicts * self.CONFLICT_PENALTY
        fused_confidence = max(0.0, min(1.0, base_confidence + synergy_bonus - conflict_penalty))
        relation_type = self._resolve_relation_type(relation_type_counts)
        reason = self._build_confidence_reason(base_confidence, synergy_bonus, conflict_penalty, relation_type_counts)

        return {
            "source_table": group["source_table"],
            "target_table": group["target_table"],
            "fk_column": group["fk_column"],
            "pk_column": group["pk_column"],
            "relation_type": relation_type,
            "fused_confidence": round(fused_confidence, 4),
            "base_confidence": round(base_confidence, 4),
            "synergy_bonus": round(synergy_bonus, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "confidence_reason": reason,
            "evidence_count": len(evidence_details),
            "evidence_sources": list(relation_type_counts.keys()),
            "evidence_chain": evidence_details,
        }

    @staticmethod
    def _resolve_relation_type(relation_type_counts: dict[str, int]) -> str:
        if "orm_collection" in relation_type_counts:
            return "1:N"
        if "sql_join" in relation_type_counts:
            return "N:1"
        return "N:1"

    @staticmethod
    def _build_confidence_reason(base: float, synergy: float, penalty: float, relation_type_counts: dict[str, int]) -> str:
        sources = ", ".join(sorted(relation_type_counts)) or "unknown"
        parts = [f"base={base:.2f} from {sources}"]
        if synergy > 0:
            parts.append(f"+{synergy:.2f} multi-source agreement")
        if penalty > 0:
            parts.append(f"-{penalty:.2f} conflicting target candidates")
        return "; ".join(parts)

    def _calculate_source_contributions(self, relations: list[dict]) -> dict:
        source_counts = {}
        for rel in relations:
            for src in rel.get("evidence_sources", []):
                source_counts[src] = source_counts.get(src, 0) + 1
        total = sum(source_counts.values()) or 1
        return {
            source: {"count": count, "percentage": round(count / total * 100, 1)}
            for source, count in sorted(source_counts.items(), key=lambda item: -item[1])
        }
