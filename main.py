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

MAIN_GROUP = "@warworld3"


async def daily_loop(game: Game):
    while True:
        try:
            n = await game.daily_payout_all()
            if n:
                log.info("Daily payout countries=%s", n)
            done = await game.complete_due_jobs()
            if done:
                log.info("Workshop jobs completed=%s", done)
        except Exception:
            log.exception("daily/workshop loop")
        await asyncio.sleep(60)


async def group_log_loop(game: Game, bot):
    while True:
        try:
            rows = await game.pop_group_logs(10)
            for r in rows:
                text = r.get("summary") or ""
                if not text:
                    continue
                try:
                    if hasattr(bot, "send_message"):
                        await bot.send_message(MAIN_GROUP, text[:3500])
                except Exception:
                    log.exception("group log send failed")
                    await game.log_activity(r.get("kind") or "group_log", text)
        except Exception:
            log.exception("group log loop")
        await asyncio.sleep(15)


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
    db = await create_database(settings)
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
