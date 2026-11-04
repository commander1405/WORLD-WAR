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
        except Exception:
            log.exception("daily payout")
        await asyncio.sleep(60)


async def group_log_loop(game: Game, bot):
    """Flush queued group logs to main Bale group when possible."""
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
                    # re-queue lightly
                    await game.log_activity(r.get("kind") or "group_log", text)
        except Exception:
            log.exception("group log loop")
        await asyncio.sleep(15)


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
