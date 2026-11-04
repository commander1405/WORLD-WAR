"""News module — initial country report and world date."""
from __future__ import annotations

from datetime import datetime, timezone

from database.interface import Database
from engine.world_engine import WorldEngine


class NewsService:
    def __init__(self, db: Database, world: WorldEngine):
        self.db = db
        self.world = world

    async def initial_country_report(self, country_code: str) -> str:
        code = country_code.upper()
        gdate = await self.world.current_game_date()
        country = await self.db.fetchrow(
            "SELECT * FROM countries WHERE country_code = $1", (code,)
        )
        baseline = await self.db.fetchrow(
            "SELECT * FROM country_baselines WHERE country_code = $1", (code,)
        )
        if not country:
            return "Country not found."
        lines = [
            f"WORLD WAR — Report",
            f"Game date: {gdate.isoformat()}",
            f"Country: {country.get('name_en')} ({code})",
            f"Control: {country.get('controlled_by')}",
            f"Stability: {country.get('stability')}",
            f"Treasury: {country.get('treasury')}",
        ]
        if baseline:
            lines.append(
                f"Baseline ({baseline.get('reference_date')}): "
                f"pop_ref={baseline.get('population_ref')} gdp_ref={baseline.get('gdp_ref')} "
                f"source={baseline.get('source_note') or 'n/a'} confidence={baseline.get('confidence') or 'n/a'}"
            )
        return "\n".join(lines)

    async def publish(self, headline: str, body: str = "", country_code: str | None = None, importance: int = 1) -> None:
        gdate = await self.world.current_game_date()
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO news_items (game_date, real_time, headline, body, country_code, importance)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            (gdate.isoformat(), now, headline, body, country_code, importance),
        )
