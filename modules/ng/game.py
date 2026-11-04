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

    def _default_logs(self) -> dict:
        keys = [
            "buy","sell","attack","destroy","statement","peace","aid_money","aid_army",
            "ban","unban","trade","admin",
        ]
        return {k: True for k in keys}

    async def _seed_catalog(self) -> None:
        for c in CATALOG:
            exists = await self.db.fetchrow(
                "SELECT item_code FROM ng_shop_catalog WHERE item_code=$1", (c["item_code"],)
            )
            if not exists:
                await self.db.execute(
                    """
                    INSERT INTO ng_shop_catalog (
                        item_code, category, name_fa, description_fa, unit_price, max_per_order,
                        power_score, daily_income, maintenance, is_building
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    (
                        c["item_code"], c["category"], c["name_fa"], c["description_fa"],
                        c["unit_price"], c["max_per_order"], c["power_score"],
                        c["daily_income"], c["maintenance"], c["is_building"],
                    ),
                )

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
        p = await self.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (pid,))
        return (p or {}).get("country_code")

    # ---------- claim ----------
    async def list_countries(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_countries WHERE is_destroyed=0 ORDER BY name_fa"
        )

    async def claim(self, pid: int, code: str) -> dict:
        await self.assert_not_banned(pid)
        code = code.upper()
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
        await self.log_activity("claim", f"انتخاب کشور {code}", code, pid)
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
    async def power(self, code: str, kind: str) -> float:
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1", (code,)
        )
        total = 0.0
        cat_map = {"ground": "ground", "air": "air", "sea": "sea"}
        want = cat_map.get(kind, kind)
        for r in inv:
            meta = self._cat.get(r["item_code"])
            if not meta:
                continue
            if meta["category"] == want or (kind == "ground" and meta["category"] == "defense"):
                total += float(meta["power_score"]) * float(r["quantity"])
        return total

    async def attack(self, attacker: str, defender: str, kind: str, percent: float, pid: int) -> str:
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if meta and int(meta.get("war_enabled") or 0) != 1:
            raise GameError("جنگ توسط سازمان ملل بسته شده است.")
        if await self.at_peace(attacker, defender):
            raise GameError("پیمان صلح فعال است؛ حمله ممکن نیست.")
        if attacker == defender:
            raise GameError("نامعتبر")
        percent = max(10, min(100, float(percent))) / 100.0
        ap = await self.power(attacker, kind) * percent
        dp = await self.power(defender, kind) + await self.power(defender, "defense") * 0.5
        # consume nothing physically for abstract percent engagement except economic toll
        damage = max(20, (ap - dp * 0.6) * 0.4 + 30)
        loot = 0.0
        result = "تساوی نسبی"
        async with self.db.transaction() as tx:
            d = await tx.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (defender,))
            a = await tx.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (attacker,))
            if not d or not a or int(d.get("is_destroyed") or 0):
                raise GameError("هدف معتبر نیست")
            new_hp = max(0, float(d["hp"]) - damage)
            await tx.execute(
                "UPDATE ng_countries SET hp=$1 WHERE country_code=$2", (new_hp, defender)
            )
            # small cost to attacker
            toll = min(float(a["treasury"]) * 0.005, 200_000)
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(a["treasury"]) - toll, attacker),
            )
            if ap >= dp:
                result = f"پیروزی {attacker}"
                loot = min(float(d["treasury"]) * 0.01, 500_000)
                if loot > 0 and float(d["treasury"]) >= loot:
                    await tx.execute(
                        "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                        (float(d["treasury"]) - loot, defender),
                    )
                    await tx.execute(
                        "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                        (float(a["treasury"]) - toll + loot, attacker),
                    )
                else:
                    loot = 0
            else:
                result = f"برتری دفاعی {defender}"
            destroyed = False
            if new_hp <= 0:
                destroyed = True
                # transfer 50% assets
                inv = await tx.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1", (defender,)
                )
                for r in inv:
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
                half_money = float(d["treasury"]) * 0.5
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1, owner_player_id=NULL, is_destroyed=1 WHERE country_code=$2",
                    (float(d["treasury"]) - half_money, defender),
                )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(a["treasury"]) - toll + loot + half_money, attacker),
                )
                # cooldown for previous owner
                prev = d.get("owner_player_id")
                if prev:
                    until = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
                    await tx.execute(
                        "UPDATE ng_players SET country_code=NULL, destroy_cooldown_until=$1 WHERE player_id=$2",
                        (until, int(prev)),
                    )
        report = (
            f"⚔️ گزارش درگیری\n\n"
            f"مهاجم: {attacker}\nمدافع: {defender}\nنوع: {kind}\n"
            f"نتیجه: {result}\n"
            f"خسارت سلامت: {int(damage)}\n"
            f"سلامت فعلی مدافع: {int(max(0, new_hp))}\n"
            f"غنیمت: {int(loot):,}" + (" (غنیمت به دست نیامد)" if loot <= 0 and ap >= dp else "")
        )
        await self.log_activity("attack", report.replace("\n", " | "), attacker, pid)
        await self.broadcast_log("attack", report)
        if new_hp <= 0:
            await self.broadcast_log("destroy", f"💥 کشور {defender} نابود شد.")
        return report

    # ---------- statements ----------
    async def submit_statement(self, code: str, pid: int, body: str) -> str:
        body = body.strip()
        if len(body) < 5:
            raise GameError("متن بیانیه خیلی کوتاه است.")
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_statements")
        await self.db.execute(
            "INSERT INTO ng_statements (id, country_code, player_id, body, status, created_at) VALUES ($1,$2,$3,$4,'pending',$5)",
            (int(nid["id"]), code, pid, body[:2000], datetime.now(timezone.utc).isoformat()),
        )
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
            text = (
                f"📜 بیانیه رسمی کشور {c['name_fa']}\n"
                f"با رهبری {c['leader_fa']}\n\n"
                f"او در پی سخنرانی خود گفت:\n{s['body']}"
            )
            await self.broadcast_log("statement", text)
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
        ]
        async with self.db.transaction() as tx:
            for t in tables:
                await tx.execute(f"DELETE FROM {t}")
            await tx.execute(
                "UPDATE ng_countries SET owner_player_id=NULL, treasury=0, daily_income=0, daily_expense=0, hp=1000, is_destroyed=0, peace_penalty_until=NULL, claimed_at=NULL"
            )
            now = datetime.now(timezone.utc).isoformat()
            await tx.execute(
                "UPDATE world_meta SET started_at=$1, reset_count=reset_count+1, war_enabled=1, nuclear_enabled=0 WHERE id=1",
                (now,),
            )
        await self.admin_log(actor, "full_reset", "world wiped")
        return "🔴 جهان به‌طور کامل ریست شد. کشورها آزاد هستند."

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
