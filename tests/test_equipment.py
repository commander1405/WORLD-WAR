
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.ng import equipment as eq
from modules.ng.catalog import CATALOG
from modules.ng.game import Game, GameError
from database.sqlite import SQLiteDatabase


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def boot(path, owner=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = SQLiteDatabase(path)
    await db.connect()
    await db.migrate()
    g = Game(db, owner_id=owner)
    await g.bootstrap()
    return db, g


def test_catalog_stats_independent():
    damages = {c["item_code"]: c.get("damage", c.get("power_score")) for c in CATALOG if c.get("category") in ("ground","air","missile")}
    assert len(set(damages.values())) > 5
    assert eq.consumption_type("m_cruise") == "expendable"
    assert eq.consumption_type("a_f22") == "sortie"
    assert eq.consumption_type("sp_intel") == "specialist"
    assert eq.consume_amount("m_cruise", 3, victory=True) >= 3
    assert eq.consume_amount("a_f22", 10, victory=True) < 10  # sortie attrition only


def test_missile_consumed_sortie_partial(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "eq1.db", owner=99)
        await g.claim(10, "US")
        await g.claim(11, "RU")
        await db.execute("UPDATE ng_countries SET treasury=$1 WHERE country_code=$2", (500_000_000, "US"))
        await db.execute("UPDATE ng_countries SET treasury=$1 WHERE country_code=$2", (500_000_000, "RU"))
        # give missiles and tanks
        await db.execute("INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)", ("US", "m_cruise", 5))
        await db.execute("INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)", ("US", "g_armor", 10))
        await db.execute("INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)", ("RU", "d_sam_med", 5))
        await db.execute("UPDATE world_meta SET war_enabled=1 WHERE id=1")
        before_m = (await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","m_cruise")))["quantity"]
        before_t = (await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","g_armor")))["quantity"]
        msg = await g.attack("US", "RU", "ground", 50, 10)
        after_m = (await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","m_cruise")))["quantity"]
        after_t = (await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","g_armor")))["quantity"]
        # missiles for ground: m_cruise matches - engaged ~50% should be fully consumed
        assert float(after_m) < float(before_m)
        # tanks sortie: should not wipe all 50% engaged
        assert float(after_t) > float(before_t) * 0.3
        assert "گزارش" in msg or "درگیری" in msg
        await db.close()
    run(_t())


def test_specialist_two_uses(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "eq2.db", owner=99)
        await g.claim(10, "US")
        await g.claim(11, "CN")
        await db.execute("UPDATE ng_countries SET treasury=$1 WHERE country_code=$2", (500_000_000, "US"))
        await db.execute("INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)", ("US", "g_armor", 20))
        await db.execute("INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)", ("US", "sp_intel", 2))
        await db.execute("UPDATE world_meta SET war_enabled=1 WHERE id=1")
        await db.execute("DELETE FROM ng_war_state")
        await g.attack("US", "CN", "ground", 50, 10)
        q1 = float((await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","sp_intel")))["quantity"])
        assert q1 == 1
        await db.execute("DELETE FROM ng_war_state")
        await g.attack("US", "CN", "ground", 50, 10)
        row = await db.fetchrow("SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2", ("US","sp_intel"))
        q2 = float(row["quantity"]) if row else 0
        assert q2 == 0
        await db.close()
    run(_t())


def test_cannot_attack_without_force(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "eq3.db", owner=99)
        await g.claim(10, "US")
        await g.claim(11, "FR")
        await db.execute("UPDATE world_meta SET war_enabled=1 WHERE id=1")
        try:
            await g.attack("US", "FR", "ground", 50, 10)
            assert False
        except GameError:
            pass
        await db.close()
    run(_t())
