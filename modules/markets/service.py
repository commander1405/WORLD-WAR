"""Shop cart, inventory, marketplace, buildings — transactional."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from database.interface import Database
from modules.markets.catalog import CATALOG, CATEGORY_FA, BUILDING_CODES, BUILDING_OUTPUT


class MarketError(Exception):
    pass


class MarketService:
    def __init__(self, db: Database, world=None):
        self.db = db
        self.world = world
        self._by_code = {c["item_code"]: c for c in CATALOG}

    async def ensure_seed(self) -> None:
        for c in CATALOG:
            row = await self.db.fetchrow(
                "SELECT item_code FROM shop_catalog WHERE item_code=$1", (c["item_code"],)
            )
            if not row:
                await self.db.execute(
                    """
                    INSERT INTO shop_catalog (
                        item_code, category, name_fa, description_fa, unit_price,
                        max_per_order, power_score, maintenance_cost
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    (
                        c["item_code"], c["category"], c["name_fa"], c["description_fa"],
                        c["unit_price"], c["max_per_order"], c["power_score"], c["maintenance_cost"],
                    ),
                )
        # seed base resources for countries that have none
        countries = await self.db.fetch("SELECT country_code FROM countries")
        for co in countries:
            code = co["country_code"]
            for res, qty in (("res_oil", 100), ("res_gas", 80), ("res_water", 200), ("res_power", 150), ("res_minerals", 50)):
                await self._ensure_inv(code, res, qty, only_if_missing=True)
            await self._ensure_military_row(code)

    async def _ensure_military_row(self, country_code: str) -> None:
        row = await self.db.fetchrow(
            "SELECT country_code FROM military_status WHERE country_code=$1", (country_code,)
        )
        if not row:
            now = datetime.now(timezone.utc).isoformat()
            await self.db.execute(
                "INSERT INTO military_status (country_code, updated_at) VALUES ($1,$2)",
                (country_code, now),
            )

    async def _ensure_inv(self, country: str, item: str, qty: float, only_if_missing: bool = False) -> None:
        row = await self.db.fetchrow(
            "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
            (country, item),
        )
        now = datetime.now(timezone.utc).isoformat()
        if not row:
            await self.db.execute(
                "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                (country, item, qty, now),
            )
        elif not only_if_missing:
            await self.db.execute(
                "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                (float(row["quantity"]) + qty, now, country, item),
            )

    async def _log(self, kind: str, summary: str, country: str | None = None, player_id: int | None = None, meta=None):
        now = datetime.now(timezone.utc).isoformat()
        gdate = None
        if self.world:
            try:
                gdate = (await self.world.current_game_date()).isoformat()
            except Exception:
                gdate = None
        await self.db.execute(
            """
            INSERT INTO activity_log (country_code, player_id, game_date, real_time, kind, summary, meta_json)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            (country, player_id, gdate, now, kind, summary, json.dumps(meta or {}, ensure_ascii=False)),
        )

    def item(self, code: str) -> dict:
        if code not in self._by_code:
            raise MarketError("کالا یافت نشد")
        return self._by_code[code]

    async def categories(self) -> list[tuple[str, str]]:
        return list(CATEGORY_FA.items())

    async def list_category(self, category: str) -> list[dict]:
        return [c for c in CATALOG if c["category"] == category]

    async def cart_add(self, player_id: int, item_code: str, qty: float) -> str:
        item = self.item(item_code)
        qty = max(1, min(float(item["max_per_order"]), float(qty)))
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT quantity FROM cart_items WHERE player_id=$1 AND item_code=$2",
            (player_id, item_code),
        )
        if row:
            new_q = min(float(item["max_per_order"]), float(row["quantity"]) + qty)
            await self.db.execute(
                "UPDATE cart_items SET quantity=$1, updated_at=$2 WHERE player_id=$3 AND item_code=$4",
                (new_q, now, player_id, item_code),
            )
        else:
            await self.db.execute(
                "INSERT INTO cart_items (player_id, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                (player_id, item_code, qty, now),
            )
        return f"✅ {item['name_fa']} × {int(qty)} به سبد اضافه شد."

    async def cart_set(self, player_id: int, item_code: str, qty: float) -> str:
        item = self.item(item_code)
        qty = float(qty)
        if qty <= 0:
            await self.db.execute(
                "DELETE FROM cart_items WHERE player_id=$1 AND item_code=$2",
                (player_id, item_code),
            )
            return f"🗑 {item['name_fa']} از سبد حذف شد."
        qty = min(float(item["max_per_order"]), qty)
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT quantity FROM cart_items WHERE player_id=$1 AND item_code=$2",
            (player_id, item_code),
        )
        if row:
            await self.db.execute(
                "UPDATE cart_items SET quantity=$1, updated_at=$2 WHERE player_id=$3 AND item_code=$4",
                (qty, now, player_id, item_code),
            )
        else:
            await self.db.execute(
                "INSERT INTO cart_items (player_id, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                (player_id, item_code, qty, now),
            )
        return f"✅ تعداد {item['name_fa']} = {int(qty)}"

    async def cart_clear(self, player_id: int) -> None:
        await self.db.execute("DELETE FROM cart_items WHERE player_id=$1", (player_id,))

    async def cart_view(self, player_id: int) -> tuple[str, float, list[dict]]:
        rows = await self.db.fetch(
            "SELECT * FROM cart_items WHERE player_id=$1 ORDER BY item_code", (player_id,)
        )
        lines = ["🛒 سبد خرید", ""]
        total = 0.0
        items = []
        for r in rows:
            it = self.item(r["item_code"])
            line_total = float(r["quantity"]) * float(it["unit_price"])
            total += line_total
            items.append({**r, **it, "line_total": line_total})
            lines.append(f"• {it['name_fa']} × {int(r['quantity'])} = {int(line_total):,}")
        if not rows:
            lines.append("سبد خالی است.")
        lines.append("")
        lines.append(f"جمع: {int(total):,}")
        return "\n".join(lines), total, items

    async def checkout(self, player_id: int, country_code: str) -> str:
        _, total, items = await self.cart_view(player_id)
        if not items:
            raise MarketError("سبد خرید خالی است.")
        async with self.db.transaction() as tx:
            eco = await tx.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1", (country_code,)
            )
            if not eco:
                raise MarketError("اقتصاد کشور یافت نشد.")
            treasury = float(eco["treasury"] or 0)
            if treasury < total:
                raise MarketError("موجودی خزانه برای این خرید کافی نیست.")
            new_treasury = treasury - total
            await tx.execute(
                "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                (new_treasury, country_code),
            )
            await tx.execute(
                "UPDATE countries SET treasury=$1 WHERE country_code=$2",
                (new_treasury, country_code),
            )
            now = datetime.now(timezone.utc).isoformat()
            for it in items:
                inv = await tx.fetchrow(
                    "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                    (country_code, it["item_code"]),
                )
                q = float(it["quantity"])
                if inv:
                    await tx.execute(
                        "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                        (float(inv["quantity"]) + q, now, country_code, it["item_code"]),
                    )
                else:
                    await tx.execute(
                        "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                        (country_code, it["item_code"], q, now),
                    )
                if it["item_code"] in BUILDING_CODES:
                    for _ in range(int(q)):
                        await tx.execute(
                            """
                            INSERT INTO country_buildings (country_code, building_code, level, built_at, active)
                            VALUES ($1,$2,1,$3,1)
                            """,
                            (country_code, it["item_code"], now),
                        )
            await tx.execute("DELETE FROM cart_items WHERE player_id=$1", (player_id,))
        await self.recalc_military(country_code)
        await self._log("purchase", f"خرید از فروشگاه به مبلغ {int(total):,}", country_code, player_id, {"total": total})
        return f"✅ خرید موفق\nمبلغ: {int(total):,}\nخزانه باقی‌مانده: {int(new_treasury):,}"

    async def inventory(self, country_code: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM inventory_items WHERE country_code=$1 AND quantity > 0 ORDER BY item_code",
            (country_code,),
        )
        out = []
        for r in rows:
            meta = self._by_code.get(r["item_code"], {"name_fa": r["item_code"], "unit_price": 0, "category": "?"})
            out.append({**r, **meta})
        return out

    async def inventory_text(self, country_code: str) -> str:
        rows = await self.inventory(country_code)
        lines = ["📦 انبار من", ""]
        if not rows:
            lines.append("انبار خالی است.")
        for r in rows:
            val = float(r["quantity"]) * float(r.get("unit_price") or 0)
            lines.append(
                f"• {r.get('name_fa', r['item_code'])}: {int(float(r['quantity']))} "
                f"(ارزش تقریبی {int(val):,})"
            )
        return "\n".join(lines)

    async def list_market(self, category: str | None = None, page: int = 0, per: int = 8) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT * FROM market_listings WHERE active=1 AND quantity > 0
            ORDER BY unit_price ASC
            """
        )
        if category:
            rows = [r for r in rows if self._by_code.get(r["item_code"], {}).get("category") == category]
        start = page * per
        return rows[start : start + per]

    async def create_listing(self, country: str, item_code: str, qty: float, unit_price: float, player_id: int | None = None) -> str:
        item = self.item(item_code)
        qty = float(qty)
        unit_price = float(unit_price)
        if qty <= 0 or unit_price <= 0:
            raise MarketError("تعداد یا قیمت نامعتبر است.")
        async with self.db.transaction() as tx:
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (country, item_code),
            )
            have = float(inv["quantity"]) if inv else 0.0
            if have < qty:
                raise MarketError("موجودی انبار کافی نیست.")
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                (have - qty, now, country, item_code),
            )
            # SQLite autoincrement: use max+1 for portable id
            mid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM market_listings")
            lid = int(mid["id"])
            await tx.execute(
                """
                INSERT INTO market_listings (id, seller_country, item_code, quantity, unit_price, created_at, active)
                VALUES ($1,$2,$3,$4,$5,$6,1)
                """,
                (lid, country, item_code, qty, unit_price, now),
            )
        await self._log("market_list", f"آگهی {item['name_fa']} × {int(qty)}", country, player_id)
        return f"✅ آگهی ثبت شد (شماره {lid})"

    async def buy_listing(self, listing_id: int, buyer_country: str, player_id: int | None = None) -> str:
        async with self.db.transaction() as tx:
            listing = await tx.fetchrow(
                "SELECT * FROM market_listings WHERE id=$1 AND active=1", (listing_id,)
            )
            if not listing or float(listing["quantity"]) <= 0:
                raise MarketError("این آگهی دیگر موجود نیست.")
            if listing["seller_country"] == buyer_country:
                raise MarketError("نمی‌توانید از آگهی خودتان بخرید.")
            qty = float(listing["quantity"])
            price = qty * float(listing["unit_price"])
            buyer = await tx.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1", (buyer_country,)
            )
            seller = await tx.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1",
                (listing["seller_country"],),
            )
            if not buyer or not seller:
                raise MarketError("اقتصاد طرفین یافت نشد.")
            if float(buyer["treasury"]) < price:
                raise MarketError("موجودی خزانه برای این خرید کافی نیست.")
            # deactivate listing first (optimistic lock style)
            upd = await tx.execute(
                "UPDATE market_listings SET active=0, quantity=0 WHERE id=$1 AND active=1 AND quantity=$2",
                (listing_id, qty),
            )
            # still apply money
            await tx.execute(
                "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                (float(buyer["treasury"]) - price, buyer_country),
            )
            await tx.execute(
                "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                (float(seller["treasury"]) + price, listing["seller_country"]),
            )
            now = datetime.now(timezone.utc).isoformat()
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (buyer_country, listing["item_code"]),
            )
            if inv:
                await tx.execute(
                    "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                    (float(inv["quantity"]) + qty, now, buyer_country, listing["item_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                    (buyer_country, listing["item_code"], qty, now),
                )
        name = self._by_code.get(listing["item_code"], {}).get("name_fa", listing["item_code"])
        await self._log("market_buy", f"خرید {name} از بازار", buyer_country, player_id, {"listing_id": listing_id})
        return f"✅ خرید از بازار انجام شد\n{name} × {int(qty)}\nمبلغ: {int(price):,}"

    async def cancel_listing(self, listing_id: int, country: str) -> str:
        async with self.db.transaction() as tx:
            listing = await tx.fetchrow(
                "SELECT * FROM market_listings WHERE id=$1 AND active=1 AND seller_country=$2",
                (listing_id, country),
            )
            if not listing:
                raise MarketError("آگهی یافت نشد.")
            qty = float(listing["quantity"])
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE market_listings SET active=0 WHERE id=$1", (listing_id,)
            )
            inv = await tx.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (country, listing["item_code"]),
            )
            if inv:
                await tx.execute(
                    "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                    (float(inv["quantity"]) + qty, now, country, listing["item_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                    (country, listing["item_code"], qty, now),
                )
        return "✅ آگهی لغو و کالا به انبار برگشت."

    async def produce_buildings(self, country_code: str | None = None) -> int:
        """Run production for active buildings. Returns number of productions."""
        if country_code:
            buildings = await self.db.fetch(
                "SELECT * FROM country_buildings WHERE active=1 AND country_code=$1",
                (country_code,),
            )
        else:
            buildings = await self.db.fetch(
                "SELECT * FROM country_buildings WHERE active=1"
            )
        n = 0
        now = datetime.now(timezone.utc).isoformat()
        for b in buildings:
            out = BUILDING_OUTPUT.get(b["building_code"])
            if not out:
                continue
            item_code, base = out
            qty = base * int(b.get("level") or 1)
            # maintenance from treasury if possible
            meta = self._by_code.get(b["building_code"], {})
            maint = float(meta.get("maintenance_cost") or 0)
            eco = await self.db.fetchrow(
                "SELECT treasury FROM country_economy WHERE country_code=$1",
                (b["country_code"],),
            )
            if eco and float(eco["treasury"]) >= maint:
                await self.db.execute(
                    "UPDATE country_economy SET treasury=$1 WHERE country_code=$2",
                    (float(eco["treasury"]) - maint, b["country_code"]),
                )
            inv = await self.db.fetchrow(
                "SELECT quantity FROM inventory_items WHERE country_code=$1 AND item_code=$2",
                (b["country_code"], item_code),
            )
            if inv:
                await self.db.execute(
                    "UPDATE inventory_items SET quantity=$1, updated_at=$2 WHERE country_code=$3 AND item_code=$4",
                    (float(inv["quantity"]) + qty, now, b["country_code"], item_code),
                )
            else:
                await self.db.execute(
                    "INSERT INTO inventory_items (country_code, item_code, quantity, updated_at) VALUES ($1,$2,$3,$4)",
                    (b["country_code"], item_code, qty, now),
                )
            await self.db.execute(
                "UPDATE country_buildings SET last_produced_at=$1 WHERE id=$2",
                (now, b["id"]),
            )
            n += 1
        if n:
            await self._log("production", f"تولید صنعتی: {n} تأسیسات", country_code)
        return n

    async def recalc_military(self, country_code: str) -> None:
        rows = await self.inventory(country_code)
        ground = air = sea = defense = 0.0
        for r in rows:
            cat = r.get("category")
            score = float(r.get("power_score") or 0) * float(r["quantity"])
            if cat == "ground":
                ground += score
            elif cat == "air":
                air += score
            elif cat == "sea":
                sea += score
            elif cat == "defense":
                defense += score
        now = datetime.now(timezone.utc).isoformat()
        await self._ensure_military_row(country_code)
        await self.db.execute(
            """
            UPDATE military_status SET ground_power=$1, air_power=$2, sea_power=$3,
                defense_power=$4, updated_at=$5 WHERE country_code=$6
            """,
            (ground, air, sea, defense, now, country_code),
        )

    async def military_text(self, country_code: str) -> str:
        await self.recalc_military(country_code)
        m = await self.db.fetchrow(
            "SELECT * FROM military_status WHERE country_code=$1", (country_code,)
        )
        if not m:
            return "وضعیت نظامی در دسترس نیست."
        return (
            "🛡 مدیریت دفاعی\n\n"
            f"آمادگی دفاعی: {float(m['readiness']):.0f}\n"
            f"قدرت زمینی: {float(m['ground_power']):.0f}\n"
            f"قدرت هوایی: {float(m['air_power']):.0f}\n"
            f"قدرت دریایی: {float(m['sea_power']):.0f}\n"
            f"پدافند: {float(m['defense_power']):.0f}\n"
            f"سهم بودجه دفاعی: {float(m['defense_budget_rate'])*100:.0f}٪\n\n"
            "واحدها از فروشگاه خریداری و در انبار نگهداری می‌شوند."
        )

    async def crisis_resolve(self, attacker: str, defender: str, player_id: int | None = None) -> str:
        """Abstract crisis outcome — no real combat mechanics."""
        await self.recalc_military(attacker)
        await self.recalc_military(defender)
        a = await self.db.fetchrow("SELECT * FROM military_status WHERE country_code=$1", (attacker,))
        d = await self.db.fetchrow("SELECT * FROM military_status WHERE country_code=$1", (defender,))
        ae = await self.db.fetchrow("SELECT treasury, stability, public_satisfaction FROM country_economy WHERE country_code=$1", (attacker,))
        de = await self.db.fetchrow("SELECT treasury, stability, public_satisfaction FROM country_economy WHERE country_code=$1", (defender,))
        ap = sum(float(a[k]) for k in ("ground_power", "air_power", "sea_power", "defense_power")) + float(a["readiness"])
        dp = sum(float(d[k]) for k in ("ground_power", "air_power", "sea_power", "defense_power")) + float(d["readiness"]) + float(de["stability"]) * 0.5
        # economic stress both sides
        async with self.db.transaction() as tx:
            cost_a = min(float(ae["treasury"]) * 0.02, 5000)
            cost_d = min(float(de["treasury"]) * 0.015, 4000)
            await tx.execute(
                "UPDATE country_economy SET treasury=$1, stability=$2 WHERE country_code=$3",
                (float(ae["treasury"]) - cost_a, max(0, float(ae["stability"]) - 2), attacker),
            )
            await tx.execute(
                "UPDATE country_economy SET treasury=$1, stability=$2 WHERE country_code=$3",
                (float(de["treasury"]) - cost_d, max(0, float(de["stability"]) - (3 if ap > dp else 1)), defender),
            )
        winner = attacker if ap > dp else defender
        await self._log(
            "crisis",
            f"مدیریت بحران بین {attacker} و {defender} — نتیجه انتزاعی به نفع {winner}",
            attacker,
            player_id,
            {"attacker_score": ap, "defender_score": dp},
        )
        return (
            "⚖️ نتیجه مدیریت بحران (انتزاعی)\n"
            f"طرف اول: {attacker} (امتیاز {ap:.0f})\n"
            f"طرف دوم: {defender} (امتیاز {dp:.0f})\n"
            f"جمع‌بندی سیاسی: فشار بیشتر روی {defender if ap>dp else attacker}\n"
            "هزینه اقتصادی محدود برای هر دو طرف ثبت شد."
        )

    async def activity_text(self, country_code: str, limit: int = 12) -> str:
        rows = await self.db.fetch(
            """
            SELECT * FROM activity_log WHERE country_code=$1
            ORDER BY real_time DESC
            """,
            (country_code,),
        )
        rows = rows[:limit]
        lines = ["📜 گزارش فعالیت‌ها", ""]
        if not rows:
            lines.append("هنوز فعالیتی ثبت نشده است.")
        for r in rows:
            lines.append(f"• [{r.get('game_date') or '—'}] {r['summary']}")
        return "\n".join(lines)
