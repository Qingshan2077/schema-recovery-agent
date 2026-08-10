"""Deterministic, replayable log-odds evidence fusion with full breakdown."""

from __future__ import annotations

from math import exp, log

from backend.agent.runtime.hybrid_contracts import (
    ConfidenceBreakdown,
    ConfidenceContribution,
    EvidenceItem,
    FusedRelation,
    RelationCandidate,
)
from backend.evidence.calibration import IdentityCalibrator, ProbabilityCalibrator
from backend.evidence.correlation import select_independent_evidence


DEFAULT_SOURCE_WEIGHTS = {
    "catalog": 0.8,
    "column_profile": 1.2,
    "name_semantics": 0.65,
    "sql_ast": 1.45,
    "sql_llm": 0.55,
    "orm": 1.25,
    "memory": 0.4,
    "human": 2.0,
}


class EvidenceFusionEngine:
    def __init__(
        self,
        *,
        model_version: str = "log_odds_v2",
        weight_version: str = "phase3-default-v1",
        source_weights: dict[str, float] | None = None,
        calibrator: ProbabilityCalibrator | None = None,
        prior_probability: float = 0.18,
    ):
        self.model_version = model_version
        self.weight_version = weight_version
        self.source_weights = dict(source_weights or DEFAULT_SOURCE_WEIGHTS)
        self.calibrator = calibrator or IdentityCalibrator()
        self.prior_probability = prior_probability

    def fuse(self, candidate: RelationCandidate, evidence: list[EvidenceItem]) -> FusedRelation:
        scoped = [item for item in evidence if item.claim_key == candidate.claim_key]
        included, correlated = select_independent_evidence(scoped)
        prior_log_odds = _logit(self.prior_probability)
        contributions: list[ConfidenceContribution] = []
        total_delta = 0.0
        for item in included:
            weight = self.source_weights.get(item.source_type, 0.35)
            direction = 1.0 if item.polarity == "support" else -1.0 if item.polarity == "oppose" else 0.0
            delta = direction * weight * item.strength * item.reliability
            total_delta += delta
            contributions.append(_contribution(item, weight, delta, included=True))
        for item in correlated:
            weight = self.source_weights.get(item.source_type, 0.35)
            contributions.append(_contribution(item, weight, 0.0, included=False, reason="correlated_duplicate"))

        hard_flags = {
            flag for flag in candidate.validation_flags
            if flag.startswith("missing_") or flag.startswith("type_mismatch")
        }
        hard_adjustment = -8.0 if hard_flags else 0.0
        opposing_targets = sum(flag.startswith("conflicting_target") for flag in candidate.validation_flags)
        cardinality_conflicts = sum(flag.startswith("cardinality_conflict") for flag in candidate.validation_flags)
        conflict_adjustment = (-0.6 * opposing_targets) + (-0.4 * cardinality_conflicts)
        final_log_odds = prior_log_odds + total_delta + hard_adjustment + conflict_adjustment
        probability = self.calibrator.calibrate(_sigmoid(final_log_odds))
        band = "high" if probability >= 0.70 else "medium" if probability >= 0.40 else "low"
        breakdown = ConfidenceBreakdown(
            model_version=self.model_version,
            weight_version=self.weight_version,
            prior_probability=self.prior_probability,
            prior_log_odds=prior_log_odds,
            contributions=contributions,
            hard_constraint_adjustment=hard_adjustment,
            conflict_adjustment=conflict_adjustment,
            final_log_odds=final_log_odds,
            probability=probability,
            band=band,
        )
        return FusedRelation(candidate=candidate, probability=probability, band=band, breakdown=breakdown)


def _contribution(
    item: EvidenceItem,
    weight: float,
    delta: float,
    *,
    included: bool,
    reason: str | None = None,
) -> ConfidenceContribution:
    return ConfidenceContribution(
        evidence_id=item.evidence_id,
        source_type=item.source_type,
        polarity=item.polarity,
        source_weight=weight,
        strength=item.strength,
        reliability=item.reliability,
        log_odds_delta=delta,
        correlation_key=item.correlation_key,
        included=included,
        exclusion_reason=reason,
    )


def _logit(probability: float) -> float:
    bounded = min(max(probability, 1e-9), 1 - 1e-9)
    return log(bounded / (1 - bounded))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + exp(-value))
    exponential = exp(value)
    return exponential / (1 + exponential)
