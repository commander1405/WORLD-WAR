"""WORLD WAR entrypoint — Railway worker & local Pydroid3."""
from __future__ import annotations

import asyncio
import logging
import sys

from config.settings import load_settings
from database import create_database
from engine.world_engine import WorldEngine
from engine.country_engine import CountryEngine
from engine.event_engine import EventEngine
from bot.main import create_bot, register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("worldwar")


async def async_main() -> None:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level)
    log.info("DATABASE_MODE=%s", settings.database_mode)

    db = await create_database(settings)
    if not await db.health_check():
        raise RuntimeError("Database health check failed")

    world = WorldEngine(
        db,
        game_start=settings.world_start_date,
        real_days_per_year=settings.real_days_per_game_year,
    )
    await world.ensure_initialized()
    gdate = await world.current_game_date()
    log.info("World game date: %s", gdate.isoformat())

    app_ctx = {
        "settings": settings,
        "db": db,
        "world": world,
        "countries": CountryEngine(db),
        "events": EventEngine(db),
    }

    if not settings.bale_token:
        log.warning("BALE_TOKEN not set — running infrastructure-only (no bot polling)")
        # Keep process alive briefly for health verification on Railway misconfig diagnosis
        await asyncio.sleep(1)
        await db.close()
        return

    bot = await create_bot(settings.bale_token)
    register_handlers(bot, app_ctx)
    log.info("Starting Bale bot...")
    try:
        # python-bale-bot run patterns vary by version
        if hasattr(bot, "run"):
            await bot.run()
        elif hasattr(bot, "start"):
            await bot.start()
        else:
            raise RuntimeError("Unsupported python-bale-bot API — check library version")
    finally:
        await db.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
