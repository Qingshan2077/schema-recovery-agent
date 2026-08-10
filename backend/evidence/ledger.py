"""High-level append-only ledger with stable IDs and snapshot isolation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.agent.runtime.hybrid_contracts import CollectorArtifact, EvidenceItem, RelationCandidate
from backend.core.identity import stable_id
from backend.evidence.repository import EvidenceRepository


class EvidenceLedger:
    def __init__(self, repository: EvidenceRepository):
        self.repository = repository

    def write_artifact(
        self,
        *,
        snapshot_id: str,
        subject_refs: list[str],
        content: dict[str, Any],
        completeness: float,
        missing_capabilities: list[str],
        tool_call_ids: list[str],
        collector_version: str,
        idempotency_key: str,
    ) -> CollectorArtifact:
        content_hash = _hash(content)
        artifact_id = stable_id("artifact", snapshot_id, idempotency_key, content_hash)
        self.repository.append_artifact(
            artifact_id=artifact_id,
            snapshot_id=snapshot_id,
            content_hash=content_hash,
            content=content,
            metadata={
                "subject_refs": subject_refs,
                "completeness": completeness,
                "missing_capabilities": missing_capabilities,
                "tool_call_ids": tool_call_ids,
                "collector_version": collector_version,
            },
        )
        return CollectorArtifact(
            artifact_id=artifact_id,
            snapshot_id=snapshot_id,
            subject_refs=subject_refs,
            content_ref=f"evidence://artifact/{artifact_id}",
            content_hash=content_hash,
            completeness=completeness,
            missing_capabilities=missing_capabilities,
            tool_call_ids=tool_call_ids,
            collector_version=collector_version,
        )

    def append_evidence(self, item: EvidenceItem) -> bool:
        return self.repository.append_evidence(item)

    def append_relation(self, candidate: RelationCandidate, *, snapshot_id: str, producer: str) -> bool:
        if any(not evidence_id.startswith("evd_") for evidence_id in candidate.evidence_ids):
            raise ValueError("relation candidate contains an invalid evidence ID")
        return self.repository.append_relation(candidate, snapshot_id=snapshot_id, producer=producer)

    def evidence_for_claim(self, *, snapshot_id: str, claim_key: str) -> list[EvidenceItem]:
        return self.repository.query_evidence(snapshot_id=snapshot_id, claim_key=claim_key)

    def create_revision(self, *, snapshot_id: str, reason: str) -> str:
        return self.repository.create_revision(snapshot_id=snapshot_id, reason=reason)

    def read_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return self.repository.get_artifact(artifact_id)


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
