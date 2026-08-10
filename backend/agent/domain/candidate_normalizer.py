"""Normalize candidate direction and column order without changing evidence."""

from __future__ import annotations

from backend.agent.runtime.hybrid_contracts import RelationCandidate


class CandidateNormalizer:
    def normalize(self, candidate: RelationCandidate) -> RelationCandidate:
        pairs = sorted(
            zip(candidate.source_columns, candidate.target_columns),
            key=lambda pair: (pair[0].casefold(), pair[1].casefold()),
        )
        return candidate.model_copy(
            update={
                "source_table": candidate.source_table.casefold(),
                "target_table": candidate.target_table.casefold(),
                "source_columns": [pair[0].casefold() for pair in pairs],
                "target_columns": [pair[1].casefold() for pair in pairs],
            }
        )
