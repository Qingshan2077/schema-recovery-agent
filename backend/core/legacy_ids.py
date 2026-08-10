"""Persistent compatibility mapping for legacy session identifiers."""

from __future__ import annotations

import os
import sqlite3
from typing import Literal

from backend.config import Config
from backend.core.identity import canonicalize_legacy_id


class LegacyIdStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "runtime_identity.db")
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS legacy_session_map (
                    legacy_session_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(legacy_session_id, entity_type),
                    UNIQUE(canonical_id)
                )
                """
            )

    def resolve(
        self,
        legacy_session_id: str | None,
        *,
        entity_type: Literal["thread", "run"],
    ) -> str:
        if not legacy_session_id:
            return canonicalize_legacy_id(None, entity_type=entity_type)

        expected_prefix = "thr_" if entity_type == "thread" else "run_"
        if legacy_session_id.startswith(expected_prefix):
            return canonicalize_legacy_id(legacy_session_id, entity_type=entity_type)

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT canonical_id FROM legacy_session_map
                WHERE legacy_session_id = ? AND entity_type = ?
                """,
                (legacy_session_id, entity_type),
            ).fetchone()
            if row:
                return str(row[0])
            canonical_id = canonicalize_legacy_id(legacy_session_id, entity_type=entity_type)
            connection.execute(
                """
                INSERT OR IGNORE INTO legacy_session_map(
                    legacy_session_id, entity_type, canonical_id
                ) VALUES (?, ?, ?)
                """,
                (legacy_session_id, entity_type, canonical_id),
            )
            resolved = connection.execute(
                """
                SELECT canonical_id FROM legacy_session_map
                WHERE legacy_session_id = ? AND entity_type = ?
                """,
                (legacy_session_id, entity_type),
            ).fetchone()
            return str(resolved[0])
