from datetime import datetime, timezone

import pytest

from backend.agent.dba.ast_validator import DDLValidationError, validate_and_normalize
from backend.agent.dba.contracts import ActorContext
from backend.agent.dba.operation_store import OperationConflict, OperationStore
from backend.agent.dba.planner import DDLPlanner
from backend.agent.dba.service import DBAService
from backend.observability.tracing import TraceRecorder


def actor(actor_id="requester", role="analyst"):
    return ActorContext(actor_id=actor_id, roles=[role], tenant_id="tenant", project_id="project", environment="dev", capabilities=["dba_plan"])


def test_ast_blocks_multiple_statements():
    with pytest.raises(DDLValidationError):
        validate_and_normalize(["CREATE TABLE a(id INT); DROP TABLE b"], dialect="mysql")


@pytest.mark.asyncio
async def test_client_hash_tamper_and_self_approval_are_rejected(tmp_path):
    service = DBAService(store=OperationStore(tmp_path / "dba.db"), planner=DDLPlanner(), traces=TraceRecorder(tmp_path / "trace.db"))
    operation = await service.create_operation("CREATE TABLE audit_log(id BIGINT)", actor=actor(), connection_id="dev-db", thread_id="thr_test", run_id="run_test", dialect="mysql", snapshot_id="snp_test", snapshot_hash="sha256:snapshot")
    with pytest.raises(PermissionError):
        service.resolve(operation.operation_id, expected_version=1, decision="approve", reason="self", acknowledged_hash=operation.normalized_sql_hash, request_id="one", actor=actor())
    with pytest.raises(OperationConflict):
        service.resolve(operation.operation_id, expected_version=1, decision="approve", reason="review", acknowledged_hash="sha256:tampered", request_id="two", actor=actor("reviewer", "dba_approver"))
