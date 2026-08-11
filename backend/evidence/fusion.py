"""Deterministic, replayable log-odds evidence fusion with full breakdown."""

from __future__ import annotations

from math import exp, log
from datetime import datetime

from backend.agent.runtime.hybrid_contracts import (
    ConfidenceBreakdown,
    ConfidenceContribution,
    EvidenceItem,
    FusedRelation,
    RelationCandidate,
)
from backend.evidence.calibration import IdentityCalibrator, ProbabilityCalibrator
from backend.evidence.contracts import (
    Contribution as VersionedContribution,
    EvidenceItem as VersionedEvidenceItem,
    FusionResult as VersionedFusionResult,
    RelationCandidateVersion,
    ThresholdPolicy,
)
from backend.evidence.correlation import select_independent_evidence
from backend.evidence.features import EvidenceFeatureExtractor


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

DEFAULT_FEATURE_COEFFICIENTS = {
    "support_catalog": 0.8, "oppose_catalog": -0.9,
    "support_column_profile": 1.2, "oppose_column_profile": -1.3,
    "support_name_semantics": 0.65, "oppose_name_semantics": -0.75,
    "support_sql_ast": 1.45, "oppose_sql_ast": -1.6,
    "support_sql_llm": 0.55, "oppose_sql_llm": -0.65,
    "support_orm": 1.25, "oppose_orm": -1.4,
    "support_memory": 0.35, "oppose_memory": -0.4,
    "support_human": 2.0, "oppose_human": -2.2,
    "support_legacy_import": 0.25, "oppose_legacy_import": -0.3,
    "synergy_multi_source": 0.35,
    "conflict_root_count": -0.9,
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


class VersionedFusionEngine:
    """Replayable scorer: raw features, calibration and thresholds are separate versions."""

    def __init__(
        self,
        *,
        fusion_version: str,
        feature_schema_hash: str,
        threshold_policy: ThresholdPolicy,
        calibrator: ProbabilityCalibrator | None = None,
        coefficients: dict[str, float] | None = None,
        prior_probability: float = 0.18,
    ):
        self.fusion_version = fusion_version
        self.feature_schema_hash = feature_schema_hash
        self.threshold_policy = threshold_policy
        self.calibrator = calibrator or IdentityCalibrator()
        self.coefficients = dict(DEFAULT_FEATURE_COEFFICIENTS)
        self.coefficients.update(coefficients or {})
        self.prior_probability = prior_probability
        self.extractor = EvidenceFeatureExtractor()

    def fuse(
        self,
        template: RelationCandidateVersion,
        evidence: list[VersionedEvidenceItem],
        *,
        version: int,
        run_id: str,
        now: datetime,
    ) -> VersionedFusionResult:
        scoped = [item for item in evidence if item.claim_key == template.claim_key]
        extraction = self.extractor.extract(scoped)
        raw_score = _logit(self.prior_probability)
        breakdown: list[VersionedContribution] = []
        for feature in sorted(extraction.values):
            value = extraction.values[feature]
            coefficient = self.coefficients.get(feature, 0.0)
            delta = value * coefficient
            raw_score += delta
            ids = [
                item.evidence_id for item in extraction.included
                if feature.endswith(item.source_type) or feature in {
                    "independent_root_count", "support_root_count", "oppose_root_count",
                    "non_memory_root_count", "source_diversity", "synergy_multi_source",
                    "conflict_root_count", "memory_only", "single_root",
                }
            ]
            breakdown.append(VersionedContribution(
                feature=feature, value=value, coefficient=coefficient,
                log_odds_delta=delta, evidence_ids=sorted(set(ids)),
            ))
        hard_flags = [
            flag for flag in template.validation_flags
            if flag.startswith(("missing_", "type_mismatch", "target_not_candidate_key"))
        ]
        if hard_flags:
            raw_score -= 8.0
            breakdown.append(VersionedContribution(
                feature="hard_constraint_violation", value=1.0, coefficient=-8.0,
                log_odds_delta=-8.0,
            ))
        raw_probability = _sigmoid(raw_score)
        calibrated = self.calibrator.calibrate(raw_probability)
        band = self._band(calibrated, extraction.values)
        relation = template.model_copy(update={
            "version": version,
            "evidence_ids": sorted(item.evidence_id for item in extraction.included),
            "feature_vector": extraction.values,
            "feature_schema_hash": self.feature_schema_hash,
            "raw_score": raw_score,
            "raw_probability": raw_probability,
            "calibrated_probability": calibrated,
            "confidence_band": band,
            "fusion_version": self.fusion_version,
            "calibration_version": self.calibrator.version,
            "threshold_policy_version": self.threshold_policy.version,
            "contribution_breakdown": breakdown,
            "created_by_run_id": run_id,
            "created_at": now,
            "superseded_by_version": None,
        })
        hints: list[dict[str, str]] = []
        if extraction.values["memory_only"]:
            hints.append({"type": "current_snapshot_fact", "reason": "memory_only_candidate"})
        if extraction.conflicts:
            hints.append({"type": "conflict_resolution", "reason": "opposing_root_facts"})
        return VersionedFusionResult(
            relation=relation,
            independent_root_fact_ids=extraction.independent_root_fact_ids,
            excluded_evidence_ids=sorted(item.evidence_id for item in extraction.excluded),
            conflict_reasons=[f"opposing_polarity:{root}" for root in extraction.conflicts],
            evidence_request_hints=hints,
            calibration_applied=self.calibrator.version != "identity-v1",
        )

    def _band(self, probability: float, features: dict[str, float]) -> str:
        if probability >= self.threshold_policy.high:
            if self.threshold_policy.memory_only_high_forbidden and features["memory_only"]:
                return "medium"
            if self.threshold_policy.single_root_high_forbidden and features["single_root"]:
                return "medium"
            return "high"
        return "medium" if probability >= self.threshold_policy.medium else "low"


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
