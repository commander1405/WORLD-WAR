"""Automatic world cycle: AI economy ticks without player messages.

Prevents duplicate ticks via world_state.last_tick_at + transaction guard.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from database.interface import Database
from engine.world_engine import WorldEngine

log = logging.getLogger(__name__)


class WorldTicker:
    def __init__(
        self,
        db: Database,
        world: WorldEngine,
        ai,
        *,
        interval_seconds: int = 300,
    ):
        self.db = db
        self.world = world
        self.ai = ai
        self.interval = max(30, int(interval_seconds))
        self._task: asyncio.Task | None = None
        self._stopping = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="world-ticker")
        log.info("WorldTicker started (interval=%ss)", self.interval)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("WorldTicker stopped")

    async def _loop(self) -> None:
        # small initial delay so bot ready logs appear first
        await asyncio.sleep(5)
        while not self._stopping:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("WorldTicker iteration failed")
            await asyncio.sleep(self.interval)

    async def ensure_ai_tick_column(self) -> None:
        try:
            await self.db.execute(
                "ALTER TABLE world_state ADD COLUMN last_ai_tick_at TEXT"
            )
        except Exception:
            pass

    async def run_once(self) -> bool:
        """Run one AI world tick if not duplicated. Returns True if executed."""
        await self.ensure_ai_tick_column()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        # Claim tick slot using last_ai_tick_at (separate from calendar last_tick_at)
        async with self.db.transaction() as tx:
            st = await tx.fetchrow("SELECT * FROM world_state WHERE id = 1")
            if not st:
                return False
            last = st.get("last_ai_tick_at")
            if last:
                try:
                    last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - last_dt).total_seconds()
                    if elapsed < self.interval * 0.9:
                        log.debug("Skip AI tick — last AI tick %.0fs ago", elapsed)
                        return False
                except Exception:
                    pass
            await tx.execute(
                "UPDATE world_state SET last_ai_tick_at = $1 WHERE id = 1",
                (now_iso,),
            )

        # Outside lock: AI decisions (each writes its own rows)
        n = await self.ai.tick_all(limit=30)
        gdate = await self.world.current_game_date()
        await self.db.execute(
            """
            INSERT INTO events (game_date, real_time, event_type, summary)
            VALUES ($1, $2, $3, $4)
            """,
            (
                gdate.isoformat(),
                now_iso,
                "world_tick",
                f"Automatic AI tick processed {n} countries",
            ),
        )
        if n > 0:
            await self.db.execute(
                """
                INSERT INTO news_items (game_date, real_time, headline, body, importance)
                VALUES ($1, $2, $3, $4, 1)
                """,
                (
                    gdate.isoformat(),
                    now_iso,
                    "چرخه اقتصادی جهان",
                    f"{n} کشور تحت کنترل AI تصمیم اقتصادی گرفتند.",
                ),
            )
        log.info("World tick done — AI countries=%s game_date=%s", n, gdate.isoformat())
        return True
