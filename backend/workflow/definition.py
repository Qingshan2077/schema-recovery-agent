"""Versioned schema recovery workflow consumed by both engines."""

from backend.workflow.contracts import WorkflowDefinition, WorkflowNode


def schema_recovery_v2() -> WorkflowDefinition:
    reducers = {
        "pending_work_units": "stable_id_set",
        "completed_stage_keys": "stable_id_set",
        "artifact_ids": "stable_id_set",
        "evidence_ids": "stable_id_set",
        "relation_ids": "stable_id_set",
        "errors": "append_only",
        "budget": "usage_sum",
        "attempts": "keyed_max",
        "output_refs": "keyed_single_writer",
    }
    return WorkflowDefinition(
        workflow_id="schema-recovery",
        version="schema-recovery-v2",
        state_schema_version="2",
        entry_node="load_context",
        reducers=reducers,
        nodes=[
            WorkflowNode(node_id="load_context", writes=[]),
            WorkflowNode(node_id="survey", stage_id="recovery.survey", depends_on=["load_context"], writes=["artifact_ids", "output_refs"]),
            WorkflowNode(node_id="plan_work", depends_on=["survey"], writes=["pending_work_units"]),
            WorkflowNode(node_id="fan_out", depends_on=["plan_work"], fanout_source="pending_work_units", writes=["pending_work_units"]),
            WorkflowNode(node_id="column", stage_id="recovery.column", depends_on=["fan_out"], writes=["artifact_ids", "evidence_ids", "relation_ids", "errors"]),
            WorkflowNode(node_id="name", stage_id="recovery.name", depends_on=["fan_out"], writes=["artifact_ids", "evidence_ids", "relation_ids", "errors"]),
            WorkflowNode(node_id="code", stage_id="recovery.code", depends_on=["fan_out"], writes=["artifact_ids", "evidence_ids", "relation_ids", "errors"]),
            WorkflowNode(node_id="orm", stage_id="recovery.orm", depends_on=["fan_out"], required=False, writes=["artifact_ids", "evidence_ids", "relation_ids", "errors"]),
            WorkflowNode(node_id="validate_join", depends_on=["column", "name", "code", "orm"], join_policy="required", writes=["errors"]),
            WorkflowNode(node_id="merge", stage_id="recovery.merge", depends_on=["validate_join"], writes=["artifact_ids", "relation_ids", "output_refs"]),
            WorkflowNode(node_id="critic", depends_on=["merge"], route_key="critic_action", loop_limit=2, writes=["pending_work_units", "errors"]),
            WorkflowNode(node_id="persist_result", depends_on=["critic"], writes=["output_refs"]),
            WorkflowNode(node_id="finalize", depends_on=["persist_result"], writes=[]),
        ],
    )
