"""Persistent LangGraph adapter compiled from the portable workflow definition."""

from __future__ import annotations

import operator
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Annotated, Any, TypedDict

from backend.agent.runtime.hybrid_contracts import StageResult, WorkUnit
from backend.engines.manual import ManualEngine
from backend.persistence.checkpoints import LangGraphPersistenceFactory, checkpoint_config
from backend.core.identity import stable_id
from backend.workflow.contracts import InterruptRef, RecoveryStateV2, RunControl, StatePatch, WorkflowDefinition
from backend.workflow.reducer import merge_patches


class GraphRuntimeState(TypedDict):
    portable_state: dict[str, Any]
    fanout_units: list[dict[str, Any]]
    fanout_results: Annotated[list[dict[str, Any]], operator.add]
    merge_result: dict[str, Any] | None
    route: str
    resume_decision: dict[str, Any] | None


class LangGraphEngine:
    name = "langgraph"

    def __init__(
        self,
        *,
        definition: WorkflowDefinition,
        portable_scheduler: ManualEngine,
        persistence: LangGraphPersistenceFactory,
        recursion_limit: int = 32,
        max_concurrency: int = 4,
    ):
        self.definition = definition
        self.portable = portable_scheduler
        self.persistence = persistence
        self.recursion_limit = recursion_limit
        self.max_concurrency = max_concurrency
        self._compiled = None

    def capability_check(self) -> dict[str, Any]:
        capabilities = self.persistence.capabilities()
        return capabilities.__dict__

    def compile(self):
        if self._compiled is not None:
            return self._compiled
        from langgraph.graph import END, START, StateGraph

        checkpointer, store = self.persistence.create()
        graph = StateGraph(GraphRuntimeState)
        graph.add_node("survey", self._survey_node)
        graph.add_node("plan_work", self._plan_node)
        graph.add_node("execute_unit", self._execute_unit_node)
        graph.add_node("validate_join", self._join_node)
        graph.add_node("merge", self._merge_node)
        graph.add_node("critic", self._critic_node)
        graph.add_node("human_interrupt", self._interrupt_node)
        graph.add_node("finalize", self._finalize_node)
        graph.add_edge(START, "survey")
        graph.add_conditional_edges(
            "survey", self._continue_route,
            {"continue": "plan_work", "finalize": "finalize"},
        )
        graph.add_conditional_edges("plan_work", self._fanout_route, ["execute_unit"])
        graph.add_edge("execute_unit", "validate_join")
        graph.add_conditional_edges(
            "validate_join", self._continue_route,
            {"continue": "merge", "finalize": "finalize"},
        )
        graph.add_edge("merge", "critic")
        graph.add_conditional_edges(
            "critic", self._critic_route,
            {"fanout": "plan_work", "interrupt": "human_interrupt", "finalize": "finalize"},
        )
        graph.add_edge("human_interrupt", "finalize")
        graph.add_edge("finalize", END)
        self._compiled = graph.compile(checkpointer=checkpointer, store=store)
        return self._compiled

    async def run(self, state: RecoveryStateV2, *, resume_value: dict[str, Any] | None = None) -> RecoveryStateV2:
        if state.active_engine != "langgraph":
            raise ValueError("LangGraphEngine may only execute a state assigned to langgraph")
        graph = self.compile()
        config = checkpoint_config(
            run_id=state.run_id, thread_id=state.thread_id, project_id=state.project_id,
            workflow_version=state.workflow_version, recursion_limit=self.recursion_limit,
            max_concurrency=self.max_concurrency,
        )
        if resume_value is not None:
            from langgraph.types import Command

            final = await graph.ainvoke(Command(resume=resume_value), config=config)
        else:
            initial: GraphRuntimeState = {
                "portable_state": state.model_dump(mode="json"),
                "fanout_units": [], "fanout_results": [], "merge_result": None,
                "route": "survey", "resume_decision": None,
            }
            final = await graph.ainvoke(initial, config=config)
        return RecoveryStateV2.model_validate(final["portable_state"])

    async def _survey_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        if state.status == "queued":
            state = self.portable._commit(state, StatePatch(status="running", phase="load_context", expected_version=state.version))
            state = self.portable._event(state, "run.started", node_id="load_context")
        if state.snapshot_id:
            return {"portable_state": state.model_dump(mode="json")}
        unit = self.portable._work_unit(state, "survey", evidence_round=0)
        state, _ = await self.portable._run_one_and_apply(state, unit, phase="survey", execution_engine="langgraph")
        return {"portable_state": state.model_dump(mode="json")}

    def _plan_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        if state.evidence_round > 0 and graph_state.get("fanout_units"):
            units = [WorkUnit.model_validate(item) for item in graph_state["fanout_units"]]
        else:
            units = [self.portable._work_unit(state, worker, evidence_round=state.evidence_round) for worker in ("column", "name", "code", "orm")]
        reason = "critic_evidence" if state.evidence_round > 0 else "initial_fanout"
        if not state.work_plan_ref or state.evidence_round > 0:
            state = self.portable._persist_work_plan(state, units, reason=reason)
        existing = {item.work_unit_id for item in state.pending_work_units}
        additions = [item for item in units if item.work_unit_id not in existing]
        if additions:
            state = self.portable._commit(state, StatePatch(
                phase="plan_work", pending_work_units_add=additions,
                expected_version=state.version,
            ))
        state = self.portable._event(
            state, "fanout.created", node_id="plan_work",
            payload={"work_unit_ids": [item.work_unit_id for item in units]},
        )
        return {
            "portable_state": state.model_dump(mode="json"),
            "fanout_units": [item.model_dump(mode="json") for item in units],
            "route": "fanout",
        }

    def _fanout_route(self, graph_state: GraphRuntimeState):
        from langgraph.types import Send

        return [Send("execute_unit", {**graph_state, "fanout_units": [unit]}) for unit in graph_state["fanout_units"]]

    async def _execute_unit_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        unit = WorkUnit.model_validate(graph_state["fanout_units"][0])
        result = await self.portable._execute_stage(state, unit, execution_engine="langgraph")
        return {"fanout_results": [{"unit": unit.model_dump(mode="json"), "result": result.model_dump(mode="json")} ]}

    def _join_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        patches = []
        for raw in graph_state["fanout_results"]:
            unit = WorkUnit.model_validate(raw["unit"])
            if any(f":{unit.work_unit_id}:" in key for key in state.completed_stage_keys):
                continue
            result = StageResult.model_validate(raw["result"])
            patches.append(self.portable._patch_for_result(state, unit, result, "validate_join"))
        if patches:
            state = self.portable._commit(state, merge_patches(patches).model_copy(update={"expected_version": state.version}))
            state = self.portable._checkpoint(state, reason="langgraph:validate_join")
        state = self.portable._event(state, "join.completed", node_id="validate_join")
        return {"portable_state": state.model_dump(mode="json")}

    async def _merge_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        unit = self.portable._work_unit(state, "merge", evidence_round=state.evidence_round)
        state, result = await self.portable._run_one_and_apply(state, unit, phase="merge", execution_engine="langgraph")
        return {"portable_state": state.model_dump(mode="json"), "merge_result": result.model_dump(mode="json")}

    def _critic_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        result = StageResult.model_validate(graph_state["merge_result"])
        raw_action = result.state_patch.get("critic_action", "accept")
        route = "finalize"
        if raw_action == "needs_review":
            route = "interrupt"
        elif result.evidence_requests and state.evidence_round < self.portable.max_evidence_rounds:
            parent = self.portable._work_unit(state, "merge", evidence_round=state.evidence_round)
            child_units = []
            for request in result.evidence_requests:
                allowed, _ = self.portable.evidence_policy.authorize(request, parent)
                if allowed:
                    child_units.append(self.portable.evidence_policy.to_work_unit(request, parent))
            state = self.portable._commit(state, StatePatch(evidence_round=state.evidence_round + 1, expected_version=state.version))
            route = "fanout" if child_units else "finalize"
            return {
                "portable_state": state.model_dump(mode="json"), "route": route,
                "fanout_units": [item.model_dump(mode="json") for item in child_units],
            }
        return {"portable_state": state.model_dump(mode="json"), "route": route}

    @staticmethod
    def _critic_route(graph_state: GraphRuntimeState) -> str:
        return graph_state["route"]

    @staticmethod
    def _continue_route(graph_state: GraphRuntimeState) -> str:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        return "finalize" if state.status in {"failed", "blocked", "canceled"} else "continue"

    def _interrupt_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        from langgraph.types import interrupt

        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        safe_payload = {
            "run_id": state.run_id,
            "type": "relation_review",
            "safe_summary": (graph_state.get("merge_result") or {}).get("state_patch", {}).get("critic_summary", "Review ambiguous relations"),
            "artifact_ids": state.artifact_ids,
            "evidence_ids": state.evidence_ids,
        }
        payload_hash = hashlib.sha256(json.dumps(safe_payload, sort_keys=True).encode("utf-8")).hexdigest()
        interrupt_id = stable_id("interrupt", state.run_id, state.evidence_round, payload_hash)
        interrupt_ref = InterruptRef(
            interrupt_id=interrupt_id, type="relation_review", requested_by_stage="critic",
            safe_summary=safe_payload["safe_summary"], option_schema={"type": "string", "enum": ["accept", "reject"]},
            artifact_ids=state.artifact_ids, evidence_ids=state.evidence_ids, payload_hash=payload_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24), required_role="schema_reviewer",
        )
        control = RunControl(
            run_id=state.run_id, control_type="interrupt", request_id=interrupt_ref.interrupt_id,
            payload_hash=payload_hash, payload=safe_payload, created_at=datetime.now(timezone.utc),
        )
        persisted = self.portable.runs.get(state.run_id)
        if persisted.pending_interrupt is None:
            self.portable.runs.append_control(control)
            state = self.portable._commit(persisted, StatePatch(
                status="waiting_approval", pending_interrupt=interrupt_ref, phase="human_interrupt",
                expected_version=persisted.version,
            ))
            state = self.portable._event(state, "approval.required", node_id="human_interrupt", payload={"interrupt_id": interrupt_ref.interrupt_id})
            state = self.portable._event(state, "run.paused", node_id="human_interrupt")
        else:
            state = persisted
        decision = interrupt({**safe_payload, "interrupt_id": interrupt_ref.interrupt_id, "payload_hash": payload_hash})
        self.portable.runs.resolve_control(state.run_id, interrupt_ref.interrupt_id, status="resolved")
        decision_artifact = stable_id("artifact", state.run_id, interrupt_ref.interrupt_id, "human-decision")
        self.portable.runs.put_artifact(
            decision_artifact,
            {"interrupt_id": interrupt_ref.interrupt_id, "decision": decision, "payload_hash": payload_hash},
            kind="human_control",
        )
        state = self.portable._commit(state, StatePatch(
            status="running", clear_interrupt=True, artifact_ids_add=[decision_artifact],
            output_refs_merge={f"approval:{interrupt_ref.interrupt_id}": decision_artifact},
            phase="human_resolved", expected_version=state.version,
        ))
        state = self.portable._event(state, "approval.resolved", node_id="human_interrupt", payload={"interrupt_id": interrupt_ref.interrupt_id})
        state = self.portable._event(state, "run.resumed", node_id="human_interrupt")
        return {"route": "finalize", "portable_state": state.model_dump(mode="json"), "resume_decision": decision}

    def _finalize_node(self, graph_state: GraphRuntimeState) -> dict[str, Any]:
        state = RecoveryStateV2.model_validate(graph_state["portable_state"])
        result_ref = state.output_refs.get("merge_result")
        required_failed = any(error.source in {"survey", "column", "name", "code", "merge"} for error in state.errors)
        optional_failed = any(error.source == "orm" for error in state.errors)
        degraded = any(key.endswith(":degraded") for key in state.completed_stage_keys)
        partial = any(key.endswith(":partial") for key in state.completed_stage_keys)
        target_status = (
            state.status
            if state.status in {"failed", "blocked", "canceled"}
            else self.portable_definition_terminal(
                required_failed, optional_failed, degraded, partial, bool(result_ref),
            )
        )
        terminal = self.portable._commit(state, StatePatch(
            status=target_status,
            phase="finalize", result_ref=result_ref, expected_version=state.version,
        ))
        terminal = self.portable._checkpoint(terminal, reason=f"terminal:{terminal.status}")
        terminal = self.portable._event(terminal, f"run.{terminal.status}", node_id="finalize")
        return {"portable_state": terminal.model_dump(mode="json")}

    @staticmethod
    def portable_definition_terminal(
        required_failed: bool,
        optional_failed: bool,
        degraded: bool,
        partial: bool,
        has_result: bool,
    ) -> str:
        from backend.workflow.state_machine import RecoveryStateMachine

        return RecoveryStateMachine.terminal_for(
            required_failed=required_failed, optional_failed=optional_failed,
            degraded=degraded, partial=partial, has_result=has_result,
        )
