"""Reproducible baseline manifest helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.config import Config, ROOT_DIR


class BaselineManifest(BaseModel):
    baseline_id: str
    dataset_version: str
    dataset_sha256: str
    fixture_snapshot_hash: str
    git_sha: str
    source_tree_hash: str
    runtime_config_hash: str
    fusion_version: str = "legacy-v1"
    model_profiles: dict[str, Any] = Field(default_factory=dict)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    target_metrics: dict[str, float] = Field(
        default_factory=lambda: {"precision": 0.92, "recall": 0.85}
    )


def load_baseline_manifest(
    dataset_path: str,
    *,
    manifest_path: str | None = None,
) -> BaselineManifest:
    dataset = Path(dataset_path)
    candidate = Path(manifest_path) if manifest_path else dataset.with_name("manifest.json")
    if candidate.exists():
        raw = json.loads(candidate.read_text(encoding="utf-8"))
        return BaselineManifest.model_validate(raw)

    raw_dataset = json.loads(dataset.read_text(encoding="utf-8"))
    fixture = ROOT_DIR / "data" / "sim_schema.sql"
    dataset_sha256 = _file_sha256(dataset)
    return BaselineManifest(
        baseline_id=f"base_{dataset_sha256[:16]}",
        dataset_version=str(raw_dataset.get("meta", {}).get("version", "legacy-1.0")),
        dataset_sha256=dataset_sha256,
        fixture_snapshot_hash=_file_sha256(fixture) if fixture.exists() else "unavailable",
        git_sha=_read_git_sha(ROOT_DIR),
        source_tree_hash=_source_tree_hash(ROOT_DIR),
        runtime_config_hash=_runtime_config_hash(),
    )


def _runtime_config_hash() -> str:
    safe_config = {
        "database_name": Config.DB_NAME,
        "langgraph_enabled": Config.LANGGRAPH_ENABLED,
        "runtime_identity_v2": Config.RUNTIME_IDENTITY_V2,
        "stream_events_v2": Config.STREAM_EVENTS_V2,
        "weights": {
            "code": Config.WEIGHT_CODE,
            "orm": Config.WEIGHT_ORM,
            "column": Config.WEIGHT_COLUMN,
            "name": Config.WEIGHT_NAME,
        },
    }
    return _value_sha256(safe_config)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = []
    for directory in (root / "backend", root / "frontend" / "src"):
        if not directory.exists():
            continue
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}
        )
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_git_sha(root: Path) -> str:
    git_path = root / ".git"
    if git_path.is_file():
        pointer = git_path.read_text(encoding="utf-8").strip()
        if pointer.startswith("gitdir:"):
            git_path = (root / pointer.split(":", 1)[1].strip()).resolve()
    head = git_path / "HEAD"
    if not head.exists():
        return "unavailable"
    value = head.read_text(encoding="utf-8").strip()
    if not value.startswith("ref:"):
        return value
    ref = value.split(" ", 1)[1]
    ref_path = git_path / ref
    if ref_path.exists():
        return ref_path.read_text(encoding="utf-8").strip()
    packed_refs = git_path / "packed-refs"
    if packed_refs.exists():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(("#", "^")):
                sha, name = line.split(" ", 1)
                if name == ref:
                    return sha
    return "unavailable"
