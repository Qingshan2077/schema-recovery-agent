"""Deterministic verifier that binds model proposals back to collector facts."""

from __future__ import annotations

from backend.agent.domain.candidate_normalizer import CandidateNormalizer
from backend.agent.domain.catalog_resolver import RecoveryCatalogResolver
from backend.agent.domain.relation_keys import build_correlation_key
from backend.agent.runtime.hybrid_contracts import EvidenceItem, ReasoningProposal, VerificationDecision, WorkUnit
from backend.core.identity import stable_id


class WorkerVerifier:
    version = "1.0.0"

    def __init__(self, worker: str):
        self.worker = worker
        self.normalizer = CandidateNormalizer()

    def verify(
        self,
        *,
        unit: WorkUnit,
        proposal: ReasoningProposal,
        collector_content: dict,
        catalog: RecoveryCatalogResolver,
        artifact_id: str,
    ) -> VerificationDecision:
        if proposal.snapshot_id != unit.snapshot_id:
            raise ValueError("proposal snapshot does not match work unit snapshot")
        facts_by_claim = {
            item.get("claim_key"): item
            for item in collector_content.get("candidate_facts", [])
            if item.get("claim_key")
        }
        accepted = []
        rejected = []
        evidence_items: list[EvidenceItem] = []
        for raw_candidate in proposal.candidates:
            candidate = self.normalizer.normalize(raw_candidate)
            fact = facts_by_claim.get(candidate.claim_key)
            flags = list(dict.fromkeys(candidate.validation_flags + catalog.validate_candidate(candidate)))
            if fact is None:
                flags.append("unsupported_by_collector")
            elif fact.get("source_type") in {"sql_ast", "sql_llm", "orm"} and not fact.get("source_locator"):
                flags.append("missing_source_locator")
            candidate = candidate.model_copy(update={"validation_flags": flags})
            hard = any(
                flag == "unsupported_by_collector"
                or flag.startswith("missing_")
                or flag.startswith("type_mismatch")
                or flag.startswith("target_not_unique")
                for flag in flags
            )
            if hard:
                rejected.append(candidate)
                if fact is not None:
                    evidence_items.append(self._evidence(unit, candidate, fact, artifact_id, polarity="oppose", strength=1.0))
                continue
            evidence = self._evidence(unit, candidate, fact, artifact_id)
            candidate = candidate.model_copy(update={"evidence_ids": [evidence.evidence_id]})
            accepted.append(candidate)
            evidence_items.append(evidence)
        completeness = len(accepted) / max(len(proposal.candidates), 1) if proposal.candidates else 1.0
        return VerificationDecision(
            proposal_id=proposal.proposal_id,
            accepted=accepted,
            rejected=rejected,
            evidence_items=evidence_items,
            unresolved_requests=proposal.evidence_requests,
            completeness=completeness,
            decision_summary=f"accepted={len(accepted)} rejected={len(rejected)} with catalog and collector binding",
        )

    def _evidence(
        self,
        unit: WorkUnit,
        candidate,
        fact: dict,
        artifact_id: str,
        *,
        polarity: str | None = None,
        strength: float | None = None,
    ) -> EvidenceItem:
        locator = dict(fact.get("source_locator") or {})
        source_type = fact.get("source_type", "catalog")
        correlation_key = build_correlation_key(
            source_type=source_type,
            producer=self.worker,
            artifact_id=artifact_id,
            source_uri=fact.get("source_uri"),
            source_locator={"seed": fact.get("correlation_seed"), **locator},
        )
        evidence_id = stable_id(
            "evidence", unit.snapshot_id, candidate.claim_key, self.worker,
            fact.get("polarity"), fact.get("summary"), correlation_key,
        )
        return EvidenceItem(
            evidence_id=evidence_id,
            snapshot_id=unit.snapshot_id,
            database_fingerprint=unit.database_fingerprint,
            claim_key=candidate.claim_key,
            relation_id=candidate.relation_id,
            source_type=source_type,
            producer=self.worker,
            polarity=polarity or fact.get("polarity", "neutral"),
            strength=strength if strength is not None else fact.get("strength", 0.5),
            reliability=fact.get("reliability", 0.5),
            summary=fact.get("summary", "verified collector fact"),
            source_uri=fact.get("source_uri"),
            source_locator=locator,
            artifact_id=artifact_id,
            tool_call_id=(fact.get("tool_call_id") or None),
            trace_id=unit.trace_id,
            correlation_key=correlation_key,
        )
