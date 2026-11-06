
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.sqlite import SQLiteDatabase
from modules.ng.game import Game

def run(c):
    return asyncio.get_event_loop().run_until_complete(c)

async def boot(p):
    path = Path(p)
    if path.exists(): path.unlink()
    db = SQLiteDatabase(path)
    await db.connect(); await db.migrate()
    g = Game(db, owner_id=1)
    await g.bootstrap()
    return db, g

def test_legendary_core(tmp_path):
    async def _t():
        db, g = await boot(tmp_path / "leg.db")
        await g.claim(10, "US")
        await g.claim(11, "RU")
        await g.legendary.admin_charge_wallet(1, 10, 10000)
        await g.legendary.buy(10, "leg_anime_girl")
        await g.legendary.use_item(10, "leg_anime_girl", None)
        m = await g.legendary.income_multiplier("US")
        assert abs(m - 1.15) < 1e-6
        await db.close()
    run(_t())
