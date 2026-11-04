import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import Settings
from database import create_database
from modules.ng.game import Game, GameError


def run(c):
    return asyncio.run(c)


async def boot(tmp_path, owner=1):
    settings = Settings(
        bale_token="",
        owner_id=owner,
        database_mode="sqlite",
        database_url="",
        sqlite_path=tmp_path / "ng.db",
        log_level="WARNING",
        world_start_date="2020-01-01",
        real_days_per_game_year=15,
    )
    db = await create_database(settings)
    g = Game(db, owner_id=owner)
    await g.bootstrap()
    return db, g


def test_claim_atomic_and_single(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        c = await g.claim(10, "IR")
        assert c["owner_player_id"] == 10
        assert float(c["treasury"]) >= 30_000_000
        with pytest.raises(GameError):
            await g.claim(11, "IR")
        with pytest.raises(GameError):
            await g.claim(10, "US")
        await db.close()
    run(_t())


def test_shop_checkout_and_daily(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        await g.cart_add(1, "b_farm", 1)
        msg = await g.checkout(1, "US")
        assert "موفق" in msg
        n = await g.daily_payout_all()
        assert n >= 1
        n2 = await g.daily_payout_all()
        assert n2 == 0  # same day no double pay
        await db.close()
    run(_t())


def test_market_and_aid(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        await g.claim(2, "DE")
        await g.cart_add(1, "g_inf", 5)
        await g.checkout(1, "US")
        await g.market_create("US", "g_inf", 2, 1000, 1)
        listings = await g.market_list()
        assert listings
        await g.market_buy(listings[0]["id"], "DE", 2)
        await g.aid_money("US", "DE", 1000, 1)
        with pytest.raises(GameError):
            await g.aid_money("US", "DE", 10**15, 1)
        await db.close()
    run(_t())


def test_peace_and_attack_block(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        await g.claim(2, "FR")
        await g.peace_request("US", "FR", 2, 1)
        rows = await db.fetch("SELECT * FROM ng_peace WHERE status='pending'")
        assert rows
        await g.peace_accept(rows[0]["id"], "FR", 2)
        with pytest.raises(GameError):
            await g.attack("US", "FR", "ground", 50, 1)
        await db.close()
    run(_t())


def test_reset_owner_only(tmp_path):
    async def _t():
        db, g = await boot(tmp_path, owner=99)
        await g.claim(1, "IR")
        with pytest.raises(GameError):
            await g.full_reset(1, "ریست کامل جهان")
        msg = await g.full_reset(99, "ریست کامل جهان")
        assert "ریست" in msg
        c = await db.fetchrow("SELECT owner_player_id FROM ng_countries WHERE country_code='IR'")
        assert c["owner_player_id"] is None
        await db.close()
    run(_t())
