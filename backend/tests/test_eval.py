from backend.eval.judge import LLMJudge
from backend.eval.test_runner import TestRunner
from backend.eval.report import EvalReportStore


def test_test_cases_loaded():
    runner = TestRunner()
    assert runner.test_cases_path.endswith("test_cases.json")


def test_llm_judge_skips_without_key():
    result = LLMJudge(api_key="").judge_analysis({"merge_result": {}})
    assert result["status"] == "skipped"


def test_eval_report_store_reads_latest_without_running_evaluation(tmp_path):
    store = EvalReportStore(str(tmp_path))
    saved = store.save({"report_title": "baseline", "report_date": "2026-08-10T00:00:00Z"})

    assert store.latest()["report_id"] == saved["report_id"]
