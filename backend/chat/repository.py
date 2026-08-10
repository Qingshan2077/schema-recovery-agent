"""Transactional SQLite repository for chat threads, runs and evidence artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Protocol

from backend.chat.contracts import ChatEventRecord, ChatMessageRecord, ChatThreadRecord, EventPage, QARunRecord, StartedRun
from backend.core.identity import RunIdentity, new_id


class ChatRepository(Protocol):
    def create_thread(self, *, owner_id: str, title: str = "") -> ChatThreadRecord: ...
    def get_thread(self, thread_id: str, *, owner_id: str) -> ChatThreadRecord | None: ...
    def start_run(self, *, thread_id: str, owner_id: str, content: str, idempotency_key: str | None) -> StartedRun: ...
    def complete_run(self, run_id: str, *, result: dict[str, Any]) -> ChatMessageRecord | None: ...


class SQLiteChatRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_path = Path(__file__).resolve().parent / "migrations" / "001_phase2_chat.sql"
        self._migrate()

    def create_thread(self, *, owner_id: str, title: str = "") -> ChatThreadRecord:
        now = _now()
        thread_id = new_id("thread")
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO chat_threads(thread_id, owner_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, owner_id, title, now, now),
            )
        return ChatThreadRecord(thread_id=thread_id, title=title, created_at=now, updated_at=now, last_sequence=0)

    def ensure_thread(self, thread_id: str, *, owner_id: str) -> ChatThreadRecord:
        existing = self.get_thread(thread_id, owner_id=owner_id)
        if existing:
            return existing
        now = _now()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO chat_threads(thread_id, owner_id, title, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
                (thread_id, owner_id, now, now),
            )
        return ChatThreadRecord(thread_id=thread_id, title="", created_at=now, updated_at=now, last_sequence=0)

    def get_thread(self, thread_id: str, *, owner_id: str) -> ChatThreadRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_threads WHERE thread_id = ? AND owner_id = ?",
                (thread_id, owner_id),
            ).fetchone()
            if row is None:
                return None
            messages = connection.execute(
                "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY created_at, rowid",
                (thread_id,),
            ).fetchall()
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS value FROM chat_events WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()["value"]
        return ChatThreadRecord(
            thread_id=row["thread_id"], title=row["title"], created_at=row["created_at"], updated_at=row["updated_at"],
            messages=[_message(item) for item in messages],
            last_sequence=int(sequence),
        )

    def start_run(
        self,
        *,
        thread_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str | None,
    ) -> StartedRun:
        now = _now()
        identity = RunIdentity.create(thread_id=thread_id)
        message_id = new_id("message")
        with self._transaction() as connection:
            owner = connection.execute(
                "SELECT 1 FROM chat_threads WHERE thread_id = ? AND owner_id = ?",
                (thread_id, owner_id),
            ).fetchone()
            if owner is None:
                raise KeyError("thread_not_found")
            if idempotency_key:
                existing = connection.execute(
                    """SELECT r.run_id, r.trace_id, r.user_message_id
                       FROM chat_messages m JOIN qa_runs r ON r.user_message_id = m.message_id
                       WHERE m.thread_id = ? AND m.idempotency_key = ?""",
                    (thread_id, idempotency_key),
                ).fetchone()
                if existing:
                    return StartedRun(
                        thread_id=thread_id, message_id=existing["user_message_id"],
                        run_id=existing["run_id"], trace_id=existing["trace_id"], reused=True,
                        events_url=f"/api/v2/threads/{thread_id}/events?after_sequence=0",
                    )
            connection.execute(
                "INSERT INTO chat_messages(message_id, thread_id, role, content, content_hash, run_id, idempotency_key, created_at) VALUES (?, ?, 'user', ?, ?, ?, ?, ?)",
                (message_id, thread_id, content, _content_hash(content), identity.run_id, idempotency_key, now),
            )
            connection.execute(
                "INSERT INTO qa_runs(run_id, thread_id, trace_id, user_message_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'running', ?, ?)",
                (identity.run_id, thread_id, identity.trace_id, message_id, now, now),
            )
            connection.execute("UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?", (now, thread_id))
            self._append_event_tx(connection, thread_id, identity.run_id, "run.started", "running", {})
            self._append_event_tx(connection, thread_id, identity.run_id, "qa.message.accepted", "running", {"message_id": message_id})
        return StartedRun(
            thread_id=thread_id, message_id=message_id, run_id=identity.run_id, trace_id=identity.trace_id,
            events_url=f"/api/v2/threads/{thread_id}/events?after_sequence=0",
        )

    def complete_run(self, run_id: str, *, result: dict[str, Any]) -> ChatMessageRecord | None:
        now = _now()
        status = str(result["status"])
        output = result.get("output") or {}
        answer = output.get("answer") or output.get("clarification_question")
        if not answer and result.get("error"):
            answer = result["error"].get("message", "QA run failed")
        with self._transaction() as connection:
            run = connection.execute("SELECT * FROM qa_runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise KeyError("run_not_found")
            assistant_id = run["assistant_message_id"]
            if assistant_id:
                existing = connection.execute("SELECT * FROM chat_messages WHERE message_id = ?", (assistant_id,)).fetchone()
                return _message(existing) if existing else None
            assistant_id = new_id("message")
            connection.execute(
                "INSERT INTO chat_messages(message_id, thread_id, role, content, content_hash, run_id, structured_json, created_at) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)",
                (assistant_id, run["thread_id"], str(answer or ""), _content_hash(str(answer or "")), run_id, _json(output), now),
            )
            connection.execute(
                "UPDATE qa_runs SET assistant_message_id = ?, status = ?, intent = ?, prompt_versions_json = ?, result_json = ?, error_json = ?, error_code = ?, completed_at = ?, updated_at = ? WHERE run_id = ?",
                (
                    assistant_id, status, output.get("intent"),
                    _json({"qa": result.get("prompt_version")}) if result.get("prompt_version") else "{}",
                    _json(output), _json(result.get("error")) if result.get("error") else None,
                    (result.get("error") or {}).get("code"), now, now, run_id,
                ),
            )
            for citation in output.get("citations", []):
                connection.execute(
                    "INSERT OR REPLACE INTO chat_citations(citation_id, run_id, claim_id, tool_call_id, fact_ids_json, label, locator_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (citation["citation_id"], run_id, citation["claim_id"], None, _json(citation["fact_ids"]), citation["label"], _json(citation["locator"])),
                )
            for artifact in output.get("artifacts", []):
                connection.execute(
                    "INSERT OR REPLACE INTO chat_artifacts(artifact_id, run_id, artifact_type, schema_version, title, data_uri, data_hash, data_json, fact_ids_json) VALUES (?, ?, ?, '2.0', ?, ?, ?, ?, ?)",
                    (
                        artifact["artifact_id"], run_id, artifact["type"], artifact["title"], None,
                        _content_hash(_json(artifact["data"])), _json(artifact["data"]), _json(artifact["fact_ids"]),
                    ),
                )
            terminal_type = (
                "run.completed" if status in {"success", "degraded", "partial"}
                else "run.cancelled" if status == "cancelled"
                else "run.failed"
            )
            self._append_event_tx(connection, run["thread_id"], run_id, terminal_type, status, {"message_id": assistant_id, "result": output, "error": result.get("error")})
            connection.execute("UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?", (now, run["thread_id"]))
        return ChatMessageRecord(message_id=assistant_id, thread_id=run["thread_id"], role="assistant", content=str(answer or ""), structured=output, created_at=now)

    def append_event(self, *, thread_id: str, run_id: str, event_type: str, status: str, payload: dict[str, Any]) -> ChatEventRecord:
        with self._transaction() as connection:
            return self._append_event_tx(connection, thread_id, run_id, event_type, status, payload)

    def get_events(self, thread_id: str, *, owner_id: str, after_sequence: int = 0, limit: int = 100) -> EventPage:
        with self._connect() as connection:
            owner = connection.execute("SELECT 1 FROM chat_threads WHERE thread_id = ? AND owner_id = ?", (thread_id, owner_id)).fetchone()
            if owner is None:
                raise KeyError("thread_not_found")
            rows = connection.execute(
                "SELECT rowid, * FROM chat_events WHERE thread_id = ? AND sequence > ? ORDER BY sequence LIMIT ?",
                (thread_id, max(after_sequence, 0), min(max(limit, 1), 500)),
            ).fetchall()
        events = [_event(row) for row in rows]
        return EventPage(events=events, next_sequence=events[-1].sequence if events else after_sequence)

    def get_run(self, run_id: str, *, owner_id: str) -> QARunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT r.* FROM qa_runs r JOIN chat_threads t ON t.thread_id = r.thread_id WHERE r.run_id = ? AND t.owner_id = ?",
                (run_id, owner_id),
            ).fetchone()
        return _run(row) if row else None

    def request_cancel(self, run_id: str, *, owner_id: str) -> bool:
        now = _now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT r.thread_id FROM qa_runs r JOIN chat_threads t ON t.thread_id = r.thread_id WHERE r.run_id = ? AND t.owner_id = ? AND r.status = 'running'",
                (run_id, owner_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute("UPDATE qa_runs SET cancel_requested = 1, updated_at = ? WHERE run_id = ?", (now, run_id))
            self._append_event_tx(connection, row["thread_id"], run_id, "run.cancel_requested", "running", {})
            return True

    def _append_event_tx(self, connection: sqlite3.Connection, thread_id: str, run_id: str, event_type: str, status: str, payload: dict[str, Any]) -> ChatEventRecord:
        sequence = int(connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM chat_events WHERE thread_id = ?", (thread_id,)).fetchone()["value"])
        event_id = new_id("event")
        now = _now()
        connection.execute(
            "INSERT INTO chat_events(event_id, thread_id, run_id, sequence, event_type, status, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, thread_id, run_id, sequence, event_type, status, _json(payload), now),
        )
        return ChatEventRecord(event_id=event_id, thread_id=thread_id, run_id=run_id, sequence=sequence, event_type=event_type, status=status, payload=payload, created_at=now)

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(self.migration_path.read_text(encoding="utf-8"))

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _message(row: sqlite3.Row) -> ChatMessageRecord:
    return ChatMessageRecord(message_id=row["message_id"], thread_id=row["thread_id"], role=row["role"], content=row["content"], structured=json.loads(row["structured_json"]) if row["structured_json"] else None, created_at=row["created_at"])


def _event(row: sqlite3.Row) -> ChatEventRecord:
    return ChatEventRecord(event_id=row["event_id"], thread_id=row["thread_id"], run_id=row["run_id"], sequence=row["sequence"], event_type=row["event_type"], status=row["status"], payload=json.loads(row["payload_json"]), created_at=row["created_at"])


def _run(row: sqlite3.Row) -> QARunRecord:
    return QARunRecord(run_id=row["run_id"], thread_id=row["thread_id"], trace_id=row["trace_id"], user_message_id=row["user_message_id"], assistant_message_id=row["assistant_message_id"], status=row["status"], result=json.loads(row["result_json"]) if row["result_json"] else None, error=json.loads(row["error_json"]) if row["error_json"] else None, cancel_requested=bool(row["cancel_requested"]), created_at=row["created_at"], updated_at=row["updated_at"])
