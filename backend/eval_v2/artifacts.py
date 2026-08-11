"""Content-addressed, immutable eval artifact publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.eval_v2.hashing import canonical_json, content_hash


class ImmutableArtifactError(RuntimeError):
    pass


class EvalArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def create_run(self, eval_run_id: str, manifest: dict[str, Any]) -> str:
        directory = self.root / eval_run_id
        if directory.exists():
            raise ImmutableArtifactError("eval run artifact path already exists")
        directory.mkdir(parents=True)
        digest = self.write_once(eval_run_id, "manifest.json", manifest)
        self.write_once(eval_run_id, "manifest.sha256", {"hash": digest})
        return digest

    def write_once(self, eval_run_id: str, relative: str, payload: Any) -> str:
        directory = (self.root / eval_run_id).resolve()
        target = (directory / relative).resolve()
        if directory != target and directory not in target.parents:
            raise ImmutableArtifactError("artifact path escapes eval run")
        if target.exists():
            raise ImmutableArtifactError(f"artifact is immutable: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        wrapped = {
            "artifact_schema_version": "1.0",
            "producer": "eval_v2",
            "content_hash": content_hash(payload),
            "payload": payload,
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, target)
        return wrapped["content_hash"]

    def read(self, eval_run_id: str, relative: str) -> dict[str, Any]:
        target = self.root / eval_run_id / relative
        if not target.exists():
            raise KeyError(relative)
        wrapped = json.loads(target.read_text(encoding="utf-8"))
        if content_hash(wrapped["payload"]) != wrapped["content_hash"]:
            raise ImmutableArtifactError("artifact content hash mismatch")
        return wrapped

    def finalized(self, eval_run_id: str) -> bool:
        return (self.root / eval_run_id / "finalization.json").exists()
