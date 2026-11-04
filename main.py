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


async def daily_loop(game: Game):
    while True:
        try:
            n = await game.daily_payout_all()
            if n:
                log.info("Daily payout countries=%s", n)
        except Exception:
            log.exception("daily payout")
        await asyncio.sleep(60)


async def async_main() -> None:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level)
    db = await create_database(settings)
    try:
        if not await db.health_check():
            raise RuntimeError("DB health failed")
        game = Game(db, owner_id=settings.owner_id, group_id="@warworld3")
        await game.bootstrap()
        log.info("New Generation world ready")

        asyncio.create_task(daily_loop(game))

        if not settings.bale_token:
            log.error("BALE_TOKEN missing — offline bootstrap only")
            await game.daily_payout_all()
            return

        bot = await create_bot(settings.bale_token)
        register_handlers(bot, {"game": game, "settings": settings, "db": db})
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
