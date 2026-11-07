"""WORLD WAR New Generation entrypoint."""
from __future__ import annotations

import asyncio
import logging
import sys

from config.settings import load_settings
from database import create_database
from modules.ng.game import Game
from bot.ng_ui import create_bot, register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("worldwar")

# quiet noisy libraries
for name in ("httpx", "httpcore", "asyncio", "bale", "aiohttp"):
    logging.getLogger(name).setLevel(logging.WARNING)

MAIN_GROUP = "@warworld3"


async def queue_nightly_if_needed(game: Game):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    TEHRAN = ZoneInfo("Asia/Tehran")
    today = datetime.now(TEHRAN).date().isoformat()
    try:
        meta = await game.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if (meta or {}).get("last_nightly_date") == today:
            return
        text = await game.build_nightly_report()
        await game.log_activity("nightly_report", text)
        # also DM owner
        try:
            if game.owner_id:
                await game.log_activity(
                    "dm_notice",
                    text[:3500],
                    None,
                    int(game.owner_id),
                )
        except Exception:
            log.exception("nightly owner dm")
        try:
            await game.db.execute(
                "UPDATE world_meta SET last_nightly_date=$1 WHERE id=1", (today,)
            )
        except Exception:
            # column may missing — try add via raw
            try:
                await game.db.execute("ALTER TABLE world_meta ADD COLUMN last_nightly_date TEXT")
                await game.db.execute(
                    "UPDATE world_meta SET last_nightly_date=$1 WHERE id=1", (today,)
                )
            except Exception:
                log.exception("set last_nightly_date")
        log.info("Nightly report queued for %s", today)
    except Exception:
        log.exception("queue_nightly_if_needed")




async def daily_loop(game: Game):
    """Pay daily income only after Tehran midnight; workshop jobs every minute."""
    from datetime import datetime, timedelta, time as dtime
    from zoneinfo import ZoneInfo
    TEHRAN = ZoneInfo("Asia/Tehran")
    while True:
        try:
            now = datetime.now(TEHRAN)
            today = now.date().isoformat()
            meta = await game.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
            last = (meta or {}).get("last_daily_date")
            # Pay once when Tehran calendar day advances (right after 00:00)
            if last != today and now.hour == 0:
                n = await game.daily_payout_all()
                try:
                    await game.db.execute(
                        "UPDATE world_meta SET last_daily_date=$1 WHERE id=1", (today,)
                    )
                except Exception:
                    log.exception("set last_daily_date")
                if n:
                    log.info("Daily payout countries=%s date=%s", n, today)
                    await queue_nightly_if_needed(game)
            elif last != today and now.hour > 0:
                # Bot was offline at midnight — catch up once after restart
                n = await game.daily_payout_all()
                try:
                    await game.db.execute(
                        "UPDATE world_meta SET last_daily_date=$1 WHERE id=1", (today,)
                    )
                except Exception:
                    log.exception("set last_daily_date catchup")
                if n:
                    log.info("Daily payout catch-up countries=%s date=%s", n, today)
                    await queue_nightly_if_needed(game)
            await queue_nightly_if_needed(game)
            done = await game.complete_due_jobs()
            if done:
                log.info("Workshop jobs completed=%s", done)
        except Exception:
            log.exception("daily/workshop loop")
        # Near midnight check more often
        now = datetime.now(TEHRAN)
        if now.hour == 23 or now.hour == 0:
            await asyncio.sleep(20)
        else:
            await asyncio.sleep(60)


async def group_log_loop(game: Game, bot):
    while True:
        try:
            rows = await game.pop_group_logs(10)
            for r in rows:
                text = r.get("summary") or ""
                if not text:
                    continue
                kind = r.get("kind") or ""
                try:
                    msg = None
                    if hasattr(bot, "send_message"):
                        msg = await bot.send_message(MAIN_GROUP, text[:3500])
                    # Pin UN statements
                    if kind in ("group_pin_statement", "nightly_report", "group_pin") and msg is not None:
                        mid = getattr(msg, "message_id", None) or getattr(msg, "id", None)
                        if mid is not None:
                            pinned = False
                            for method, args in (
                                ("pin_chat_message", (MAIN_GROUP, mid)),
                                ("pin_message", (MAIN_GROUP, mid)),
                                ("pin_chat_message", (MAIN_GROUP, mid, True)),
                            ):
                                if hasattr(bot, method):
                                    try:
                                        await getattr(bot, method)(*args)
                                        pinned = True
                                        break
                                    except Exception:
                                        log.exception("pin via %s failed", method)
                            if not pinned:
                                log.warning("could not pin message id=%s kind=%s", mid, kind)
                except Exception:
                    log.exception("group log send failed")
                    await game.log_activity(r.get("kind") or "group_log", text)
        except Exception:
            log.exception("group log loop")
        await asyncio.sleep(15)


async def dm_notice_loop(game: Game, bot):
    """Send queued private notices (tax, condemn) without re-running finance."""
    while True:
        try:
            rows = await game.db.fetch(
                "SELECT * FROM ng_activity WHERE kind='dm_notice' ORDER BY id ASC"
            )
            batch = rows[:15]
            for r in batch:
                pid = r.get("player_id")
                text = r.get("summary") or ""
                try:
                    if pid and hasattr(bot, "send_message"):
                        await bot.send_message(int(pid), text[:3500])
                except Exception:
                    log.exception("dm_notice failed player=%s", pid)
                await game.db.execute("DELETE FROM ng_activity WHERE id=$1", (r["id"],))
                await asyncio.sleep(0.35)
        except Exception:
            log.exception("dm_notice loop")
        await asyncio.sleep(20)


async def owner_inbox_loop(game: Game, bot, owner_id: int):

    if not owner_id:
        return
    while True:
        try:
            rows = await game.pop_owner_inbox(5)
            for r in rows:
                text = f"{r.get('title') or ''}\n\n{r.get('body') or ''}\n\nاز پنل مالک بررسی کنید."
                try:
                    if hasattr(bot, "send_message"):
                        await bot.send_message(int(owner_id), text[:3500])
                except Exception:
                    log.exception("owner inbox send failed")
                    await game._owner_inbox(
                        r.get("kind") or "note",
                        int(r.get("ref_id") or 0),
                        r.get("title") or "",
                        r.get("body") or "",
                    )
        except Exception:
            log.exception("owner inbox loop")
        await asyncio.sleep(12)


async def async_main() -> None:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level)
    for name in ("httpx", "httpcore", "asyncio", "bale", "aiohttp"):
        logging.getLogger(name).setLevel(logging.WARNING)
    db = await create_database(settings)
    log.info("DATABASE_MODE=%s", settings.database_mode)
    if settings.is_sqlite:
        log.info("SQLite file: %s", settings.sqlite_path)

    try:
        if not await db.health_check():
            raise RuntimeError("DB health failed")
        game = Game(db, owner_id=settings.owner_id, group_id=MAIN_GROUP)
        await game.bootstrap()
        log.info("New Generation world ready owner_id=%s", settings.owner_id)

        asyncio.create_task(daily_loop(game))

        if not settings.bale_token:
            log.error("BALE_TOKEN missing — offline bootstrap only")
            await game.daily_payout_all()
            return

        bot = await create_bot(settings.bale_token)
        register_handlers(bot, {"game": game, "settings": settings, "db": db})
        asyncio.create_task(group_log_loop(game, bot))
        asyncio.create_task(owner_inbox_loop(game, bot, settings.owner_id))
        asyncio.create_task(dm_notice_loop(game, bot))
        log.info("Starting bot connect()")
        async with bot:
            await bot.connect()
    finally:
        await db.close()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.info("stop")


if __name__ == "__main__":
    main()
