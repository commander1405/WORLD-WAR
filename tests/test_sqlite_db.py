"""SQLite integration tests."""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# Ensure package imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from database import create_database
from engine.world_engine import WorldEngine
from engine.country_engine import CountryEngine, CountryClaimError


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def test_sqlite_migrate_and_health(db_path):
    async def _t():
        settings = Settings(
            bale_token="",
            database_mode="sqlite",
            database_url="",
            sqlite_path=db_path,
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        assert await db.health_check()
        world = WorldEngine(db)
        await world.ensure_initialized()
        d = await world.current_game_date()
        assert d.year >= 2020
        await db.close()
    run(_t())


def test_country_claim_atomic(db_path):
    async def _t():
        settings = Settings(
            bale_token="",
            database_mode="sqlite",
            database_url="",
            sqlite_path=db_path,
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        await db.execute(
            "INSERT INTO country_baselines (country_code, name_en, reference_date) VALUES ($1, $2, $3)",
            ("TST", "Testland", "2020-01-01"),
        )
        await db.execute(
            "INSERT INTO countries (country_code, name_en, controlled_by) VALUES ($1, $2, $3)",
            ("TST", "Testland", "ai"),
        )
        eng = CountryEngine(db)
        c1 = await eng.claim_country(101, "TST", username="a")
        assert c1["owner_player_id"] == 101
        with pytest.raises(CountryClaimError):
            await eng.claim_country(202, "TST", username="b")
        await db.close()
    run(_t())
