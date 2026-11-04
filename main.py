"""WORLD WAR entrypoint — Railway worker & local Termux/Pydroid3."""
from __future__ import annotations

import asyncio
import logging
import sys

from config.settings import load_settings
from database import create_database
from engine.world_engine import WorldEngine
from engine.country_engine import CountryEngine
from engine.event_engine import EventEngine
from engine.economy_engine import EconomyEngine
from engine.ai_engine import AIEngine
from modules.players.service import PlayerService
from modules.countries.seed import seed_countries
from modules.countries.management import CountryManagement
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
    if settings.owner_id:
        log.info("OWNER_ID configured: %s", settings.owner_id)

    db = await create_database(settings)
    try:
        if not await db.health_check():
            raise RuntimeError("Database health check failed")

        n = await seed_countries(db)
        log.info("Countries available: %s", n)

        world = WorldEngine(
            db,
            game_start=settings.world_start_date,
            real_days_per_year=settings.real_days_per_game_year,
        )
        await world.ensure_initialized()
        gdate = await world.current_game_date()
        log.info("World game date: %s", gdate.isoformat())

        economy = EconomyEngine(db)
        management = CountryManagement(db, world, economy)
        await management.ensure_schema()
        ai = AIEngine(db, world, management)

        app_ctx = {
            "settings": settings,
            "db": db,
            "world": world,
            "countries": CountryEngine(db),
            "events": EventEngine(db),
            "players": PlayerService(db),
            "economy": economy,
            "management": management,
            "ai": ai,
        }

        if not settings.bale_token:
            log.error(
                "BALE_TOKEN missing. Set environment BALE_TOKEN or local config "
                "(see config.example.py). Infrastructure check complete without bot."
            )
            return

        bot = await create_bot(settings.bale_token)
        register_handlers(bot, app_ctx)
        log.info("Starting Bale bot via async connect() (not Bot.run())...")
        # python-bale-bot 2.5.0: Bot.run() calls asyncio.run() internally and
        # cannot be awaited inside an already-running event loop.
        async with bot:
            await bot.connect()
    finally:
        await db.close()
        log.info("Database closed")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.info("Interrupted")


if __name__ == "__main__":
    main()
