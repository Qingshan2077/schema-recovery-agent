"""Portable memory lifecycle stages shared by manual and LangGraph engines."""

from __future__ import annotations

from typing import Any

from backend.agent.memory.contracts import MemoryNamespace, MemoryRetrievalQuery
from backend.agent.memory.service import MemoryService
from backend.agent.runtime.hybrid_contracts import StageResult, WorkUnit
from backend.core.status import AgentError, RunStatus
from backend.evidence.ledger import EvidenceLedger
from backend.workflow.contracts import StageCapabilities


_STAGE_IDS = {
    "memory_retrieve": "memory.retrieve",
    "memory_verify": "memory.verify",
    "memory_consolidate": "memory.consolidate",
}


class MemoryRecoveryStage:
    input_schema_version = "5.0"
    output_schema_version = "5.0"
    capabilities = StageCapabilities(
        retry_safe=True, cancellable=True, interruptible=False,
        parallel_safe=False, max_concurrency=1,
    )

    def __init__(
        self, worker: str, service: MemoryService, ledger: EvidenceLedger,
        *, read_enabled: bool = True, write_enabled: bool = True,
        versioned_repository: Any | None = None,
    ):
        if worker not in _STAGE_IDS:
            raise ValueError(f"unknown memory worker: {worker}")
        self.worker = worker
        self.stage_id = _STAGE_IDS[worker]
        self.service = service
        self.ledger = ledger
        self.read_enabled = read_enabled
        self.write_enabled = write_enabled
        self.versioned_repository = versioned_repository
        self._cancelled = False

    async def execute(
        self,
        state: dict[str, Any],
        unit: WorkUnit,
        context: dict[str, Any],
    ) -> StageResult:
        if self._cancelled or (state.get("cancellation") or {}).get("requested"):
            return StageResult(
                stage_id=self.stage_id, status=RunStatus.CANCELLED, state_patch={},
                error=AgentError(
                    code="run_cancelled", category="cancelled", message="memory stage cancelled",
                    source=self.worker,
                ),
            )
        namespace = MemoryNamespace(
            tenant_id=str(state.get("tenant_id") or "default"),
            project_id=str(state["project_id"]),
            connection_id=str(state["connection_id"]),
            database_name=str(state.get("database_name") or state["connection_id"]),
            schema_name=str(state.get("schema_name") or "default"),
            snapshot_id=unit.snapshot_id,
            thread_id=str(state["thread_id"]),
            run_id=unit.run_id,
        )
        if self.worker == "memory_retrieve":
            if not self.read_enabled:
                return _disabled(self.stage_id, "memory_v2_read_disabled")
            self.service.sync_thread(namespace, state, status="active")
            package = self.service.retrieve(MemoryRetrievalQuery(
                namespace=namespace,
                task_type="schema_recovery",
                object_ids=unit.subject_refs,
                query_text=" ".join(unit.subject_refs),
                current_run_id=unit.run_id,
            ))
            return StageResult(
                stage_id=self.stage_id,
                status=RunStatus.DEGRADED if package.degraded else RunStatus.SUCCESS,
                state_patch={"output_refs": {"memory_context": package.package_id}},
                domain_events=[{
                    "type": "memory.retrieved", "package_id": package.package_id,
                    "selected_count": package.selected_count,
                    "degraded": package.degraded,
                }],
                idempotency_record={"idempotency_key": unit.idempotency_key},
            )
        package_id = dict(state.get("output_refs") or {}).get("memory_context")
        if self.worker == "memory_verify":
            if not self.read_enabled:
                return _disabled(self.stage_id, "memory_v2_read_disabled")
            if not package_id:
                return StageResult(
                    stage_id=self.stage_id, status=RunStatus.DEGRADED,
                    state_patch={}, domain_events=[{"type": "memory.skipped", "reason": "context_missing"}],
                )
            catalog = _catalog_from_state(state, self.ledger)
            evidence = [
                item.model_dump(mode="json")
                for item in self.ledger.repository.query_evidence(snapshot_id=unit.snapshot_id)
            ]
            verified = self.service.verify(
                package_id, catalog=catalog, current_evidence=evidence,
            )
            return StageResult(
                stage_id=self.stage_id, status=RunStatus.SUCCESS,
                state_patch={"output_refs": {"memory_verification": package_id}},
                evidence_ids=sorted({evidence_id for row in verified for evidence_id in row.evidence_ids}),
                domain_events=[{
                    "type": "memory.verified", "package_id": package_id,
                    "outcomes": {outcome: sum(row.outcome == outcome for row in verified)
                                 for outcome in ("verified", "rejected", "stale", "insufficient")},
                }],
            )
        if not self.write_enabled:
            return _disabled(self.stage_id, "memory_v2_write_disabled")
        if self.versioned_repository is None:
            return _disabled(self.stage_id, "versioned_evidence_repository_unavailable")
        relations = self.versioned_repository.list_relations(
            tenant_key=namespace.canonical_tenant_id,
            project_key=namespace.canonical_project_id,
            connection_key=namespace.canonical_connection_id or "",
            database_key=namespace.canonical_database_name or "",
            schema_key=namespace.canonical_schema_name or "",
            status="accepted",
            limit=1000,
        )
        written = []
        for relation in relations:
            evidence = self.versioned_repository.query_evidence(relation_id=relation.relation_id)
            memory = self.service.consolidate_relation(
                relation,
                root_fact_ids=[item.root_fact_id for item in evidence if item.tombstoned_at is None],
            )
            if memory is not None:
                written.append(memory.memory_id)
        self.service.sync_thread(namespace, state, status="completed")
        return StageResult(
            stage_id=self.stage_id, status=RunStatus.SUCCESS,
            state_patch={"output_refs": {"memory_consolidation": package_id or "none"}},
            domain_events=[{
                "type": "memory.consolidated", "package_id": package_id,
                "written_count": len(written), "memory_ids": written,
            }],
        )

    def cancel(self, reason: str) -> None:
        self._cancelled = True


def stage_id_for_worker(worker: str) -> str:
    return _STAGE_IDS.get(worker, f"recovery.{worker}")


def _disabled(stage_id: str, reason: str) -> StageResult:
    return StageResult(
        stage_id=stage_id, status=RunStatus.SUCCESS, state_patch={},
        domain_events=[{"type": "memory.skipped", "reason": reason}],
    )


def _catalog_from_state(state: dict[str, Any], ledger: EvidenceLedger) -> list[dict[str, Any]]:
    survey_ref = dict(state.get("output_refs") or {}).get("survey_result")
    if not survey_ref:
        return []
    payload = ledger.read_artifact(survey_ref) or {}
    return list(payload.get("schema_catalog") or payload.get("tables") or [])
