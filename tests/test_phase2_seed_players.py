import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import Settings
from database import create_database
from modules.countries.seed import seed_countries, load_seed_file
from modules.players.service import PlayerService
from engine.country_engine import CountryEngine, CountryClaimError
from modules.news.briefing import build_initial_briefing
from engine.world_engine import WorldEngine


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        bale_token="",
        owner_id=1967315238,
        database_mode="sqlite",
        database_url="",
        sqlite_path=tmp_path / "p2.db",
        log_level="WARNING",
        world_start_date="2020-01-01",
        real_days_per_game_year=15,
    )


def test_seed_has_30_and_sources():
    data = load_seed_file()
    assert len(data["countries"]) == 30
    for c in data["countries"]:
        assert c.get("country_code")
        assert c.get("source_name")
        assert c.get("confidence")
        assert "population_ref" in c or c.get("population") is not None


def test_seed_and_registration_and_claim(settings):
    async def _t():
        db = await create_database(settings)
        n = await seed_countries(db)
        assert n == 30
        rows = await db.fetch("SELECT country_code FROM countries")
        assert len(rows) == 30
        # source metadata present
        ir = await db.fetchrow(
            "SELECT * FROM country_baselines WHERE country_code='IR'"
        )
        assert ir is not None
        assert ir.get("source_note") or ir.get("confidence")

        players = PlayerService(db)
        p = await players.register_or_update(42, username="u", display_name="User")
        assert p["player_id"] == 42
        p2 = await players.register_or_update(42, username="u2")
        assert p2["player_id"] == 42

        eng = CountryEngine(db)
        c = await eng.claim_country(42, "IR")
        assert c["owner_player_id"] == 42
        with pytest.raises(CountryClaimError):
            await eng.claim_country(99, "IR")
        with pytest.raises(CountryClaimError):
            await eng.claim_country(42, "US")

        world = WorldEngine(db)
        await world.ensure_initialized()
        text = await build_initial_briefing(db, world, "IR")
        assert "ایران" in text or "IR" in text
        assert "2020" in text or "تاریخ" in text
        await players.set_briefing_sent(42)
        assert await players.briefing_sent(42)
        await db.close()
    run(_t())
