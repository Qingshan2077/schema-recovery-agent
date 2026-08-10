"""LLM-first query planning with an explicit degraded deterministic fallback."""

from __future__ import annotations

import json

from backend.agent.qa.contracts import CatalogEntity, EntityMention, PlannerOutcome, QAContext, QueryPlan
from backend.agent.qa.prompt_schemas import QUERY_PLAN_SCHEMA
from backend.agent.runtime.contracts import ModelRequest
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext


class QueryPlanner:
    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway

    async def plan(
        self,
        question: str,
        context: QAContext,
        inventory: list[CatalogEntity],
        run_context: RunContext,
    ) -> PlannerOutcome:
        request = ModelRequest(
            profile="fast",
            prompt_id="qa.query_plan",
            prompt_version="1.0.0",
            input={
                "question": question[:4000],
                "conversation_context": json.dumps(
                    [turn.model_dump(mode="json") for turn in context.messages],
                    ensure_ascii=False,
                ),
                "catalog_entities": json.dumps(
                    [{"name": item.name, "kind": item.kind, "schema": item.schema_name} for item in inventory],
                    ensure_ascii=False,
                ),
            },
            output_schema=QUERY_PLAN_SCHEMA,
            metadata={"agent": "qa", "stage": "planning"},
        )
        result = await self.gateway.generate_structured(request, run_context.for_agent("qa.planner"))
        if result.status in {"success", "degraded"} and result.parsed is not None:
            return PlannerOutcome(
                plan=QueryPlan.model_validate(result.parsed),
                degraded=result.status == "degraded",
                reason="model_gateway_degraded" if result.status == "degraded" else None,
            )
        return PlannerOutcome(
            plan=self.fallback_plan(question, inventory, context),
            degraded=True,
            reason=result.error.code if result.error else "model_unavailable",
        )

    @staticmethod
    def fallback_plan(question: str, inventory: list[CatalogEntity], context: QAContext) -> QueryPlan:
        folded = question.casefold()
        language = "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in question) else "en"
        if any(token in folded for token in ("字段", "列", "column", "field")):
            intent = "table_columns"
        elif any(token in folded for token in ("元数据", "引擎", "创建时间", "metadata", "engine")):
            intent = "table_metadata"
        elif any(token in folded for token in ("关系", "关联", "外键", "relation", "foreign key")):
            intent = "relations"
        elif any(token in folded for token in ("索引", "index")):
            intent = "indexes"
        elif any(token in folded for token in ("分析状态", "analysis status", "进度")):
            intent = "analysis_status"
        elif any(token in folded for token in ("证据", "为什么", "evidence", "why")):
            intent = "evidence_explain"
        elif any(token in folded for token in ("多少张表", "概览", "overview", "tables")):
            intent = "schema_overview"
        else:
            intent = "unknown"

        matches = [entity for entity in inventory if entity.name.casefold() in folded]
        matches.sort(key=lambda entity: (folded.find(entity.name.casefold()), -len(entity.name), entity.name))
        mentions = [EntityMention(mention=entity.name, kind="table") for entity in matches[:2]]
        if not mentions and any(token in folded for token in ("这个表", "该表", "上一个表", "this table", "it")):
            mentions = [EntityMention(mention="这个表" if language == "zh-CN" else "this table", kind="table")]
        needs_table = intent in {"table_columns", "table_metadata", "indexes"}
        clarification = None
        if needs_table and not mentions:
            clarification = "请明确要查询的表名。" if language == "zh-CN" else "Which table should I inspect?"
        return QueryPlan(
            intent=intent,
            entities=mentions,
            required_information=[intent] if intent != "unknown" else [],
            suggested_tools=[],
            clarification_question=clarification,
            language=language,
            plan_summary=f"degraded deterministic plan for {intent}",
        )
