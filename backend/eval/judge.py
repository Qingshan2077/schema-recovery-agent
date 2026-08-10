"""LLM-as-Judge consumer backed exclusively by the Phase 1 ModelGateway."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from backend.agent.runtime import ModelRequest, RuntimeContainer, build_runtime_container
from backend.agent.runtime.contracts import StrictContract
from backend.agent.runtime.run_context import RunContext
from backend.config import Config
from backend.core.identity import RunIdentity


class JudgeResult(StrictContract):
    accuracy: int = Field(ge=0, le=100)
    evidence_quality: int = Field(ge=0, le=100)
    confidence_calibration: int = Field(ge=0, le=100)
    completeness: int = Field(ge=0, le=100)
    overall_comment: str = Field(max_length=2000)
    improvement_suggestions: list[str] = Field(default_factory=list, max_length=10)


class LLMJudge:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        runtime: RuntimeContainer | None = None,
        run_context: RunContext | None = None,
    ):
        self.api_key = Config.LLM_API_KEY if api_key is None else api_key
        self.runtime = runtime
        self.run_context = run_context

    def judge_analysis(self, analysis_result: dict[str, Any]) -> dict[str, Any]:
        if (
            not self.api_key
            and self.runtime is None
            and str(Config.MODEL_PROVIDER_MODE).strip().lower() != "fake"
        ):
            return {
                "status": "skipped",
                "message": "No LLM API key configured. Quantitative evaluation remains available.",
                "reason": "model_provider_unavailable",
            }
        runtime = self.runtime or self._build_runtime()
        context = self.run_context or runtime.new_context(
            RunIdentity.create(),
            agent_id="llm_judge",
        )
        prompt = runtime.prompts.get("judge.analysis", "1.0.0")
        request = ModelRequest(
            profile="judge",
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.semantic_version,
            input={"analysis_summary": self._build_relations_summary(analysis_result.get("merge_result", {}))},
            output_schema=prompt.output_schema,
            metadata={"max_output_tokens": 2048, "evaluation": True},
            fallback_profile="fast",
        )
        result = runtime.model_gateway.generate_structured_sync(request, context)
        if result.status in {"error", "cancelled"} or result.parsed is None:
            return {
                "status": result.status,
                "message": "LLM judge failed through the controlled model runtime.",
                "error": result.error.model_dump(mode="json") if result.error else None,
                "model_call_id": result.model_call_id,
            }
        judged = JudgeResult.model_validate(result.parsed).model_dump(mode="json")
        if result.status == "degraded":
            judged["runtime_status"] = "degraded"
            judged["degradation_reasons"] = result.degradation_reasons
        judged["model_call_id"] = result.model_call_id
        judged["prompt_version"] = prompt.semantic_version
        judged["prompt_hash"] = prompt.sha256
        return judged

    def _build_runtime(self) -> RuntimeContainer:
        return build_runtime_container(_ConfigOverride(Config, LLM_API_KEY=self.api_key))

    def _build_relations_summary(self, merge_result: dict[str, Any]) -> str:
        summary = merge_result.get("summary", {})
        lines = [
            f"total_relations: {summary.get('total_relations', 0)}",
            f"high_confidence: {summary.get('high_confidence', 0)}",
            f"medium_confidence: {summary.get('medium_confidence', 0)}",
            "evidence contributions:",
        ]
        for source, info in merge_result.get("source_contributions", {}).items():
            lines.append(f"- {source}: {info.get('percentage', 0)}%")
        lines.append("sample high-confidence relations:")
        for relation in merge_result.get("high_confidence_relations", [])[:5]:
            lines.append(
                f"- {relation.get('source_table', '')}.{relation.get('fk_column', '')} -> "
                f"{relation.get('target_table', '')}.{relation.get('pk_column', '')} "
                f"confidence={relation.get('fused_confidence', 0)}"
            )
        return "\n".join(lines)


class _ConfigOverride:
    """Read-only configuration overlay used for the legacy api_key constructor."""

    def __init__(self, base: object, **overrides: Any):
        self._base = base
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._base, name)
