from backend.eval.judge import LLMJudge
from backend.eval.test_runner import TestRunner


def test_test_cases_loaded():
    runner = TestRunner()
    assert runner.test_cases_path.endswith("test_cases.json")


def test_llm_judge_skips_without_key():
    result = LLMJudge(api_key="").judge_analysis({"merge_result": {}})
    assert result["status"] == "skipped"

