"""Economy foundation — production/consumption hooks (no fabricated stats)."""
from __future__ import annotations

from database.interface import Database


class EconomyEngine:
    def __init__(self, db: Database):
        self.db = db

    async def get_resources(self, country_code: str) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM resources WHERE country_code = $1 ORDER BY resource_code",
            (country_code.upper(),),
        )

    async def set_resource(self, country_code: str, resource_code: str, quantity: float, unit: str | None = None) -> None:
        code = country_code.upper()
        # upsert portable
        existing = await self.db.fetchrow(
            "SELECT resource_code FROM resources WHERE country_code = $1 AND resource_code = $2",
            (code, resource_code),
        )
        if existing:
            await self.db.execute(
                "UPDATE resources SET quantity = $1, unit = COALESCE($2, unit) WHERE country_code = $3 AND resource_code = $4",
                (quantity, unit, code, resource_code),
            )
        else:
            await self.db.execute(
                "INSERT INTO resources (country_code, resource_code, quantity, unit) VALUES ($1, $2, $3, $4)",
                (code, resource_code, quantity, unit),
            )
