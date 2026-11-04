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


def test_cart_remove_and_market_cancel(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        await g.cart_add(1, "g_inf", 3)
        await g.cart_set(1, "g_inf", 0)
        _, total, items = await g.cart_view(1, "US")
        assert total == 0 and not items
        await g.cart_add(1, "g_inf", 4)
        await g.checkout(1, "US")
        await g.market_create("US", "g_inf", 2, 5000, 1)
        listings = await g.market_list()
        assert listings
        await g.market_cancel(listings[0]["id"], "US")
        await db.close()
    run(_t())


def test_aid_army_and_log_flags(tmp_path):
    async def _t():
        db, g = await boot(tmp_path, owner=5)
        await g.claim(1, "US")
        await g.claim(2, "DE")
        await g.cart_add(1, "g_inf", 5)
        await g.checkout(1, "US")
        await g.aid_army("US", "DE", "g_inf", 2, 1)
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='DE' AND item_code='g_inf'"
        )
        assert float(inv["quantity"]) >= 2
        msg = await g.set_log_flag(5, "buy", False)
        assert "خاموش" in msg
        flags = await g.get_log_flags()
        assert flags["buy"] is False
        await db.close()
    run(_t())


def test_ban_by_username(tmp_path):
    async def _t():
        db, g = await boot(tmp_path, owner=9)
        await g.touch_player(3, username="testuser", display="T")
        await g.ban_user(9, "@testuser", "spam")
        with pytest.raises(GameError):
            await g.assert_not_banned(3)
        await g.unban_user(9, "testuser")
        await g.assert_not_banned(3)
        await db.close()
    run(_t())


def test_workshop_upgrade_and_jobs(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        # give refinery + scientist + money
        await db.execute("UPDATE ng_countries SET treasury=500000000 WHERE country_code='US'")
        await g.admin_give_item(1, "US", "b_refinery", 1)  # not owner - will fail
        await db.close()
    try:
        run(_t())
    except Exception:
        pass

    async def _t2():
        db, g = await boot(tmp_path / "w2", owner=1)
        await g.claim(1, "US")
        await db.execute("UPDATE ng_countries SET treasury=500000000 WHERE country_code='US'")
        await g.admin_give_item(1, "US", "b_refinery", 1)
        await g.admin_give_item(1, "US", "sp_scientist", 1)
        msg = await g.workshop_upgrade("US", 1)
        assert "ارتق" in msg
        msg2 = await g.start_uranium_job("US", 1)
        assert "شروع" in msg2
        # force complete
        await db.execute(
            "UPDATE ng_workshop_jobs SET finishes_at=$1 WHERE country_code='US' AND status='running'",
            ("2000-01-01T00:00:00+00:00",),
        )
        n = await g.complete_due_jobs("US")
        assert n >= 1
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='US' AND item_code='res_uranium'"
        )
        assert inv and float(inv["quantity"]) > 0
        await g.start_research_job("US", 1)
        await db.close()
    run(_t2())


def test_npt_request_and_review(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "npt", owner=9)
        await g.claim(1, "IL")  # non-member seed
        c = await db.fetchrow("SELECT npt_member FROM ng_countries WHERE country_code='IL'")
        assert int(c["npt_member"]) == 0
        await g.request_npt_change("IL", 1, "join")
        rows = await g.pending_npt_list()
        assert rows
        rid = rows[0]["id"]
        with pytest.raises(GameError):
            await g.review_npt(rid, True, 1)  # not owner
        await g.review_npt(rid, True, 9)
        c2 = await db.fetchrow("SELECT npt_member FROM ng_countries WHERE country_code='IL'")
        assert int(c2["npt_member"]) == 1
        # double review fails
        with pytest.raises(GameError):
            await g.review_npt(rid, True, 9)
        await db.close()
    run(_t())


def test_settings_start_about(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "set", owner=3)
        await g.set_setting(3, "start_message", "سلام تست شروع")
        assert "سلام تست" in await g.get_setting("start_message")
        await g.reset_setting(3, "start_message")
        assert "جنگ جهانی" in await g.get_setting("start_message")
        await g.set_setting(3, "about_message", "درباره تست")
        assert "درباره تست" == await g.get_setting("about_message")
        await db.close()
    run(_t())
