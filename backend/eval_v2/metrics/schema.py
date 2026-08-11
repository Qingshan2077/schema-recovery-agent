"""Direction/cardinality/composite-key aware schema metrics."""

from __future__ import annotations

from backend.eval_v2.bootstrap import bootstrap_ci


def _edge(item: dict) -> tuple:
    return (
        str(item.get("source_table", "")).casefold(),
        tuple(str(value).casefold() for value in item.get("source_columns") or [item.get("fk_column", "")]),
        str(item.get("target_table", "")).casefold(),
        tuple(str(value).casefold() for value in item.get("target_columns") or [item.get("pk_column", "")]),
    )


def schema_metrics(predicted: list[dict], gold: list[dict]) -> dict[str, float | list[float]]:
    predicted_map = {_edge(item): item for item in predicted}
    gold_map = {_edge(item): item for item in gold}
    correct = set(predicted_map) & set(gold_map)
    precision = len(correct) / len(predicted_map) if predicted_map else 0.0
    recall = len(correct) / len(gold_map) if gold_map else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    cardinality = [
        str(predicted_map[key].get("cardinality") or predicted_map[key].get("relation_type"))
        == str(gold_map[key].get("cardinality") or gold_map[key].get("relation_type"))
        for key in correct
    ]
    high = [item for item in predicted if float(item.get("confidence", item.get("calibrated_probability", 0))) >= .7]
    high_correct = sum(_edge(item) in gold_map for item in high)
    case_hits = [1.0 if key in predicted_map else 0.0 for key in gold_map]
    ci_low, ci_high = bootstrap_ci(case_hits, lambda rows: sum(rows) / len(rows)) if case_hits else (0.0, 0.0)
    return {
        "schema_exact_precision": precision,
        "schema_exact_recall": recall,
        "schema_exact_f1": f1,
        "schema_cardinality_accuracy": sum(cardinality) / len(cardinality) if cardinality else 0.0,
        "schema_high_confidence_precision": high_correct / len(high) if high else 0.0,
        "schema_recall_ci_low": ci_low,
        "schema_recall_ci_high": ci_high,
        "schema_wrong_target": float(sum(
            any(key[:2] == gold_key[:2] and key[2:] != gold_key[2:] for gold_key in gold_map)
            for key in predicted_map if key not in gold_map
        )),
        "schema_missed_relations": float(len(set(gold_map) - set(predicted_map))),
    }
