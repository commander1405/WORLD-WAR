"""Event / audit log helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import json

from database.interface import Database


class EventEngine:
    def __init__(self, db: Database):
        self.db = db

    async def record(
        self,
        event_type: str,
        *,
        summary: str,
        game_date: Optional[str] = None,
        actor_player_id: Optional[int] = None,
        country_code: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO events (game_date, real_time, event_type, actor_player_id, country_code, payload_json, summary)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            (
                game_date,
                now,
                event_type,
                actor_player_id,
                country_code,
                json.dumps(payload) if payload else None,
                summary,
            ),
        )
