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
from engine.country_engine import CountryEngine


def run(c):
    return asyncio.run(c)


@pytest.fixture
def env(tmp_path):
    async def _setup():
        settings = Settings(
            bale_token="",
            owner_id=0,
            database_mode="sqlite",
            database_url="",
            sqlite_path=tmp_path / "mgmt.db",
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        await seed_countries(db)
        world = WorldEngine(db)
        await world.ensure_initialized()
        eco = EconomyEngine(db)
        mgmt = CountryManagement(db, world, eco)
        await mgmt.ensure_schema()
        return db, world, eco, mgmt
    return _setup


def test_tax_and_invest_change_state(env):
    async def _t():
        db, world, eco, mgmt = await env()
        before = await db.fetchrow("SELECT * FROM country_economy WHERE country_code='IR'")
        msg = await mgmt.set_tax_rate("IR", 0.2, player_id=1)
        assert "مالیات" in msg or "tax" in msg.lower() or "✅" in msg
        after = await db.fetchrow("SELECT * FROM country_economy WHERE country_code='IR'")
        assert float(after["tax_rate"]) == pytest.approx(0.2)
        assert float(after["public_satisfaction"]) != float(before["public_satisfaction"])
        # invest
        await db.execute(
            "UPDATE country_economy SET treasury=100000 WHERE country_code='IR'"
        )
        msg2 = await mgmt.invest("IR", "industry", 1000, player_id=1)
        assert "✅" in msg2
        sec = await db.fetchrow(
            "SELECT * FROM production_sectors WHERE country_code='IR' AND sector_code='industry'"
        )
        assert float(sec["investment"]) >= 1000
        # cabinet
        await mgmt.appoint_minister("IR", "finance", "Test Minister", 1)
        cab = await db.fetchrow(
            "SELECT * FROM cabinet_members WHERE country_code='IR' AND portfolio='finance'"
        )
        assert cab["minister_name"] == "Test Minister"
        # AI tick
        ai = AIEngine(db, world, mgmt)
        n = await ai.tick_all(limit=5)
        assert n >= 1
        # events persisted
        ev = await db.fetch("SELECT * FROM events WHERE country_code='IR'")
        assert len(ev) >= 1
        await db.close()
    run(_t())


def test_baseline_not_overwritten_by_economy(env):
    async def _t():
        db, world, eco, mgmt = await env()
        b1 = await db.fetchrow("SELECT leader_name, gdp_ref FROM country_baselines WHERE country_code='US'")
        await mgmt.apply_budget_tick("US")
        b2 = await db.fetchrow("SELECT leader_name, gdp_ref FROM country_baselines WHERE country_code='US'")
        assert b1["leader_name"] == b2["leader_name"]
        assert b1["gdp_ref"] == b2["gdp_ref"]
        await db.close()
    run(_t())
