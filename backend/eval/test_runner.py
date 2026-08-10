"""Quantitative evaluation runner."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from backend.agent.orchestrator import Orchestrator
from backend.config import Config
from backend.eval.manifest import BaselineManifest, load_baseline_manifest
from backend.mcp.server import init_mcp_tools
from backend.monitor.recorder import MonitorRecorder


class TestRunner:
    def __init__(
        self,
        test_cases_path: str | None = None,
        *,
        manifest_path: str | None = None,
    ):
        self.test_cases_path = test_cases_path or os.path.join(Config.DATA_DIR, "eval", "test_cases.json")
        if not os.path.exists(self.test_cases_path):
            self.test_cases_path = os.path.join(os.getcwd(), "data", "eval", "test_cases.json")
        self.manifest_path = manifest_path

    def run_evaluation(self) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        with open(self.test_cases_path, "r", encoding="utf-8") as handle:
            test_data = json.load(handle)
        manifest = load_baseline_manifest(self.test_cases_path, manifest_path=self.manifest_path)

        with tempfile.TemporaryDirectory(prefix="schema-recovery-eval-") as isolated_dir:
            registry = init_mcp_tools()
            recorder = MonitorRecorder(os.path.join(isolated_dir, "monitor.db"))
            orchestrator = Orchestrator(
                registry,
                recorder=recorder,
                memory_db_path=os.path.join(isolated_dir, "schema_memory.db"),
                global_memory_db_path=os.path.join(isolated_dir, "global_memory.db"),
                snapshot_db_path=os.path.join(isolated_dir, "schema_snapshots.db"),
            )
            analysis = orchestrator.run_full_analysis()
            monitor_stats = recorder.get_stats()

        merge = analysis.get("merge_result", {})
        detected_relations = [
            self._normalize_detected(relation)
            for relation in (
                merge.get("high_confidence_relations", [])
                + merge.get("medium_confidence_relations", [])
            )
        ]
        expected = [self._normalize_expected(item) for item in test_data["expected_relations"]]

        detected_exact = {self._exact_key(item) for item in detected_relations}
        expected_exact = {self._exact_key(item) for item in expected}
        detected_fk = {self._fk_key(item) for item in detected_relations}
        expected_fk = {self._fk_key(item) for item in expected}

        exact_correct = len(detected_exact & expected_exact)
        partial_fk_correct = len(detected_fk & expected_fk)
        wrong_target = self._count_wrong_target(detected_relations, expected)
        wrong_cardinality = self._count_wrong_cardinality(detected_relations, expected)
        false_positive = len(detected_exact - expected_exact)
        missed = len(expected_exact - detected_exact)

        high_confidence_correct = sum(
            1
            for detected in detected_relations
            if detected["confidence"] >= 0.7 and self._exact_key(detected) in expected_exact
        )
        high_confidence_wrong = sum(
            1
            for detected in detected_relations
            if detected["confidence"] >= 0.7 and self._exact_key(detected) not in expected_exact
        )
        medium_confidence_correct = sum(
            1
            for detected in detected_relations
            if detected["confidence"] < 0.7 and self._exact_key(detected) in expected_exact
        )
        high_confidence_total = sum(1 for detected in detected_relations if detected["confidence"] >= 0.7)
        precision = exact_correct / len(detected_exact) if detected_exact else 0
        recall = exact_correct / len(expected_exact) if expected_exact else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        high_precision = high_confidence_correct / high_confidence_total if high_confidence_total else 0
        observed = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "high_confidence_precision": round(high_precision, 4),
            "partial_fk_recall": round(partial_fk_correct / len(expected_fk), 4) if expected_fk else 0,
        }

        finished_at = datetime.now(timezone.utc)
        return {
            "analysis": analysis,
            "test_info": {
                "total_expected_relations": len(expected_exact),
                "total_detected_relations": len(detected_exact),
            },
            "scores": observed,
            "targets": manifest.target_metrics,
            "monitor": monitor_stats,
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
            "metadata": self._run_metadata(
                manifest,
                analysis,
                started_at=started_at,
                finished_at=finished_at,
            ),
        }

    @staticmethod
    def _run_metadata(
        manifest: BaselineManifest,
        analysis: dict[str, Any],
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> dict[str, Any]:
        return {
            **manifest.model_dump(),
            "engine": (analysis.get("graph") or {}).get("engine", "unknown"),
            "memory_namespace": f"isolated-eval-{analysis.get('run_id', 'unknown')}",
            "run_id": analysis.get("run_id"),
            "trace_id": analysis.get("trace_id"),
            "snapshot_id": analysis.get("snapshot_id"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        }

    @staticmethod
    def _normalize_detected(relation: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_table": relation.get("source_table", "").lower(),
            "target_table": relation.get("target_table", "").lower(),
            "fk_column": relation.get("fk_column", "").lower(),
            "pk_column": relation.get("pk_column", "").lower(),
            "relation_type": relation.get("relation_type", "").upper(),
            "confidence": relation.get("fused_confidence", 0),
        }

    @staticmethod
    def _normalize_expected(expected: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_table": expected.get("source_table", "").lower(),
            "target_table": expected.get("target_table", "").lower(),
            "fk_column": expected.get("fk_column", "").lower(),
            "pk_column": expected.get("pk_column", "").lower(),
            "relation_type": expected.get("relation_type", "").upper(),
        }

    @staticmethod
    def _exact_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return item["source_table"], item["fk_column"], item["target_table"], item["pk_column"]

    @staticmethod
    def _fk_key(item: dict[str, Any]) -> tuple[str, str]:
        return item["source_table"], item["fk_column"]

    def _count_wrong_target(self, detected: list[dict[str, Any]], expected: list[dict[str, Any]]) -> int:
        expected_by_fk = {self._fk_key(item): item for item in expected}
        return sum(
            1
            for item in detected
            if (match := expected_by_fk.get(self._fk_key(item)))
            and item["target_table"] != match["target_table"]
        )

    def _count_wrong_cardinality(self, detected: list[dict[str, Any]], expected: list[dict[str, Any]]) -> int:
        expected_by_exact = {self._exact_key(item): item for item in expected}
        return sum(
            1
            for item in detected
            if (match := expected_by_exact.get(self._exact_key(item)))
            and item["relation_type"]
            and match["relation_type"]
            and item["relation_type"] != match["relation_type"]
        )
