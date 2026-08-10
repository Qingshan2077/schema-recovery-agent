"""Deterministic claim/citation/artifact grounding gate."""

from __future__ import annotations

from backend.agent.qa.contracts import FactSet, SynthesisDraft, VerificationReport


class AnswerVerifier:
    def verify(self, draft: SynthesisDraft, fact_set: FactSet) -> VerificationReport:
        known = {fact.fact_id for fact in fact_set.facts}
        facts_by_id = {fact.fact_id: fact for fact in fact_set.facts}
        errors: list[str] = []
        cited_claims = {citation.claim_id for citation in draft.citations}
        claim_ids = {claim.claim_id for claim in draft.claims}
        for claim in draft.claims:
            unknown = set(claim.fact_ids) - known
            if unknown:
                errors.append(f"claim {claim.claim_id} references unknown facts")
            if claim.claim_id not in cited_claims:
                errors.append(f"claim {claim.claim_id} has no citation")
            covered = {
                fact_id
                for citation in draft.citations
                if citation.claim_id == claim.claim_id
                for fact_id in citation.fact_ids
            }
            if set(claim.fact_ids) - covered:
                errors.append(f"claim {claim.claim_id} is not fully covered by its citations")
        for citation in draft.citations:
            if citation.claim_id not in claim_ids:
                errors.append(f"citation {citation.citation_id} references an unknown claim")
            if set(citation.fact_ids) - known:
                errors.append(f"citation {citation.citation_id} references unknown facts")
                continue
            expected_locators = [facts_by_id[fact_id].locator for fact_id in citation.fact_ids]
            expected_calls = sorted({facts_by_id[fact_id].source_tool_call_id for fact_id in citation.fact_ids})
            if citation.locator.get("fact_locators") != expected_locators:
                errors.append(f"citation {citation.citation_id} has an unverified source locator")
            if citation.locator.get("tool_call_ids") != expected_calls:
                errors.append(f"citation {citation.citation_id} has an unverified tool-call locator")
        for artifact in draft.artifacts:
            if set(artifact.fact_ids) - known:
                errors.append(f"artifact {artifact.artifact_id} references unknown facts")
        if draft.claims and draft.answer.strip() != "\n".join(claim.text for claim in draft.claims).strip():
            errors.append("answer contains text outside the verified claims")
        coverage = 1.0 if not draft.claims else len(cited_claims & claim_ids) / len(claim_ids)
        if coverage != 1.0:
            errors.append("citation coverage is below 100%")
        return VerificationReport(valid=not errors, citation_coverage=coverage, errors=errors)
