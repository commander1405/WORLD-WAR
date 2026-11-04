"""AI-controlled countries placeholder — unclaimed states remain AI-owned."""
from __future__ import annotations

from database.interface import Database


class AIEngine:
    def __init__(self, db: Database):
        self.db = db

    async def list_ai_countries(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM countries WHERE controlled_by = 'ai' ORDER BY country_code"
        )
