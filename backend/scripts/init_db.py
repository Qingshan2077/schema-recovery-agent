"""Initialize the demo MySQL database.

Usage:
    python -m backend.scripts.init_db
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pymysql

from backend.config import Config

ROOT = Path(__file__).resolve().parents[2]


def _connect_without_db():
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )


def _split_mysql_script(sql: str) -> list[str]:
    statements: list[str] = []
    delimiter = ";"
    buffer: list[str] = []

    for raw_line in sql.splitlines():
        line = raw_line.rstrip()
        if line.strip().upper().startswith("DELIMITER "):
            if buffer:
                statements.append("\n".join(buffer).strip())
                buffer = []
            delimiter = line.split(None, 1)[1]
            continue
        buffer.append(line)
        if line.endswith(delimiter):
            stmt = "\n".join(buffer).strip()
            stmt = stmt[: -len(delimiter)].strip()
            if stmt:
                statements.append(stmt)
            buffer = []

    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def _execute_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    statements = _split_mysql_script(sql)
    with conn.cursor() as cursor:
        for stmt in statements:
            if stmt.strip():
                cursor.execute(stmt)


def main() -> None:
    last_error: Exception | None = None
    conn = None
    for _ in range(5):
        try:
            conn = _connect_without_db()
            break
        except Exception as exc:  # pragma: no cover - runtime helper
            last_error = exc
            time.sleep(2)
    if conn is None:
        raise RuntimeError(f"Could not connect to MySQL: {last_error}")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE {Config.DB_NAME}")

        for name in ["sim_schema.sql", "sim_sp.sql", "seed_data.sql"]:
            _execute_file(conn, ROOT / "data" / name)

        target_orm = Path(Config.DATA_DIR)
        if not target_orm.is_absolute():
            target_orm = ROOT / target_orm
        target_orm = target_orm / "orm"
        target_orm.mkdir(parents=True, exist_ok=True)
        for src in (ROOT / "data" / "orm").glob("*.xml"):
            destination = target_orm / src.name
            if src.resolve() == destination.resolve():
                continue
            shutil.copy2(src, destination)
    finally:
        conn.close()


if __name__ == "__main__":
    main()


