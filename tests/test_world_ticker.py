import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import Settings
from database import create_database
from modules.countries.seed import seed_countries
from modules.countries.management import CountryManagement
from engine.world_engine import WorldEngine
from engine.economy_engine import EconomyEngine
from engine.ai_engine import AIEngine
from engine.world_ticker import WorldTicker


def run(c):
    return asyncio.run(c)


def test_ticker_runs_and_dedupes(tmp_path):
    async def _t():
        settings = Settings(
            bale_token="",
            owner_id=0,
            database_mode="sqlite",
            database_url="",
            sqlite_path=tmp_path / "tick.db",
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        await seed_countries(db)
        world = WorldEngine(db)
        await world.ensure_initialized()
        mgmt = CountryManagement(db, world, EconomyEngine(db))
        await mgmt.ensure_schema()
        ai = AIEngine(db, world, mgmt)
        ticker = WorldTicker(db, world, ai, interval_seconds=60)
        ok1 = await ticker.run_once()
        assert ok1 is True
        ok2 = await ticker.run_once()  # should skip — too soon
        assert ok2 is False
        ev = await db.fetch("SELECT * FROM events WHERE event_type='world_tick'")
        assert len(ev) >= 1
        await db.close()
    run(_t())
