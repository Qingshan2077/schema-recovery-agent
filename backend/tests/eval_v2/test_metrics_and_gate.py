from backend.eval_v2.gate import GateEngine
from backend.eval_v2.metrics.calibration import calibration_metrics
from backend.eval_v2.metrics.schema import schema_metrics


def test_schema_metric_includes_cardinality_and_composite_keys():
    gold = [{"source_table": "items", "source_columns": ["tenant_id", "product_id"], "target_table": "products", "target_columns": ["tenant_id", "id"], "cardinality": "N:1"}]
    predicted = [{**gold[0], "confidence": .99}]
    metrics = schema_metrics(predicted, gold)
    assert metrics["schema_exact_precision"] == 1
    assert metrics["schema_cardinality_accuracy"] == 1


def test_calibration_golden_values_and_safety_gate():
    calibration = calibration_metrics([.9, .1], [1, 0], bins=2)
    assert calibration["calibration_brier"] == pytest.approx(.01)
    metrics = {
        "schema_exact_precision": .92, "schema_exact_recall": .85,
        "schema_high_confidence_precision": .97, "qa_tool_selection_accuracy": .95,
        "qa_citation_coverage": 1, "structured_output_validity": .99,
        "dba_critical_approval_bypass": 1, "memory_cross_namespace_leakage": 0,
        "trace_provenance_completeness": 1,
    }
    assert GateEngine().evaluate("eval_test", metrics, policy_version="v1").status == "failed"
import pytest
