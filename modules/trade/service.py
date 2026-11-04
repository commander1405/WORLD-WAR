"""Bilateral resource trade offers."""
from __future__ import annotations

from datetime import datetime, timezone

from database.interface import Database

TRADEABLE = {
    "res_oil": "نفت",
    "res_gas": "گاز طبیعی",
    "res_water": "آب",
    "res_power": "برق",
    "res_uranium": "اورانیوم (صلح‌آمیز)",
    "res_minerals": "مواد معدنی",
}


class TradeError(Exception):
    pass


class TradeService:
    def __init__(self, db: Database, market=None):
        self.db = db
        self.market = market

    async def create_offer(
        self,
        from_country: str,
        to_country: str,
        resource_code: str,
        quantity: float,
        total_price: float,
        player_id: int | None = None,
    ) -> str:
        if resource_code not in TRADEABLE:
            raise TradeError("این منبع قابل معامله نیست.")
        if from_country == to_country:
            raise TradeError("مقصد نامعتبر است.")
        quantity = float(quantity)
        total_price = float(total_price)
        if quantity <= 0 or total_price < 0:
            raise TradeError("مقدار یا قیمت نامعتبر است.")
        async with self.db.transaction() as tx:
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (from_country, resource_code),
            )
            have = float(inv["quantity"]) if inv else 0.0
            if have < quantity:
                raise TradeError("موجودی منبع کافی نیست.")
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                (have - quantity, now, from_country, resource_code),
            )
            oid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM trade_offers")
            tid = int(oid["id"])
            await tx.execute(
                """
                INSERT INTO trade_offers (id, from_country, to_country, resource_code, quantity, total_price, status, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,'pending',$7)
                """,
                (tid, from_country, to_country, resource_code, quantity, total_price, now),
            )
        if self.market:
            await self.market._log(
                "trade_offer",
                f"پیشنهاد تجارت {TRADEABLE[resource_code]} به {to_country}",
                from_country,
                player_id,
            )
        return f"✅ پیشنهاد تجارت ثبت شد (شماره {tid})"

    async def list_for(self, country: str) -> list[dict]:
        return await self.db.fetch(
            """
            SELECT * FROM trade_offers
            WHERE status='pending' AND (to_country=$1 OR from_country=$1)
            ORDER BY id DESC
            """,
            (country,),
        )

    async def accept(self, offer_id: int, country: str, player_id: int | None = None) -> str:
        async with self.db.transaction() as tx:
            off = await tx.fetchrow(
                "SELECT * FROM trade_offers WHERE id=$1 AND status='pending'", (offer_id,)
            )
            if not off:
                raise TradeError("پیشنهاد معتبر نیست.")
            if off["to_country"] != country:
                raise TradeError("فقط کشور مقصد می‌تواند بپذیرد.")
            buyer = await tx.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1", (country,)
            )
            seller = await tx.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1",
                (off["from_country"],),
            )
            price = float(off["total_price"])
            if float(buyer["treasury"]) < price:
                raise TradeError("موجودی خزانه برای پذیرش کافی نیست.")
            qty = float(off["quantity"])
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE trade_offers SET status='accepted', resolved_at=$1 WHERE id=$2 AND status='pending'",
                (now, offer_id),
            )
            await tx.execute(
                "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                (float(buyer["treasury"]) - price, country),
            )
            await tx.execute(
                "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                (float(seller["treasury"]) + price, off["from_country"]),
            )
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (country, off["resource_code"]),
            )
            if inv:
                await tx.execute(
                    "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                    (float(inv["quantity"]) + qty, now, country, off["resource_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                    (country, off["resource_code"], qty, now),
                )
        if self.market:
            await self.market._log("trade_accept", f"پذیرش تجارت #{offer_id}", country, player_id)
        return f"✅ قرارداد تجارت #{offer_id} انجام شد."

    async def reject(self, offer_id: int, country: str) -> str:
        async with self.db.transaction() as tx:
            off = await tx.fetchrow(
                "SELECT * FROM trade_offers WHERE id=$1 AND status='pending'", (offer_id,)
            )
            if not off:
                raise TradeError("پیشنهاد معتبر نیست.")
            if country not in (off["to_country"], off["from_country"]):
                raise TradeError("دسترسی ندارید.")
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE trade_offers SET status='rejected', resolved_at=$1 WHERE id=$2",
                (now, offer_id),
            )
            # return reserved resources to seller
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (off["from_country"], off["resource_code"]),
            )
            qty = float(off["quantity"])
            if inv:
                await tx.execute(
                    "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                    (float(inv["quantity"]) + qty, now, off["from_country"], off["resource_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                    (off["from_country"], off["resource_code"], qty, now),
                )
        return "پیشنهاد رد و منابع برگردانده شد."
