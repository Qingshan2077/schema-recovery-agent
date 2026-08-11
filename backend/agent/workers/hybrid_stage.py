"""Shared Phase 3 Collector -> Reasoner -> Verifier -> Ledger stage."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from threading import Thread
from typing import Any

from backend.agent.collectors import collector_for
from backend.agent.collectors.base import CollectorRuntime
from backend.agent.domain.catalog_resolver import RecoveryCatalogResolver
from backend.agent.reasoners import WorkerReasoner
from backend.agent.runtime.hybrid_contracts import (
    BudgetSlice,
    HybridWorkerResult,
    EvidenceRequest,
    RelationCandidate,
    StageResult,
    WorkUnit,
    WorkerMode,
)
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext, RuntimeCancelledError
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.agent.verifiers import WorkerVerifier
from backend.config import Config
from backend.core.identity import new_id, stable_id
from backend.core.status import AgentError, RunStatus
from backend.evidence.fusion import EvidenceFusionEngine
from backend.evidence.ledger import EvidenceLedger
from backend.evidence.repository import EvidenceIntegrityError, SQLiteEvidenceRepository
from backend.workflow.contracts import StageCapabilities


@dataclass(frozen=True)
class HybridStageDependencies:
    run_context: RunContext
    tool_runtime: ToolRuntime
    model_gateway: ModelGateway | None
    ledger: EvidenceLedger
    legacy_workers: dict[str, Any] = field(default_factory=dict)
    memory_service: Any | None = None
    versioned_evidence_repository: Any | None = None


class HybridRecoveryStage:
    """One implementation shared by all six workers.

    Collectors own observations, the model may only propose interpretations,
    verifiers bind proposals back to observations, and only verified objects are
    written to the append-only ledger.
    """

    def __init__(self, worker: str, dependencies: HybridStageDependencies):
        self.worker = worker
        self.dependencies = dependencies
        self.collector = collector_for(worker)
        self.reasoner = WorkerReasoner(worker, dependencies.model_gateway)
        self.verifier = WorkerVerifier(worker)

    async def execute(self, unit: WorkUnit, context: dict[str, Any]) -> HybridWorkerResult:
        runtime_context = self.dependencies.run_context.for_agent(f"recovery.{self.worker}")
        span_id = new_id("span")
        artifact_ids: list[str] = []
        evidence_ids: list[str] = []
        relation_ids: list[str] = []
        model_call_ids: list[str] = []
        missing: list[str] = []
        uncertainties: list[str] = []
        try:
            runtime_context.cancellation.raise_if_cancelled()
            await _emit(runtime_context, "worker.started", "running", span_id, unit)
            await _emit(runtime_context, "collector.started", "running", span_id, unit)
            collector_runtime = CollectorRuntime(
                self.dependencies.tool_runtime,
                runtime_context,
                caller_agent=f"recovery.{self.worker}",
            )
            collected = await self.collector.collect(unit, context, collector_runtime)
            collected.tool_call_ids = list(dict.fromkeys(collected.tool_call_ids + collector_runtime.tool_call_ids))
            await _emit(
                runtime_context,
                "collector.completed",
                "success",
                span_id,
                unit,
                {"completeness": collected.completeness, "tool_call_ids": collected.tool_call_ids},
            )
            artifact = self.dependencies.ledger.write_artifact(
                snapshot_id=unit.snapshot_id,
                subject_refs=unit.subject_refs,
                content=collected.content,
                completeness=collected.completeness,
                missing_capabilities=collected.missing_capabilities,
                tool_call_ids=collected.tool_call_ids,
                collector_version=collected.collector_version,
                idempotency_key=unit.idempotency_key,
            )
            artifact_ids.append(artifact.artifact_id)
            await _emit(runtime_context, "artifact.created", "success", span_id, unit, {"artifact_id": artifact.artifact_id})

            deterministic = unit.worker == "merge" and not context.get("_allow_merge_llm", True)
            proposal, degraded, degradation_reason = await self.reasoner.reason(
                unit=unit,
                collector_summary=collected.content,
                context=runtime_context,
                deterministic=deterministic,
                memory_context=context.get("memory_context"),
            )
            model_call_ids.extend(proposal.model_call_ids)
            uncertainties.extend(proposal.uncertainties)
            if proposal.used_memory_ids:
                await _emit(
                    runtime_context, "memory.used", "success", span_id, unit,
                    {"memory_ids": proposal.used_memory_ids},
                )
            if degradation_reason:
                uncertainties.append(degradation_reason)
            missing.extend(collected.missing_capabilities)

            await _emit(runtime_context, "verifier.started", "running", span_id, unit)
            catalog = RecoveryCatalogResolver(
                snapshot_id=unit.snapshot_id,
                catalog=list((context.get("survey_result") or {}).get("schema_catalog") or []),
            )
            decision = self.verifier.verify(
                unit=unit,
                proposal=proposal,
                collector_content=collected.content,
                catalog=catalog,
                artifact_id=artifact.artifact_id,
            )
            await _emit(
                runtime_context,
                "verifier.completed",
                "success",
                span_id,
                unit,
                {"accepted": len(decision.accepted), "rejected": len(decision.rejected)},
            )

            # Shadow is observational: it records its collector artifact but can
            # never contaminate the accepted evidence/candidate ledger.
            if unit.worker != "merge" and context.get("_worker_mode") != "shadow":
                for item in decision.evidence_items:
                    self.dependencies.ledger.append_evidence(item)
                    evidence_ids.append(item.evidence_id)
                    await _emit(runtime_context, "evidence.created", "success", span_id, unit, {"evidence_id": item.evidence_id})
                for candidate in decision.accepted:
                    self.dependencies.ledger.append_relation(candidate, snapshot_id=unit.snapshot_id, producer=self.worker)
                    relation_ids.append(candidate.relation_id)
                    await _emit(runtime_context, "relation.proposed", "success", span_id, unit, {"relation_id": candidate.relation_id})

            output = self._build_output(
                collected.legacy_output,
                decision.accepted,
                decision.rejected,
                context,
                artifact.artifact_id,
                unit,
            )
            if unit.worker == "merge" and output.get("critic_decision"):
                critique = output["critic_decision"]
                await _emit(runtime_context, "critic.started", "running", span_id, unit)
                if critique.get("evidence_requests"):
                    await _emit(
                        runtime_context,
                        "critic.evidence_requested",
                        "success",
                        span_id,
                        unit,
                        {"request_ids": [item["request_id"] for item in critique["evidence_requests"]]},
                    )
                await _emit(runtime_context, "critic.completed", "success", span_id, unit, {"action": critique["action"]})
            revision = self.dependencies.ledger.create_revision(
                snapshot_id=unit.snapshot_id,
                reason=f"{self.worker}:{unit.work_unit_id}:{context.get('_worker_mode', 'hybrid')}",
            )
            status = RunStatus.DEGRADED if degraded or missing else RunStatus.SUCCESS
            pending_requests = [item.model_dump(mode="json") for item in decision.unresolved_requests]
            if output.get("critic_decision"):
                pending_requests.extend(output["critic_decision"].get("evidence_requests") or [])
            pending_requests = list({item["dedupe_key"]: item for item in pending_requests}.values())
            output.update({
                "status": status.value,
                "hybrid_contract_version": "3.0",
                "worker_mode": context.get("_worker_mode", "hybrid"),
                "work_unit_id": unit.work_unit_id,
                "artifact_ids": artifact_ids,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "relation_ids": list(dict.fromkeys(relation_ids)),
                "model_call_ids": model_call_ids,
                "used_memory_ids": proposal.used_memory_ids,
                "ledger_revision": revision,
                "evidence_requests": pending_requests,
                "missing_capabilities": list(dict.fromkeys(missing)),
                "uncertainties": list(dict.fromkeys(uncertainties)),
                "reasoning_summary": proposal.decision_summary,
            })
            event_type = "worker.degraded" if status == RunStatus.DEGRADED else "worker.completed"
            await _emit(runtime_context, event_type, status.value, span_id, unit, {"ledger_revision": revision})
            return HybridWorkerResult(
                status=status,
                worker=unit.worker,
                mode=context.get("_worker_mode", "hybrid"),
                work_unit_id=unit.work_unit_id,
                snapshot_id=unit.snapshot_id,
                artifact_ids=artifact_ids,
                evidence_ids=evidence_ids,
                relation_ids=relation_ids,
                tool_call_ids=collected.tool_call_ids,
                model_call_ids=model_call_ids,
                used_memory_ids=proposal.used_memory_ids,
                assumptions=proposal.assumptions,
                uncertainties=list(dict.fromkeys(uncertainties)),
                missing_capabilities=list(dict.fromkeys(missing)),
                output=output,
                ledger_revision=revision,
                idempotency_key=unit.idempotency_key,
            )
        except RuntimeCancelledError as exc:
            error = AgentError(code="worker_cancelled", category="cancelled", message=str(exc), source=self.worker)
            await _emit(runtime_context, "worker.failed", "cancelled", span_id, unit, {"code": error.code})
            return _failure_result(unit, context, RunStatus.CANCELLED, error, artifact_ids)
        except EvidenceIntegrityError as exc:
            error = AgentError(
                code="evidence_integrity_blocked",
                category="validation",
                message=str(exc),
                retryable=False,
                source=self.worker,
            )
            await _emit(runtime_context, "worker.failed", "blocked", span_id, unit, {"code": error.code})
            return _failure_result(unit, context, RunStatus.BLOCKED, error, artifact_ids)
        except Exception as exc:
            error = AgentError(
                code="hybrid_worker_failed",
                category="internal",
                message=str(exc),
                retryable=True,
                source=self.worker,
            )
            await _emit(runtime_context, "worker.failed", "error", span_id, unit, {"code": error.code})
            return _failure_result(unit, context, RunStatus.ERROR, error, artifact_ids)

    def _build_output(
        self,
        legacy_output: dict[str, Any],
        accepted: list[RelationCandidate],
        rejected: list[RelationCandidate],
        context: dict[str, Any],
        artifact_id: str,
        unit: WorkUnit,
    ) -> dict[str, Any]:
        if self.worker == "survey":
            return dict(legacy_output)
        if self.worker == "merge":
            return _merge_output(
                context, unit,
                versioned_repository=self.dependencies.versioned_evidence_repository,
            )
        relations = [_candidate_output(item, artifact_id) for item in accepted]
        base: dict[str, Any] = {
            "relations": relations,
            "total_relations": len(relations),
            "rejected_candidates": [_candidate_output(item, artifact_id) for item in rejected],
            "score_semantics": "verified_evidence_strength_not_final_probability",
        }
        if self.worker == "column":
            analyzed: dict[str, dict[str, Any]] = {}
            for relation in relations:
                table = relation["source_table"]
                entry = analyzed.setdefault(table, {"table": table, "potential_relations": [], "relation_count": 0})
                entry["potential_relations"].append(relation)
                entry["relation_count"] += 1
            base.update({
                "table_count": len((context.get("survey_result") or {}).get("schema_catalog") or []),
                "potential_relations": relations,
                "relation_count": len(relations),
                "analyzed_tables": analyzed,
            })
        elif self.worker == "name":
            base.update({
                "column_name_matches": {"matches": relations, "count": len(relations), "match_count": len(relations)},
                "associative_tables": {"count": 0, "tables": []},
            })
        return base


class Phase4RecoveryStageAdapter:
    """Expose the Phase 3 worker pipeline through the shared Stage contract."""

    def __init__(self, worker: str, dependencies: HybridStageDependencies):
        self.worker = worker
        self.stage_id = f"recovery.{worker}"
        self.input_schema_version = "3.0"
        self.output_schema_version = "3.0"
        self.capabilities = StageCapabilities(
            retry_safe=True,
            cancellable=True,
            interruptible=worker == "merge",
            parallel_safe=worker in {"column", "name", "code", "orm"},
            max_concurrency=8 if worker in {"column", "name", "code", "orm"} else 1,
        )
        self.stage = HybridRecoveryStage(worker, dependencies)

    async def execute(
        self,
        state: dict[str, Any],
        unit: WorkUnit,
        context: dict[str, Any],
    ) -> StageResult:
        if (state.get("cancellation") or {}).get("requested"):
            return StageResult(
                stage_id=self.stage_id,
                status=RunStatus.CANCELLED,
                state_patch={},
                error=AgentError(
                    code="run_cancelled", category="cancelled",
                    message=str((state.get("cancellation") or {}).get("reason") or "cancelled"),
                    source=self.worker,
                ),
            )
        usage_before = self.stage.dependencies.run_context.budget.snapshot()
        hydrated: dict[str, Any] = {}
        for key, artifact_id in dict(state.get("output_refs") or {}).items():
            content = self.stage.dependencies.ledger.read_artifact(artifact_id)
            if content is None and key == "memory_context" and self.stage.dependencies.memory_service:
                content = self.stage.dependencies.memory_service.get_context_package(artifact_id).model_dump(mode="json")
            if content is not None:
                hydrated[key] = content
        stage_context = {**state, **hydrated, **context}
        if self.worker == "survey" and not stage_context.get("_survey_collector_output"):
            legacy = self.stage.dependencies.legacy_workers.get("survey")
            if legacy is None:
                raise RuntimeError("survey bootstrap requires the registered deterministic collector")
            baseline = legacy.run(stage_context)
            server_info = baseline.get("server_info") or {}
            actual_snapshot = server_info.get("snapshot_id")
            actual_fingerprint = server_info.get("database_fingerprint")
            if not actual_snapshot or not actual_fingerprint:
                raise RuntimeError("survey bootstrap did not produce snapshot identity")
            stage_context["_survey_collector_output"] = baseline
            stage_context["snapshot_id"] = actual_snapshot
            stage_context["database_fingerprint"] = actual_fingerprint
            unit = unit.model_copy(update={
                "snapshot_id": actual_snapshot,
                "database_fingerprint": actual_fingerprint,
            })
        result = await self.stage.execute(unit, stage_context)
        output_artifact = self.stage.dependencies.ledger.write_artifact(
            snapshot_id=unit.snapshot_id,
            subject_refs=unit.subject_refs,
            content=result.output,
            completeness=1.0 if result.status == RunStatus.SUCCESS else 0.7,
            missing_capabilities=result.missing_capabilities,
            tool_call_ids=result.tool_call_ids,
            collector_version=f"stage-output:{self.worker}:3.0",
            idempotency_key=_hash({"unit": unit.idempotency_key, "kind": "stage-output"}),
        )
        requests = [
            item if isinstance(item, EvidenceRequest) else EvidenceRequest.model_validate(item)
            for item in result.output.get("evidence_requests", [])
        ]
        critic = dict(result.output.get("critic_decision") or {})
        output_key = (
            f"{self.worker}_result"
            if unit.requested_by is None else f"{self.worker}_result:{unit.work_unit_id}"
        )
        portable_patch = {
            "output_refs": {output_key: output_artifact.artifact_id},
            "snapshot_id": result.snapshot_id,
            "database_fingerprint": unit.database_fingerprint,
        }
        if self.worker == "merge":
            portable_patch["critic_action"] = critic.get("action", "accept")
            portable_patch["critic_summary"] = critic.get("summary", result.output.get("reasoning_summary", ""))
        return StageResult(
            stage_id=self.stage_id,
            status=result.status,
            state_patch=portable_patch,
            artifact_ids=result.artifact_ids + [output_artifact.artifact_id],
            evidence_ids=result.evidence_ids,
            relation_ids=result.relation_ids,
            evidence_requests=requests,
            usage_delta=_usage_delta(
                usage_before,
                self.stage.dependencies.run_context.budget.snapshot(),
            ),
            retry_classification="safe" if result.status == RunStatus.ERROR else "never",
            idempotency_record={
                "idempotency_key": unit.idempotency_key,
                "output_ref": output_artifact.artifact_id,
            },
            error=result.error,
        )

    def cancel(self, reason: str) -> None:
        self.stage.dependencies.run_context.cancellation.cancel(reason)


def _usage_delta(before: Any, after: Any) -> dict[str, int | float | str]:
    return {
        "model_calls": max(0, after.model_calls - before.model_calls),
        "tool_calls": max(0, after.tool_calls - before.tool_calls),
        "input_tokens": max(0, after.input_tokens - before.input_tokens),
        "output_tokens": max(0, after.output_tokens - before.output_tokens),
        "cost_usd": str(max(0, after.cost_usd - before.cost_usd)),
        "loop_iterations": max(0, after.loop_iterations - before.loop_iterations),
    }


class HybridWorkerRunner:
    """Synchronous compatibility adapter used by manual and LangGraph flows."""

    def __init__(
        self,
        *,
        run_context: RunContext,
        tool_runtime: ToolRuntime,
        model_gateway: ModelGateway | None,
        ledger: EvidenceLedger | None = None,
    ):
        self.dependencies = HybridStageDependencies(
            run_context=run_context,
            tool_runtime=tool_runtime,
            model_gateway=model_gateway,
            ledger=ledger or EvidenceLedger(SQLiteEvidenceRepository(Config.EVIDENCE_DB_PATH)),
        )

    def run(self, worker_id: str, legacy_worker: Any, context: dict[str, Any], mode: str) -> dict[str, Any]:
        mode = normalize_worker_mode(mode)
        if mode == "legacy":
            return legacy_worker.run(context)

        baseline: dict[str, Any] | None = None
        if worker_id == "survey" or mode == "shadow":
            baseline = legacy_worker.run(context)
            if worker_id == "survey":
                context["_survey_collector_output"] = baseline
                server_info = baseline.get("server_info") or {}
                context["snapshot_id"] = server_info.get("snapshot_id")
                context["database_fingerprint"] = server_info.get("database_fingerprint")
        if not context.get("snapshot_id") or not context.get("database_fingerprint"):
            if baseline is not None:
                return _degraded_legacy(baseline, "hybrid_snapshot_identity_missing", mode)
            fallback = legacy_worker.run(context)
            return _degraded_legacy(fallback, "hybrid_snapshot_identity_missing", mode)

        stage_context = dict(context)
        stage_context["_worker_mode"] = mode
        repository = self.dependencies.ledger.repository
        if worker_id == "merge":
            stage_context["_ledger_relations"] = [
                item.model_dump(mode="json") for item in repository.query_relations(snapshot_id=context["snapshot_id"])
            ]
            stage_context["_ledger_evidence"] = [
                item.model_dump(mode="json") for item in repository.query_evidence(snapshot_id=context["snapshot_id"])
            ]
        unit = build_work_unit(worker_id, stage_context)
        result = _run_async(HybridRecoveryStage(worker_id, self.dependencies).execute(unit, stage_context))
        if mode == "shadow":
            assert baseline is not None
            comparison = self.dependencies.ledger.write_artifact(
                snapshot_id=unit.snapshot_id,
                subject_refs=unit.subject_refs,
                content={
                    "kind": "hybrid_shadow_comparison",
                    "worker": worker_id,
                    "legacy": _comparison_projection(baseline),
                    "hybrid": _comparison_projection(result.output),
                    "hybrid_status": result.status.value,
                },
                completeness=1.0,
                missing_capabilities=result.missing_capabilities,
                tool_call_ids=result.tool_call_ids,
                collector_version="shadow-comparison-v1",
                idempotency_key=_hash({"unit": unit.idempotency_key, "kind": "shadow-comparison"}),
            )
            baseline = dict(baseline)
            baseline["shadow_comparison"] = {
                "status": result.status.value,
                "work_unit_id": result.work_unit_id,
                "artifact_ids": result.artifact_ids + [comparison.artifact_id],
                "comparison_artifact_id": comparison.artifact_id,
                "relation_ids": result.relation_ids,
                "missing_capabilities": result.missing_capabilities,
            }
            baseline["worker_mode"] = "shadow"
            return baseline
        if result.status in {RunStatus.BLOCKED, RunStatus.CANCELLED}:
            return {
                "status": result.status.value,
                "error": result.error.message if result.error else result.status.value,
                "error_detail": result.error.model_dump(mode="json") if result.error else None,
                "work_unit_id": result.work_unit_id,
                "artifact_ids": result.artifact_ids,
            }
        if result.status == RunStatus.ERROR:
            fallback = baseline if baseline is not None else legacy_worker.run(context)
            return _degraded_legacy(fallback, result.error.code if result.error else "hybrid_worker_failed", mode)
        return result.output


def build_work_unit(worker_id: str, context: dict[str, Any], *, evidence_round: int = 0) -> WorkUnit:
    subjects = _subject_refs(worker_id, context)
    idempotency_key = _hash({
        "snapshot_id": context["snapshot_id"],
        "worker": worker_id,
        "subjects": subjects,
        "round": evidence_round,
        "prompt_version": "1.0.0",
        "fusion_version": Config.FUSION_MODEL_VERSION,
    })
    return WorkUnit(
        work_unit_id=stable_id("work_unit", context["run_id"], idempotency_key),
        run_id=context["run_id"],
        trace_id=context["trace_id"],
        snapshot_id=context["snapshot_id"],
        database_fingerprint=context["database_fingerprint"],
        worker=worker_id,
        subject_refs=subjects,
        evidence_round=evidence_round,
        idempotency_key=idempotency_key,
        budget_slice=BudgetSlice(
            max_model_calls=Config.WORK_UNIT_MAX_MODEL_CALLS,
            timeout_seconds=Config.WORK_UNIT_TIMEOUT_SECONDS,
        ),
    )


def normalize_worker_mode(value: str) -> WorkerMode:
    normalized = str(value or "legacy").strip().lower()
    if normalized not in {"legacy", "hybrid", "shadow"}:
        raise ValueError(f"unknown worker implementation mode: {value!r}")
    return normalized


def configured_worker_mode(worker_id: str) -> WorkerMode:
    return normalize_worker_mode(getattr(Config, f"WORKER_IMPL_{worker_id.upper()}", "legacy"))


def _merge_output(
    context: dict[str, Any], unit: WorkUnit, *, versioned_repository: Any | None = None,
) -> dict[str, Any]:
    raw_candidates = [RelationCandidate.model_validate(item) for item in context.get("_ledger_relations", [])]
    evidence_by_id = {
        item["evidence_id"]: item for item in context.get("_ledger_evidence", [])
    }
    combined: dict[str, RelationCandidate] = {}
    for candidate in raw_candidates:
        previous = combined.get(candidate.relation_id)
        if previous is None:
            combined[candidate.relation_id] = candidate
            continue
        cardinalities = {value for value in (previous.cardinality, candidate.cardinality) if value != "unknown"}
        resolved_cardinality = previous.cardinality
        cardinality_flags: list[str] = []
        if previous.cardinality == "unknown" and candidate.cardinality != "unknown":
            resolved_cardinality = candidate.cardinality
        elif len(cardinalities) > 1:
            resolved_cardinality = "unknown"
            cardinality_flags.append("cardinality_conflict:" + ":".join(sorted(cardinalities)))
        combined[candidate.relation_id] = previous.model_copy(update={
            "evidence_ids": list(dict.fromkeys(previous.evidence_ids + candidate.evidence_ids)),
            "validation_flags": list(dict.fromkeys(previous.validation_flags + candidate.validation_flags + cardinality_flags)),
            "cardinality": resolved_cardinality,
        })
    by_source: dict[tuple[str, tuple[str, ...]], list[RelationCandidate]] = {}
    for candidate in combined.values():
        key = (candidate.source_table.casefold(), tuple(column.casefold() for column in candidate.source_columns))
        by_source.setdefault(key, []).append(candidate)
    for candidates in by_source.values():
        targets = {
            (item.target_table.casefold(), tuple(column.casefold() for column in item.target_columns))
            for item in candidates
        }
        if len(targets) <= 1:
            continue
        for candidate in candidates:
            conflicts = [
                f"conflicting_target:{other.relation_id}"
                for other in candidates
                if other.relation_id != candidate.relation_id
            ]
            combined[candidate.relation_id] = candidate.model_copy(update={
                "validation_flags": list(dict.fromkeys(candidate.validation_flags + conflicts)),
            })
    engine = EvidenceFusionEngine(
        model_version=Config.FUSION_MODEL_VERSION,
        weight_version=Config.FUSION_WEIGHT_VERSION,
    )
    bands: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}
    details: dict[str, Any] = {}
    source_counts: dict[str, int] = {}
    for candidate in combined.values():
        scoped = [
            evidence_by_id[evidence_id]
            for evidence_id in candidate.evidence_ids
            if evidence_id in evidence_by_id
        ]
        from backend.agent.runtime.hybrid_contracts import EvidenceItem

        legacy_evidence = [EvidenceItem.model_validate(item) for item in scoped]
        if Config.FUSION_V2_ENABLED:
            fused = _fuse_versioned(
                candidate, legacy_evidence, context=context, unit=unit,
                repository=versioned_repository,
            )
        else:
            fused = engine.fuse(candidate, legacy_evidence)
        relation = _candidate_output(candidate, None)
        relation.update({
            "fused_confidence": fused.probability,
            "confidence_band": fused.band,
            "confidence_breakdown": fused.breakdown.model_dump(mode="json"),
            "evidence_chain": scoped,
        })
        bands[fused.band].append(relation)
        details[candidate.relation_id] = fused.breakdown.model_dump(mode="json")
        for item in scoped:
            source = str(item.get("source_type") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
    total_sources = sum(source_counts.values()) or 1
    output = {
        "high_confidence_relations": bands["high"],
        "medium_confidence_relations": bands["medium"],
        "low_confidence_relations": bands["low"],
        "total_relations": sum(len(items) for items in bands.values()),
        "evidence_detail": details,
        "source_contributions": {key: round(value / total_sources * 100, 2) for key, value in source_counts.items()},
        "fusion_model_version": Config.FUSION_MODEL_VERSION,
        "fusion_weight_version": Config.FUSION_WEIGHT_VERSION,
    }
    if Config.CRITIC_ENABLED:
        from backend.agent.critics import RecoveryCritic

        output["critic_decision"] = RecoveryCritic().review(output, unit).model_dump(mode="json")
    return output


def _fuse_versioned(
    candidate: RelationCandidate,
    evidence: list[Any],
    *,
    context: dict[str, Any],
    unit: WorkUnit,
    repository: Any | None,
) -> Any:
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from backend.evidence.bridge import namespace_from_context, relation_template, upgrade_evidence
    from backend.evidence.fusion import VersionedFusionEngine
    from backend.evidence.policy_loader import load_fusion_policy

    namespace = namespace_from_context(context, unit.snapshot_id, unit.run_id)
    upgraded = [
        upgrade_evidence(item, namespace=namespace, run_id=unit.run_id)
        for item in evidence
    ]
    policy = load_fusion_policy(
        Config.FUSION_POLICY_PATH,
        calibration_enabled=Config.CALIBRATION_ENABLED,
        feature_schema_path=Config.FUSION_FEATURE_SCHEMA_PATH,
    )
    feature_hash = policy.feature_schema_hash
    existing = None
    if repository is not None:
        try:
            existing = repository.get_relation(candidate.relation_id)
        except KeyError:
            existing = None
    relation_version = 1 if existing is None else existing.version + 1
    fusion = VersionedFusionEngine(
        fusion_version=policy.fusion_version,
        feature_schema_hash=feature_hash,
        threshold_policy=policy.threshold_policy,
        calibrator=policy.calibrator,
        coefficients=policy.coefficients,
        prior_probability=policy.prior_probability,
    ).fuse(
        relation_template(
            candidate, namespace=namespace, run_id=unit.run_id,
            feature_schema_hash=feature_hash,
        ),
        upgraded,
        version=relation_version,
        run_id=unit.run_id,
        now=datetime.now(timezone.utc),
    )
    if fusion.relation.confidence_band == "high":
        fusion = fusion.model_copy(update={
            "relation": fusion.relation.model_copy(update={"status": "accepted"}),
        })
    if repository is not None:
        for item in upgraded:
            repository.append_evidence(item)
        if existing is not None and existing.created_by_run_id == unit.run_id:
            fusion = fusion.model_copy(update={"relation": existing})
        else:
            repository.append_relation_version(fusion.relation)
    breakdown = {
        "model_version": fusion.relation.fusion_version,
        "weight_version": fusion.relation.feature_schema_hash,
        "prior_probability": policy.prior_probability,
        "prior_log_odds": 0.0,
        "contributions": [item.model_dump(mode="json") for item in fusion.relation.contribution_breakdown],
        "hard_constraint_adjustment": sum(
            item.log_odds_delta for item in fusion.relation.contribution_breakdown
            if item.feature == "hard_constraint_violation"
        ),
        "conflict_adjustment": sum(
            item.log_odds_delta for item in fusion.relation.contribution_breakdown
            if item.feature == "conflict_root_count"
        ),
        "final_log_odds": fusion.relation.raw_score,
        "probability": fusion.relation.calibrated_probability,
        "band": fusion.relation.confidence_band,
        "calibration_version": fusion.relation.calibration_version,
        "threshold_policy_version": fusion.relation.threshold_policy_version,
        "independent_root_fact_ids": fusion.independent_root_fact_ids,
        "excluded_evidence_ids": fusion.excluded_evidence_ids,
    }
    return SimpleNamespace(
        probability=fusion.relation.calibrated_probability,
        band=fusion.relation.confidence_band,
        breakdown=SimpleNamespace(model_dump=lambda **_: breakdown),
    )


def _candidate_output(candidate: RelationCandidate, artifact_id: str | None) -> dict[str, Any]:
    return {
        "relation_id": candidate.relation_id,
        "claim_key": candidate.claim_key,
        "source_table": candidate.source_table,
        "source_columns": candidate.source_columns,
        "fk_column": candidate.source_columns[0],
        "target_table": candidate.target_table,
        "target_columns": candidate.target_columns,
        "pk_column": candidate.target_columns[0],
        "relation_type": candidate.cardinality,
        "evidence_ids": candidate.evidence_ids,
        "validation_flags": candidate.validation_flags,
        "artifact_id": artifact_id,
    }


def _subject_refs(worker_id: str, context: dict[str, Any]) -> list[str]:
    survey = context.get("survey_result") or context.get("_survey_collector_output") or {}
    if worker_id in {"survey", "column", "name"}:
        return sorted(str(item.get("name")) for item in survey.get("schema_catalog", []) if item.get("name"))
    if worker_id == "code":
        return sorted(
            f"{kind}:{item.get('name')}"
            for kind, key in (("view", "views"), ("procedure", "stored_procedures"), ("trigger", "triggers"))
            for item in survey.get(key, {}).get("details", [])
        )
    if worker_id == "orm":
        return sorted(str(item.get("path")) for item in survey.get("orm_files", {}).get("details", []) if item.get("path"))
    return sorted(str(item.get("relation_id")) for item in context.get("_ledger_relations", []) if item.get("relation_id"))


def _degraded_legacy(output: dict[str, Any], reason: str, mode: str) -> dict[str, Any]:
    adapted = dict(output)
    adapted["status"] = "degraded"
    adapted["worker_mode"] = mode
    adapted["uncertainties"] = list(dict.fromkeys(list(adapted.get("uncertainties") or []) + [reason]))
    adapted["missing_capabilities"] = list(dict.fromkeys(list(adapted.get("missing_capabilities") or []) + [reason]))
    return adapted


def _comparison_projection(output: dict[str, Any]) -> dict[str, Any]:
    relations = list(output.get("relations") or output.get("potential_relations") or [])
    if not relations and output.get("column_name_matches"):
        relations = list(output["column_name_matches"].get("matches") or [])
    if not relations:
        relations = [
            item
            for key in ("high_confidence_relations", "medium_confidence_relations", "low_confidence_relations")
            for item in output.get(key, [])
        ]
    signatures = sorted({
        (
            str(item.get("source_table") or ""),
            str(item.get("fk_column") or (item.get("source_columns") or [""])[0]),
            str(item.get("target_table") or ""),
            str(item.get("pk_column") or (item.get("target_columns") or [""])[0]),
        )
        for item in relations
    })
    return {
        "status": output.get("status"),
        "relation_count": len(signatures),
        "relation_signatures": signatures,
        "missing_capabilities": list(output.get("missing_capabilities") or []),
    }


def _failure_result(
    unit: WorkUnit,
    context: dict[str, Any],
    status: RunStatus,
    error: AgentError,
    artifact_ids: list[str],
) -> HybridWorkerResult:
    return HybridWorkerResult(
        status=status,
        worker=unit.worker,
        mode=context.get("_worker_mode", "hybrid"),
        work_unit_id=unit.work_unit_id,
        snapshot_id=unit.snapshot_id,
        artifact_ids=artifact_ids,
        error=error,
        idempotency_key=unit.idempotency_key,
    )


async def _emit(
    context: RunContext,
    event_type: str,
    status: str,
    span_id: str,
    unit: WorkUnit,
    payload: dict[str, Any] | None = None,
) -> None:
    await context.tracer.emit(
        context=context,
        event_type=event_type,
        status=status,
        span_id=span_id,
        parent_span_id=context.parent_span_id,
        payload={"worker": unit.worker, "work_unit_id": unit.work_unit_id, "snapshot_id": unit.snapshot_id, **(payload or {})},
    )


def _run_async(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    outcome: dict[str, Any] = {}

    def runner() -> None:
        try:
            outcome["result"] = asyncio.run(awaitable)
        except BaseException as exc:
            outcome["error"] = exc

    thread = Thread(target=runner, name="hybrid-recovery-stage", daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
