"""Player registration by stable Bale user id."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from database.interface import Database


class PlayerService:
    def __init__(self, db: Database):
        self.db = db

    async def register_or_update(
        self,
        player_id: int,
        username: str | None = None,
        display_name: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT * FROM players WHERE player_id = $1", (player_id,)
        )
        if row:
            await self.db.execute(
                """
                UPDATE players SET
                    username = COALESCE($1, username),
                    display_name = COALESCE($2, display_name),
                    last_seen_at = $3
                WHERE player_id = $4
                """,
                (username, display_name, now, player_id),
            )
            return await self.db.fetchrow(
                "SELECT * FROM players WHERE player_id = $1", (player_id,)
            ) or row
        await self.db.execute(
            """
            INSERT INTO players (player_id, username, display_name, joined_at, last_seen_at, is_active)
            VALUES ($1, $2, $3, $4, $4, 1)
            """,
            (player_id, username, display_name, now),
        )
        return await self.db.fetchrow(
            "SELECT * FROM players WHERE player_id = $1", (player_id,)
        )

    async def get(self, player_id: int) -> Optional[dict]:
        return await self.db.fetchrow(
            "SELECT * FROM players WHERE player_id = $1", (player_id,)
        )

    async def set_briefing_sent(self, player_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT player_id FROM player_flags WHERE player_id = $1", (player_id,)
        )
        if row:
            await self.db.execute(
                "UPDATE player_flags SET initial_briefing_sent = 1, updated_at = $1 WHERE player_id = $2",
                (now, player_id),
            )
        else:
            await self.db.execute(
                "INSERT INTO player_flags (player_id, initial_briefing_sent, updated_at) VALUES ($1, 1, $2)",
                (player_id, now),
            )

    async def briefing_sent(self, player_id: int) -> bool:
        row = await self.db.fetchrow(
            "SELECT initial_briefing_sent FROM player_flags WHERE player_id = $1",
            (player_id,),
        )
        return bool(row and row.get("initial_briefing_sent"))
