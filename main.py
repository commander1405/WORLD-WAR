"""WORLD WAR entrypoint — Railway worker & local Termux/Pydroid3."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from config.settings import load_settings
from database import create_database
from engine.world_engine import WorldEngine
from engine.country_engine import CountryEngine
from engine.event_engine import EventEngine
from engine.economy_engine import EconomyEngine
from engine.ai_engine import AIEngine
from engine.world_ticker import WorldTicker
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
    ticker = None
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

        interval = int(os.getenv("WORLD_TICK_INTERVAL", "300"))
        ticker = WorldTicker(db, world, ai, interval_seconds=interval)

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
            "ticker": ticker,
        }

        if not settings.bale_token:
            log.error(
                "BALE_TOKEN missing. Set environment BALE_TOKEN or local config.py "
                "(gitignored). Running one offline world tick then exit."
            )
            await ticker.run_once()
            return

        bot = await create_bot(settings.bale_token)
        register_handlers(bot, app_ctx)
        # Verify registration against bot.events map used by 2.5.0
        n_handlers = len(getattr(bot, "events", {}).get("on_message") or [])
        log.info("on_message handlers attached: %s", n_handlers)
        if n_handlers < 1:
            raise RuntimeError("on_message handler was not registered")

        ticker.start()
        log.info("Starting Bale bot (async with + connect / single polling loop)...")
        async with bot:
            await bot.connect()
    finally:
        if ticker:
            await ticker.stop()
        await db.close()
        log.info("Database closed")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.info("Interrupted")


if __name__ == "__main__":
    main()
