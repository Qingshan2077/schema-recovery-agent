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
        declared_manifest = DatasetManifest.model_validate(manifest_payload)
        if entry.get("content_hash") and entry["content_hash"] != declared_manifest.content_hash:
            raise DatasetIntegrityError("registry and dataset manifest hash mismatch")
        split_path = self._safe_path(str(Path(entry["path"]) / "splits" / f"{split}.json"))
        split_payload = json.loads(split_path.read_text(encoding="utf-8"))
        case_path = self._safe_path(str(Path(entry["path"]) / split_payload["cases_file"]))
        cases = [EvalCase.model_validate(json.loads(line)) for line in case_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        allowed_ids = set(split_payload.get("case_ids") or [])
        selected = [case for case in cases if case.case_id in allowed_ids and case.split == split]
        if len(selected) != len(allowed_ids):
            raise DatasetIntegrityError("split references missing or mismatched cases")
        computed_split_hash = content_hash([case.model_dump(mode="json") for case in selected])
        declared_split_hash = declared_manifest.split_hashes.get(split)
        if declared_split_hash not in {None, "computed"} and computed_split_hash != declared_split_hash:
            raise DatasetIntegrityError("split content hash mismatch")
        computed_fixture_hashes: dict[str, str] = {}
        for case in cases:
            fixture_hash = content_hash(case.input.get("fixture") or {})
            existing_fixture_hash = computed_fixture_hashes.get(case.fixture_id)
            if existing_fixture_hash is not None and existing_fixture_hash != fixture_hash:
                raise DatasetIntegrityError(
                    f"fixture_id maps to different immutable snapshots: {case.fixture_id}"
                )
            computed_fixture_hashes[case.fixture_id] = fixture_hash
        computed_splits: dict[str, str] = {}
        for split_name in declared_manifest.split_hashes:
            descriptor_path = self._safe_path(str(Path(entry["path"]) / "splits" / f"{split_name}.json"))
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            descriptor_case_path = self._safe_path(str(Path(entry["path"]) / descriptor["cases_file"]))
            descriptor_cases = [EvalCase.model_validate(json.loads(line)) for line in descriptor_case_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            descriptor_ids = set(descriptor.get("case_ids") or [])
            descriptor_selected = [case for case in descriptor_cases if case.case_id in descriptor_ids and case.split == split_name]
            if len(descriptor_selected) != len(descriptor_ids):
                raise DatasetIntegrityError(f"split references missing or mismatched cases: {split_name}")
            computed_splits[split_name] = content_hash([case.model_dump(mode="json") for case in descriptor_selected])
        normalized = declared_manifest.model_copy(update={
            "split_hashes": computed_splits,
            "fixture_hashes": computed_fixture_hashes,
        })
        manifest = normalized.model_copy(update={
            "content_hash": content_hash(normalized.model_dump(mode="json", exclude={"content_hash"})),
        })
        return manifest, selected

    def _registry(self) -> dict:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _safe_path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise DatasetIntegrityError("dataset path escapes registry root")
        return target
