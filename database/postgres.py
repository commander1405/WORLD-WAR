"""PostgreSQL backend (Railway / production)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Sequence

from database.interface import Database

try:
    import asyncpg
except ImportError:  # optional unless DATABASE_MODE=postgres
    asyncpg = None  # type: ignore

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class PostgresDatabase(Database):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if asyncpg is None:
            raise RuntimeError("asyncpg is not installed but DATABASE_MODE=postgres")
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=1,
                max_size=10,
                command_timeout=60,
            )
        except Exception as exc:
            log.exception("PostgreSQL connection failed")
            raise RuntimeError(
                f"PostgreSQL connection failed (DATABASE_MODE=postgres). "
                f"Not falling back to SQLite. Error: {exc}"
            ) from exc
        log.info("PostgreSQL pool ready")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _pool_or_raise(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("PostgreSQL pool is not connected")
        return self._pool

    async def execute(self, sql: str, args: Sequence[Any] = ()) -> str:
        pool = self._pool_or_raise()
        return await pool.execute(self._convert(sql), *args)

    async def fetch(self, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
        pool = self._pool_or_raise()
        rows = await pool.fetch(self._convert(sql), *args)
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, args: Sequence[Any] = ()) -> Optional[dict[str, Any]]:
        pool = self._pool_or_raise()
        row = await pool.fetchrow(self._convert(sql), *args)
        return dict(row) if row else None

    async def fetchval(self, sql: str, args: Sequence[Any] = ()) -> Any:
        pool = self._pool_or_raise()
        return await pool.fetchval(self._convert(sql), *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        pool = self._pool_or_raise()
        async with pool.acquire() as conn:
            async with conn.transaction():
                yield _PostgresConn(conn)

    async def health_check(self) -> bool:
        try:
            val = await self.fetchval("SELECT 1")
            return val == 1
        except Exception:
            log.exception("PostgreSQL health check failed")
            return False

    async def migrate(self) -> None:
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        applied = {r["version"] for r in await self.fetch("SELECT version FROM schema_migrations")}
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for path in files:
            ver = path.name
            if ver in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # strip SQLite-only sections if marked
            sql = _strip_dialect(sql, "postgres")
            async with self.transaction() as tx:
                for stmt in _split_sql(sql):
                    if stmt.strip():
                        await tx.execute(stmt)
                await tx.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    (ver,),
                )
            log.info("Applied migration %s", ver)

    @staticmethod
    def _convert(sql: str) -> str:
        """Keep $1-style placeholders (asyncpg native)."""
        return sql


class _PostgresConn(Database):
    """Single-connection adapter used inside transactions."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def connect(self) -> None:  # pragma: no cover
        pass

    async def close(self) -> None:  # pragma: no cover
        pass

    async def execute(self, sql: str, args: Sequence[Any] = ()) -> str:
        return await self._conn.execute(sql, *args)

    async def fetch(self, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(sql, *args)
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, args: Sequence[Any] = ()) -> Optional[dict[str, Any]]:
        row = await self._conn.fetchrow(sql, *args)
        return dict(row) if row else None

    async def fetchval(self, sql: str, args: Sequence[Any] = ()) -> Any:
        return await self._conn.fetchval(sql, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        yield self

    async def health_check(self) -> bool:
        return True

    async def migrate(self) -> None:
        raise RuntimeError("migrate() on transactional connection is not supported")


def _strip_dialect(sql: str, keep: str) -> str:
    """Optional blocks: -- DIALECT:sqlite ... -- END DIALECT"""
    lines = sql.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        if line.strip().startswith("-- DIALECT:"):
            dialect = line.split(":", 1)[1].strip().lower()
            skip = dialect != keep
            continue
        if line.strip() == "-- END DIALECT":
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out)


def _split_sql(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if ";" in line:
            chunk = "\n".join(buf)
            for piece in chunk.split(";"):
                piece = piece.strip()
                if piece:
                    parts.append(piece)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts
