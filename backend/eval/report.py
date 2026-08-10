"""Evaluation report generation and immutable artifact storage."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import Config
from backend.eval.judge import LLMJudge
from backend.eval.test_runner import TestRunner


class EvalReportStore:
    def __init__(self, report_dir: str | None = None):
        self.report_dir = Path(report_dir or Config.EVAL_REPORT_DIR)

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_id = report.get("report_id") or f"eval_{uuid.uuid4().hex}"
        persisted = {**report, "report_id": report_id}
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.report_dir / f"{timestamp}_{report_id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(persisted, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return persisted

    def latest(self) -> dict[str, Any] | None:
        if not self.report_dir.exists():
            return None
        reports = sorted(self.report_dir.glob("*_eval_*.json"), reverse=True)
        if not reports:
            return None
        return json.loads(reports[0].read_text(encoding="utf-8"))


class EvalReporter:
    def __init__(self, *, store: EvalReportStore | None = None):
        self.store = store or EvalReportStore()

    def run_and_save_report(self) -> dict[str, Any]:
        return self.store.save(self._build_report())

    def run_full_report(self) -> dict[str, Any]:
        """Backward-compatible write path; GET handlers must not call it."""

        return self.run_and_save_report()

    def get_latest_report(self) -> dict[str, Any] | None:
        return self.store.latest()

    def _build_report(self) -> dict[str, Any]:
        quantitative = TestRunner().run_evaluation()
        analysis = quantitative.pop("analysis")
        monitor = quantitative.pop("monitor")
        qualitative = LLMJudge().judge_analysis(analysis)
        scores = quantitative["scores"]
        return {
            "report_title": "Schema Recovery Agent Evaluation Report",
            "report_date": datetime.now(timezone.utc).isoformat(),
            "quantitative": {
                "description": "Observed exact relation metrics; target values are reported separately.",
                "precision": scores["precision"],
                "recall": scores["recall"],
                "f1_score": scores["f1_score"],
                "high_confidence_precision": scores["high_confidence_precision"],
                "partial_fk_recall": scores["partial_fk_recall"],
                "observed": scores,
                "targets": quantitative["targets"],
                "details": quantitative["details"],
                "test_info": quantitative["test_info"],
                "metadata": quantitative["metadata"],
            },
            "qualitative": qualitative,
            "monitor": monitor,
        }
