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


async def boot(tmp_path, owner=900001):
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


def test_peace_removed(tmp_path):
    async def _t():
        db, g = await boot(tmp_path)
        await g.claim(1, "US")
        await g.claim(2, "FR")
        with pytest.raises(GameError):
            await g.peace_request("US", "FR", 2, 1)
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
        await g.claim(10, "US")
        await db.execute("UPDATE ng_countries SET treasury=500000000 WHERE country_code='US'")
        await g.admin_give_item(1, "US", "b_refinery", 1)
        await g.admin_give_item(1, "US", "sp_scientist", 1)
        msg = await g.workshop_upgrade("US", 10)
        assert "ارتق" in msg
        await db.execute("UPDATE ng_countries SET treasury=500000000 WHERE country_code='US'")
        msg2 = await g.start_uranium_job("US", 10)
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
        await g.start_research_job("US", 10)
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
        # Owner is UN; bind test mode to UN country
        await db.execute("UPDATE ng_countries SET treasury=12345 WHERE country_code='UN'")
        await g.enable_test_mode(1)
        c = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='UN'")
        assert float(c["treasury"]) >= 999_999_999
        await g.disable_test_mode(1)
        c2 = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='UN'")
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
        await g.claim(10, "US")
        await g.claim(2, "DE")
        await db.execute("UPDATE ng_countries SET treasury=100000000 WHERE country_code='US'")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','res_uranium',30)"
        )
        await db.execute("UPDATE world_meta SET nuclear_enabled=1 WHERE id=1")
        msg = await g.craft_atom_bomb("US", 10)
        assert "بمب" in msg
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='US' AND item_code='item_atom_bomb'"
        )
        assert float(inv["quantity"]) >= 1
        report = await g.attack_nuclear("US", "DE", 10)
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


def test_sqlite_path_resolver_not_under_db_folder():
    from config.settings import _resolve_sqlite_path
    path = _resolve_sqlite_path("")
    # should not be .../world-war/db/ when default
    assert "world_war.db" in str(path)
    assert path.name == "world_war.db"


def test_player_panel_and_global_tax(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "tax", owner=1)
        await g.claim(10, "US")
        await g.claim(11, "DE")
        await db.execute("UPDATE ng_countries SET treasury=50000 WHERE country_code='US'")
        await db.execute("UPDATE ng_countries SET treasury=5000 WHERE country_code='DE'")
        await db.execute("UPDATE ng_countries SET treasury=1000 WHERE country_code='UN'")
        await g.record_start(10)
        stats = await g.player_stats()
        assert stats["total"] >= 2
        assert stats["active_today"] >= 1
        page, total = await g.list_players_page(0)
        assert total >= 2
        result = await g.global_tax(1, 10000)
        assert result["taxed"] == 1  # only US can pay
        assert result["skipped"] >= 1
        us = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'")
        un = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='UN'")
        assert abs(float(us["treasury"]) - 40000) < 1
        assert float(un["treasury"]) >= 11000
        await g.condemn_country(1, "DE", "تست محکومیت")
        await db.close()
    run(_t())


def test_catalog_has_military_expansion():
    from modules.ng.catalog import CATALOG, CAT_FA
    codes = {c["item_code"] for c in CATALOG}
    assert "a_f22" in codes
    assert "m_cruise" in codes
    assert "s_carrier" in codes
    assert "missile" in CAT_FA
    # no duplicate item codes
    assert len(codes) == len(CATALOG)


def test_country_label_and_player_reset(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "rst", owner=1)
        await g.claim(10, "IR")
        label = await g.country_label("IR")
        assert "ایران" in label
        assert "IR" not in label or "ایران" in label
        await db.execute("UPDATE ng_countries SET treasury=99999 WHERE country_code='IR'")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('IR','g_inf',5)"
        )
        msg = await g.reset_player(1, 10)
        assert "ریست" in msg
        p = await db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=10")
        assert p["country_code"] is None
        c = await db.fetchrow("SELECT owner_player_id, treasury FROM ng_countries WHERE country_code='IR'")
        assert c["owner_player_id"] is None
        inv = await db.fetch("SELECT * FROM ng_inventory WHERE country_code='IR'")
        assert len(inv) == 0
        # can reclaim
        await g.claim(10, "IR")
        p2 = await db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=10")
        assert p2["country_code"] == "IR"
        await db.close()
    run(_t())


def test_guide_content_structure():
    from modules.ng.guide import GUIDE_SECTIONS, GUIDE_MENU_ORDER, guide_page, guide_menu_rows
    assert len(GUIDE_SECTIONS) == 10
    assert len(GUIDE_MENU_ORDER) == 10
    text, rows = guide_page("faq", 0)
    assert "سؤالات" in text or "متداول" in text
    assert any("راهنما" in b[0] for row in rows for b in row)
    assert guide_menu_rows()


def test_defense_intercept_and_cyber(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "cyber", owner=1)
        await g.claim(10, "US")
        await g.claim(11, "DE")
        await db.execute("UPDATE ng_countries SET treasury=50000000 WHERE country_code IN ('US','DE')")
        # give US ground force and DE strong SAM
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','g_inf',20)"
        )
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('DE','m_sam_s400',10)"
        )
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('DE','d_radar',10)"
        )
        await db.execute("UPDATE world_meta SET war_enabled=1 WHERE id=1")
        cov, meta = await g.defense_coverage("DE", "air")
        assert 0 < cov <= g.DEFENSE_COVER_CAP
        # cyber hack needs item
        try:
            await g.hack_defense("US", "DE", 10)
            assert False, "should need item"
        except GameError:
            pass
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','cyber_hack_def',2)"
        )
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','cyber_hack_asset',1)"
        )
        msg = await g.hack_defense("US", "DE", 10)
        assert "پدافند" in msg
        dis = await g.active_cyber_disable_ratio("DE")
        assert dis >= 0.29
        report = await g.hack_assets("US", "DE", 10)
        assert "خزانه" in report
        # attack should include intercept fields
        rep = await g.attack("US", "DE", "ground", 50, 10)
        assert "رهگیری" in rep or "خسارت" in rep
        await db.close()
    run(_t())


def test_daily_grant_and_referral_and_away(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "ref", owner=1)
        await g.claim(10, "US")
        await g.claim(11, "DE")
        await db.execute("UPDATE ng_countries SET treasury=1000 WHERE country_code='US'")
        await db.execute("UPDATE ng_countries SET treasury=1000 WHERE country_code='DE'")
        n = await g.daily_payout_all()
        assert n >= 2
        us = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'")
        assert float(us["treasury"]) >= 1000 + 20_000_000 - 1
        n2 = await g.daily_payout_all()
        assert n2 == 0  # no double pay
        # referral
        await g.ensure_referral_row(10)
        r10 = await g.ensure_referral_row(10)
        code = r10["referral_code"]
        msg = await g.apply_referral_code(11, code)
        assert "ثبت" in msg or "✅" in msg
        de = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='DE'")
        us2 = await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'")
        assert float(de["treasury"]) >= 1000 + 20_000_000 + 2_000_000 - 2
        assert float(us2["treasury"]) >= float(us["treasury"]) + 15_000_000 - 1
        # no self-ref
        try:
            await g.apply_referral_code(10, code)
            assert False
        except GameError:
            pass
        # owner away
        await g.set_owner_away(1, True)
        assert await g.get_owner_away()
        await g.set_owner_away(1, False)
        assert not await g.get_owner_away()
        # admin money
        before = float((await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'"))["treasury"])
        await g.admin_money(1, "US", 5000)
        after = float((await db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code='US'"))["treasury"])
        assert abs(after - before - 5000) < 1
        allies = await g.list_alliances()
        assert isinstance(allies, list)
        await db.close()
    run(_t())


def test_alliance_system_v2(tmp_path):
    async def _t():
        from modules.ng.alliances import create_cost, AllianceError
        db, g = await boot(tmp_path / "ally", owner=1)
        await g.claim(10, "US")
        await g.claim(11, "DE")
        await db.execute("UPDATE ng_countries SET treasury=500000000 WHERE country_code IN ('US','DE')")
        cost = create_cost(5, 200_000_000)
        assert cost >= 15_000_000
        msg = await g.alliances.create(10, "US", "Dark Alliance", 5, 200_000_000)
        assert "ساخته" in msg or "✅" in msg
        mem = await g.alliances.member_of("US")
        assert mem and mem["role"] == "founder"
        await g.alliances.join(11, "DE", mem["alliance_id"])
        assert await g.alliances.member_of("DE")
        try:
            await g.alliances.create(11, "DE", "Other", 3, 100_000_000)
            assert False
        except AllianceError:
            pass
        await g.alliances.deposit(11, "DE", 1_000_000)
        a = await g.alliances.get(mem["alliance_id"])
        assert float(a["treasury"]) >= 1_000_000
        await g.alliances.equal_split(10)
        a2 = await g.alliances.get(mem["alliance_id"])
        assert float(a2["treasury"]) < float(a["treasury"])
        await g.alliances.leave(11, "DE")
        # betrayal: attack US within window
        await db.execute("UPDATE world_meta SET war_enabled=1 WHERE id=1")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('DE','g_inf',20)"
        )
        # re-claim DE still has country
        warn = await g.alliances.check_betrayal_on_attack(11, "DE", "US")
        assert warn and "خیانت" in warn
        mult = await g.alliances.shop_mult_for_player(11)
        assert mult == 2.0
        await db.close()
    run(_t())


def test_alliance_create_cost_and_retry(tmp_path):
    async def _t():
        from modules.ng.alliances import create_cost, AllianceError
        db, g = await boot(tmp_path / "ally2", owner=1)
        await g.claim(10, "US")
        await db.execute("UPDATE ng_countries SET treasury=20000000 WHERE country_code='US'")
        cost = create_cost(2, 100_000_000)
        assert cost == 15_000_000
        msg = await g.alliances.create(10, "US", "Alpha", 2, 100_000_000)
        assert "ساخته" in msg or "✅" in msg
        mem = await g.alliances.member_of("US")
        assert mem and mem["role"] == "founder"
        # second create fails
        try:
            await g.alliances.create(10, "US", "Beta", 2, 100_000_000)
            assert False
        except AllianceError:
            pass
        await db.close()
    run(_t())


def test_defense_wear_and_double_hp(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "defhp", owner=1)
        await g.claim(10, "US")
        await g.claim(11, "DE")
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('DE','d_sam',3)"
        )
        # force wear break quickly
        await db.execute(
            "INSERT INTO ng_defense_hits (country_code, hits, break_at) VALUES ('DE', 2, 3)"
        )
        msg = await g.apply_defense_wear("DE")
        assert msg and "پدافند" in msg
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='DE' AND item_code='d_sam'"
        )
        assert float(inv["quantity"]) == 2
        # double hp
        before = await db.fetchrow("SELECT hp, max_hp FROM ng_countries WHERE country_code='US'")
        await g.set_double_hp(1, "US", True)
        after = await db.fetchrow("SELECT hp, max_hp, double_hp FROM ng_countries WHERE country_code='US'")
        assert int(after["double_hp"]) == 1
        assert float(after["max_hp"]) == float(before["max_hp"]) * 2
        card = await g.country_card("US")
        assert "×۲" in card or "فعال" in card
        await g.set_double_hp(1, "US", False)
        off = await db.fetchrow("SELECT double_hp FROM ng_countries WHERE country_code='US'")
        assert int(off["double_hp"]) == 0
        # cyber consume
        await db.execute(
            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ('US','cyber_hack_def',1)"
        )
        await g.hack_defense("US", "DE", 10)
        left = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code='US' AND item_code='cyber_hack_def'"
        )
        assert left is None or float(left["quantity"] or 0) <= 0
        await db.close()
    run(_t())
