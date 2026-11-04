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
from modules.markets.service import MarketService, MarketError
from modules.trade.service import TradeService, TradeError


def run(c):
    return asyncio.run(c)


async def setup(tmp_path):
    settings = Settings(
        bale_token="",
        owner_id=0,
        database_mode="sqlite",
        database_url="",
        sqlite_path=tmp_path / "p4.db",
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
    market = MarketService(db, world)
    await market.ensure_seed()
    trade = TradeService(db, market)
    # fund IR
    await db.execute("UPDATE country_economy SET treasury=100000 WHERE country_code='IR'")
    await db.execute("UPDATE country_economy SET treasury=100000 WHERE country_code='US'")
    return db, market, trade


def test_cart_checkout_and_insufficient(tmp_path):
    async def _t():
        db, market, trade = await setup(tmp_path)
        await market.cart_add(1, "gnd_infantry", 2)
        text, total, items = await market.cart_view(1)
        assert items and total > 0
        msg = await market.checkout(1, "IR")
        assert "موفق" in msg
        inv = await market.inventory("IR")
        assert any(i["item_code"] == "gnd_infantry" and float(i["quantity"]) >= 2 for i in inv)
        # insufficient
        await market.cart_add(1, "bld_uranium_plant", 2)
        await db.execute("UPDATE country_economy SET treasury=10 WHERE country_code='IR'")
        with pytest.raises(MarketError):
            await market.checkout(1, "IR")
        await db.close()
    run(_t())


def test_cart_remove(tmp_path):
    async def _t():
        db, market, trade = await setup(tmp_path)
        await market.cart_add(7, "res_oil", 5)
        await market.cart_set(7, "res_oil", 0)
        _, total, items = await market.cart_view(7)
        assert not items and total == 0
        await db.close()
    run(_t())


def test_marketplace_and_over_sell(tmp_path):
    async def _t():
        db, market, trade = await setup(tmp_path)
        await market.cart_add(1, "res_oil", 20)
        await market.checkout(1, "IR")
        with pytest.raises(MarketError):
            await market.create_listing("IR", "res_oil", 9999, 10, 1)
        await market.create_listing("IR", "res_oil", 5, 60, 1)
        listings = await market.list_market()
        assert listings
        lid = listings[0]["id"]
        msg = await market.buy_listing(lid, "US", 2)
        assert "موفق" in msg or "خرید" in msg
        # second buy same listing fails
        with pytest.raises(MarketError):
            await market.buy_listing(lid, "US", 2)
        await db.close()
    run(_t())


def test_trade_flow(tmp_path):
    async def _t():
        db, market, trade = await setup(tmp_path)
        # ensure oil
        await market.cart_add(1, "res_oil", 30)
        await market.checkout(1, "IR")
        msg = await trade.create_offer("IR", "US", "res_oil", 10, 500, 1)
        assert "ثبت" in msg
        offers = await trade.list_for("US")
        assert offers
        oid = offers[0]["id"]
        msg2 = await trade.accept(oid, "US", 2)
        assert "انجام" in msg2
        await db.close()
    run(_t())


def test_refinery_production(tmp_path):
    async def _t():
        db, market, trade = await setup(tmp_path)
        await db.execute("UPDATE country_economy SET treasury=200000 WHERE country_code='IR'")
        await market.cart_add(1, "bld_refinery", 1)
        await market.checkout(1, "IR")
        before = {i["item_code"]: float(i["quantity"]) for i in await market.inventory("IR")}
        n = await market.produce_buildings("IR")
        assert n >= 1
        after = {i["item_code"]: float(i["quantity"]) for i in await market.inventory("IR")}
        assert after.get("res_oil", 0) > before.get("res_oil", 0)
        await db.close()
    run(_t())
