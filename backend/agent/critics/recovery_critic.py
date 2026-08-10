"""Deterministic Critic that can request evidence but cannot change scores."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.agent.critics.evidence_request_policy import EvidenceRequestPolicy
from backend.agent.runtime.hybrid_contracts import (
    BudgetSlice,
    CritiqueDecision,
    EvidenceRequest,
    WorkUnit,
)
from backend.core.identity import new_id


class RecoveryCritic:
    version = "critic-v1"

    def __init__(self, policy: EvidenceRequestPolicy | None = None):
        self.policy = policy or EvidenceRequestPolicy()

    def review(self, merge_output: dict[str, Any], unit: WorkUnit) -> CritiqueDecision:
        medium = list(merge_output.get("medium_confidence_relations") or [])
        conflicted = [
            item
            for band in ("high_confidence_relations", "medium_confidence_relations", "low_confidence_relations")
            for item in merge_output.get(band, [])
            if any(str(flag).startswith("conflicting_target") for flag in item.get("validation_flags", []))
        ]
        targets = conflicted + [item for item in medium if item not in conflicted]
        requests: list[EvidenceRequest] = []
        authorized_relations: list[str] = []
        rejected_reasons: list[str] = []
        for relation in targets[:8]:
            request = self._request(relation, unit)
            authorized, reason = self.policy.authorize(request, unit)
            if authorized:
                requests.append(request)
                authorized_relations.append(relation["relation_id"])
            elif reason:
                rejected_reasons.append(reason)
        if requests:
            return CritiqueDecision(
                action="request_evidence",
                relation_ids=authorized_relations,
                evidence_requests=requests,
                conflicts=[item["relation_id"] for item in conflicted],
                uncertainties=["medium_confidence_requires_targeted_aggregate_profile"],
                summary=f"Requested {len(requests)} bounded aggregate checks; confidence was not modified.",
            )
        if targets and rejected_reasons:
            termination = "max_rounds" if "max_rounds" in rejected_reasons else "capability_missing"
            return CritiqueDecision(
                action="needs_review",
                relation_ids=[item["relation_id"] for item in targets],
                conflicts=[item["relation_id"] for item in conflicted],
                uncertainties=list(dict.fromkeys(rejected_reasons)),
                summary="No targeted request passed the evidence policy.",
                termination_reason=termination,
            )
        return CritiqueDecision(
            action="accept",
            relation_ids=[item["relation_id"] for item in merge_output.get("high_confidence_relations", [])],
            summary="No actionable conflict or medium-confidence relation remains.",
            termination_reason="accepted",
        )

    @staticmethod
    def _request(relation: dict[str, Any], unit: WorkUnit) -> EvidenceRequest:
        subject_refs = [
            f"{relation['source_table']}.{relation['fk_column']}",
            f"{relation['target_table']}.{relation['pk_column']}",
        ]
        dedupe = hashlib.sha256(json.dumps(
            {"snapshot": unit.snapshot_id, "relation": relation["relation_id"], "round": unit.evidence_round + 1},
            sort_keys=True,
        ).encode("utf-8")).hexdigest()
        return EvidenceRequest(
            request_id=new_id("request"),
            claim_key=relation["claim_key"],
            target_worker="column",
            requested_fact="aggregate overlap, orphan ratio, null ratio, and uniqueness for the candidate pair",
            subject_refs=subject_refs,
            allowed_tools=["recovery.profile_column", "recovery.profile_relationship"],
            reason="Resolve a conflict or medium-confidence edge with aggregate-only evidence.",
            expected_information_gain=0.75,
            estimated_budget=BudgetSlice(max_model_calls=0, max_tool_calls=3),
            round=unit.evidence_round + 1,
            dedupe_key=dedupe,
        )
