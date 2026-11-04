"""Lifecycle helpers without real Bale network."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import Settings
from database import create_database


def test_db_start_close(tmp_path):
    async def _t():
        settings = Settings(
            bale_token="",
            owner_id=0,
            database_mode="sqlite",
            database_url="",
            sqlite_path=tmp_path / "life.db",
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        assert await db.health_check()
        await db.close()
        # reconnect path
        db2 = await create_database(settings)
        assert await db2.health_check()
        await db2.close()
    asyncio.run(_t())


def test_sqlite_transaction_rollback(tmp_path):
    async def _t():
        settings = Settings(
            bale_token="",
            owner_id=0,
            database_mode="sqlite",
            database_url="",
            sqlite_path=tmp_path / "tx.db",
            log_level="WARNING",
            world_start_date="2020-01-01",
            real_days_per_game_year=15,
        )
        db = await create_database(settings)
        await db.execute(
            "INSERT INTO country_baselines (country_code, name_en, reference_date) VALUES ($1,$2,$3)",
            ("ZZ", "Zed", "2020-01-01"),
        )
        try:
            async with db.transaction():
                await db.execute(
                    "INSERT INTO countries (country_code, name_en, controlled_by) VALUES ($1,$2,$3)",
                    ("ZZ", "Zed", "ai"),
                )
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        row = await db.fetchrow("SELECT * FROM countries WHERE country_code=$1", ("ZZ",))
        assert row is None
        await db.close()
    asyncio.run(_t())
