"""New Generation game core — countries, economy, war, peace, admin."""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from database.interface import Database
from modules.ng.catalog import CATALOG, CAT_FA

log = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "countries" / "seed_ng.json"
UN_CODE = "UN"


class GameError(Exception):
    pass


class Game:
    def __init__(self, db: Database, owner_id: int = 0, group_id: str | None = None):
        self.db = db
        self.owner_id = owner_id
        self.group_id = group_id
        self._cat = {c["item_code"]: c for c in CATALOG}

    # ---------- bootstrap ----------
    async def bootstrap(self) -> None:
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        now = datetime.now(timezone.utc).isoformat()
        if not meta:
            await self.db.execute(
                """
                INSERT INTO world_meta (id, started_at, war_enabled, nuclear_enabled, log_flags_json, main_group_id, reset_count)
                VALUES (1,$1,1,0,$2,$3,0)
                """,
                (now, json.dumps(self._default_logs()), self.group_id),
            )
        await self._seed_catalog()
        await self._seed_countries()
        await self.ensure_un_country()
        await self._seed_bot_settings()
        await self._seed_membership()

    def _default_logs(self) -> dict:
        keys = [
            "buy","sell","attack","destroy","statement","peace","aid_money","aid_army",
            "ban","unban","trade","admin",
        ]
        return {k: True for k in keys}

    async def ensure_shop_catalog(self) -> None:
        """Re-run catalog seed so new items appear without full world reset."""
        await self._seed_catalog()

    async def _seed_catalog(self) -> None:
        """Insert new items; refresh metadata for existing without wiping inventory."""
        for c in CATALOG:
            exists = await self.db.fetchrow(
                "SELECT item_code FROM ng_shop_catalog WHERE item_code=$1", (c["item_code"],)
            )
            vals = (
                c["item_code"], c["category"], c["name_fa"], c["description_fa"],
                c["unit_price"], c["max_per_order"], c["power_score"],
                c["daily_income"], c["maintenance"], c["is_building"],
            )
            if not exists:
                await self.db.execute(
                    """
                    INSERT INTO ng_shop_catalog (
                        item_code, category, name_fa, description_fa, unit_price, max_per_order,
                        power_score, daily_income, maintenance, is_building
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    vals,
                )
            else:
                await self.db.execute(
                    """
                    UPDATE ng_shop_catalog SET
                        category=$2, name_fa=$3, description_fa=$4, unit_price=$5,
                        max_per_order=$6, power_score=$7, daily_income=$8,
                        maintenance=$9, is_building=$10
                    WHERE item_code=$1
                    """,
                    vals,
                )
            self._cat[c["item_code"]] = c

    async def _seed_countries(self) -> None:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for c in data:
            exists = await self.db.fetchrow(
                "SELECT country_code FROM ng_countries WHERE country_code=$1", (c["code"],)
            )
            if exists:
                continue
            # free country — no treasury until claimed
            await self.db.execute(
                """
                INSERT INTO ng_countries (
                    country_code, name_fa, name_en, flag, capital_fa, leader_fa, leader_title_fa,
                    currency_code, currency_name_fa, npt_member, owner_player_id, treasury, hp, max_hp, is_destroyed
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NULL,0,1000,1000,0)
                """,
                (
                    c["code"], c["name_fa"], c["name_en"], c["flag"], c["capital_fa"],
                    c["leader_fa"], c["leader_title_fa"], c["currency_code"], c["currency_name_fa"],
                    int(c.get("npt", 1)),
                ),
            )


    async def ensure_un_country(self) -> None:
        """Ensure UN country exists and is permanently owned by the bot owner."""
        if not self.owner_id:
            return
        row = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (UN_CODE,)
        )
        now = datetime.now(timezone.utc).isoformat()
        if not row:
            await self.db.execute(
                """
                INSERT INTO ng_countries (
                    country_code, name_fa, name_en, flag, capital_fa, leader_fa, leader_title_fa,
                    currency_code, currency_name_fa, npt_member, owner_player_id, treasury, hp, max_hp, is_destroyed, claimed_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,1,$10,$11,1000,1000,0,$12)
                """,
                (
                    UN_CODE, "سازمان ملل", "United Nations", "🇺🇳", "نیویورک",
                    "دبیرکل سازمان ملل", "دبیرکل", "UND", "واحد سازمان ملل",
                    self.owner_id, 200_000_000.0, now,
                ),
            )
        else:
            await self.db.execute(
                """
                UPDATE ng_countries
                SET owner_player_id=$1, is_destroyed=0, name_fa='سازمان ملل', flag='🇺🇳'
                WHERE country_code=$2
                """,
                (self.owner_id, UN_CODE),
            )
        # bind owner player row
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (self.owner_id,))
        if not p:
            await self.db.execute(
                "INSERT INTO ng_players (player_id, username, display_name, country_code, joined_at, last_seen_at) VALUES ($1,$2,$3,$4,$5,$5)",
                (self.owner_id, "owner", "مالک", UN_CODE, now),
            )
        else:
            # only force UN if owner has no other country or already UN
            cur = p.get("country_code")
            if not cur or cur == UN_CODE:
                await self.db.execute(
                    "UPDATE ng_players SET country_code=$1 WHERE player_id=$2",
                    (UN_CODE, self.owner_id),
                )

    def starting_capital(self, code: str) -> float:

        data = {c["code"]: c for c in json.loads(SEED_PATH.read_text(encoding="utf-8"))}
        mult = float(data.get(code, {}).get("capital_mult", 0.8))
        base = random.uniform(50_000_000, 100_000_000)
        return round(base * mult, 2)

    # ---------- players ----------
    async def touch_player(self, pid: int, username=None, display=None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (pid,))
        if row:
            await self.db.execute(
                "UPDATE ng_players SET username=COALESCE($1,username), display_name=COALESCE($2,display_name), last_seen_at=$3 WHERE player_id=$4",
                (username, display, now, pid),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_players (player_id, username, display_name, joined_at, last_seen_at) VALUES ($1,$2,$3,$4,$4)",
                (pid, username, display, now),
            )
        if self.owner_id and int(pid) == int(self.owner_id):
            await self.ensure_un_country()
        return await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (pid,))

    async def assert_not_banned(self, pid: int) -> None:
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (pid,))
        if not p:
            return
        if int(p.get("is_banned") or 0) == 1:
            until = p.get("banned_until")
            if until:
                try:
                    if datetime.now(timezone.utc) < datetime.fromisoformat(until.replace("Z", "+00:00")):
                        raise GameError("شما مسدود شده‌اید و نمی‌توانید از بازی استفاده کنید.")
                except GameError:
                    raise
                except Exception:
                    raise GameError("شما مسدود شده‌اید.")
            else:
                raise GameError("شما مسدود شده‌اید و نمی‌توانید از بازی استفاده کنید.")

    async def player_country(self, pid: int) -> Optional[str]:
        if self.owner_id and int(pid) == int(self.owner_id):
            await self.ensure_un_country()
            return UN_CODE
        p = await self.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (pid,))
        return (p or {}).get("country_code")

    # ---------- claim ----------
    async def list_countries(self, *, for_owner: bool = False, include_un: bool = False) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_countries WHERE is_destroyed=0 ORDER BY name_fa"
        )
        if for_owner or include_un:
            return rows
        return [r for r in rows if r.get("country_code") != UN_CODE]

    async def claim(self, pid: int, code: str) -> dict:
        await self.assert_not_banned(pid)
        code = code.upper()
        if code == UN_CODE:
            raise GameError("کشور سازمان ملل فقط متعلق به مالک بازی است و قابل انتخاب نیست.")
        p = await self.touch_player(pid)
        if p.get("country_code"):
            raise GameError("شما هم‌اکنون یک کشور دارید.")
        cd = p.get("destroy_cooldown_until")
        if cd:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(cd.replace("Z", "+00:00")):
                    raise GameError("کشور شما نابود شده است. تا ۲ روز آینده امکان انتخاب کشور جدید ندارید.")
            except GameError:
                raise
            except Exception:
                pass
        capital = self.starting_capital(code)
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            c = await tx.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
            )
            if not c or int(c.get("is_destroyed") or 0):
                raise GameError("کشور معتبر نیست.")
            if c.get("owner_player_id"):
                raise GameError("این کشور دارای بازیکن است.")
            # atomic claim
            await tx.execute(
                """
                UPDATE ng_countries SET owner_player_id=$1, treasury=$2, claimed_at=$3, hp=1000, is_destroyed=0
                WHERE country_code=$4 AND owner_player_id IS NULL
                """,
                (pid, capital, now, code),
            )
            check = await tx.fetchrow(
                "SELECT owner_player_id FROM ng_countries WHERE country_code=$1", (code,)
            )
            if not check or int(check["owner_player_id"]) != pid:
                raise GameError("کشور در لحظه آخر توسط بازیکن دیگری گرفته شد.")
            await tx.execute(
                "UPDATE ng_players SET country_code=$1 WHERE player_id=$2", (code, pid)
            )
        await self.log_activity("claim", f"انتخاب کشور {await self.country_name_only(code)}", code, pid)
        return await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))

    # ---------- economy / shop ----------
    def shop_price_multiplier(self, country: dict) -> float:
        pen = country.get("peace_penalty_until")
        if not pen:
            return 1.0
        try:
            if datetime.now(timezone.utc) < datetime.fromisoformat(str(pen).replace("Z", "+00:00")):
                return 1.15
        except Exception:
            pass
        return 1.0

    async def cart_add(self, pid: int, item: str, qty: float) -> str:
        meta = self._cat[item]
        qty = max(1, min(float(meta["max_per_order"]), float(qty)))
        row = await self.db.fetchrow(
            "SELECT quantity FROM ng_cart WHERE player_id=$1 AND item_code=$2", (pid, item)
        )
        if row:
            nq = min(float(meta["max_per_order"]), float(row["quantity"]) + qty)
            await self.db.execute(
                "UPDATE ng_cart SET quantity=$1 WHERE player_id=$2 AND item_code=$3",
                (nq, pid, item),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_cart (player_id, item_code, quantity) VALUES ($1,$2,$3)",
                (pid, item, qty),
            )
        return f"✅ {meta['name_fa']} × {int(qty)} به سبد اضافه شد."

    async def cart_view(self, pid: int, country_code: str) -> tuple[str, float, list]:
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (country_code,))
        mult = self.shop_price_multiplier(c or {})
        rows = await self.db.fetch("SELECT * FROM ng_cart WHERE player_id=$1", (pid,))
        total = 0.0
        items = []
        lines = ["🛒 سبد خرید", ""]
        for r in rows:
            meta = self._cat[r["item_code"]]
            price = float(meta["unit_price"]) * mult
            lt = price * float(r["quantity"])
            total += lt
            items.append({**r, **meta, "line_total": lt, "unit_price_eff": price})
            lines.append(f"• {meta['name_fa']} × {int(float(r['quantity']))} = {int(lt):,}")
        if not rows:
            lines.append("سبد خالی است.")
        lines.append(f"\nجمع: {int(total):,}")
        if mult > 1:
            lines.append("⚠ قیمت‌ها به‌خاطر نقض پیمان ۱۵٪ افزایش یافته‌اند.")
        return "\n".join(lines), total, items

    async def checkout(self, pid: int, country_code: str) -> str:
        _, total, items = await self.cart_view(pid, country_code)
        if not items:
            raise GameError("سبد خالی است.")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            c = await tx.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (country_code, pid),
            )
            if not c:
                raise GameError("مالکیت کشور معتبر نیست.")
            if float(c["treasury"]) < total:
                raise GameError("موجودی خزانه برای این خرید کافی نیست.")
            # nuclear gate
            meta_w = await tx.fetchrow("SELECT nuclear_enabled FROM world_meta WHERE id=1")
            nuke_on = int((meta_w or {}).get("nuclear_enabled") or 0) == 1
            for it in items:
                if it.get("category") == "nuclear" and not nuke_on:
                    raise GameError("قابلیت هسته‌ای بازی توسط سازمان ملل بسته است.")
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - total, country_code),
            )
            for it in items:
                inv = await tx.fetchrow(
                    "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                    (country_code, it["item_code"]),
                )
                q = float(it["quantity"])
                if inv:
                    await tx.execute(
                        "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                        (float(inv["quantity"]) + q, country_code, it["item_code"]),
                    )
                else:
                    await tx.execute(
                        "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                        (country_code, it["item_code"], q),
                    )
                if int(it.get("is_building") or 0):
                    for _ in range(int(q)):
                        nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_buildings")
                        await tx.execute(
                            "INSERT INTO ng_buildings (id, country_code, building_code, level, built_at, active) VALUES ($1,$2,$3,1,$4,1)",
                            (int(nid["id"]), country_code, it["item_code"], now),
                        )
            await tx.execute("DELETE FROM ng_cart WHERE player_id=$1", (pid,))
        await self.recalc_income(country_code)
        await self.log_activity("buy", f"خرید به مبلغ {int(total):,}", country_code, pid)
        await self.broadcast_log("buy", f"🛒 کشور {country_code} خرید انجام داد. مبلغ: {int(total):,}")
        return f"✅ خرید موفق\nمبلغ: {int(total):,}"

    async def recalc_income(self, code: str) -> None:
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1", (code,)
        )
        income = 0.0
        expense = 0.0
        for r in inv:
            meta = self._cat.get(r["item_code"])
            if not meta:
                continue
            q = float(r["quantity"])
            income += float(meta["daily_income"]) * q
            expense += float(meta["maintenance"]) * q
        await self.db.execute(
            "UPDATE ng_countries SET daily_income=$1, daily_expense=$2 WHERE country_code=$3",
            (income, expense, code),
        )

    async def daily_payout_all(self) -> int:
        """Pay once per Tehran calendar day."""
        today = datetime.now(TEHRAN).date().isoformat()
        countries = await self.db.fetch(
            "SELECT * FROM ng_countries WHERE owner_player_id IS NOT NULL AND is_destroyed=0"
        )
        n = 0
        for c in countries:
            code = c["country_code"]
            exists = await self.db.fetchrow(
                "SELECT 1 AS x FROM ng_daily_payouts WHERE country_code=$1 AND payout_date=$2",
                (code, today),
            )
            if exists:
                continue
            await self.recalc_income(code)
            c2 = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
            net = float(c2["daily_income"]) - float(c2["daily_expense"])
            async with self.db.transaction() as tx:
                again = await tx.fetchrow(
                    "SELECT 1 AS x FROM ng_daily_payouts WHERE country_code=$1 AND payout_date=$2",
                    (code, today),
                )
                if again:
                    continue
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(c2["treasury"]) + net, code),
                )
                await tx.execute(
                    "INSERT INTO ng_daily_payouts (country_code, payout_date, amount) VALUES ($1,$2,$3)",
                    (code, today, net),
                )
            n += 1
            await self.log_activity("daily", f"درآمد روزانه: {int(net):,}", code)
        return n

    # ---------- market ----------
    async def market_list(self, page=0, per=8):
        rows = await self.db.fetch(
            "SELECT * FROM ng_market WHERE active=1 AND quantity>0 ORDER BY unit_price"
        )
        return rows[page * per : (page + 1) * per]

    async def market_create(self, code: str, item: str, qty: float, price: float, pid: int) -> str:
        qty = float(qty)
        price = float(price)
        if qty <= 0 or price <= 0:
            raise GameError("مقدار/قیمت نامعتبر")
        async with self.db.transaction() as tx:
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (code, item),
            )
            have = float(inv["quantity"]) if inv else 0
            if have < qty:
                raise GameError("موجودی انبار کافی نیست.")
            await tx.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                (have - qty, code, item),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_market")
            await tx.execute(
                "INSERT INTO ng_market (id, seller_country, item_code, quantity, unit_price, active, created_at) VALUES ($1,$2,$3,$4,$5,1,$6)",
                (int(nid["id"]), code, item, qty, price, datetime.now(timezone.utc).isoformat()),
            )
        await self.log_activity("sell", f"آگهی بازار {item} × {int(qty)}", code, pid)
        return "✅ آگهی ثبت شد."

    async def market_buy(self, listing_id: int, buyer: str, pid: int) -> str:
        async with self.db.transaction() as tx:
            L = await tx.fetchrow("SELECT * FROM ng_market WHERE id=$1 AND active=1", (listing_id,))
            if not L or float(L["quantity"]) <= 0:
                raise GameError("آگهی موجود نیست.")
            if L["seller_country"] == buyer:
                raise GameError("خرید از خودتان ممکن نیست.")
            qty = float(L["quantity"])
            cost = qty * float(L["unit_price"])
            b = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (buyer,))
            s = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (L["seller_country"],)
            )
            if float(b["treasury"]) < cost:
                raise GameError("موجودی خزانه برای این خرید کافی نیست.")
            await tx.execute(
                "UPDATE ng_market SET active=0, quantity=0 WHERE id=$1 AND active=1 AND quantity=$2",
                (listing_id, qty),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(b["treasury"]) - cost, buyer),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(s["treasury"]) + cost, L["seller_country"]),
            )
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (buyer, L["item_code"]),
            )
            if inv:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (float(inv["quantity"]) + qty, buyer, L["item_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                    (buyer, L["item_code"], qty),
                )
        await self.log_activity("buy", f"خرید بازار #{listing_id}", buyer, pid)
        return f"✅ خرید بازار انجام شد. مبلغ {int(cost):,}"

    # ---------- aid ----------
    async def aid_money(self, src: str, dst: str, amount: float, pid: int) -> str:
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ نامعتبر")
        if src == dst:
            raise GameError("مقصد نامعتبر")
        async with self.db.transaction() as tx:
            a = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (src,))
            b = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (dst,))
            if not a or not b:
                raise GameError("کشور یافت نشد")
            if float(a["treasury"]) < amount:
                raise GameError("موجودی کافی نیست")
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(a["treasury"]) - amount, src),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(b["treasury"]) + amount, dst),
            )
        await self.log_activity("aid_money", f"کمک مالی {int(amount):,} به {dst}", src, pid)
        await self.broadcast_log("aid_money", f"💰 {src} به {dst} کمک مالی کرد: {int(amount):,}")
        return "✅ کمک مالی انجام شد."

    async def aid_army(self, src: str, dst: str, item: str, qty: float, pid: int) -> str:
        qty = float(qty)
        if qty <= 0:
            raise GameError("تعداد نامعتبر")
        async with self.db.transaction() as tx:
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (src, item),
            )
            have = float(inv["quantity"]) if inv else 0
            if have < qty:
                raise GameError("موجودی تجهیزات کافی نیست")
            await tx.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                (have - qty, src, item),
            )
            inv2 = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (dst, item),
            )
            if inv2:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (float(inv2["quantity"]) + qty, dst, item),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                    (dst, item, qty),
                )
        await self.log_activity("aid_army", f"کمک نظامی {item}×{int(qty)} به {dst}", src, pid)
        await self.broadcast_log("aid_army", f"📦 {src} به {dst} کمک نظامی ارسال کرد.")
        return "✅ کمک نظامی ارسال شد."

    # ---------- peace ----------
    async def peace_request(self, a: str, b: str, hours: float, pid: int) -> str:
        hours = max(1.0, min(20.0, float(hours)))
        if a == b:
            raise GameError("نامعتبر")
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_peace")
        await self.db.execute(
            """
            INSERT INTO ng_peace (id, country_a, country_b, status, duration_hours, requested_by, started_at)
            VALUES ($1,$2,$3,'pending',$4,$5,$6)
            """,
            (
                int(nid["id"]),
                a,
                b,
                hours,
                a,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return f"✅ درخواست صلح {hours:g} ساعته برای {b} ارسال شد."

    async def peace_accept(self, peace_id: int, country: str, pid: int) -> str:
        async with self.db.transaction() as tx:
            p = await tx.fetchrow("SELECT * FROM ng_peace WHERE id=$1 AND status='pending'", (peace_id,))
            if not p:
                raise GameError("درخواست یافت نشد")
            if p["country_b"] != country and p["country_a"] != country:
                raise GameError("دسترسی ندارید")
            # acceptor should be the other party
            now = datetime.now(timezone.utc)
            ends = now + timedelta(hours=float(p["duration_hours"]))
            await tx.execute(
                "UPDATE ng_peace SET status='active', started_at=$1, ends_at=$2 WHERE id=$3",
                (now.isoformat(), ends.isoformat(), peace_id),
            )
        await self.broadcast_log("peace", f"🕊 پیمان صلح بین {p['country_a']} و {p['country_b']} فعال شد.")
        return "✅ پیمان صلح فعال شد."

    async def peace_break(self, peace_id: int, country: str, pid: int) -> str:
        async with self.db.transaction() as tx:
            p = await tx.fetchrow("SELECT * FROM ng_peace WHERE id=$1 AND status='active'", (peace_id,))
            if not p:
                raise GameError("پیمان فعال یافت نشد")
            if country not in (p["country_a"], p["country_b"]):
                raise GameError("دسترسی ندارید")
            await tx.execute(
                "UPDATE ng_peace SET status='broken', broken_by=$1 WHERE id=$2",
                (country, peace_id),
            )
            until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            await tx.execute(
                "UPDATE ng_countries SET peace_penalty_until=$1 WHERE country_code=$2",
                (until, country),
            )
        await self.broadcast_log("peace", f"⚠ {country} پیمان صلح را نقض کرد.")
        return "پیمان پایان یافت. مجازات یک‌ساعته اعمال شد."

    async def at_peace(self, a: str, b: str) -> bool:
        rows = await self.db.fetch(
            "SELECT * FROM ng_peace WHERE status='active'"
        )
        now = datetime.now(timezone.utc)
        for p in rows:
            pair = {p["country_a"], p["country_b"]}
            if {a, b} != pair:
                continue
            ends = p.get("ends_at")
            if ends:
                try:
                    if now < datetime.fromisoformat(str(ends).replace("Z", "+00:00")):
                        return True
                    else:
                        await self.db.execute(
                            "UPDATE ng_peace SET status='expired' WHERE id=$1", (p["id"],)
                        )
                except Exception:
                    return True
        return False

    # ---------- war ----------
    ATTACK_COOLDOWN_SEC = 300
    MAX_LOOT_RATIO = 0.08  # max 8% of defender treasury
    MAX_LOOT_ABS = 2_000_000

    async def power(self, code: str, kind: str) -> float:
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        total = 0.0
        for r in inv:
            meta = self._cat.get(r["item_code"])
            if not meta:
                continue
            cat = meta["category"]
            ps = float(meta.get("power_score") or 0) * float(r["quantity"])
            if kind == "ground" and cat in ("ground", "defense"):
                total += ps
            elif kind == "ground" and cat == "missile" and r["item_code"] in ("m_cruise", "m_ballistic", "m_agm"):
                total += ps * 0.8
            elif kind == "air" and cat == "air":
                total += ps
            elif kind == "air" and cat == "missile" and r["item_code"] in ("m_aam", "m_agm"):
                total += ps * 0.7
            elif kind == "sea" and cat == "sea":
                total += ps
            elif kind == "sea" and cat == "missile" and r["item_code"] == "m_antiship":
                total += ps
            elif kind == "defense" and cat in ("defense",):
                total += ps
            elif kind == "defense" and cat == "missile" and r["item_code"] in ("m_sam_patriot", "m_sam_s400"):
                total += ps
        return total


    # ---- air defense & cyber ----
    DEFENSE_COVER_CAP = 0.65  # never 100%
    CYBER_DEF_DISABLE_RATIO = 0.30  # 30% of defense offline
    CYBER_DEF_DURATION_SEC = 120
    CYBER_HACK_COOLDOWN_SEC = 180  # per attacker country

    async def defense_power(self, code: str) -> float:
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        total = 0.0
        for r in inv:
            meta = self._cat.get(r["item_code"])
            if not meta:
                continue
            cat = meta["category"]
            code_i = r["item_code"]
            if cat == "defense" or code_i in ("m_sam_patriot", "m_sam_s400", "d_sam", "d_radar"):
                total += float(meta.get("power_score") or 0) * float(r["quantity"])
        return total

    async def active_cyber_disable_ratio(self, code: str) -> float:
        """Return fraction of defense currently disabled (0..1)."""
        now = datetime.now(timezone.utc)
        rows = await self.db.fetch(
            "SELECT * FROM ng_cyber_effects WHERE target_country=$1 AND effect_type='def_disable'",
            (code,),
        )
        best = 0.0
        for r in rows:
            try:
                ends = datetime.fromisoformat(str(r["ends_at"]).replace("Z", "+00:00"))
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                if ends > now:
                    best = max(best, float(r.get("strength") or self.CYBER_DEF_DISABLE_RATIO))
            except Exception:
                continue
        return min(0.9, best)

    async def defense_coverage(self, code: str, attack_kind: str) -> tuple[float, dict]:
        """Return (intercept_ratio 0..cap, meta for report)."""
        raw = await self.defense_power(code)
        # soft curve, expensive to max out
        base = raw / (raw + 120.0) * 0.72
        base = min(self.DEFENSE_COVER_CAP, max(0.0, base))
        # effectiveness by attack type
        kind_factor = {"air": 1.0, "ground": 0.4, "sea": 0.25, "nuclear": 0.15}.get(attack_kind, 0.5)
        disable = await self.active_cyber_disable_ratio(code)
        effective = base * kind_factor * (1.0 - disable)
        effective = min(self.DEFENSE_COVER_CAP, max(0.0, effective))
        return effective, {
            "defense_power": raw,
            "base_cover": base,
            "kind_factor": kind_factor,
            "cyber_disable": disable,
            "intercept": effective,
        }

    async def _consume_item(self, code: str, item: str, qty: float = 1.0) -> None:
        row = await self.db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (code, item),
        )
        if not row or float(row["quantity"]) < qty:
            raise GameError("آیتم موردنیاز را ندارید.")
        left = float(row["quantity"]) - qty
        if left <= 0:
            await self.db.execute(
                "DELETE FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (code, item),
            )
        else:
            await self.db.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                (left, code, item),
            )

    async def hack_defense(self, attacker: str, target: str, pid: int) -> str:
        if attacker == target:
            raise GameError("هدف نامعتبر است")
        if target == UN_CODE:
            raise GameError("هدف مجاز نیست")
        a = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (attacker, pid),
        )
        if not a:
            raise GameError("کشور شما یافت نشد")
        t = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (target,))
        if not t or int(t.get("is_destroyed") or 0):
            raise GameError("هدف معتبر نیست")
        # cooldown: no overlapping active effect from same source, and global cooldown
        now = datetime.now(timezone.utc)
        active = await self.db.fetch(
            "SELECT * FROM ng_cyber_effects WHERE source_country=$1 AND effect_type='def_disable'",
            (attacker,),
        )
        for r in active:
            try:
                ends = datetime.fromisoformat(str(r["ends_at"]).replace("Z", "+00:00"))
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                if ends > now:
                    raise GameError("هنوز یک عملیات هکر پدافند فعال دارید. صبر کنید تا تمام شود.")
                starts = datetime.fromisoformat(str(r["starts_at"]).replace("Z", "+00:00"))
                if starts.tzinfo is None:
                    starts = starts.replace(tzinfo=timezone.utc)
                if (now - starts).total_seconds() < self.CYBER_HACK_COOLDOWN_SEC:
                    left = int(self.CYBER_HACK_COOLDOWN_SEC - (now - starts).total_seconds())
                    raise GameError(f"محدودیت استفاده از هکر پدافند: {left} ثانیه.")
            except GameError:
                raise
            except Exception:
                pass
        await self._consume_item(attacker, "cyber_hack_def", 1)
        ends = now + timedelta(seconds=self.CYBER_DEF_DURATION_SEC)
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_cyber_effects")
        await self.db.execute(
            """
            INSERT INTO ng_cyber_effects
            (id, target_country, effect_type, source_country, actor_id, strength, starts_at, ends_at, created_at)
            VALUES ($1,$2,'def_disable',$3,$4,$5,$6,$7,$6)
            """,
            (
                int(nid["id"]), target, attacker, pid, self.CYBER_DEF_DISABLE_RATIO,
                now.isoformat(), ends.isoformat(),
            ),
        )
        tname = await self.country_label(target)
        msg = (
            f"🛡 عملیات هکر پدافند موفق بود.\n"
            f"هدف: {tname}\n"
            f"اثر: ۳۰٪ ظرفیت پدافند هدف به مدت ۲ دقیقه مختل شد.\n"
            f"پایان اثر: {ends.astimezone(TEHRAN).strftime('%H:%M:%S')} (تهران)\n"
            f"۱ عدد «هکر پدافند» مصرف شد."
        )
        await self.log_activity("cyber", f"هکر پدافند روی {target}", attacker, pid)
        await self.broadcast_log("admin", f"💻 اختلال پدافند موقت روی {tname}")
        return msg

    async def hack_assets(self, attacker: str, target: str, pid: int) -> str:
        if attacker == target:
            raise GameError("هدف نامعتبر است")
        if target == UN_CODE:
            raise GameError("هدف مجاز نیست")
        a = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (attacker, pid),
        )
        if not a:
            raise GameError("کشور شما یافت نشد")
        t = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (target,))
        if not t or int(t.get("is_destroyed") or 0):
            raise GameError("هدف معتبر نیست")
        await self._consume_item(attacker, "cyber_hack_asset", 1)
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
            (target,),
        )
        mil = 0
        eco = []
        lines = []
        for r in inv:
            meta = self._cat.get(r["item_code"], {})
            name = meta.get("name_fa", r["item_code"])
            q = float(r["quantity"])
            cat = meta.get("category", "")
            if cat in ("ground", "air", "sea", "missile", "defense"):
                mil += q
                lines.append(f"• {name}: {int(q)}")
            elif cat in ("mine", "infra", "nuclear", "specialist") or meta.get("is_building"):
                eco.append(f"• {name}: {int(q)}")
        tname = await self.country_label(target)
        text = (
            f"💰 گزارش هکر دارایی — {tname}\n\n"
            f"خزانه: {int(float(t['treasury'])):,} {t.get('currency_name_fa') or ''}\n"
            f"سلامت: {int(float(t['hp']))}/{int(float(t['max_hp']))}\n"
            f"NPT: {'عضو' if int(t.get('npt_member') or 0) else 'غیرعضو'}\n"
            f"درآمد روزانه ثبت‌شده: {int(float(t.get('daily_income') or 0)):,}\n"
            f"هزینه روزانه ثبت‌شده: {int(float(t.get('daily_expense') or 0)):,}\n\n"
            f"تعداد کل واحدهای نظامی در انبار: {int(mil)}\n"
        )
        if lines:
            text += "تجهیزات نظامی:\n" + "\n".join(lines[:25])
            if len(lines) > 25:
                text += f"\n… و {len(lines)-25} مورد دیگر"
        if eco:
            text += "\n\nدارایی‌های اقتصادی:\n" + "\n".join(eco[:15])
        text += "\n\n۱ عدد «هکر دارایی» مصرف شد. هیچ تغییری در دارایی هدف اعمال نشد."
        await self.log_activity("cyber", f"هکر دارایی روی {target}", attacker, pid)
        return text

    async def cyber_status_text(self, code: str) -> str:
        dis = await self.active_cyber_disable_ratio(code)
        cov, meta = await self.defense_coverage(code, "air")
        lines = [
            "💻 وضعیت پدافند و سایبری",
            f"قدرت پدافند خام: {meta['defense_power']:.0f}",
            f"پوشش هوایی مؤثر: {cov*100:.1f}% (سقف {self.DEFENSE_COVER_CAP*100:.0f}%)",
        ]
        if dis > 0:
            lines.append(f"⚠ اختلال سایبری فعال: {dis*100:.0f}% ظرفیت پدافند موقتاً از کار افتاده")
            rows = await self.db.fetch(
                "SELECT * FROM ng_cyber_effects WHERE target_country=$1 AND effect_type='def_disable' ORDER BY ends_at DESC",
                (code,),
            )
            now = datetime.now(timezone.utc)
            for r in rows[:3]:
                try:
                    ends = datetime.fromisoformat(str(r["ends_at"]).replace("Z", "+00:00"))
                    if ends.tzinfo is None:
                        ends = ends.replace(tzinfo=timezone.utc)
                    if ends > now:
                        left = int((ends - now).total_seconds())
                        lines.append(f"زمان باقی‌مانده اختلال: {left} ثانیه")
                except Exception:
                    pass
        else:
            lines.append("اختلال سایبری فعال نیست.")
        return "\n".join(lines)


    async def available_force(self, code: str, kind: str) -> tuple[float, list]:
        """Return (total_power, units[{item, qty, power}]) for free (non-zero) inventory."""
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        units = []
        total = 0.0
        for r in inv:
            meta = self._cat.get(r["item_code"])
            if not meta:
                continue
            cat = meta["category"]
            if kind == "ground" and cat not in ("ground", "defense"):
                continue
            if kind in ("air", "sea", "defense") and cat != kind:
                continue
            if kind not in ("ground", "air", "sea", "defense"):
                continue
            ps = float(meta.get("power_score") or 0)
            if ps <= 0 and cat != "defense":
                continue
            q = float(r["quantity"])
            total += ps * q
            units.append({"item_code": r["item_code"], "quantity": q, "power": ps})
        return total, units

    async def can_attack(self, code: str, kind: str | None = None) -> tuple[bool, str]:
        if await self.is_test_mode_player_country(code):
            # test country of owner — still need some force unless test grants units
            pass
        kinds = [kind] if kind else ["ground", "air", "sea"]
        any_power = 0.0
        for k in kinds:
            p, _ = await self.available_force(code, k)
            any_power += p
        if any_power <= 0:
            return False, "نیروی نظامی قابل‌استفاده ندارید. ابتدا از فروشگاه تجهیز تهیه کنید."
        ws = await self.db.fetchrow("SELECT * FROM ng_war_state WHERE country_code=$1", (code,))
        if ws and ws.get("last_attack_at") and not await self.is_test_active_for_country(code):
            try:
                last = datetime.fromisoformat(str(ws["last_attack_at"]).replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < self.ATTACK_COOLDOWN_SEC:
                    left = int(self.ATTACK_COOLDOWN_SEC - elapsed)
                    return False, f"هنوز در محدودیت حمله هستید. {left} ثانیه صبر کنید."
            except Exception:
                pass
        return True, ""

    async def attack(self, attacker: str, defender: str, kind: str, percent: float, pid: int) -> str:
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if meta and int(meta.get("war_enabled") or 0) != 1:
            raise GameError("جنگ توسط سازمان ملل بسته شده است.")
        if await self.at_peace(attacker, defender):
            raise GameError("پیمان صلح فعال است؛ حمله ممکن نیست.")
        if attacker == defender:
            raise GameError("نامعتبر")
        if kind not in ("ground", "air", "sea"):
            raise GameError("نوع درگیری نامعتبر است.")
        percent = max(10, min(100, float(percent)))
        test_atk = await self.is_test_active_for_country(attacker)
        cover = 0.0
        intercepted = 0.0

        async with self.db.transaction() as tx:
            a = await tx.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (attacker, pid),
            )
            d = await tx.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (defender,))
            if not a or not d or int(d.get("is_destroyed") or 0):
                raise GameError("هدف یا مالکیت معتبر نیست.")
            if d.get("owner_player_id") is None:
                raise GameError("کشور هدف بدون بازیکن است.")

            # cooldown inside transaction
            ws = await tx.fetchrow("SELECT * FROM ng_war_state WHERE country_code=$1", (attacker,))
            now = datetime.now(timezone.utc)
            if ws and ws.get("last_attack_at") and not test_atk:
                try:
                    last = datetime.fromisoformat(str(ws["last_attack_at"]).replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now - last).total_seconds()
                    if elapsed < self.ATTACK_COOLDOWN_SEC:
                        left = int(self.ATTACK_COOLDOWN_SEC - elapsed)
                        raise GameError(f"محدودیت حمله: {left} ثانیه باقی مانده است.")
                except GameError:
                    raise
                except Exception:
                    pass

            # forces from inventory (locked by transaction)
            inv = await tx.fetch(
                "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (attacker,)
            )
            units = []
            total_power = 0.0
            for r in inv:
                meta_i = self._cat.get(r["item_code"])
                if not meta_i:
                    continue
                cat = meta_i["category"]
                if kind == "ground" and cat not in ("ground", "defense"):
                    continue
                if kind in ("air", "sea") and cat != kind:
                    continue
                ps = float(meta_i.get("power_score") or 0)
                if ps <= 0:
                    continue
                q = float(r["quantity"])
                total_power += ps * q
                units.append((r["item_code"], q, ps))

            if total_power <= 0:
                raise GameError("نیروی نظامی قابل‌استفاده برای این نوع حمله ندارید.")

            # deploy percent of units (casualties / commitment)
            ratio = percent / 100.0
            engaged_power = total_power * ratio
            for item_code, q, ps in units:
                use = q * ratio
                if use <= 0:
                    continue
                # consume 10% of engaged as losses (min 0)
                loss = max(0.0, use * 0.1)
                new_q = max(0.0, q - loss)
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (new_q, attacker, item_code),
                )

            dp_units = await tx.fetch(
                "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (defender,)
            )
            dp = 0.0
            for r in dp_units:
                meta_i = self._cat.get(r["item_code"])
                if not meta_i:
                    continue
                if meta_i["category"] in (kind, "defense") or (kind == "ground" and meta_i["category"] == "defense"):
                    dp += float(meta_i.get("power_score") or 0) * float(r["quantity"])

            ap = engaged_power
            # damage scales with power difference
            if ap <= 0:
                raise GameError("نیروی اعزامی صفر است.")
            raw = (ap - dp * 0.55) * 0.35 + 15
            damage = max(5.0, min(200.0, raw))
            # air defense interception (never 100%)
            cover, def_meta = await self.defense_coverage(defender, kind)
            intercepted = damage * cover
            damage = max(3.0, damage - intercepted)
            victory = ap >= dp * 0.85
            result = f"پیروزی {attacker}" if victory else f"برتری دفاعی {defender}"

            new_hp = max(0.0, float(d["hp"]) - damage)
            await tx.execute(
                "UPDATE ng_countries SET hp=$1 WHERE country_code=$2", (new_hp, defender)
            )

            # economic toll on attacker
            toll = min(float(a["treasury"]) * 0.003, 150_000)
            if not test_atk:
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (max(0.0, float(a["treasury"]) - toll), attacker),
                )
                a_treas = max(0.0, float(a["treasury"]) - toll)
            else:
                a_treas = float(a["treasury"])

            loot = 0.0
            if victory:
                # loot based on damage relative to max_hp and defender treasury
                hp_ratio = damage / max(float(d["max_hp"]), 1.0)
                econ_ratio = min(1.0, damage / 100.0)
                loot = float(d["treasury"]) * min(self.MAX_LOOT_RATIO, 0.02 + hp_ratio * 0.1 + econ_ratio * 0.03)
                loot = min(loot, self.MAX_LOOT_ABS, float(d["treasury"]) * 0.5)
                loot = max(0.0, loot)
                if loot > 0:
                    await tx.execute(
                        "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                        (float(d["treasury"]) - loot, defender),
                    )
                    await tx.execute(
                        "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                        (a_treas + loot, attacker),
                    )
                    a_treas = a_treas + loot
                    await self._tx_log_activity(
                        tx, "economy", f"غنیمت جنگی {int(loot):,} از {defender}", attacker, pid
                    )

            # set cooldown
            seq = int((ws or {}).get("attack_seq") or 0) + 1
            if ws:
                await tx.execute(
                    "UPDATE ng_war_state SET last_attack_at=$1, attack_seq=$2 WHERE country_code=$3",
                    (now.isoformat(), seq, attacker),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_war_state (country_code, last_attack_at, attack_seq) VALUES ($1,$2,$3)",
                    (attacker, now.isoformat(), seq),
                )

            destroyed = new_hp <= 0
            if destroyed:
                inv_d = await tx.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1", (defender,)
                )
                d_row = await tx.fetchrow(
                    "SELECT treasury, owner_player_id FROM ng_countries WHERE country_code=$1",
                    (defender,),
                )
                half_money = float(d_row["treasury"]) * 0.5
                for r in inv_d:
                    half = float(r["quantity"]) * 0.5
                    if half <= 0:
                        continue
                    await tx.execute(
                        "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                        (float(r["quantity"]) - half, defender, r["item_code"]),
                    )
                    inv2 = await tx.fetchrow(
                        "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                        (attacker, r["item_code"]),
                    )
                    if inv2:
                        await tx.execute(
                            "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                            (float(inv2["quantity"]) + half, attacker, r["item_code"]),
                        )
                    else:
                        await tx.execute(
                            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                            (attacker, r["item_code"], half),
                        )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1, owner_player_id=NULL, is_destroyed=1 WHERE country_code=$2",
                    (float(d_row["treasury"]) - half_money, defender),
                )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (a_treas + half_money, attacker),
                )
                prev = d_row.get("owner_player_id")
                if prev:
                    until = (now + timedelta(hours=48)).isoformat()
                    await tx.execute(
                        "UPDATE ng_players SET country_code=NULL, destroy_cooldown_until=$1 WHERE player_id=$2",
                        (until, int(prev)),
                    )

        atk_name = await self.country_label(attacker)
        def_name = await self.country_label(defender)
        report = (
            f"⚔️ گزارش درگیری\n\n"
            f"مهاجم: {atk_name}\nمدافع: {def_name}\nنوع: {kind}\nشدت: {int(percent)}٪\n"
            f"نتیجه: {result}\n"
            f"خسارت نهایی: {int(damage)}\n"
            f"رهگیری پدافند: {int(intercepted)} (پوشش {cover*100:.0f}٪)\n"
            f"سلامت فعلی مدافع: {int(max(0, new_hp))}\n"
            f"غنیمت نقدی: {int(loot):,}"
            + (" (غنیمتی نبود)" if loot <= 0 and victory else "")
        )
        await self.log_activity("attack", report.replace("\n", " | "), attacker, pid)
        await self.broadcast_log("attack", report)
        if new_hp <= 0:
            await self.broadcast_log("destroy", f"💥 کشور {def_name} نابود شد.")
        return report

    async def _tx_log_activity(self, tx, kind, summary, country=None, player_id=None):
        nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_activity")
        await tx.execute(
            "INSERT INTO ng_activity (id, kind, country_code, player_id, summary, created_at, meta_json) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            (
                int(nid["id"]),
                kind,
                country,
                player_id,
                summary[:500],
                datetime.now(timezone.utc).isoformat(),
                "{}",
            ),
        )

    # ---------- statements ----------
    async def submit_statement(self, code: str, pid: int, body: str) -> str:
        body = body.strip()
        if len(body) < 5:
            raise GameError("متن بیانیه خیلی کوتاه است.")
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_statements")
        now = datetime.now(timezone.utc).isoformat()
        sid = int(nid["id"])
        if code == UN_CODE and self.is_owner(pid):
            await self.db.execute(
                "INSERT INTO ng_statements (id, country_code, player_id, body, status, created_at, reviewed_at) VALUES ($1,$2,$3,$4,'approved',$5,$5)",
                (sid, code, pid, body[:2000], now),
            )
            text = "🇺🇳 بیانیه رسمی سازمان ملل\n\n" + body[:2000]
            text = "🇺🇳 بیانیه رسمی سازمان ملل" + chr(10) + chr(10) + body[:2000]
            await self.broadcast_log("statement", text)
            await self.log_activity("group_pin_statement", text, UN_CODE, pid)
            return "✅ بیانیه سازمان ملل منتشر شد و برای پین در گروه اصلی صف شد."
        await self.db.execute(
            "INSERT INTO ng_statements (id, country_code, player_id, body, status, created_at) VALUES ($1,$2,$3,$4,'pending',$5)",
            (sid, code, pid, body[:2000], now),
        )
        c = await self.db.fetchrow("SELECT name_fa FROM ng_countries WHERE country_code=$1", (code,))
        name = (c or {}).get("name_fa") or code
        owner_body = (
            "📢 بیانیه جدید" + chr(10) + chr(10) + "متن:" + chr(10) + body[:1500] + chr(10) + chr(10)
            + "شناسه فرستنده:" + chr(10) + str(pid) + chr(10) + chr(10) + "کشور:" + chr(10) + str(name)
        )
        await self._owner_inbox("statement", sid, f"بیانیه — {name}", owner_body)
        return "✅ بیانیه برای بررسی مالک ارسال شد."

    async def review_statement(self, sid: int, approve: bool, actor: int) -> str:
        if actor != self.owner_id:
            raise GameError("فقط مالک")
        s = await self.db.fetchrow("SELECT * FROM ng_statements WHERE id=$1", (sid,))
        if not s or s["status"] != "pending":
            raise GameError("یافت نشد")
        status = "approved" if approve else "rejected"
        await self.db.execute(
            "UPDATE ng_statements SET status=$1, reviewed_at=$2 WHERE id=$3",
            (status, datetime.now(timezone.utc).isoformat(), sid),
        )
        if approve:
            c = await self.db.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1", (s["country_code"],)
            )
            is_un = (s["country_code"] == UN_CODE) or (c and c.get("country_code") == UN_CODE)
            if is_un:
                text = (
                    f"🇺🇳 بیانیه رسمی سازمان ملل\n\n"
                    f"{s['body']}"
                )
            else:
                text = (
                    f"📜 بیانیه رسمی کشور {c['name_fa']}\n"
                    f"با رهبری {c['leader_fa']}\n\n"
                    f"او در پی سخنرانی خود گفت:\n{s['body']}"
                )
            await self.broadcast_log("statement", text)
            # queue pin for UN statements
            if is_un:
                await self.log_activity("group_pin_statement", text)
            return text
        return "بیانیه رد شد."

    # ---------- admin ----------
    def is_owner(self, pid: int) -> bool:
        return self.owner_id and int(pid) == int(self.owner_id)

    async def ban(self, actor: int, target: int, reason: str = "") -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE ng_players SET is_banned=1, ban_reason=$1 WHERE player_id=$2",
            (reason, target),
        )
        await self.admin_log(actor, "ban", f"ban {target} {reason}")
        await self.broadcast_log("ban", f"🚫 بازیکن {target} توسط سازمان ملل مسدود شد.")
        return "مسدود شد."

    async def unban(self, actor: int, target: int) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE ng_players SET is_banned=0, ban_reason=NULL, banned_until=NULL WHERE player_id=$1",
            (target,),
        )
        await self.admin_log(actor, "unban", f"unban {target}")
        await self.broadcast_log("unban", f"✅ مسدودیت بازیکن {target} برداشته شد.")
        return "رفع مسدودیت انجام شد."

    async def set_war(self, actor: int, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE world_meta SET war_enabled=$1 WHERE id=1", (1 if enabled else 0,)
        )
        return "جنگ باز شد." if enabled else "جنگ بسته شد."

    async def set_nuclear(self, actor: int, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE world_meta SET nuclear_enabled=$1 WHERE id=1", (1 if enabled else 0,)
        )
        return "قابلیت هسته‌ای بازی فعال شد." if enabled else "قابلیت هسته‌ای بازی غیرفعال شد."

    async def admin_money(self, actor: int, code: str, amount: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        c = await self.db.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (code,))
        if not c:
            raise GameError("کشور نیست")
        await self.db.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (float(c["treasury"]) + float(amount), code),
        )
        await self.admin_log(actor, "money", f"{code} {amount}")
        return "انجام شد."

    async def full_reset(self, actor: int, confirm_phrase: str) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        if confirm_phrase.strip() != "ریست کامل جهان":
            raise GameError("عبارت تأیید نادرست است.")
        tables = [
            "ng_cart","ng_market","ng_peace","ng_statements","ng_daily_payouts",
            "ng_activity","ng_admin_log","ng_buildings","ng_inventory","ng_players",
            "ng_workshop","ng_workshop_jobs","ng_npt_requests","ng_owner_inbox","ng_war_state","ng_test_mode","ng_finance_ledger","ng_player_activity","ng_cyber_effects",
        ]
        async with self.db.transaction() as tx:
            for t in tables:
                await tx.execute(f"DELETE FROM {t}")
            await tx.execute(
                "UPDATE ng_countries SET owner_player_id=NULL, treasury=0, daily_income=0, daily_expense=0, hp=1000, is_destroyed=0, peace_penalty_until=NULL, claimed_at=NULL WHERE country_code<>$1",
                (UN_CODE,),
            )
            await tx.execute(
                "UPDATE ng_countries SET owner_player_id=$1, is_destroyed=0, treasury=200000000, hp=1000 WHERE country_code=$2",
                (self.owner_id, UN_CODE),
            )
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE world_meta SET started_at=$1, reset_count=reset_count+1, war_enabled=1, nuclear_enabled=0 WHERE id=1",
                (now,),
            )
        await self.ensure_un_country()
        await self.admin_log(actor, "full_reset", "world wiped")
        return "🔴 جهان به‌طور کامل ریست شد. کشورها آزاد هستند. سازمان ملل برای مالک باقی ماند."

    async def admin_log(self, actor: int, action: str, detail: str) -> None:
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_admin_log")
        await self.db.execute(
            "INSERT INTO ng_admin_log (id, actor_id, action, detail, created_at) VALUES ($1,$2,$3,$4,$5)",
            (int(nid["id"]), actor, action, detail, datetime.now(timezone.utc).isoformat()),
        )

    async def log_activity(self, kind: str, summary: str, country=None, player_id=None, meta=None):
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_activity")
        await self.db.execute(
            "INSERT INTO ng_activity (id, kind, country_code, player_id, summary, created_at, meta_json) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            (
                int(nid["id"]), kind, country, player_id, summary[:500],
                datetime.now(timezone.utc).isoformat(),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )

    async def broadcast_log(self, kind: str, text: str) -> None:
        """Queue log; actual Bale send is done by bot layer if group configured."""
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        flags = self._default_logs()
        if meta and meta.get("log_flags_json"):
            try:
                flags.update(json.loads(meta["log_flags_json"]))
            except Exception:
                pass
        if not flags.get(kind, True):
            return
        # store as activity for group publisher
        await self.log_activity("group_" + kind, text)


    async def country_label(self, code: str | None) -> str:
        """Human-readable country name for UI (never raw codes like IR)."""
        if not code:
            return "نامشخص"
        if code == UN_CODE:
            return "🇺🇳 سازمان ملل"
        row = await self.db.fetchrow(
            "SELECT flag, name_fa FROM ng_countries WHERE country_code=$1", (code,)
        )
        if row:
            return f"{row.get('flag') or ''} {row['name_fa']}".strip()
        return str(code)

    async def country_name_only(self, code: str | None) -> str:
        if not code:
            return "نامشخص"
        row = await self.db.fetchrow(
            "SELECT name_fa FROM ng_countries WHERE country_code=$1", (code,)
        )
        return (row or {}).get("name_fa") or str(code)

    async def country_card(self, code: str) -> str:
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        if not c:
            return "کشور یافت نشد."
        npt = "عضو پیمان منع گسترش سلاح‌های هسته‌ای" if int(c["npt_member"]) else "غیرعضو پیمان منع گسترش"
        return (
            f"{c.get('flag') or ''} {c['name_fa']}\n"
            f"👑 رهبر: {c['leader_fa']} ({c['leader_title_fa']})\n"
            f"🏙 پایتخت: {c['capital_fa']}\n"
            f"💵 پول: {c['currency_name_fa']}\n"
            f"💰 خزانه: {int(float(c['treasury'])):,}\n"
            f"📈 درآمد روزانه: {int(float(c['daily_income'])):,}\n"
            f"📉 هزینه روزانه: {int(float(c['daily_expense'])):,}\n"
            f"❤️ سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}\n"
            f"☢ {npt}\n"
            f"بازیکن: {'دارد' if c.get('owner_player_id') else 'آزاد'}"
        )

    async def inventory_text(self, code: str) -> str:
        rows = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
            (code,),
        )
        lines = ["📦 انبار من", ""]
        if not rows:
            lines.append("خالی")
        for r in rows:
            meta = self._cat.get(r["item_code"], {"name_fa": r["item_code"]})
            lines.append(f"• {meta['name_fa']}: {int(float(r['quantity']))}")
        return "\n".join(lines)


    async def cart_set(self, pid: int, item: str, qty: float) -> str:
        meta = self._cat.get(item)
        if not meta:
            raise GameError("کالا یافت نشد")
        qty = float(qty)
        if qty <= 0:
            await self.db.execute(
                "DELETE FROM ng_cart WHERE player_id=$1 AND item_code=$2", (pid, item)
            )
            return f"🗑 {meta['name_fa']} از سبد حذف شد."
        qty = min(float(meta["max_per_order"]), qty)
        row = await self.db.fetchrow(
            "SELECT quantity FROM ng_cart WHERE player_id=$1 AND item_code=$2", (pid, item)
        )
        if row:
            await self.db.execute(
                "UPDATE ng_cart SET quantity=$1 WHERE player_id=$2 AND item_code=$3",
                (qty, pid, item),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_cart (player_id, item_code, quantity) VALUES ($1,$2,$3)",
                (pid, item, qty),
            )
        return f"✅ تعداد {meta['name_fa']} = {int(qty)}"

    async def market_cancel(self, listing_id: int, country: str) -> str:
        async with self.db.transaction() as tx:
            L = await tx.fetchrow(
                "SELECT * FROM ng_market WHERE id=$1 AND active=1 AND seller_country=$2",
                (listing_id, country),
            )
            if not L:
                raise GameError("آگهی یافت نشد")
            qty = float(L["quantity"])
            await tx.execute("UPDATE ng_market SET active=0 WHERE id=$1", (listing_id,))
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (country, L["item_code"]),
            )
            if inv:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (float(inv["quantity"]) + qty, country, L["item_code"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                    (country, L["item_code"], qty),
                )
        return "✅ آگهی لغو و کالا به انبار برگشت."

    async def find_player(self, query: str) -> Optional[dict]:
        q = (query or "").strip().lstrip("@")
        if not q:
            return None
        if q.isdigit():
            return await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (int(q),))
        return await self.db.fetchrow(
            "SELECT * FROM ng_players WHERE lower(username)=lower($1)", (q,)
        )

    async def list_players(self, limit: int = 30) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_players ORDER BY last_seen_at DESC"
        )[:limit]

    async def ban_user(self, actor: int, query: str, reason: str = "") -> str:
        p = await self.find_player(query)
        if not p:
            raise GameError("بازیکن یافت نشد")
        return await self.ban(actor, int(p["player_id"]), reason)

    async def unban_user(self, actor: int, query: str) -> str:
        p = await self.find_player(query)
        if not p:
            raise GameError("بازیکن یافت نشد")
        return await self.unban(actor, int(p["player_id"]))

    async def admin_give_item(self, actor: int, code: str, item: str, qty: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        if item not in self._cat:
            raise GameError("کالا نامعتبر")
        qty = float(qty)
        inv = await self.db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (code, item),
        )
        if inv:
            await self.db.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                (float(inv["quantity"]) + qty, code, item),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                (code, item, qty),
            )
        await self.recalc_income(code)
        await self.admin_log(actor, "give_item", f"{code} {item} {qty}")
        return "✅ تجهیزات اضافه شد."

    async def admin_take_item(self, actor: int, code: str, item: str, qty: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        qty = float(qty)
        inv = await self.db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (code, item),
        )
        have = float(inv["quantity"]) if inv else 0
        if have < qty:
            raise GameError("موجودی کافی نیست")
        await self.db.execute(
            "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
            (have - qty, code, item),
        )
        await self.recalc_income(code)
        await self.admin_log(actor, "take_item", f"{code} {item} {qty}")
        return "✅ تجهیزات برداشت شد."

    async def set_log_flag(self, actor: int, kind: str, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        meta = await self.db.fetchrow("SELECT log_flags_json FROM world_meta WHERE id=1")
        flags = self._default_logs()
        if meta and meta.get("log_flags_json"):
            try:
                flags.update(json.loads(meta["log_flags_json"]))
            except Exception:
                pass
        if kind not in flags:
            raise GameError("نوع لاگ نامعتبر")
        flags[kind] = bool(enabled)
        await self.db.execute(
            "UPDATE world_meta SET log_flags_json=$1 WHERE id=1",
            (json.dumps(flags, ensure_ascii=False),),
        )
        return f"لاگ «{kind}» {'روشن' if enabled else 'خاموش'} شد."

    async def get_log_flags(self) -> dict:
        meta = await self.db.fetchrow("SELECT log_flags_json FROM world_meta WHERE id=1")
        flags = self._default_logs()
        if meta and meta.get("log_flags_json"):
            try:
                flags.update(json.loads(meta["log_flags_json"]))
            except Exception:
                pass
        return flags

    async def pending_peace_for(self, country: str) -> list[dict]:
        return await self.db.fetch(
            """
            SELECT * FROM ng_peace
            WHERE status='pending' AND (country_a=$1 OR country_b=$1)
            ORDER BY id DESC
            """,
            (country,),
        )

    async def active_peace_for(self, country: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_peace WHERE status='active' AND (country_a=$1 OR country_b=$1)",
            (country,),
        )
        # expire if needed
        out = []
        for p in rows:
            if await self.at_peace(p["country_a"], p["country_b"]):
                out.append(p)
        return out

    async def peace_reject(self, peace_id: int, country: str) -> str:
        p = await self.db.fetchrow("SELECT * FROM ng_peace WHERE id=$1 AND status='pending'", (peace_id,))
        if not p:
            raise GameError("درخواست یافت نشد")
        if country not in (p["country_a"], p["country_b"]):
            raise GameError("دسترسی ندارید")
        await self.db.execute(
            "UPDATE ng_peace SET status='rejected' WHERE id=$1", (peace_id,)
        )
        return "درخواست صلح رد شد."

    async def pop_group_logs(self, limit: int = 20) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_activity WHERE kind LIKE 'group_%' ORDER BY id ASC"
        )
        rows = rows[:limit]
        for r in rows:
            await self.db.execute("DELETE FROM ng_activity WHERE id=$1", (r["id"],))
        return rows

    async def world_status_text(self, *, for_owner: bool = False) -> str:
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        countries = await self.list_countries(for_owner=for_owner)
        free = sum(1 for c in countries if not c.get("owner_player_id") and c.get("country_code") != UN_CODE)
        owned = sum(1 for c in countries if c.get("owner_player_id") and c.get("country_code") != UN_CODE)
        total_public = 30
        total_shown = len([c for c in countries if c.get("country_code") != UN_CODE]) if not for_owner else len(countries)
        war = "باز" if meta and int(meta.get("war_enabled") or 0) else "بسته"
        nuke = "فعال" if meta and int(meta.get("nuclear_enabled") or 0) else "غیرفعال"
        lines = [
            "🌍 وضعیت جهان",
            f"شروع جهان: {(meta or {}).get('started_at') or '—'}",
            f"جنگ: {war}",
            f"هسته‌ای بازی: {nuke}",
            f"تعداد کشورها: {30 if not for_owner else 31}",
            f"کشور آزاد: {free} | دارای بازیکن: {owned}",
            f"ریست‌ها: {int((meta or {}).get('reset_count') or 0)}",
        ]
        return "\n".join(lines)


    DEFAULT_START = (
        "🕹 به جنگ جهانی خوش آمدید\n"
        "نسل جدید — مدیریت کشور، اقتصاد، دیپلماسی و جنگ\n"
        "از دکمه‌های پایین برای شروع استفاده کنید."
    )
    DEFAULT_ABOUT = (
        "📖 درباره جنگ جهانی\n\n"
        "یک بازی چندنفره کشور‌داری با اقتصاد درون‌بازی، تجارت، صلح و جنگ انتزاعی.\n"
        "تمام عملیات با دکمه انجام می‌شود.\n"
        "سازمان ملل توسط مالک بازی مدیریت می‌شود."
    )

    # Workshop balance (server-side)
    WS_MAX_LEVEL = 10
    WS_UPGRADE_BASE = 2_000_000
    WS_URANIUM_BASE_COST = 500_000
    WS_URANIUM_BASE_AMOUNT = 10
    WS_URANIUM_BASE_MINUTES = 30
    WS_RESEARCH_BASE_COST = 800_000
    WS_RESEARCH_BASE_POINTS = 1
    WS_RESEARCH_BASE_MINUTES = 45

    async def _seed_bot_settings(self) -> None:
        defaults = {
            "start_message": self.DEFAULT_START,
            "about_message": self.DEFAULT_ABOUT,
        }
        for k, v in defaults.items():
            row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", (k,))
            if not row:
                await self.db.execute(
                    "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", (k, v)
                )

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self.db.fetchrow("SELECT value FROM ng_bot_settings WHERE key=$1", (key,))
        return (row["value"] if row else default) or default

    async def set_setting(self, actor: int, key: str, value: str) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        value = (value or "").strip()
        if len(value) < 3:
            raise GameError("متن خیلی کوتاه است.")
        if len(value) > 3500:
            raise GameError("متن خیلی بلند است.")
        row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", (key,))
        if row:
            await self.db.execute(
                "UPDATE ng_bot_settings SET value=$1 WHERE key=$2", (value, key)
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", (key, value)
            )
        await self.admin_log(actor, "set_setting", key)
        await self.log_activity("admin", f"تغییر تنظیم {key}", player_id=actor)
        return "✅ متن ذخیره شد."

    async def reset_setting(self, actor: int, key: str) -> str:
        if key == "start_message":
            return await self.set_setting(actor, key, self.DEFAULT_START)
        if key == "about_message":
            return await self.set_setting(actor, key, self.DEFAULT_ABOUT)
        raise GameError("کلید نامعتبر")

    async def ensure_workshop(self, code: str) -> dict:
        row = await self.db.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
        if not row:
            await self.db.execute(
                "INSERT INTO ng_workshop (country_code, level, tech_level) VALUES ($1,1,0)",
                (code,),
            )
            row = await self.db.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
        return row

    def _workshop_upgrade_cost(self, level: int) -> float:
        # steep curve: base * level^2.2
        return float(self.WS_UPGRADE_BASE) * (float(level) ** 2.2)

    async def workshop_status(self, code: str) -> str:
        await self.complete_due_jobs(code)
        ws = await self.ensure_workshop(code)
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        jobs = await self.db.fetch(
            "SELECT * FROM ng_workshop_jobs WHERE country_code=$1 AND status='running' ORDER BY id",
            (code,),
        )
        level = int(ws["level"])
        tech = int(ws["tech_level"])
        next_cost = self._workshop_upgrade_cost(level)
        lines = [
            "🏭 کارگاه ملی",
            f"سطح کارگاه: {level}/{self.WS_MAX_LEVEL}",
            f"سطح فناوری صلح‌آمیز: {tech}",
            f"هزینه ارتقا بعدی: {int(next_cost):,}",
            f"NPT: {'عضو' if int(c['npt_member']) else 'غیرعضو'}",
            "",
        ]
        if jobs:
            lines.append("⏳ عملیات در حال انجام:")
            for j in jobs:
                lines.append(
                    f"• {j['job_type']} تا {j['finishes_at']} | مقدار {int(float(j['amount']))}"
                )
        else:
            lines.append("عملیات فعالی ندارید.")
        inv_u = await self.db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='res_uranium'",
            (code,),
        )
        lines.append(f"\n📦 اورانیوم انبار: {int(float((inv_u or {}).get('quantity') or 0))} واحد")
        return "\n".join(lines)

    async def workshop_upgrade(self, code: str, pid: int) -> str:
        async with self.db.transaction() as tx:
            ws = await tx.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
            if not ws:
                await tx.execute(
                    "INSERT INTO ng_workshop (country_code, level, tech_level) VALUES ($1,1,0)",
                    (code,),
                )
                level = 1
            else:
                level = int(ws["level"])
            if level >= self.WS_MAX_LEVEL:
                raise GameError("کارگاه به حداکثر سطح رسیده است.")
            cost = self._workshop_upgrade_cost(level)
            c = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (code, pid),
            )
            if not c:
                raise GameError("مالکیت معتبر نیست.")
            if float(c["treasury"]) < cost:
                raise GameError("موجودی خزانه برای ارتقا کافی نیست.")
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, code),
            )
            await tx.execute(
                "UPDATE ng_workshop SET level=$1, upgraded_at=$2 WHERE country_code=$3",
                (level + 1, now, code),
            )
        await self.log_activity("workshop", f"ارتقای کارگاه به سطح {level+1}", code, pid)
        await self.admin_log(pid, "workshop_upgrade", f"{code}->{level+1}")
        return f"✅ کارگاه به سطح {level+1} ارتقا یافت.\nهزینه: {int(cost):,}"

    async def _has_item(self, tx_or_db, code: str, item: str, min_q: float = 1) -> bool:
        inv = await tx_or_db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (code, item),
        )
        return bool(inv and float(inv["quantity"]) >= min_q)

    async def start_uranium_job(self, code: str, pid: int) -> str:
        """Peaceful uranium feedstock production — requires refinery."""
        await self.complete_due_jobs(code)
        async with self.db.transaction() as tx:
            # only one uranium job at a time
            running = await tx.fetchrow(
                "SELECT id FROM ng_workshop_jobs WHERE country_code=$1 AND job_type='uranium' AND status='running'",
                (code,),
            )
            if running:
                raise GameError("یک عملیات تولید اورانیوم در حال اجرا است.")
            if not await self._has_item(tx, code, "b_refinery", 1):
                # also accept building table
                b = await tx.fetchrow(
                    "SELECT id FROM ng_buildings WHERE country_code=$1 AND building_code='b_refinery' AND active=1",
                    (code,),
                )
                inv = await tx.fetchrow(
                    "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='b_refinery'",
                    (code,),
                )
                if not b and not (inv and float(inv["quantity"]) >= 1):
                    raise GameError("برای تولید اورانیوم به پالایشگاه نیاز دارید.")
            ws = await tx.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
            if not ws:
                await tx.execute(
                    "INSERT INTO ng_workshop (country_code, level, tech_level) VALUES ($1,1,0)", (code,)
                )
                level = 1
            else:
                level = int(ws["level"])
            cost = self.WS_URANIUM_BASE_COST / (1 + 0.08 * (level - 1))
            amount = self.WS_URANIUM_BASE_AMOUNT * (1 + 0.15 * (level - 1))
            minutes = max(5, self.WS_URANIUM_BASE_MINUTES / (1 + 0.1 * (level - 1)))
            c = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (code, pid),
            )
            if not c or float(c["treasury"]) < cost:
                raise GameError("موجودی خزانه برای شروع تولید کافی نیست.")
            now = datetime.now(timezone.utc)
            instant = await self.is_test_mode(pid)
            fin = now if instant else now + timedelta(minutes=minutes)
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, code),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_workshop_jobs")
            await tx.execute(
                """
                INSERT INTO ng_workshop_jobs (id, country_code, job_type, started_at, finishes_at, cost, amount, status)
                VALUES ($1,$2,'uranium',$3,$4,$5,$6,'running')
                """,
                (int(nid["id"]), code, now.isoformat(), fin.isoformat(), cost, amount),
            )
        await self.complete_due_jobs(code)
        await self.log_activity("workshop", f"شروع تولید اورانیوم ×{amount:.0f}", code, pid)
        if instant:
            return f"✅ (تست) تولید اورانیوم فوری انجام شد — {amount:.0f} واحد"
        return (
            f"✅ تولید اورانیوم شروع شد\n"
            f"هزینه: {int(cost):,}\nمقدار: {amount:.0f} واحد\nمدت تقریبی: {minutes:.0f} دقیقه"
        )

    async def start_research_job(self, code: str, pid: int) -> str:
        await self.complete_due_jobs(code)
        async with self.db.transaction() as tx:
            running = await tx.fetchrow(
                "SELECT id FROM ng_workshop_jobs WHERE country_code=$1 AND job_type='research' AND status='running'",
                (code,),
            )
            if running:
                raise GameError("یک پروژه تحقیقاتی در حال اجرا است.")
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='sp_scientist'",
                (code,),
            )
            if not inv or float(inv["quantity"]) < 1:
                raise GameError("برای توسعه فناوری به متخصص هسته‌ای (دانشمند) نیاز دارید.")
            ws = await tx.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
            if not ws:
                await tx.execute(
                    "INSERT INTO ng_workshop (country_code, level, tech_level) VALUES ($1,1,0)", (code,)
                )
                level, tech = 1, 0
            else:
                level, tech = int(ws["level"]), int(ws["tech_level"])
            c = await tx.fetchrow(
                "SELECT treasury, npt_member FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (code, pid),
            )
            if not c:
                raise GameError("مالکیت معتبر نیست.")
            # NPT members can research peaceful tech but slower/cheaper energy path
            npt = int(c["npt_member"] or 0) == 1
            cost = self.WS_RESEARCH_BASE_COST * (1 + 0.2 * tech) / (1 + 0.05 * (level - 1))
            if npt:
                cost *= 0.9
            points = self.WS_RESEARCH_BASE_POINTS * (1 + 0.1 * (level - 1))
            minutes = max(5, self.WS_RESEARCH_BASE_MINUTES * (1 + 0.15 * tech) / (1 + 0.08 * (level - 1)))
            if float(c["treasury"]) < cost:
                raise GameError("موجودی خزانه کافی نیست.")
            now = datetime.now(timezone.utc)
            instant = await self.is_test_mode(pid)
            fin = now if instant else now + timedelta(minutes=minutes)
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, code),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_workshop_jobs")
            await tx.execute(
                """
                INSERT INTO ng_workshop_jobs (id, country_code, job_type, started_at, finishes_at, cost, amount, status)
                VALUES ($1,$2,'research',$3,$4,$5,$6,'running')
                """,
                (int(nid["id"]), code, now.isoformat(), fin.isoformat(), cost, points),
            )
        await self.complete_due_jobs(code)
        await self.log_activity("workshop", f"شروع تحقیق فناوری سطح+{points:.0f}", code, pid)
        if instant:
            return f"✅ (تست) تحقیق فوری: +{points:.0f} سطح فناوری"
        return (
            f"✅ تحقیق فناوری صلح‌آمیز شروع شد\n"
            f"هزینه: {int(cost):,}\nپیشرفت: +{points:.0f} سطح\nمدت: {minutes:.0f} دقیقه"
        )

    async def complete_due_jobs(self, code: str | None = None) -> int:
        """Finish jobs whose time has passed; idempotent."""
        now = datetime.now(timezone.utc)
        if code:
            jobs = await self.db.fetch(
                "SELECT * FROM ng_workshop_jobs WHERE status='running' AND country_code=$1",
                (code,),
            )
        else:
            jobs = await self.db.fetch(
                "SELECT * FROM ng_workshop_jobs WHERE status='running'"
            )
        n = 0
        for j in jobs:
            try:
                fin = datetime.fromisoformat(str(j["finishes_at"]).replace("Z", "+00:00"))
                if fin.tzinfo is None:
                    fin = fin.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if now < fin:
                continue
            async with self.db.transaction() as tx:
                still = await tx.fetchrow(
                    "SELECT * FROM ng_workshop_jobs WHERE id=$1 AND status='running'",
                    (j["id"],),
                )
                if not still:
                    continue
                cc = still["country_code"]
                if still["job_type"] == "uranium":
                    inv = await tx.fetchrow(
                        "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='res_uranium'",
                        (cc,),
                    )
                    q = float(still["amount"])
                    if inv:
                        await tx.execute(
                            "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code='res_uranium'",
                            (float(inv["quantity"]) + q, cc),
                        )
                    else:
                        await tx.execute(
                            "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,'res_uranium',$2)",
                            (cc, q),
                        )
                elif still["job_type"] == "research":
                    ws = await tx.fetchrow("SELECT tech_level FROM ng_workshop WHERE country_code=$1", (cc,))
                    if not ws:
                        await tx.execute(
                            "INSERT INTO ng_workshop (country_code, level, tech_level) VALUES ($1,1,$2)",
                            (cc, int(float(still["amount"]))),
                        )
                    else:
                        await tx.execute(
                            "UPDATE ng_workshop SET tech_level=$1 WHERE country_code=$2",
                            (int(ws["tech_level"]) + int(float(still["amount"])), cc),
                        )
                await tx.execute(
                    "UPDATE ng_workshop_jobs SET status='done' WHERE id=$1 AND status='running'",
                    (j["id"],),
                )
            n += 1
            await self.log_activity("workshop", f"اتمام {j['job_type']} مقدار {j['amount']}", j["country_code"])
        return n

    async def request_npt_change(self, code: str, pid: int, request_type: str) -> str:
        if request_type not in ("join", "leave"):
            raise GameError("نوع درخواست نامعتبر")
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (code, pid),
        )
        if not c:
            raise GameError("مالکیت معتبر نیست.")
        is_member = int(c["npt_member"] or 0) == 1
        if request_type == "join" and is_member:
            raise GameError("کشور هم‌اکنون عضو NPT است.")
        if request_type == "leave" and not is_member:
            raise GameError("کشور عضو NPT نیست.")
        pending = await self.db.fetchrow(
            "SELECT id FROM ng_npt_requests WHERE country_code=$1 AND status='pending'",
            (code,),
        )
        if pending:
            raise GameError("یک درخواست NPT در انتظار بررسی دارید.")
        now = datetime.now(timezone.utc).isoformat()
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_npt_requests")
        rid = int(nid["id"])
        await self.db.execute(
            """
            INSERT INTO ng_npt_requests (id, country_code, player_id, request_type, status, created_at)
            VALUES ($1,$2,$3,$4,'pending',$5)
            """,
            (rid, code, pid, request_type, now),
        )
        label = "عضویت در NPT" if request_type == "join" else "خروج از NPT"
        body = (
            f"کشور {c['name_fa']} درخواست {label} را ارسال کرده است.\n\n"
            f"شناسه بازیکن: {pid}\nزمان: {now}"
        )
        await self._owner_inbox("npt", rid, f"درخواست NPT — {c['name_fa']}", body)
        await self.log_activity("npt", f"درخواست {label}", code, pid)
        return f"✅ درخواست «{label}» برای بررسی مالک ارسال شد."

    async def review_npt(self, request_id: int, approve: bool, actor: int) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک می‌تواند تصمیم بگیرد.")
        async with self.db.transaction() as tx:
            r = await tx.fetchrow(
                "SELECT * FROM ng_npt_requests WHERE id=$1 AND status='pending'", (request_id,)
            )
            if not r:
                raise GameError("درخواست یافت نشد یا قبلاً بررسی شده است.")
            now = datetime.now(timezone.utc).isoformat()
            status = "approved" if approve else "rejected"
            await tx.execute(
                "UPDATE ng_npt_requests SET status=$1, reviewed_at=$2, reviewer_id=$3 WHERE id=$4 AND status='pending'",
                (status, now, actor, request_id),
            )
            if approve:
                new_val = 1 if r["request_type"] == "join" else 0
                await tx.execute(
                    "UPDATE ng_countries SET npt_member=$1 WHERE country_code=$2",
                    (new_val, r["country_code"]),
                )
        label = "عضویت" if r["request_type"] == "join" else "خروج"
        if approve:
            await self.log_activity("npt", f"تأیید {label} NPT", r["country_code"], actor)
            await self.admin_log(actor, "npt_approve", f"{r['country_code']} {label}")
            await self.broadcast_log("admin", f"⚖ وضعیت NPT کشور {r['country_code']} تغییر کرد ({label}).")
            return f"✅ درخواست {label} NPT برای {r['country_code']} تأیید شد."
        await self.admin_log(actor, "npt_reject", f"{r['country_code']} {label}")
        return f"درخواست {label} NPT رد شد. وضعیت قبلی حفظ شد."

    async def _owner_inbox(self, kind: str, ref_id: int, title: str, body: str) -> None:
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_owner_inbox")
        await self.db.execute(
            """
            INSERT INTO ng_owner_inbox (id, kind, ref_id, title, body, created_at, delivered)
            VALUES ($1,$2,$3,$4,$5,$6,0)
            """,
            (
                int(nid["id"]),
                kind,
                ref_id,
                title,
                body,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    async def pop_owner_inbox(self, limit: int = 10) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_owner_inbox WHERE delivered=0 ORDER BY id ASC"
        )
        rows = rows[:limit]
        for r in rows:
            await self.db.execute(
                "UPDATE ng_owner_inbox SET delivered=1 WHERE id=$1", (r["id"],)
            )
        return rows

    async def pending_npt_list(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_npt_requests WHERE status='pending' ORDER BY id DESC"
        )

    async def pending_statements_list(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_statements WHERE status='pending' ORDER BY id DESC"
        )


    async def _seed_membership(self) -> None:
        row = await self.db.fetchrow("SELECT id FROM ng_membership_cfg WHERE id=1")
        if not row:
            await self.db.execute(
                "INSERT INTO ng_membership_cfg (id, force_enabled) VALUES (1,1)"
            )
        exists = await self.db.fetchrow(
            "SELECT id FROM ng_forced_chats WHERE chat_id=$1", ("@warworld3",)
        )
        if not exists:
            nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_forced_chats")
            await self.db.execute(
                """
                INSERT INTO ng_forced_chats (id, chat_id, title, invite_link, kind, active)
                VALUES ($1,$2,$3,$4,'group',1)
                """,
                (int(nid["id"]), "@warworld3", "WORLD WAR", "https://ble.ir/warworld3"),
            )

    # ---------- test mode ----------
    async def is_test_mode(self, pid: int) -> bool:
        row = await self.db.fetchrow(
            "SELECT active FROM ng_test_mode WHERE player_id=$1", (pid,)
        )
        return bool(row and int(row.get("active") or 0) == 1)

    async def is_test_active_for_country(self, code: str) -> bool:
        c = await self.db.fetchrow(
            "SELECT owner_player_id FROM ng_countries WHERE country_code=$1", (code,)
        )
        if not c or not c.get("owner_player_id"):
            return False
        return await self.is_test_mode(int(c["owner_player_id"]))

    async def is_test_mode_player_country(self, code: str) -> bool:
        return await self.is_test_active_for_country(code)

    async def enable_test_mode(self, actor: int) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        code = await self.player_country(actor)
        if not code:
            raise GameError("ابتدا یک کشور انتخاب کنید تا Snapshot گرفته شود.")
        existing = await self.db.fetchrow(
            "SELECT active FROM ng_test_mode WHERE player_id=$1", (actor,)
        )
        if existing and int(existing.get("active") or 0) == 1:
            raise GameError("حالت تست از قبل فعال است.")
        # snapshot real state
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        inv = await self.db.fetch(
            "SELECT item_code, quantity FROM ng_inventory WHERE country_code=$1", (code,)
        )
        ws = await self.db.fetchrow("SELECT * FROM ng_workshop WHERE country_code=$1", (code,))
        war = await self.db.fetchrow("SELECT * FROM ng_war_state WHERE country_code=$1", (code,))
        snap = {
            "country_code": code,
            "country": {
                "treasury": float(c["treasury"]),
                "hp": float(c["hp"]),
                "daily_income": float(c["daily_income"]),
                "daily_expense": float(c["daily_expense"]),
            },
            "inventory": [{"item_code": r["item_code"], "quantity": float(r["quantity"])} for r in inv],
            "workshop": dict(ws) if ws else None,
            "war_state": dict(war) if war else None,
        }
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            await self.db.execute(
                "UPDATE ng_test_mode SET active=1, snapshot_json=$1, activated_at=$2 WHERE player_id=$3",
                (json.dumps(snap, ensure_ascii=False), now, actor),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_test_mode (player_id, active, snapshot_json, activated_at) VALUES ($1,1,$2,$3)",
                (actor, json.dumps(snap, ensure_ascii=False), now),
            )
        # grant test resources (does not touch other players)
        await self.db.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (999_999_999.0, code),
        )
        for item, qty in (
            ("g_inf", 500),
            ("g_armor", 100),
            ("a_fight", 50),
            ("s_patrol", 50),
            ("d_sam", 50),
            ("sp_scientist", 20),
            ("b_refinery", 5),
        ):
            inv_r = await self.db.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (code, item),
            )
            if inv_r:
                await self.db.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (float(inv_r["quantity"]) + qty, code, item),
                )
            else:
                await self.db.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                    (code, item, qty),
                )
        await self.db.execute(
            "DELETE FROM ng_war_state WHERE country_code=$1", (code,)
        )
        await self.admin_log(actor, "test_on", code)
        return "✅ حالت تست فعال شد. منابع آزمایشی فقط روی کشور شما اعمال شد. با خاموش کردن، وضعیت واقعی برمی‌گردد."

    async def disable_test_mode(self, actor: int) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        row = await self.db.fetchrow(
            "SELECT * FROM ng_test_mode WHERE player_id=$1 AND active=1", (actor,)
        )
        if not row:
            raise GameError("حالت تست فعال نیست.")
        snap = json.loads(row["snapshot_json"] or "{}")
        code = snap.get("country_code") or await self.player_country(actor)
        if not code:
            await self.db.execute(
                "UPDATE ng_test_mode SET active=0 WHERE player_id=$1", (actor,)
            )
            return "حالت تست خاموش شد (کشور یافت نشد)."
        async with self.db.transaction() as tx:
            country = snap.get("country") or {}
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1, hp=$2, daily_income=$3, daily_expense=$4 WHERE country_code=$5",
                (
                    float(country.get("treasury") or 0),
                    float(country.get("hp") or 1000),
                    float(country.get("daily_income") or 0),
                    float(country.get("daily_expense") or 0),
                    code,
                ),
            )
            await tx.execute("DELETE FROM ng_inventory WHERE country_code=$1", (code,))
            for r in snap.get("inventory") or []:
                await tx.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                    (code, r["item_code"], float(r["quantity"])),
                )
            await tx.execute(
                "UPDATE ng_test_mode SET active=0 WHERE player_id=$1", (actor,)
            )
        await self.recalc_income(code)
        await self.admin_log(actor, "test_off", code)
        return "✅ حالت تست خاموش شد. موجودی واقعی از Snapshot بازیابی شد."

    # ---------- forced membership ----------
    async def membership_enabled(self) -> bool:
        row = await self.db.fetchrow("SELECT force_enabled FROM ng_membership_cfg WHERE id=1")
        return bool(row and int(row.get("force_enabled") or 0) == 1)

    async def set_membership_enabled(self, actor: int, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE ng_membership_cfg SET force_enabled=$1 WHERE id=1",
            (1 if enabled else 0,),
        )
        return "عضویت اجباری فعال شد." if enabled else "عضویت اجباری خاموش شد."

    async def list_forced_chats(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_forced_chats ORDER BY id"
        )

    async def add_forced_chat(self, actor: int, chat_id: str, title: str, link: str = "", kind: str = "group") -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        chat_id = (chat_id or "").strip()
        if not chat_id:
            raise GameError("شناسه نامعتبر")
        kind = kind if kind in ("group", "channel") else "group"
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_forced_chats")
        await self.db.execute(
            """
            INSERT INTO ng_forced_chats (id, chat_id, title, invite_link, kind, active)
            VALUES ($1,$2,$3,$4,$5,1)
            """,
            (int(nid["id"]), chat_id, title or chat_id, link or "", kind),
        )
        await self.admin_log(actor, "force_add", chat_id)
        return "✅ اضافه شد."

    async def remove_forced_chat(self, actor: int, chat_pk: int) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute("DELETE FROM ng_forced_chats WHERE id=$1", (chat_pk,))
        return "حذف شد."

    async def toggle_forced_chat(self, actor: int, chat_pk: int, active: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        await self.db.execute(
            "UPDATE ng_forced_chats SET active=$1 WHERE id=$2",
            (1 if active else 0, chat_pk),
        )
        return "به‌روز شد."

    async def active_forced_chats(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_forced_chats WHERE active=1"
        )


    # ---------- membership verify ----------
    async def membership_cache_ok(self, pid: int, chat_id: str, max_age_hours: float = 12) -> bool:
        row = await self.db.fetchrow(
            "SELECT verified_at FROM ng_member_cache WHERE player_id=$1 AND chat_id=$2",
            (pid, chat_id),
        )
        if not row:
            return False
        try:
            ts = datetime.fromisoformat(str(row["verified_at"]).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts).total_seconds() < max_age_hours * 3600
        except Exception:
            return False

    async def membership_cache_set(self, pid: int, chat_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT player_id FROM ng_member_cache WHERE player_id=$1 AND chat_id=$2",
            (pid, chat_id),
        )
        if row:
            await self.db.execute(
                "UPDATE ng_member_cache SET verified_at=$1 WHERE player_id=$2 AND chat_id=$3",
                (now, pid, chat_id),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_member_cache (player_id, chat_id, verified_at) VALUES ($1,$2,$3)",
                (pid, chat_id, now),
            )

    async def verify_membership(self, bot, pid: int, chat_id: str) -> tuple[bool, str]:
        """Returns (is_member, detail). detail: member|not_member|api_error"""
        if await self.membership_cache_ok(pid, chat_id):
            return True, "cache"
        if bot is None:
            return False, "api_error"
        candidates = [chat_id]
        if isinstance(chat_id, str) and chat_id.startswith("@"):
            candidates.append(chat_id[1:])
        last_err = None
        for cid in candidates:
            try:
                if not hasattr(bot, "get_chat_member"):
                    return False, "api_error"
                m = await bot.get_chat_member(cid, pid)
                if m is None:
                    last_err = "none"
                    continue
                # preferred flag
                if getattr(m, "is_member", None) is True:
                    await self.membership_cache_set(pid, chat_id)
                    return True, "is_member"
                if getattr(m, "is_member", None) is False:
                    return False, "not_member"
                st = str(getattr(m, "status", "") or "").lower()
                if st in ("member", "administrator", "creator", "owner"):
                    await self.membership_cache_set(pid, chat_id)
                    return True, st
                if st in ("left", "kicked"):
                    return False, st
                if st == "restricted":
                    # restricted users may still be in chat
                    await self.membership_cache_set(pid, chat_id)
                    return True, st
                last_err = st or "unknown"
            except Exception as e:
                last_err = str(e)
                log.warning("get_chat_member fail chat=%s user=%s err=%s", cid, pid, e)
                continue
        if last_err in ("none", "left", "kicked", "not_member"):
            return False, "not_member"
        return False, "api_error"

    # ---------- atom bomb craft ----------
    BOMB_URANIUM_COST = 25  # units of res_uranium or res_uranium_90 (90 counts as 2x)
    BOMB_MONEY_COST = 15_000_000

    async def craft_atom_bomb(self, code: str, pid: int) -> str:
        """Build abstract game atom bomb from uranium + money."""
        instant = await self.is_test_mode(pid)
        async with self.db.transaction() as tx:
            c = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (code, pid),
            )
            if not c:
                raise GameError("مالکیت معتبر نیست.")
            money_cost = 0 if instant else self.BOMB_MONEY_COST
            if float(c["treasury"]) < money_cost:
                raise GameError(f"برای ساخت بمب اتم به {int(self.BOMB_MONEY_COST):,} پول نیاز است.")
            # uranium pool: res_uranium counts 1, res_uranium_90 counts 2
            u = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='res_uranium'",
                (code,),
            )
            u90 = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='res_uranium_90'",
                (code,),
            )
            q_u = float(u["quantity"]) if u else 0.0
            q_90 = float(u90["quantity"]) if u90 else 0.0
            need = 0 if instant else float(self.BOMB_URANIUM_COST)
            points = q_u + q_90 * 2
            if points < need:
                raise GameError(
                    f"اورانیوم کافی نیست. نیاز: {int(need)} واحد "
                    f"(اورانیوم معمولی=۱، اورانیوم ۹۰٪=۲). موجودی امتیاز: {points:.0f}"
                )
            # consume uranium
            remain = need
            take90 = min(q_90, remain / 2)
            # prefer consuming whole units of 90
            take90 = min(q_90, (remain + 1) // 2) if remain else 0
            # simpler: consume 90 first
            take90 = 0.0
            while remain > 0 and q_90 > 0:
                q_90 -= 1
                take90 += 1
                remain -= 2
            if remain < 0:
                remain = 0
            take_u = min(q_u, remain)
            remain -= take_u
            if remain > 0 and not instant:
                raise GameError("اورانیوم کافی نیست.")
            if u90:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code='res_uranium_90'",
                    (q_90, code),
                )
            if u:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code='res_uranium'",
                    (q_u - take_u, code),
                )
            if money_cost:
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(c["treasury"]) - money_cost, code),
                )
            inv_b = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='item_atom_bomb'",
                (code,),
            )
            if inv_b:
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code='item_atom_bomb'",
                    (float(inv_b["quantity"]) + 1, code),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,'item_atom_bomb',1)",
                    (code,),
                )
        await self.log_activity("workshop", "ساخت بمب اتم بازی", code, pid)
        if instant:
            return "✅ (تست) بمب اتم فوری ساخته شد و به انبار اضافه شد."
        return (
            f"✅ بمب اتم ساخته شد.\\n"
            f"هزینه پول: {int(self.BOMB_MONEY_COST):,}\\n"
            f"مصرف اورانیوم: {int(self.BOMB_URANIUM_COST)} واحد معادل"
        )

    async def attack_nuclear(self, attacker: str, defender: str, pid: int) -> str:
        """Abstract nuclear strike: consumes 1 bomb, deals 25-35% max_hp damage."""
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if meta and int(meta.get("war_enabled") or 0) != 1:
            raise GameError("جنگ توسط سازمان ملل بسته شده است.")
        if meta and int(meta.get("nuclear_enabled") or 0) != 1:
            raise GameError("قابلیت هسته‌ای بازی توسط سازمان ملل غیرفعال است. از /panel آن را فعال کنید.")
        if await self.at_peace(attacker, defender):
            raise GameError("پیمان صلح فعال است؛ حمله ممکن نیست.")
        if attacker == defender:
            raise GameError("نامعتبر")
        test_atk = await self.is_test_active_for_country(attacker)
        async with self.db.transaction() as tx:
            a = await tx.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
                (attacker, pid),
            )
            d = await tx.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (defender,))
            if not a or not d or int(d.get("is_destroyed") or 0):
                raise GameError("هدف معتبر نیست.")
            if not d.get("owner_player_id"):
                raise GameError("کشور هدف بدون بازیکن است.")
            # cooldown
            ws = await tx.fetchrow("SELECT * FROM ng_war_state WHERE country_code=$1", (attacker,))
            now = datetime.now(timezone.utc)
            if ws and ws.get("last_attack_at") and not test_atk:
                try:
                    last = datetime.fromisoformat(str(ws["last_attack_at"]).replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now - last).total_seconds()
                    if elapsed < self.ATTACK_COOLDOWN_SEC:
                        raise GameError(f"محدودیت حمله: {int(self.ATTACK_COOLDOWN_SEC - elapsed)} ثانیه.")
                except GameError:
                    raise
                except Exception:
                    pass
            bomb = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='item_atom_bomb'",
                (attacker,),
            )
            bq = float(bomb["quantity"]) if bomb else 0.0
            if bq < 1:
                raise GameError("بمب اتم در انبار ندارید.")
            await tx.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code='item_atom_bomb'",
                (bq - 1, attacker),
            )
            pct = random.uniform(0.25, 0.35)
            damage = float(d["max_hp"]) * pct
            cover, _ = await self.defense_coverage(defender, "nuclear")
            intercepted = damage * cover
            damage = max(damage * 0.5, damage - intercepted)  # nuclear still hurts a lot
            new_hp = max(0.0, float(d["hp"]) - damage)
            await tx.execute(
                "UPDATE ng_countries SET hp=$1 WHERE country_code=$2", (new_hp, defender)
            )
            seq = int((ws or {}).get("attack_seq") or 0) + 1
            if ws:
                await tx.execute(
                    "UPDATE ng_war_state SET last_attack_at=$1, attack_seq=$2 WHERE country_code=$3",
                    (now.isoformat(), seq, attacker),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_war_state (country_code, last_attack_at, attack_seq) VALUES ($1,$2,$3)",
                    (attacker, now.isoformat(), seq),
                )
            destroyed = new_hp <= 0
            if destroyed:
                prev = d.get("owner_player_id")
                await tx.execute(
                    "UPDATE ng_countries SET owner_player_id=NULL, is_destroyed=1 WHERE country_code=$1",
                    (defender,),
                )
                if prev:
                    until = (now + timedelta(hours=48)).isoformat()
                    await tx.execute(
                        "UPDATE ng_players SET country_code=NULL, destroy_cooldown_until=$1 WHERE player_id=$2",
                        (until, int(prev)),
                    )
        atk_name = await self.country_label(attacker)
        def_name = await self.country_label(defender)
        report = (
            f"☢️ گزارش حمله اتمی (بازی)\n\n"
            f"مهاجم: {atk_name}\nمدافع: {def_name}\n"
            f"تخریب: {pct*100:.1f}٪ از حداکثر سلامت\n"
            f"خسارت: {int(damage)}\n"
            f"سلامت فعلی: {int(new_hp)}/{int(float(d['max_hp']))}\n"
            f"بمب مصرف‌شده: ۱"
        )
        await self.log_activity("attack", report.replace("\n", " | "), attacker, pid)
        await self.broadcast_log("attack", report)
        if new_hp <= 0:
            await self.broadcast_log("destroy", f"💥 کشور {def_name} در اثر حمله اتمی نابود شد.")
        return report


    # ---------- owner users panel ----------
    PAGE_SIZE = 8

    async def record_start(self, pid: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT player_id FROM ng_player_activity WHERE player_id=$1", (pid,)
        )
        if row:
            await self.db.execute(
                "UPDATE ng_player_activity SET last_start_at=$1, start_count=start_count+1 WHERE player_id=$2",
                (now, pid),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_player_activity (player_id, last_start_at, start_count) VALUES ($1,$2,1)",
                (pid, now),
            )

    async def player_stats(self) -> dict:
        total_rows = await self.db.fetch("SELECT player_id FROM ng_players")
        total = len(total_rows)
        today = datetime.now(TEHRAN).date().isoformat()
        acts = await self.db.fetch("SELECT * FROM ng_player_activity")
        active_today = 0
        for a in acts:
            ts = a.get("last_start_at")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt.astimezone(TEHRAN).date().isoformat() == today:
                    active_today += 1
            except Exception:
                continue
        return {"total": total, "active_today": active_today}

    async def list_players_page(self, page: int = 0) -> tuple[list[dict], int]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_players ORDER BY player_id"
        )
        total = len(rows)
        page = max(0, int(page))
        start = page * self.PAGE_SIZE
        return rows[start:start + self.PAGE_SIZE], total

    async def player_admin_card(self, target_id: int) -> str:
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (target_id,))
        if not p:
            raise GameError("بازیکن یافت نشد")
        code = p.get("country_code")
        c = None
        if code:
            c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        ban = "مسدود" if int(p.get("is_banned") or 0) else "آزاد"
        npt = "—"
        treas = 0
        if c:
            npt = "عضو NPT" if int(c.get("npt_member") or 0) else "غیرعضو NPT"
            treas = float(c.get("treasury") or 0)
        act = await self.db.fetchrow(
            "SELECT last_start_at FROM ng_player_activity WHERE player_id=$1", (target_id,)
        )
        last_start = (act or {}).get("last_start_at") or "—"
        return (
            f"👤 مدیریت کاربر\n"
            f"شناسه: {target_id}\n"
            f"نام کاربری: @{p.get('username') or '—'}\n"
            f"نام نمایشی: {p.get('display_name') or '—'}\n"
            f"کشور: {code or 'نامشخص'}\n"
            f"وضعیت: {ban}\n"
            f"دلیل بن: {p.get('ban_reason') or '—'}\n"
            f"پول: {int(treas):,}\n"
            f"NPT: {npt}\n"
            f"آخرین /start: {last_start}"
        )

    async def ledger_write(self, kind: str, amount: float, actor: int, from_c=None, to_c=None, reason: str = "") -> None:
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_finance_ledger")
        await self.db.execute(
            """
            INSERT INTO ng_finance_ledger (id, kind, from_country, to_country, amount, actor_id, reason, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            (
                int(nid["id"]), kind, from_c, to_c, float(amount), actor, reason[:200],
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    async def admin_set_npt(self, actor: int, code: str, member: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        c = await self.db.fetchrow("SELECT country_code FROM ng_countries WHERE country_code=$1", (code,))
        if not c:
            raise GameError("کشور یافت نشد")
        await self.db.execute(
            "UPDATE ng_countries SET npt_member=$1 WHERE country_code=$2",
            (1 if member else 0, code),
        )
        await self.admin_log(actor, "npt_manual", f"{code}={member}")
        return f"✅ وضعیت NPT برای {code} به {'عضو' if member else 'غیرعضو'} تغییر کرد."

    async def admin_take_money(self, actor: int, code: str, amount: float, reason: str = "برداشت مالک") -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ نامعتبر")
        async with self.db.transaction() as tx:
            c = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (code,))
            if not c:
                raise GameError("کشور یافت نشد")
            if float(c["treasury"]) < amount:
                raise GameError("موجودی کافی نیست")
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - amount, code),
            )
        await self.ledger_write("admin_take", amount, actor, from_c=code, reason=reason)
        await self.admin_log(actor, "take_money", f"{code} -{amount}")
        return f"✅ {int(amount):,} از {code} کسر شد."

    async def admin_tax_user(self, actor: int, code: str, amount: float) -> str:
        """Tax one country into UN treasury."""
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ نامعتبر")
        async with self.db.transaction() as tx:
            c = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (code,))
            if not c:
                raise GameError("کشور یافت نشد")
            have = float(c["treasury"])
            if have < amount:
                raise GameError("موجودی کاربر برای این مالیات کافی نیست")
            un = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (UN_CODE,))
            if not un:
                raise GameError("خزانه سازمان ملل یافت نشد")
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (have - amount, code),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(un["treasury"]) + amount, UN_CODE),
            )
        await self.ledger_write("tax_user", amount, actor, from_c=code, to_c=UN_CODE, reason="مالیات اختصاصی")
        await self.admin_log(actor, "tax_user", f"{code} {amount}")
        return f"✅ مالیات {int(amount):,} از {code} به خزانه سازمان ملل واریز شد."

    async def global_tax(self, actor: int, amount: float) -> dict:
        """Levy amount from all player countries that can pay; credit UN. Idempotent per call."""
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ نامعتبر")
        collected = 0.0
        taxed = 0
        skipped = 0
        recipients = []
        async with self.db.transaction() as tx:
            countries = await tx.fetch(
                "SELECT * FROM ng_countries WHERE owner_player_id IS NOT NULL AND is_destroyed=0 AND country_code<>$1",
                (UN_CODE,),
            )
            un = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (UN_CODE,))
            if not un:
                raise GameError("سازمان ملل موجود نیست")
            un_treas = float(un["treasury"])
            for c in countries:
                have = float(c["treasury"])
                if have < amount:
                    skipped += 1
                    continue
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (have - amount, c["country_code"]),
                )
                un_treas += amount
                collected += amount
                taxed += 1
                recipients.append(int(c["owner_player_id"]))
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (un_treas, UN_CODE),
            )
        await self.ledger_write(
            "tax_global", collected, actor, to_c=UN_CODE, reason=f"مالیات سراسری {amount}"
        )
        await self.admin_log(actor, "tax_global", f"amt={amount} collected={collected} n={taxed}")
        notice = (
            f"💰 مالیات سازمان ملل\n\n"
            f"از تمامی بازیکنان مبلغ {int(amount):,} واحد پول به‌عنوان مالیات کسر شد.\n\n"
            f"دلیل: مالیات سراسری سازمان ملل"
        )
        await self.broadcast_log("admin", notice)
        # queue DM notices once
        for rid in recipients:
            await self.log_activity("dm_notice", notice, player_id=rid)
        return {
            "amount": amount,
            "collected": collected,
            "taxed": taxed,
            "skipped": skipped,
            "notice": notice,
            "recipients": recipients,
        }

    async def condemn_country(self, actor: int, code: str, speech: str) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        speech = (speech or "").strip()
        if len(speech) < 2:
            raise GameError("متن سخنرانی کوتاه است")
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
        )
        if not c or c.get("country_code") == UN_CODE:
            raise GameError("کشور معتبر نیست")
        name = c["name_fa"]
        text = (
            f"⚖️ بیانیه سازمان ملل\n\n"
            f"سازمان ملل کشور {name} را محکوم کرد.\n\n"
            f"او در پی سخنرانی خود گفت:\n«{speech[:1500]}»"
        )
        await self.broadcast_log("statement", text)
        await self.log_activity("group_pin_statement", text, UN_CODE, actor)
        players = await self.db.fetch("SELECT player_id FROM ng_players")
        for pl in players:
            await self.log_activity("dm_notice", text, player_id=int(pl["player_id"]))
        await self.admin_log(actor, "condemn", f"{code}")
        return f"✅ بیانیه محکومیت {name} ثبت و برای انتشار صف شد."

    async def reset_player(self, actor: int, target_id: int) -> str:
        """Free player country and progress; keep identity, bans, audit logs."""
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        if int(target_id) == int(self.owner_id or 0):
            raise GameError("ریست مالک / سازمان ملل مجاز نیست.")
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (target_id,))
        if not p:
            raise GameError("بازیکن یافت نشد")
        code = p.get("country_code")
        if code == UN_CODE:
            raise GameError("کشور سازمان ملل قابل ریست از این مسیر نیست.")
        label = await self.country_label(code) if code else "بدون کشور"
        async with self.db.transaction() as tx:
            if code:
                await tx.execute(
                    """
                    UPDATE ng_countries SET
                        owner_player_id=NULL, treasury=0, daily_income=0, daily_expense=0,
                        hp=1000, is_destroyed=0, peace_penalty_until=NULL, claimed_at=NULL
                    WHERE country_code=$1 AND owner_player_id=$2
                    """,
                    (code, target_id),
                )
                await tx.execute("DELETE FROM ng_inventory WHERE country_code=$1", (code,))
                await tx.execute("DELETE FROM ng_buildings WHERE country_code=$1", (code,))
                await tx.execute("DELETE FROM ng_cart WHERE player_id=$1", (target_id,))
                await tx.execute("DELETE FROM ng_workshop WHERE country_code=$1", (code,))
                await tx.execute("DELETE FROM ng_workshop_jobs WHERE country_code=$1", (code,))
                await tx.execute("DELETE FROM ng_war_state WHERE country_code=$1", (code,))
                try:
                    await tx.execute(
                        "UPDATE ng_market SET status='cancelled' WHERE seller_country=$1 AND status='open'",
                        (code,),
                    )
                except Exception:
                    pass
                try:
                    await tx.execute(
                        "UPDATE ng_peace SET status='expired' WHERE (a_code=$1 OR b_code=$1) AND status IN ('pending','active')",
                        (code,),
                    )
                except Exception:
                    pass
            await tx.execute(
                "UPDATE ng_players SET country_code=NULL WHERE player_id=$1",
                (target_id,),
            )
        await self.admin_log(actor, "player_reset", f"target={target_id} country={code}")
        await self.log_activity(
            "admin",
            f"ریست کاربر {target_id} — کشور {label} آزاد شد",
            code,
            actor,
        )
        return (
            f"✅ کاربر {target_id} ریست شد.\n"
            f"کشور قبلی: {label}\n"
            f"اکنون می‌تواند کشور جدید انتخاب کند.\n"
            "بن بودن او تغییر نکرد. لاگ‌ها حفظ شدند."
        )


