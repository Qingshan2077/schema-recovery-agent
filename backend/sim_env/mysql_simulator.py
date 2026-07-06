"""MySQL access facade used by MCP tools and workers."""

from __future__ import annotations

from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from backend.config import Config


class MySQLSimulator:
    """Small database query wrapper.

    The project calls this class from tools instead of reaching directly for
    pymysql, which keeps tests and future adapters simple.
    """

    @classmethod
    def _connect(cls):
        return pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
        )

    @classmethod
    def execute_query(cls, sql: str, params: tuple[Any, ...] | None = None) -> list[dict]:
        conn = cls._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params or ())
                rows = cursor.fetchall()
                return list(rows)
        finally:
            conn.close()

    @classmethod
    def execute_dict(cls, sql: str, params: tuple[Any, ...] | None = None) -> list[dict]:
        return cls.execute_query(sql, params)

