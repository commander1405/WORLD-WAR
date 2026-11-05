"""SQLite backend (Android / Pydroid3 local)."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Sequence

import aiosqlite

from database.interface import Database

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _pg_to_qmark(sql: str, args: Sequence[Any] = ()) -> tuple[str, tuple]:
    """Convert $1-style placeholders to ? and expand repeated indices."""
    indices = [int(m.group(1)) for m in re.finditer(r"\$(\d+)", sql)]
    new_sql = re.sub(r"\$(\d+)", "?", sql)
    if not indices:
        return new_sql, tuple(args)
    new_args = tuple(args[i - 1] for i in indices)
    return new_sql, new_args


class SQLiteDatabase(Database):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._db: Optional[aiosqlite.Connection] = None
        self._tx_depth = 0

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        # Single-file mode on phone: avoid .db-wal/.db-shm looking like extra databases.
        # Data safety is preserved; checkpoint any leftover WAL on open.
        try:
            await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        await self._db.execute("PRAGMA journal_mode = DELETE")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.commit()
        log.info("SQLite ready at %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _db_or_raise(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("SQLite is not connected")
        return self._db

    async def execute(self, sql: str, args: Sequence[Any] = ()) -> str:
        db = self._db_or_raise()
        q, a = _pg_to_qmark(sql, args)
        cur = await db.execute(q, a)
        if self._tx_depth == 0:
            await db.commit()
        return f"rows={cur.rowcount}"

    async def fetch(self, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
        db = self._db_or_raise()
        q, a = _pg_to_qmark(sql, args)
        cur = await db.execute(q, a)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, args: Sequence[Any] = ()) -> Optional[dict[str, Any]]:
        db = self._db_or_raise()
        q, a = _pg_to_qmark(sql, args)
        cur = await db.execute(q, a)
        row = await cur.fetchone()
        return dict(row) if row else None

    async def fetchval(self, sql: str, args: Sequence[Any] = ()) -> Any:
        row = await self.fetchrow(sql, args)
        if not row:
            return None
        return next(iter(row.values()))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        db = self._db_or_raise()
        if self._tx_depth == 0:
            await db.execute("BEGIN")
        self._tx_depth += 1
        try:
            yield self
            self._tx_depth -= 1
            if self._tx_depth == 0:
                await db.commit()
        except Exception:
            self._tx_depth = max(0, self._tx_depth - 1)
            if self._tx_depth == 0:
                await db.rollback()
            raise

    async def health_check(self) -> bool:
        try:
            val = await self.fetchval("SELECT 1")
            return val == 1
        except Exception:
            log.exception("SQLite health check failed")
            return False

    async def migrate(self) -> None:
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        applied = {r["version"] for r in await self.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            ver = path.name
            if ver in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            sql = _strip_dialect(sql, "sqlite")
            async with self.transaction():
                # aiosqlite executescript for multi-statement
                db = self._db_or_raise()
                await db.executescript(sql)
                await db.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (ver,),
                )
            log.info("Applied migration %s", ver)


def _strip_dialect(sql: str, keep: str) -> str:
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
