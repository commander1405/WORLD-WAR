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


def test_attack_requires_forces(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "atk0")
        await g.claim(1, "US")
        await g.claim(2, "DE")
        with pytest.raises(GameError):
            await g.attack("US", "DE", "ground", 100, 1)
        ok, msg = await g.can_attack("US")
        assert ok is False
        await db.close()
    run(_t())


def test_attack_with_forces_and_cooldown(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "atk1")
        await g.claim(1, "US")
        await g.claim(2, "DE")
        await db.execute("UPDATE ng_countries SET treasury=50000000 WHERE country_code='US'")
        await db.execute("UPDATE ng_countries SET treasury=20000000 WHERE country_code='DE'")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','g_inf',20)"
        )
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('DE','g_inf',5)"
        )
        report = await g.attack("US", "DE", "ground", 50, 1)
        assert "گزارش" in report
        with pytest.raises(GameError):
            await g.attack("US", "DE", "ground", 50, 1)  # cooldown
        # force expire cooldown
        await db.execute(
            "UPDATE ng_war_state SET last_attack_at=$1 WHERE country_code='US'",
            ("2000-01-01T00:00:00+00:00",),
        )
        report2 = await g.attack("US", "DE", "ground", 30, 1)
        assert "گزارش" in report2
        await db.close()
    run(_t())


def test_test_mode_snapshot_restore(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "testm", owner=1)
        await g.claim(1, "US")
        await db.execute("UPDATE ng_countries SET treasury=12345 WHERE country_code='US'")
        await g.enable_test_mode(1)
        c = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'")
        assert float(c["treasury"]) >= 999_999_999
        await g.disable_test_mode(1)
        c2 = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'")
        assert abs(float(c2["treasury"]) - 12345) < 1
        await db.close()
    run(_t())


def test_membership_settings(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "mem", owner=7)
        assert await g.membership_enabled() is True
        await g.set_membership_enabled(7, False)
        assert await g.membership_enabled() is False
        chats = await g.list_forced_chats()
        assert any(c["chat_id"] == "@warworld3" for c in chats)
        await db.close()
    run(_t())


def test_craft_bomb_and_nuclear_attack(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "nuke", owner=1)
        await g.claim(1, "US")
        await g.claim(2, "DE")
        await db.execute("UPDATE ng_countries SET treasury=100000000 WHERE country_code='US'")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','res_uranium',30)"
        )
        # enable nuclear
        await db.execute("UPDATE world_meta SET nuclear_enabled=1 WHERE id=1")
        msg = await g.craft_atom_bomb("US", 1)
        assert "بمب" in msg
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='US' AND item_code='item_atom_bomb'"
        )
        assert float(inv["quantity"]) >= 1
        report = await g.attack_nuclear("US", "DE", 1)
        assert "اتمی" in report or "تخریب" in report
        de = await db.fetchrow("SELECT hp FROM ng_countries WHERE country_code='DE'")
        assert float(de["hp"]) < 1000
        await db.close()
    run(_t())


def test_membership_cache(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "mcache")
        await g.membership_cache_set(42, "@warworld3")
        assert await g.membership_cache_ok(42, "@warworld3") is True
        ok, detail = await g.verify_membership(None, 42, "@warworld3")
        assert ok is True and detail == "cache"
        await db.close()
    run(_t())


def test_un_country_owner_only(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "un", owner=99)
        await g.bootstrap()
        rows_public = await g.list_countries(for_owner=False)
        assert all(r["country_code"] != "UN" for r in rows_public)
        assert len(rows_public) == 30
        rows_owner = await g.list_countries(for_owner=True)
        assert any(r["country_code"] == "UN" for r in rows_owner)
        assert len(rows_owner) == 31
        code = await g.player_country(99)
        assert code == "UN"
        with pytest.raises(GameError):
            await g.claim(1, "UN")
        # normal claim still works
        await g.claim(1, "US")
        text = await g.world_status_text(for_owner=False)
        assert "30" in text
        text2 = await g.world_status_text(for_owner=True)
        assert "31" in text2
        await db.close()
    run(_t())
