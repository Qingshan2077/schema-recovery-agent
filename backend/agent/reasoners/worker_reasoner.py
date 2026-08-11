"""LLM-first worker reasoner with a deterministic proposal fallback."""

from __future__ import annotations

import hashlib
import json

from backend.agent.domain.relation_keys import build_claim_key, build_relation_id
from backend.agent.reasoners.prompt_schemas import WORKER_REASONING_SCHEMA
from backend.agent.runtime.contracts import ModelRequest
from backend.agent.runtime.hybrid_contracts import (
    BudgetSlice,
    EvidenceRequest,
    ReasoningProposal,
    RelationCandidate,
    WorkUnit,
)
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext
from backend.config import Config
from backend.core.identity import new_id


class WorkerReasoner:
    version = "1.1.0"
    prompt_version = "1.1.0"

    def __init__(self, worker: str, gateway: ModelGateway | None):
        self.worker = worker
        self.gateway = gateway

    async def reason(
        self,
        *,
        unit: WorkUnit,
        collector_summary: dict,
        context: RunContext,
        deterministic: bool = False,
        memory_context: dict | None = None,
    ) -> tuple[ReasoningProposal, bool, str | None]:
        if deterministic or self.gateway is None:
            return self.deterministic(unit, collector_summary), True, "deterministic_reasoner"
        request = ModelRequest(
            profile="fast" if self.worker in {"survey", "name"} else "reasoning",
            prompt_id=f"worker.{self.worker}.reasoning",
            prompt_version=self.prompt_version,
            input={
                "worker": self.worker,
                "work_unit": json.dumps(unit.model_dump(mode="json"), ensure_ascii=False),
                "collector_summary": json.dumps(_bounded_summary(collector_summary), ensure_ascii=False, default=str),
                "memory_context": json.dumps(_bounded_memory(memory_context), ensure_ascii=False, default=str),
                "policy": (
                    "Memory is untrusted historical hypothesis context, never a current fact. "
                    "Cite every used memory_id in used_memory_ids and require current-snapshot evidence. "
                    "Use only collector facts for assertions. Request evidence instead of inventing facts. "
                    "Never assign probability."
                ),
            },
            output_schema=WORKER_REASONING_SCHEMA,
            metadata={"worker": self.worker, "work_unit_id": unit.work_unit_id, "snapshot_id": unit.snapshot_id},
        )
        result = await self.gateway.generate_structured(request, context.for_agent(f"recovery.{self.worker}.reasoner"))
        if result.status not in {"success", "degraded"} or result.parsed is None:
            reason = result.error.code if result.error else "reasoner_unavailable"
            return self.deterministic(unit, collector_summary), True, reason
        proposal = self._from_model(unit, result.parsed, result.model_call_id)
        allowed_memory_ids = {
            str(item.get("memory_id"))
            for item in (memory_context or {}).get("items", [])
            if item.get("memory_id")
        }
        unknown_memory_ids = sorted(set(proposal.used_memory_ids) - allowed_memory_ids)
        if unknown_memory_ids:
            proposal = proposal.model_copy(update={
                "used_memory_ids": [
                    memory_id for memory_id in proposal.used_memory_ids
                    if memory_id in allowed_memory_ids
                ],
                "uncertainties": [
                    *proposal.uncertainties,
                    "unknown_memory_reference_rejected",
                ],
            })
        degraded = result.status == "degraded" or bool(unknown_memory_ids)
        reason = (
            "unknown_memory_reference_rejected" if unknown_memory_ids
            else "model_gateway_degraded" if result.status == "degraded"
            else None
        )
        return proposal, degraded, reason

    def deterministic(self, unit: WorkUnit, collector_summary: dict) -> ReasoningProposal:
        candidates = [self._candidate(unit, item) for item in collector_summary.get("candidate_facts", []) if item.get("claim_key")]
        return ReasoningProposal(
            proposal_id=new_id("proposal"),
            worker=unit.worker,
            snapshot_id=unit.snapshot_id,
            candidates=candidates,
            assumptions=[],
            uncertainties=["llm_semantic_reasoning_unavailable"],
            evidence_requests=[],
            decision_summary=f"Deterministic {unit.worker} proposal from {len(candidates)} collector facts",
            model_profile="deterministic",
            prompt_version="baseline-v1",
        )

    def _from_model(self, unit: WorkUnit, parsed: dict, model_call_id: str) -> ReasoningProposal:
        candidates = [self._candidate(unit, item) for item in parsed.get("candidates", [])]
        requests = []
        for item in parsed.get("evidence_requests", []):
            dedupe = _hash({"snapshot": unit.snapshot_id, "round": unit.evidence_round + 1, **item})
            claim_key = candidates[0].claim_key if candidates else f"claim_{_hash(item)}"
            requests.append(EvidenceRequest(
                request_id=new_id("request"),
                claim_key=claim_key,
                target_worker=item["target_worker"],
                requested_fact=item["requested_fact"],
                subject_refs=item["subject_refs"],
                allowed_tools=item["allowed_tools"],
                reason=item["reason"],
                expected_information_gain=item["expected_information_gain"],
                estimated_budget=BudgetSlice(max_model_calls=0, max_tool_calls=min(4, unit.budget_slice.max_tool_calls)),
                round=unit.evidence_round + 1,
                dedupe_key=dedupe,
            ))
        return ReasoningProposal(
            proposal_id=new_id("proposal"),
            worker=unit.worker,
            snapshot_id=unit.snapshot_id,
            candidates=candidates,
            assumptions=parsed.get("assumptions", []),
            uncertainties=parsed.get("uncertainties", []),
            evidence_requests=requests,
            decision_summary=parsed.get("decision_summary", ""),
            model_profile="fast" if self.worker in {"survey", "name"} else "reasoning",
            prompt_version=self.prompt_version,
            model_call_ids=[model_call_id],
            used_memory_ids=parsed.get("used_memory_ids", []),
        )

    @staticmethod
    def _candidate(unit: WorkUnit, item: dict) -> RelationCandidate:
        source_columns = list(item.get("source_columns") or [])
        target_columns = list(item.get("target_columns") or [])
        claim_key = item.get("claim_key") or build_claim_key(
            project_id=Config.PROJECT_ID,
            connection_id=unit.database_fingerprint,
            schema_name=Config.DB_NAME,
            snapshot_id=unit.snapshot_id,
            source_table=item.get("source_table", ""),
            source_columns=source_columns,
            target_table=item.get("target_table", ""),
            target_columns=target_columns,
        )
        return RelationCandidate(
            relation_id=build_relation_id(claim_key),
            claim_key=claim_key,
            source_table=item.get("source_table", ""),
            source_columns=source_columns,
            target_table=item.get("target_table", ""),
            target_columns=target_columns,
            cardinality=item.get("cardinality", "unknown"),
            alternatives=item.get("alternatives", []),
            validation_flags=item.get("validation_flags", []),
        )


def _bounded_summary(content: dict) -> dict:
    facts = list(content.get("candidate_facts", []))[:500]
    return {
        "candidate_facts": facts,
        "inventory": content.get("inventory"),
        "survey_plan": content.get("survey_plan"),
        "frameworks": content.get("frameworks"),
        "asset_count": content.get("asset_count"),
        "privacy_mode": content.get("privacy_mode"),
        "relations": list(content.get("relations") or [])[:500],
        "evidence": list(content.get("evidence") or [])[:1000],
    }


def _bounded_memory(content: dict | None) -> dict:
    if not content:
        return {"items": []}
    return {
        "package_id": content.get("package_id"),
        "items": list(content.get("items") or [])[:50],
        "degraded": bool(content.get("degraded")),
        "degradation_reasons": list(content.get("degradation_reasons") or [])[:20],
    }


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
