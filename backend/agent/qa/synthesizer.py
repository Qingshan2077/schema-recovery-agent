"""Evidence-bounded answer synthesis with deterministic fallback rendering."""

from __future__ import annotations

import json

from backend.agent.qa.contracts import (
    AnswerClaim,
    Citation,
    FactSet,
    QAArtifact,
    QueryPlan,
    SchemaEntityRef,
    SynthesisDraft,
)
from backend.agent.qa.prompt_schemas import SYNTHESIS_SCHEMA
from backend.agent.runtime.contracts import ModelRequest
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.run_context import RunContext
from backend.core.identity import new_id, stable_id


class AnswerSynthesizer:
    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway

    async def synthesize(
        self,
        question: str,
        plan: QueryPlan,
        entities: list[SchemaEntityRef],
        fact_set: FactSet,
        context: RunContext,
    ) -> tuple[SynthesisDraft, bool, str | None]:
        request = ModelRequest(
            profile="synthesis",
            prompt_id="qa.answer_synthesis",
            prompt_version="1.0.0",
            input={
                "question": question,
                "query_plan": json.dumps(plan.model_dump(mode="json"), ensure_ascii=False),
                "resolved_entities": json.dumps([item.model_dump(mode="json") for item in entities], ensure_ascii=False),
                "verified_facts": json.dumps(fact_set.model_dump(mode="json"), ensure_ascii=False, default=str),
            },
            output_schema=SYNTHESIS_SCHEMA,
            metadata={"agent": "qa", "stage": "synthesis", "catalog_version": fact_set.catalog_version},
        )
        result = await self.gateway.generate_structured(request, context.for_agent("qa.synthesizer"))
        if result.status in {"success", "degraded"} and result.parsed is not None:
            try:
                return (
                    SynthesisDraft.model_validate(result.parsed),
                    result.status == "degraded",
                    "model_gateway_degraded" if result.status == "degraded" else None,
                )
            except ValueError:
                pass
        return (
            self.deterministic_draft(plan, entities, fact_set),
            True,
            result.error.code if result.error else "invalid_synthesis",
        )

    @staticmethod
    def deterministic_draft(
        plan: QueryPlan,
        entities: list[SchemaEntityRef],
        fact_set: FactSet,
    ) -> SynthesisDraft:
        facts = fact_set.facts
        zh = plan.language == "zh-CN"
        if not facts:
            answer = "没有找到可验证的 Schema 事实。" if zh else "No verified schema facts were found."
            return SynthesisDraft(answer=answer, claims=[], citations=[], artifacts=[], follow_up_questions=[])

        name = next((item.canonical_name for item in entities if item.canonical_name), "database")
        values = [fact.value for fact in facts]
        artifact: QAArtifact | None = None
        if plan.intent == "table_columns":
            answer = f"表 {name} 包含 {len(facts)} 个字段。" if zh else f"Table {name} has {len(facts)} columns."
            artifact = QAArtifact(
                artifact_id=new_id("artifact"),
                type="column_table",
                title=f"{name} columns",
                data={"table": name, "columns": values},
                fact_ids=[fact.fact_id for fact in facts],
            )
        elif plan.intent == "relations" or plan.intent == "evidence_explain":
            answer = f"找到 {len(facts)} 条有证据支持的关系。" if zh else f"Found {len(facts)} evidence-backed relations."
            artifact = QAArtifact(
                artifact_id=new_id("artifact"),
                type="evidence_cards" if plan.intent == "evidence_explain" else "relation_cards",
                title="Relations",
                data={"relations": values},
                fact_ids=[fact.fact_id for fact in facts],
            )
        elif plan.intent == "indexes":
            answer = f"表 {name} 包含 {len(facts)} 个索引。" if zh else f"Table {name} has {len(facts)} indexes."
            artifact = QAArtifact(
                artifact_id=new_id("artifact"),
                type="index_table",
                title=f"{name} indexes",
                data={"table": name, "indexes": values},
                fact_ids=[fact.fact_id for fact in facts],
            )
        elif plan.intent == "table_metadata":
            answer = f"已读取表 {name} 的元数据。" if zh else f"Loaded metadata for table {name}."
            artifact = QAArtifact(
                artifact_id=new_id("artifact"),
                type="metadata_card",
                title=f"{name} metadata",
                data={fact.predicate: fact.value for fact in facts},
                fact_ids=[fact.fact_id for fact in facts],
            )
        elif plan.intent == "schema_overview":
            answer = f"当前目录包含 {len(facts)} 个表或视图。" if zh else f"The catalog contains {len(facts)} tables or views."
            artifact = QAArtifact(
                artifact_id=new_id("artifact"),
                type="overview",
                title="Schema overview",
                data={"tables": values},
                fact_ids=[fact.fact_id for fact in facts],
            )
        else:
            answer = "已读取最新分析状态。" if zh else "Loaded the latest analysis status."

        claim_id = stable_id("evidence", "qa-claim", plan.intent, answer, [fact.fact_id for fact in facts])
        claim = AnswerClaim(claim_id=claim_id, text=answer, fact_ids=[fact.fact_id for fact in facts])
        citation = Citation(
            citation_id=new_id("citation"),
            claim_id=claim_id,
            fact_ids=claim.fact_ids,
            label="verified catalog evidence",
            locator={
                "catalog_version": fact_set.catalog_version,
                "sources": sorted({fact.source_tool for fact in facts}),
                "tool_call_ids": sorted({fact.source_tool_call_id for fact in facts}),
                "fact_locators": [fact.locator for fact in facts],
            },
        )
        return SynthesisDraft(
            answer=answer,
            claims=[claim],
            citations=[citation],
            artifacts=[artifact] if artifact else [],
            follow_up_questions=[],
        )
