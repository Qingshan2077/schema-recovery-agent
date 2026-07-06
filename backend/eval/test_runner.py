"""Quantitative evaluation runner."""

from __future__ import annotations

import json
import os
from backend.config import Config
from datetime import datetime
from typing import Any

from backend.agent.orchestrator import Orchestrator
from backend.mcp.server import init_mcp_tools


class TestRunner:
    def __init__(self, test_cases_path: str | None = None):
        self.test_cases_path = test_cases_path or os.path.join(Config.DATA_DIR, "eval", "test_cases.json")
        if not os.path.exists(self.test_cases_path):
            self.test_cases_path = os.path.join(os.getcwd(), "data", "eval", "test_cases.json")

    def run_evaluation(self) -> dict:
        with open(self.test_cases_path, "r", encoding="utf-8") as fh:
            test_data = json.load(fh)

        registry = init_mcp_tools()
        analysis = Orchestrator(registry).run_full_analysis()
        merge = analysis.get("merge_result", {})
        detected_relations = [self._normalize_detected(rel) for rel in merge.get("high_confidence_relations", []) + merge.get("medium_confidence_relations", [])]
        expected = [self._normalize_expected(exp) for exp in test_data["expected_relations"]]

        detected_exact = {self._exact_key(item) for item in detected_relations}
        expected_exact = {self._exact_key(item) for item in expected}
        detected_fk = {self._fk_key(item) for item in detected_relations}
        expected_fk = {self._fk_key(item) for item in expected}

        exact_correct = len(detected_exact & expected_exact)
        partial_fk_correct = len((detected_fk & expected_fk))
        wrong_target = self._count_wrong_target(detected_relations, expected)
        wrong_cardinality = self._count_wrong_cardinality(detected_relations, expected)
        false_positive = len(detected_exact - expected_exact)
        missed = len(expected_exact - detected_exact)

        high_confidence_correct = sum(1 for det in detected_relations if det["confidence"] >= 0.7 and self._exact_key(det) in expected_exact)
        high_confidence_wrong = sum(1 for det in detected_relations if det["confidence"] >= 0.7 and self._exact_key(det) not in expected_exact)
        medium_confidence_correct = sum(1 for det in detected_relations if det["confidence"] < 0.7 and self._exact_key(det) in expected_exact)
        high_confidence_total = sum(1 for det in detected_relations if det["confidence"] >= 0.7)
        precision = exact_correct / len(detected_relations) if detected_relations else 0
        recall = exact_correct / len(expected_exact) if expected_exact else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        high_precision = high_confidence_correct / high_confidence_total if high_confidence_total else 0

        return {
            "analysis": analysis,
            "test_info": {"total_expected_relations": len(expected_exact), "total_detected_relations": len(detected_relations)},
            "scores": {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "high_confidence_precision": round(high_precision, 4),
                "partial_fk_recall": round(partial_fk_correct / len(expected_fk), 4) if expected_fk else 0,
            },
            "details": {
                "exact_correct": exact_correct,
                "partial_fk_correct": partial_fk_correct,
                "wrong_target": wrong_target,
                "wrong_cardinality": wrong_cardinality,
                "false_positive": false_positive,
                "high_confidence_correct": high_confidence_correct,
                "high_confidence_wrong": high_confidence_wrong,
                "medium_confidence_correct": medium_confidence_correct,
                "missed_relations": missed,
            },
            "metadata": {"evaluated_at": datetime.now().isoformat(), "test_set_version": test_data.get("meta", {}).get("version", "1.0")},
        }

    @staticmethod
    def _normalize_detected(rel: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_table": rel.get("source_table", "").lower(),
            "target_table": rel.get("target_table", "").lower(),
            "fk_column": rel.get("fk_column", "").lower(),
            "pk_column": rel.get("pk_column", "").lower(),
            "relation_type": rel.get("relation_type", "").upper(),
            "confidence": rel.get("fused_confidence", 0),
        }

    @staticmethod
    def _normalize_expected(exp: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_table": exp.get("source_table", "").lower(),
            "target_table": exp.get("target_table", "").lower(),
            "fk_column": exp.get("fk_column", "").lower(),
            "pk_column": exp.get("pk_column", "").lower(),
            "relation_type": exp.get("relation_type", "").upper(),
        }

    @staticmethod
    def _exact_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return (item["source_table"], item["fk_column"], item["target_table"], item["pk_column"])

    @staticmethod
    def _fk_key(item: dict[str, Any]) -> tuple[str, str]:
        return (item["source_table"], item["fk_column"])

    def _count_wrong_target(self, detected: list[dict[str, Any]], expected: list[dict[str, Any]]) -> int:
        expected_by_fk = {self._fk_key(item): item for item in expected}
        count = 0
        for det in detected:
            exp = expected_by_fk.get(self._fk_key(det))
            if exp and det["target_table"] != exp["target_table"]:
                count += 1
        return count

    def _count_wrong_cardinality(self, detected: list[dict[str, Any]], expected: list[dict[str, Any]]) -> int:
        expected_by_exact = {self._exact_key(item): item for item in expected}
        count = 0
        for det in detected:
            exp = expected_by_exact.get(self._exact_key(det))
            if exp and det["relation_type"] and exp["relation_type"] and det["relation_type"] != exp["relation_type"]:
                count += 1
        return count


