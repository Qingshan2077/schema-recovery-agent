"""L3 global design-pattern memory backed by SQLite."""

from __future__ import annotations

import os
from backend.config import Config
import sqlite3


class GlobalMemory:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(Config.DATA_DIR, "global_memory.db")
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            existing = conn.execute("SELECT COUNT(*) FROM global_knowledge").fetchone()[0]
            if existing == 0:
                self._seed_default_knowledge(conn)
            conn.commit()
        finally:
            conn.close()

    def _seed_default_knowledge(self, conn):
        defaults = [
            ("naming", "fk_suffix", "_id", "Columns ending with _id usually reference another table", 1),
            ("naming", "associative_table_pattern", "table1_table2", "Two-entity table names often mark many-to-many joins", 1),
            ("naming", "primary_key_name", "id", "Most tables use id as primary key", 1),
            ("non_fk", "status_columns", "status,state,flag,type,stage", "State columns are usually not foreign keys", 1),
            ("non_fk", "time_columns", "created_at,updated_at,deleted_at,start_time,end_time", "Time columns are not foreign keys", 1),
            ("non_fk", "descriptive_columns", "name,title,description,comment,content,note,remark,address,url,email,phone,image,avatar", "Text columns are usually descriptive", 1),
            ("common_pattern", "user_x", "<table>.user_id -> users.id", "Common user relation", 1),
            ("common_pattern", "order_x", "<table>.order_id -> orders.id", "Common order relation", 1),
            ("common_pattern", "product_x", "<table>.product_id -> products.id", "Common product relation", 1),
        ]
        conn.executemany(
            "INSERT INTO global_knowledge (category, key, value, description, priority) VALUES (?, ?, ?, ?, ?)",
            defaults,
        )

    def get_by_category(self, category: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM global_knowledge WHERE category = ? ORDER BY priority DESC",
                (category,),
            ).fetchall()
            return [
                {"id": r[0], "category": r[1], "key": r[2], "value": r[3], "description": r[4], "priority": r[5]}
                for r in rows
            ]
        finally:
            conn.close()

    def add_experience_rule(self, pattern: str, rule: str):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO global_knowledge
                    (category, key, value, description, priority)
                VALUES ('experience', ?, ?, ?, 5)
                """,
                (pattern, rule, f"Accumulated experience rule: {rule}"),
            )
            conn.commit()
        finally:
            conn.close()




