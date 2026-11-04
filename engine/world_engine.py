"""Server-authoritative world calendar.

Real time: every REAL_DAYS_PER_GAME_YEAR days => +1 game year from 2020-01-01.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Optional

from database.interface import Database


def _parse_iso_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def _parse_iso_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class WorldEngine:
    def __init__(self, db: Database, game_start: str = "2020-01-01", real_days_per_year: int = 15):
        self.db = db
        self.game_start = game_start
        self.real_days_per_year = real_days_per_year

    async def ensure_initialized(self) -> None:
        row = await self.db.fetchrow("SELECT id FROM world_state WHERE id = 1")
        if row:
            return
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO world_state (id, real_started_at, game_start_date, real_days_per_game_year, last_tick_at)
            VALUES (1, $1, $2, $3, $1)
            """,
            (now, self.game_start, self.real_days_per_year),
        )

    async def get_state(self) -> dict:
        row = await self.db.fetchrow("SELECT * FROM world_state WHERE id = 1")
        if not row:
            await self.ensure_initialized()
            row = await self.db.fetchrow("SELECT * FROM world_state WHERE id = 1")
        assert row
        return row

    def compute_game_date(self, real_started_at: str, game_start_date: str, real_days_per_year: int, at: Optional[datetime] = None) -> date:
        """Advance game calendar by full years from elapsed real time."""
        at = at or datetime.now(timezone.utc)
        started = _parse_iso_dt(real_started_at)
        elapsed_days = max(0.0, (at - started).total_seconds() / 86400.0)
        years = int(elapsed_days // real_days_per_year)
        start = _parse_iso_date(game_start_date)
        # Add years handling leap years via replace
        try:
            return start.replace(year=start.year + years)
        except ValueError:
            # Feb 29 -> Feb 28
            return start.replace(year=start.year + years, day=28)

    async def current_game_date(self) -> date:
        st = await self.get_state()
        return self.compute_game_date(
            st["real_started_at"],
            st["game_start_date"],
            int(st["real_days_per_game_year"]),
        )

    async def touch_tick(self) -> date:
        gdate = await self.current_game_date()
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE world_state SET last_tick_at = $1 WHERE id = 1",
            (now,),
        )
        return gdate
