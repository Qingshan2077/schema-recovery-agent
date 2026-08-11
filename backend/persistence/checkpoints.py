"""Persistent checkpointer/store capability adapters with fail-closed startup."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
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
        self._stack = AsyncExitStack()
        self._create_lock = asyncio.Lock()

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

    def validate_dependencies(self) -> None:
        """Validate the configured async persistence implementation without opening it."""

        capabilities = self.capabilities()
        try:
            if capabilities.backend == "sqlite":
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: F401
                from langgraph.store.sqlite.aio import AsyncSqliteStore  # noqa: F401
            else:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401
                from langgraph.store.postgres.aio import AsyncPostgresStore  # noqa: F401
        except ImportError as exc:
            raise PersistenceBackendUnavailable(
                f"async {capabilities.backend} LangGraph persistence is unavailable"
            ) from exc

    async def acreate(self) -> tuple[Any, Any]:
        if self._resources is not None:
            return self._resources
        async with self._create_lock:
            if self._resources is not None:
                return self._resources
            return await self._create_resources()

    async def _create_resources(self) -> tuple[Any, Any]:
        capabilities = self.capabilities()
        if capabilities.backend == "sqlite":
            try:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                from langgraph.store.sqlite.aio import AsyncSqliteStore
            except ImportError as exc:
                raise PersistenceBackendUnavailable(
                    "SQLite LangGraph persistence requires async SQLite checkpointer and store packages"
                ) from exc
            path = Path(self.sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            checkpointer = await self._enter(AsyncSqliteSaver.from_conn_string(str(path)))
            store_path = path.with_name(f"{path.stem}-store{path.suffix}")
            store = await self._enter(AsyncSqliteStore.from_conn_string(str(store_path)))
            await self._prepare(checkpointer)
            await self._prepare(store)
            self._resources = (checkpointer, store)
            return self._resources
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres.aio import AsyncPostgresStore
        except ImportError as exc:
            raise PersistenceBackendUnavailable(
                "PostgreSQL LangGraph persistence requires async postgres checkpoint/store packages"
            ) from exc
        checkpointer = await self._enter(AsyncPostgresSaver.from_conn_string(self.postgres_dsn))
        store = await self._enter(AsyncPostgresStore.from_conn_string(self.postgres_dsn))
        await self._prepare(checkpointer)
        await self._prepare(store)
        self._resources = (checkpointer, store)
        return self._resources

    async def aclose(self) -> None:
        async with self._create_lock:
            await self._stack.aclose()
            self._resources = None

    async def _enter(self, resource: Any) -> Any:
        if hasattr(resource, "__aenter__") and hasattr(resource, "__aexit__"):
            return await self._stack.enter_async_context(resource)
        return resource

    @staticmethod
    async def _prepare(resource: Any) -> None:
        setup = getattr(resource, "setup", None)
        if setup is not None:
            await setup()


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
