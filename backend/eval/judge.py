"""Optional LLM-as-Judge evaluator."""

from __future__ import annotations

import json

from backend.config import Config


class LLMJudge:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = Config.LLM_BASE_URL
        self.model = Config.LLM_MODEL

    def judge_analysis(self, analysis_result: dict) -> dict:
        if not self.api_key:
            return {"status": "skipped", "message": "No LLM API key configured. Use quantitative evaluation instead."}
        return self._call_llm_judge(analysis_result.get("merge_result", {}))

    def _call_llm_judge(self, merge_result: dict) -> dict:
        from openai import OpenAI

        prompt = (
            "Evaluate this schema recovery result as JSON with keys accuracy, evidence_quality, "
            "confidence_calibration, completeness, overall_comment, improvement_suggestions.\n\n"
            + self._build_relations_summary(merge_result)
        )
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as exc:
            return {"status": "error", "error": str(exc), "message": "LLM judge failed"}

    def _build_relations_summary(self, merge_result: dict) -> str:
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
        for rel in merge_result.get("high_confidence_relations", [])[:5]:
            lines.append(
                f"- {rel['source_table']}.{rel['fk_column']} -> {rel['target_table']}.{rel['pk_column']} "
                f"confidence={rel.get('fused_confidence', 0)}"
            )
        return "\n".join(lines)

