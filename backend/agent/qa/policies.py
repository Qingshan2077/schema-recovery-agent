"""Deterministic guardrails and tool policy for schema QA."""

from __future__ import annotations

from backend.agent.qa.contracts import QueryPlan, SchemaEntityRef, ToolStep
from backend.agent.qa.errors import UnsafeQuestionError

READ_ONLY_TOOLS = {
    "catalog.list_tables",
    "catalog.query_table_columns",
    "catalog.query_table_metadata",
    "catalog.query_indexes",
    "evidence.query_relations",
    "analysis.get_status",
}

INTENT_TO_TOOL = {
    "table_columns": "catalog.query_table_columns",
    "table_metadata": "catalog.query_table_metadata",
    "relations": "evidence.query_relations",
    "indexes": "catalog.query_indexes",
    "schema_overview": "catalog.list_tables",
    "analysis_status": "analysis.get_status",
    "evidence_explain": "evidence.query_relations",
}


class InputGuardrail:
    def __init__(self, *, max_chars: int = 4000):
        self.max_chars = max_chars

    def validate(self, question: str) -> str:
        normalized = question.strip()
        if not normalized:
            raise UnsafeQuestionError("Question is empty")
        if len(normalized) > self.max_chars:
            raise UnsafeQuestionError("Question exceeds the configured length limit")
        return normalized


class QAToolPolicy:
    def __init__(self, *, max_calls: int = 6, max_rounds: int = 2):
        self.max_calls = max_calls
        self.max_rounds = max_rounds

    def build_steps(self, plan: QueryPlan, entities: list[SchemaEntityRef]) -> list[ToolStep]:
        tool_name = INTENT_TO_TOOL.get(plan.intent)
        if not tool_name:
            return []
        resolved = [entity for entity in entities if entity.status == "resolved"]
        steps: list[ToolStep] = []
        if plan.intent in {"schema_overview", "analysis_status"}:
            steps.append(ToolStep(tool_name=tool_name, arguments={}, purpose=plan.plan_summary or plan.intent, round=1))
        elif plan.intent in {"relations", "evidence_explain"}:
            args: dict[str, str] = {}
            if resolved:
                args["source_table"] = resolved[0].canonical_name or ""
            if len(resolved) > 1:
                args["target_table"] = resolved[1].canonical_name or ""
            steps.append(ToolStep(tool_name=tool_name, arguments=args, purpose=plan.plan_summary or plan.intent, round=1))
        elif resolved:
            steps.append(
                ToolStep(
                    tool_name=tool_name,
                    arguments={"table_name": resolved[0].canonical_name},
                    purpose=plan.plan_summary or plan.intent,
                    round=1,
                )
            )
        self.validate_steps(steps)
        return steps

    def validate_plan(self, plan: QueryPlan) -> None:
        forbidden = [tool for tool in plan.suggested_tools if tool not in READ_ONLY_TOOLS]
        if forbidden:
            raise UnsafeQuestionError(f"Planner requested tools outside the QA allowlist: {', '.join(forbidden)}")

    def validate_steps(self, steps: list[ToolStep]) -> None:
        if len(steps) > self.max_calls:
            raise UnsafeQuestionError("QA tool-call budget exceeded")
        for step in steps:
            if step.tool_name not in READ_ONLY_TOOLS:
                raise UnsafeQuestionError(f"Tool is not allowed for QA: {step.tool_name}")
            if step.round > self.max_rounds:
                raise UnsafeQuestionError("QA tool-round budget exceeded")
