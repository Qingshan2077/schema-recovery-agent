"""Evaluation report generator."""

from datetime import datetime

from backend.eval.judge import LLMJudge
from backend.eval.test_runner import TestRunner
from backend.monitor.recorder import MonitorRecorder


class EvalReporter:
    def run_full_report(self) -> dict:
        quantitative = TestRunner().run_evaluation()
        analysis = quantitative.pop("analysis")
        qualitative = LLMJudge().judge_analysis(analysis)
        stats = MonitorRecorder().get_stats()
        return {
            "report_title": "Schema Recovery Agent Evaluation Report",
            "report_date": datetime.now().isoformat(),
            "quantitative": {
                "description": "Exact relation precision/recall with partial FK, target, cardinality, and calibration diagnostics.",
                "precision": quantitative["scores"]["precision"],
                "recall": quantitative["scores"]["recall"],
                "f1_score": quantitative["scores"]["f1_score"],
                "high_confidence_precision": quantitative["scores"]["high_confidence_precision"],
                "partial_fk_recall": quantitative["scores"]["partial_fk_recall"],
                "details": quantitative["details"],
                "test_info": quantitative["test_info"],
                "metadata": quantitative["metadata"],
            },
            "qualitative": qualitative,
            "monitor": stats,
        }
