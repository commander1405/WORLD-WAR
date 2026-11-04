"""Shared async database interface for PostgreSQL and SQLite."""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional, Sequence


class Database(ABC):
    """Minimal common API used by game modules."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def execute(self, sql: str, args: Sequence[Any] = ()) -> str:
        """Run a statement. Returns status/rowcount string."""

    @abstractmethod
    async def fetch(self, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Return list of row dicts."""

    @abstractmethod
    async def fetchrow(self, sql: str, args: Sequence[Any] = ()) -> Optional[dict[str, Any]]:
        """Return one row dict or None."""

    @abstractmethod
    async def fetchval(self, sql: str, args: Sequence[Any] = ()) -> Any:
        """Return a single value."""

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["Database"]:
        """Yield a connection/context inside a transaction."""

    @abstractmethod
    async def health_check(self) -> bool:
        """True if the database responds."""

    @abstractmethod
    async def migrate(self) -> None:
        """Apply pending schema migrations."""
