"""Country ownership — atomic claim with unique constraints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from database.interface import Database


class CountryClaimError(Exception):
    pass


class CountryEngine:
    def __init__(self, db: Database):
        self.db = db

    async def claim_country(self, player_id: int, country_code: str, username: str | None = None, display_name: str | None = None) -> dict:
        """First valid claim wins. Uses transaction + unique indexes."""
        code = country_code.strip().upper()
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            country = await tx.fetchrow(
                "SELECT * FROM countries WHERE country_code = $1",
                (code,),
            )
            if not country:
                raise CountryClaimError("Unknown country")
            if country.get("owner_player_id"):
                raise CountryClaimError("Country already owned")

            player = await tx.fetchrow(
                "SELECT * FROM players WHERE player_id = $1",
                (player_id,),
            )
            if player and player.get("country_code"):
                raise CountryClaimError("Player already owns a country")

            if not player:
                await tx.execute(
                    """
                    INSERT INTO players (player_id, username, display_name, country_code, joined_at, last_seen_at, is_active)
                    VALUES ($1, $2, $3, $4, $5, $5, 1)
                    """,
                    (player_id, username, display_name, code, now),
                )
            else:
                await tx.execute(
                    """
                    UPDATE players SET country_code = $1, username = COALESCE($2, username),
                        display_name = COALESCE($3, display_name), last_seen_at = $4
                    WHERE player_id = $5 AND country_code IS NULL
                    """,
                    (code, username, display_name, now, player_id),
                )

            await tx.execute(
                """
                UPDATE countries SET owner_player_id = $1, controlled_by = 'player', updated_at = $2
                WHERE country_code = $3 AND owner_player_id IS NULL
                """,
                (player_id, now, code),
            )
            updated = await tx.fetchrow(
                "SELECT * FROM countries WHERE country_code = $1 AND owner_player_id = $2",
                (code, player_id),
            )
            if not updated:
                raise CountryClaimError("Claim failed (race lost)")

            await tx.execute(
                """
                INSERT INTO events (game_date, real_time, event_type, actor_player_id, country_code, summary)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                (None, now, "country_claim", player_id, code, f"Player {player_id} claimed {code}"),
            )
            return updated

    async def get_country(self, country_code: str) -> Optional[dict]:
        return await self.db.fetchrow(
            "SELECT * FROM countries WHERE country_code = $1",
            (country_code.upper(),),
        )
