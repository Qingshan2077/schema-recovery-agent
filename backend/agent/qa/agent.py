"""Phase 2 QA Agent: plan, resolve, execute, verify, synthesize, verify."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.agent.qa.answer_verifier import AnswerVerifier
from backend.agent.qa.context_loader import QAContextLoader
from backend.agent.qa.contracts import CatalogEntity, QAOutput
from backend.agent.qa.entity_resolver import EntityResolver
from backend.agent.qa.errors import QAError
from backend.agent.qa.fact_verifier import FactVerifier
from backend.agent.qa.planner import QueryPlanner
from backend.agent.qa.policies import InputGuardrail, QAToolPolicy
from backend.agent.qa.synthesizer import AnswerSynthesizer
from backend.agent.qa.tool_loop import QAToolLoop
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext, RuntimeCancelledError
from backend.agent.runtime.tool_runtime import ToolRuntime
from backend.core.identity import new_id
from backend.core.status import AgentError, AgentRunResult, RunStatus


class QAAgent:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway,
        tool_runtime: ToolRuntime,
        max_tool_calls: int = 6,
        max_tool_rounds: int = 2,
        max_context_messages: int = 12,
        max_question_chars: int = 4000,
    ):
        policy = QAToolPolicy(max_calls=max_tool_calls, max_rounds=max_tool_rounds)
        self.guardrail = InputGuardrail(max_chars=max_question_chars)
        self.tool_loop = QAToolLoop(tool_runtime, policy)
        self.policy = policy
        self.planner = QueryPlanner(model_gateway)
        self.resolver = EntityResolver()
        self.fact_verifier = FactVerifier()
        self.synthesizer = AnswerSynthesizer(model_gateway)
        self.answer_verifier = AnswerVerifier()
        self.context_loader = QAContextLoader(max_messages=max_context_messages)

    async def run(
        self,
        *,
        question: str,
        run_context: RunContext,
        messages: list[dict] | None = None,
        event_emitter: Callable[[str, str, dict], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        try:
            question = self.guardrail.validate(question)
            inventory_execution = await self.tool_loop.inventory(run_context)
            if inventory_execution.status != "success" or not inventory_execution.output:
                return self._failure("catalog_unavailable", "The visible schema catalog could not be loaded", inventory_execution.error_code)
            inventory = [CatalogEntity.model_validate(item) for item in inventory_execution.output.get("tables", [])]
            catalog_version = str(inventory_execution.output.get("catalog_version") or "unknown")
            qa_context = self.context_loader.load(
                thread_id=run_context.thread_id,
                messages=messages or [],
                inventory=inventory,
            )
            planner_outcome = await self.planner.plan(question, qa_context, inventory, run_context)
            plan = planner_outcome.plan
            self.policy.validate_plan(plan)
            await _emit(event_emitter, "qa.plan.completed", "success", {
                "intent": plan.intent,
                "entities": [entity.mention for entity in plan.entities],
                "clarification_required": bool(plan.clarification_question),
                "plan_summary": plan.plan_summary,
            })
            if plan.clarification_question:
                await _emit(event_emitter, "qa.clarification.required", "blocked", {"question": plan.clarification_question})
                return self._clarification(plan.clarification_question, plan.intent, planner_outcome.reason)
            if plan.intent == "unknown":
                message = "请询问数据库表、字段、索引、关系或分析状态。" if plan.language == "zh-CN" else "Ask about database tables, columns, indexes, relations, or analysis status."
                return self._clarification(message, plan.intent, planner_outcome.reason)

            entities = self.resolver.resolve(plan.entities, inventory, focus=qa_context.focus_entities)
            await _emit(event_emitter, "qa.entity.resolved", "success", {
                "entities": [entity.model_dump(mode="json") for entity in entities],
            })
            if plan.intent in {"table_columns", "table_metadata", "indexes"} and not entities:
                message = "请明确要查询的表名。" if plan.language == "zh-CN" else "Which table should I inspect?"
                return self._clarification(message, plan.intent, "missing_table_entity")
            unresolved = [item for item in entities if item.status != "resolved"]
            if unresolved:
                item = unresolved[0]
                suggestions = [candidate.name for candidate in item.candidates]
                question_text = (
                    f"无法唯一确定“{item.mention}”，请从这些表中选择：{', '.join(suggestions)}。"
                    if suggestions
                    else f"目录中找不到表“{item.mention}”，请确认表名。"
                )
                await _emit(event_emitter, "qa.clarification.required", "blocked", {
                    "question": question_text,
                    "candidates": suggestions,
                })
                return self._clarification(question_text, plan.intent, "entity_resolution_required", entities)

            steps = self.policy.build_steps(plan, entities)
            executions = await self.tool_loop.execute(steps, run_context)
            failed = [item for item in executions if item.status != "success"]
            if failed:
                return self._failure("qa_tool_failed", "A required read-only schema tool failed", failed[0].error_code)
            fact_set = self.fact_verifier.verify(executions, catalog_version=catalog_version)
            await _emit(event_emitter, "qa.facts.verified", "success", {
                "fact_count": len(fact_set.facts),
                "fact_ids": [fact.fact_id for fact in fact_set.facts],
                "tool_call_ids": fact_set.tool_call_ids,
            })
            if fact_set.facts:
                draft, synthesis_degraded, synthesis_reason = await self.synthesizer.synthesize(
                    question, plan, entities, fact_set, run_context
                )
            else:
                draft = self.synthesizer.deterministic_draft(plan, entities, fact_set)
                synthesis_degraded = False
                synthesis_reason = None
            report = self.answer_verifier.verify(draft, fact_set)
            if not report.valid:
                draft = self.synthesizer.deterministic_draft(plan, entities, fact_set)
                report = self.answer_verifier.verify(draft, fact_set)
                synthesis_degraded = True
                synthesis_reason = "answer_grounding_regenerated"
            if not report.valid:
                return self._failure("grounding_failed", "Answer grounding verification failed", "; ".join(report.errors))
            await _emit(event_emitter, "qa.answer.verified", "success", {
                "answer": draft.answer,
                "citation_coverage": report.citation_coverage,
                "claim_count": len(draft.claims),
            })
            for artifact in draft.artifacts:
                await _emit(event_emitter, "qa.artifact.created", "success", {
                    "artifact_id": artifact.artifact_id,
                    "type": artifact.type,
                    "title": artifact.title,
                })

            reasons = [reason for reason in (planner_outcome.reason, synthesis_reason) if reason]
            output = QAOutput(
                **draft.model_dump(mode="python"),
                intent=plan.intent,
                entities=entities,
                citation_coverage=report.citation_coverage,
                degraded_reasons=reasons,
            )
            degraded = planner_outcome.degraded or synthesis_degraded
            return AgentRunResult(
                status=RunStatus.DEGRADED if degraded else RunStatus.SUCCESS,
                output=output.model_dump(mode="json"),
                evidence_ids=[fact.fact_id for fact in fact_set.facts],
                tool_call_ids=fact_set.tool_call_ids,
                uncertainties=reasons if degraded else [],
                decision_summary="Answer passed deterministic fact and citation verification",
                next_actions=["Configure an available model provider to leave degraded mode"] if degraded else [],
                model_profile="synthesis",
                prompt_version="1.0.0",
            )
        except RuntimeCancelledError as exc:
            return AgentRunResult(
                status=RunStatus.CANCELLED,
                error=AgentError(code="qa_cancelled", category="cancelled", message=str(exc), source="qa_agent"),
            )
        except QAError as exc:
            return AgentRunResult(
                status=RunStatus.BLOCKED,
                error=AgentError(code=exc.code, category="validation", message=str(exc), source="qa_agent"),
                decision_summary="QA input was blocked by deterministic policy",
                next_actions=["Revise the question and try again"],
            )
        except ValueError as exc:
            return self._failure("qa_validation_failed", "QA contract validation failed", str(exc))
        except Exception:
            return self._failure("qa_internal_error", "QA processing failed before a verified answer was produced")
        finally:
            self.tool_loop.finish(run_context.run_id)

    @staticmethod
    def _clarification(
        question: str,
        intent: str,
        reason: str | None,
        entities: list | None = None,
    ) -> AgentRunResult:
        serialized_entities = [item.model_dump(mode="json") for item in entities or []]
        candidates = [
            candidate.model_dump(mode="json")
            for item in entities or []
            for candidate in item.candidates
        ]
        return AgentRunResult(
            status=RunStatus.BLOCKED,
            output={
                "intent": intent,
                "clarification_question": question,
                "entities": serialized_entities,
                "citations": [],
                "artifacts": [{
                    "artifact_id": new_id("artifact"),
                    "type": "clarification_options",
                    "title": "Entity clarification",
                    "data": {"candidates": candidates},
                    "fact_ids": [],
                }] if candidates else [],
            },
            uncertainties=[reason] if reason else [],
            decision_summary="The agent refused to guess an unresolved schema entity",
            next_actions=[question],
            error=AgentError(code="clarification_required", category="validation", message=question, source="qa_agent"),
        )

    @staticmethod
    def _failure(code: str, message: str, detail: str | None = None) -> AgentRunResult:
        return AgentRunResult(
            status=RunStatus.ERROR,
            error=AgentError(
                code=code,
                category="tool" if "tool" in code or "catalog" in code else "internal",
                message=message,
                source="qa_agent",
                details={"reason": detail} if detail else {},
            ),
        )


async def _emit(
    emitter: Callable[[str, str, dict], Awaitable[None]] | None,
    event_type: str,
    status: str,
    payload: dict,
) -> None:
    if emitter is not None:
        await emitter(event_type, status, payload)
