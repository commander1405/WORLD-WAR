"""AI-controlled countries — simple autonomous budget decisions, persisted."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database.interface import Database
from engine.world_engine import WorldEngine

log = logging.getLogger(__name__)


class AIEngine:
    def __init__(self, db: Database, world: WorldEngine, management):
        self.db = db
        self.world = world
        self.management = management

    async def list_ai_countries(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM countries WHERE controlled_by = 'ai' ORDER BY country_code"
        )

    async def tick_all(self, limit: int = 50) -> int:
        """Run one AI decision cycle for up to `limit` AI countries."""
        rows = await self.db.fetch(
            "SELECT country_code FROM countries WHERE controlled_by='ai' ORDER BY country_code LIMIT $1",
            (limit,),
        )
        n = 0
        for r in rows:
            await self.tick_country(r["country_code"])
            n += 1
        return n

    async def tick_country(self, country_code: str) -> None:
        code = country_code.upper()
        e = await self.db.fetchrow(
            "SELECT * FROM country_economy WHERE country_code=$1", (code,)
        )
        if not e:
            await self.management.ensure_schema()
            e = await self.db.fetchrow(
                "SELECT * FROM country_economy WHERE country_code=$1", (code,)
            )
        if not e:
            return
        # simple rule: if satisfaction low, raise spending slightly; if treasury low, raise tax
        sat = float(e["public_satisfaction"])
        treas = float(e["treasury"])
        tax = float(e["tax_rate"])
        spend = float(e["public_spending_rate"])
        action = None
        if treas < float(e["gdp"]) * 0.005 and tax < 0.35:
            tax = min(0.35, tax + 0.01)
            action = ("tax", tax)
            await self.management.set_tax_rate(code, tax, player_id=None)
        elif sat < 40 and spend < 0.3:
            spend = min(0.3, spend + 0.01)
            action = ("spend", spend)
            await self.management.set_spending_rate(code, spend, player_id=None)
        else:
            await self.management.apply_budget_tick(code)
            action = ("budget_tick", None)
        log.debug("AI %s action %s", code, action)
