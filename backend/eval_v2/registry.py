"""Dataset registry with allowlisted paths and content-hash validation."""

from __future__ import annotations

import json
from pathlib import Path

from backend.eval_v2.contracts import DatasetManifest, EvalCase
from backend.eval_v2.hashing import content_hash


class DatasetIntegrityError(ValueError):
    pass


class DatasetRegistry:
    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path).resolve()
        self.root = self.registry_path.parent.resolve()

    def list(self) -> list[dict]:
        return list(self._registry().get("datasets") or [])

    def load(self, dataset_id: str, version: str, split: str) -> tuple[DatasetManifest, list[EvalCase]]:
        entry = next(
            (item for item in self.list() if item.get("dataset_id") == dataset_id and item.get("version") == version),
            None,
        )
        if entry is None:
            raise KeyError(f"dataset_not_registered:{dataset_id}:{version}")
        base = self._safe_path(entry["path"])
        manifest_payload = json.loads((base / "dataset-manifest.json").read_text(encoding="utf-8"))
        manifest = DatasetManifest.model_validate(manifest_payload)
        if entry.get("content_hash") and entry["content_hash"] != manifest.content_hash:
            raise DatasetIntegrityError("registry and dataset manifest hash mismatch")
        split_path = self._safe_path(str(Path(entry["path"]) / "splits" / f"{split}.json"))
        split_payload = json.loads(split_path.read_text(encoding="utf-8"))
        case_path = self._safe_path(str(Path(entry["path"]) / split_payload["cases_file"]))
        cases = [EvalCase.model_validate(json.loads(line)) for line in case_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        allowed_ids = set(split_payload.get("case_ids") or [])
        selected = [case for case in cases if case.case_id in allowed_ids and case.split == split]
        if content_hash([case.model_dump(mode="json") for case in selected]) != manifest.split_hashes.get(split):
            raise DatasetIntegrityError("split content hash mismatch")
        return manifest, selected

    def _registry(self) -> dict:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _safe_path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise DatasetIntegrityError("dataset path escapes registry root")
        return target
