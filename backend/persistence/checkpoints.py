"""Persistent checkpointer/store capability adapters with fail-closed startup."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


class PersistenceBackendUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistenceCapabilities:
    backend: Literal["sqlite", "postgres"]
    persistent: bool
    supports_history: bool
    supports_store: bool
    production_ready: bool


class LangGraphPersistenceFactory:
    def __init__(self, *, checkpoint_backend: str, store_backend: str, sqlite_path: str, postgres_dsn: str = ""):
        self.checkpoint_backend = checkpoint_backend
        self.store_backend = store_backend
        self.sqlite_path = sqlite_path
        self.postgres_dsn = postgres_dsn
        self._resources: tuple[Any, Any] | None = None
        self._stack = ExitStack()

    def capabilities(self) -> PersistenceCapabilities:
        backend = self.checkpoint_backend.casefold()
        store_backend = self.store_backend.casefold()
        if backend != store_backend:
            raise PersistenceBackendUnavailable(
                "checkpoint and store backends must match so a run cannot resume from split persistence"
            )
        if backend == "sqlite":
            return PersistenceCapabilities("sqlite", True, True, True, False)
        if backend == "postgres" and self.postgres_dsn:
            return PersistenceCapabilities("postgres", True, True, True, True)
        raise PersistenceBackendUnavailable("configured persistent checkpoint backend is unavailable")

    def create(self) -> tuple[Any, Any]:
        if self._resources is not None:
            return self._resources
        capabilities = self.capabilities()
        if capabilities.backend == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
                from langgraph.store.sqlite import SqliteStore
            except ImportError as exc:
                raise PersistenceBackendUnavailable(
                    "SQLite LangGraph persistence requires SQLite checkpointer and store packages"
                ) from exc
            path = Path(self.sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            checkpointer = self._enter(SqliteSaver.from_conn_string(str(path)))
            store_path = path.with_name(f"{path.stem}-store{path.suffix}")
            store = self._enter(SqliteStore.from_conn_string(str(store_path)))
            self._prepare(checkpointer)
            self._prepare(store)
            self._resources = (checkpointer, store)
            return self._resources
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from langgraph.store.postgres import PostgresStore
        except ImportError as exc:
            raise PersistenceBackendUnavailable(
                "PostgreSQL LangGraph persistence requires the postgres checkpoint/store packages"
            ) from exc
        checkpointer = self._enter(PostgresSaver.from_conn_string(self.postgres_dsn))
        store = self._enter(PostgresStore.from_conn_string(self.postgres_dsn))
        self._prepare(checkpointer)
        self._prepare(store)
        self._resources = (checkpointer, store)
        return self._resources

    def close(self) -> None:
        self._stack.close()
        self._resources = None

    def _enter(self, resource: Any) -> Any:
        if hasattr(resource, "__enter__") and hasattr(resource, "__exit__"):
            return self._stack.enter_context(resource)
        return resource

    @staticmethod
    def _prepare(resource: Any) -> None:
        setup = getattr(resource, "setup", None)
        if setup is not None:
            setup()


def checkpoint_config(*, run_id: str, thread_id: str, project_id: str, workflow_version: str, recursion_limit: int, max_concurrency: int) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": thread_id,
            "run_id": run_id,
            "checkpoint_ns": f"{project_id}/{workflow_version}",
        },
        "recursion_limit": recursion_limit,
        "max_concurrency": max_concurrency,
    }
