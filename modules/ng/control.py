"""Country internal control, satisfaction, straits, laws, sanctions."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

LAW_REGISTER_REWARD = 5_000_000  # نقدی یک‌باره هنگام ثبت قانون

if TYPE_CHECKING:
    from modules.ng.game import Game

# Strait definitions: controllers can close; affected feel oil/trade pressure
STRAITS = [
    {
        "strait_code": "hormuz",
        "name_fa": "تنگه هرمز",
        "controller_codes": ["IR", "OM"],
        "affected_codes": ["IR", "SA", "AE", "KW", "IQ", "QA", "BH", "US", "CN", "JP", "IN", "KR"],
    },
    {
        "strait_code": "bab_mandeb",
        "name_fa": "تنگه باب‌المندب",
        "controller_codes": ["YE", "DJ", "ER"],
        "affected_codes": ["YE", "SA", "EG", "SD", "ET", "US", "CN", "IN", "TR"],
    },
    {
        "strait_code": "malacca",
        "name_fa": "تنگه مالاکا",
        "controller_codes": ["MY", "ID", "SG"],
        "affected_codes": ["MY", "ID", "SG", "CN", "JP", "KR", "IN", "AU", "US"],
    },
    {
        "strait_code": "suez",
        "name_fa": "کانال سوئز",
        "controller_codes": ["EG"],
        "affected_codes": ["EG", "SA", "TR", "IT", "FR", "DE", "GB", "US", "CN", "IN"],
    },
    {
        "strait_code": "bosphorus",
        "name_fa": "تنگه بسفر",
        "controller_codes": ["TR"],
        "affected_codes": ["TR", "RU", "UA", "RO", "BG", "GE"],
    },
]


class ControlError(Exception):
    pass


class ControlService:
    def __init__(self, game: "Game"):
        self.g = game
        self.db = game.db

    async def ensure_tables(self) -> None:
        for stmt in (
            """CREATE TABLE IF NOT EXISTS ng_country_control (
                country_code TEXT PRIMARY KEY,
                flights_open INTEGER NOT NULL DEFAULT 1,
                maritime_open INTEGER NOT NULL DEFAULT 1,
                internet_on INTEGER NOT NULL DEFAULT 1,
                satisfaction REAL NOT NULL DEFAULT 70,
                base_daily_income REAL NOT NULL DEFAULT 20000000,
                leader_crisis_until TEXT,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS ng_straits (
                strait_code TEXT PRIMARY KEY,
                name_fa TEXT NOT NULL,
                controller_codes TEXT NOT NULL,
                affected_codes TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0,
                closed_by TEXT,
                closed_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS ng_laws (
                id INTEGER PRIMARY KEY,
                country_code TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                target_country TEXT,
                banned_item TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                income_bonus REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS ng_sanctions (
                id INTEGER PRIMARY KEY,
                source_country TEXT NOT NULL,
                target_country TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'trade',
                item_code TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                law_id INTEGER,
                created_at TEXT NOT NULL,
                ends_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS ng_law_daily (
                country_code TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (country_code, day)
            )""",
        ):
            try:
                await self.db.execute(stmt)
            except Exception:
                pass
        for s in STRAITS:
            exists = await self.db.fetchrow(
                "SELECT strait_code FROM ng_straits WHERE strait_code=$1", (s["strait_code"],)
            )
            if not exists:
                await self.db.execute(
                    """
                    INSERT INTO ng_straits (strait_code, name_fa, controller_codes, affected_codes, closed)
                    VALUES ($1,$2,$3,$4,0)
                    """,
                    (
                        s["strait_code"],
                        s["name_fa"],
                        json.dumps(s["controller_codes"]),
                        json.dumps(s["affected_codes"]),
                    ),
                )

    async def ensure_control(self, code: str) -> dict:
        row = await self.db.fetchrow(
            "SELECT * FROM ng_country_control WHERE country_code=$1", (code,)
        )
        if row:
            return row
        # stable random base income 20-25M once
        base = float(random.randint(20_000_000, 25_000_000))
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO ng_country_control
            (country_code, flights_open, maritime_open, internet_on, satisfaction, base_daily_income, updated_at)
            VALUES ($1,1,1,1,70,$2,$3)
            """,
            (code, base, now),
        )
        return await self.db.fetchrow(
            "SELECT * FROM ng_country_control WHERE country_code=$1", (code,)
        )

    async def panel_text(self, code: str) -> str:
        c = await self.ensure_control(code)
        name = await self.g.country_label(code)
        sat = float(c["satisfaction"])
        sat_bar = "█" * int(sat // 10) + "░" * (10 - int(sat // 10))
        return (
            f"🏛 کنترل کشور — {name}\n\n"
            f"😊 رضایت مردم: {sat:.0f}/100\n{sat_bar}\n\n"
            f"✈️ پروازها: {'باز ✅' if int(c['flights_open']) else 'متوقف ⛔'}\n"
            f"🚢 سفر دریایی: {'باز ✅' if int(c['maritime_open']) else 'متوقف ⛔'}\n"
            f"🌐 اینترنت: {'وصل ✅' if int(c['internet_on']) else 'قطع ⛔'}\n"
            f"💰 درآمد پایه روزانه: {int(float(c['base_daily_income'])):,}\n"
        )

    async def _set_flag(self, code: str, field: str, value: int, sat_delta: float, note: str) -> str:
        """Change a control flag only if state actually changes — no sat spam."""
        allowed = {"flights_open", "maritime_open", "internet_on"}
        if field not in allowed:
            raise ControlError("فیلد نامعتبر")
        await self.ensure_control(code)
        c = await self.db.fetchrow(
            "SELECT * FROM ng_country_control WHERE country_code=$1", (code,)
        )
        cur = int(c.get(field) or 0)
        value = 1 if int(value) else 0
        sat = float(c["satisfaction"])
        if cur == value:
            labels = {
                "flights_open": "پروازها",
                "maritime_open": "سفر دریایی",
                "internet_on": "اینترنت",
            }
            state = "فعال" if value else "غیرفعال"
            return (
                f"ℹ️ {labels.get(field, field)} از قبل {state} است.\n"
                f"رضایت مردم: {sat:.0f}/100 (بدون تغییر)"
            )
        sat = max(0.0, min(100.0, sat + float(sat_delta)))
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            f"UPDATE ng_country_control SET {field}=$1, satisfaction=$2, updated_at=$3 WHERE country_code=$4",
            (value, sat, now, code),
        )
        return f"✅ {note}\nرضایت مردم اکنون: {sat:.0f}/100"

    async def toggle_flights(self, code: str, pid: int, open_: bool) -> str:
        await self._assert_owner(code, pid)
        if open_:
            return await self._set_flag(code, "flights_open", 1, +3, "پروازها فعال شدند.")
        return await self._set_flag(
            code, "flights_open", 0, -5,
            "پروازها متوقف شد. پدافند هوایی کمی تقویت می‌شود؛ رضایت و درآمد کاهش می‌یابد.",
        )

    async def toggle_maritime(self, code: str, pid: int, open_: bool) -> str:
        await self._assert_owner(code, pid)
        if open_:
            return await self._set_flag(code, "maritime_open", 1, +2, "سفرهای دریایی فعال شدند.")
        return await self._set_flag(
            code, "maritime_open", 0, -6,
            "سفر دریایی متوقف شد. دفاع ضدکشتی بهتر می‌شود؛ تجارت و رضایت کاهش می‌یابد.",
        )

    async def toggle_internet(self, code: str, pid: int, on: bool) -> str:
        await self._assert_owner(code, pid)
        if on:
            return await self._set_flag(code, "internet_on", 1, +5, "اینترنت وصل شد.")
        drop = random.uniform(10, 20)
        return await self._set_flag(
            code, "internet_on", 0, -drop,
            f"اینترنت قطع شد (−{drop:.0f} رضایت). حملات سایبری دشمن تقریباً بی‌اثر می‌شوند.",
        )

    async def _assert_owner(self, code: str, pid: int) -> None:
        c = await self.db.fetchrow(
            "SELECT owner_player_id FROM ng_countries WHERE country_code=$1", (code,)
        )
        if not c or int(c["owner_player_id"] or 0) != int(pid):
            raise ControlError("فقط مالک کشور")

    async def cyber_defense_bonus(self, code: str) -> float:
        """Return residual cyber success chance multiplier (1.0 normal, 0.01 if internet off)."""
        c = await self.ensure_control(code)
        if int(c["internet_on"]) == 0:
            return 0.01
        return 1.0

    async def defense_air_bonus(self, code: str) -> float:
        c = await self.ensure_control(code)
        bonus = 0.0
        if int(c["flights_open"]) == 0:
            bonus += 0.08
        return bonus

    async def defense_sea_bonus(self, code: str) -> float:
        c = await self.ensure_control(code)
        bonus = 0.0
        if int(c["maritime_open"]) == 0:
            bonus += 0.10
        # anti-ship inventory
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        for r in inv:
            meta = self.g._cat.get(r["item_code"], {})
            if meta.get("category") == "antiship":
                bonus += min(0.15, 0.02 * float(r["quantity"]))
        return min(0.35, bonus)

    async def satisfaction_shop_mult(self, code: str) -> float:
        c = await self.ensure_control(code)
        sat = float(c["satisfaction"])
        if sat <= 30:
            return 1.45
        if sat <= 40:
            return 1.25
        if sat <= 55:
            return 1.10
        return 1.0

    async def income_modifier(self, code: str) -> float:
        """Multiplier on daily payout from controls/sanctions/straits/satisfaction."""
        c = await self.ensure_control(code)
        m = 1.0
        if int(c["flights_open"]) == 0:
            m -= 0.05
        if int(c["maritime_open"]) == 0:
            m -= 0.08
        if int(c["internet_on"]) == 0:
            m -= 0.04
        sat = float(c["satisfaction"])
        if sat <= 30:
            m -= 0.20
        elif sat <= 40:
            m -= 0.12
        elif sat <= 55:
            m -= 0.05
        # sanctions against this country
        sans = await self.db.fetch(
            "SELECT * FROM ng_sanctions WHERE target_country=$1 AND active=1", (code,)
        )
        m -= min(0.25, 0.06 * len(sans))
        # closed straits affecting this country
        straits = await self.db.fetch("SELECT * FROM ng_straits WHERE closed=1")
        for s in straits:
            try:
                aff = json.loads(s["affected_codes"] or "[]")
            except Exception:
                aff = []
            if code in aff:
                m -= 0.07
        return max(0.35, m)

    async def global_oil_price_mult(self) -> float:
        straits = await self.db.fetch("SELECT * FROM ng_straits WHERE closed=1")
        mult = 1.0
        for s in straits:
            if s["strait_code"] in ("hormuz", "bab_mandeb", "suez"):
                mult += 0.25
            else:
                mult += 0.12
        return min(2.0, mult)

    async def list_controllable_straits(self, code: str) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM ng_straits")
        out = []
        for r in rows:
            try:
                ctrls = json.loads(r["controller_codes"] or "[]")
            except Exception:
                ctrls = []
            if code in ctrls:
                out.append(r)
        return out

    async def toggle_strait(self, code: str, pid: int, strait_code: str, close: bool) -> str:
        await self._assert_owner(code, pid)
        s = await self.db.fetchrow(
            "SELECT * FROM ng_straits WHERE strait_code=$1", (strait_code,)
        )
        if not s:
            raise ControlError("تنگه یافت نشد")
        try:
            ctrls = json.loads(s["controller_codes"] or "[]")
        except Exception:
            ctrls = []
        if code not in ctrls:
            raise ControlError("کشور شما اختیار کنترل این تنگه را ندارد.")
        now = datetime.now(timezone.utc).isoformat()
        if close:
            await self.db.execute(
                "UPDATE ng_straits SET closed=1, closed_by=$1, closed_at=$2 WHERE strait_code=$3",
                (code, now, strait_code),
            )
            # satisfaction hit for controller too (diplomatic cost)
            # mild one-time diplomatic cost when closing a strait (only on real close)
            ctrl = await self.ensure_control(code)
            sat = max(0.0, float(ctrl["satisfaction"]) - 4)
            await self.db.execute(
                "UPDATE ng_country_control SET satisfaction=$1, updated_at=$2 WHERE country_code=$3",
                (sat, datetime.now(timezone.utc).isoformat(), code),
            )
            await self.g.broadcast_log(
                "strait",
                f"🌊 تنگه «{s['name_fa']}» توسط {await self.g.country_label(code)} بسته شد.\nقیمت نفت و تجارت جهانی تحت فشار قرار گرفت.",
            )
            return f"⛔ تنگه «{s['name_fa']}» بسته شد.\nقیمت جهانی نفت افزایش می‌یابد."
        await self.db.execute(
            "UPDATE ng_straits SET closed=0, closed_by=NULL, closed_at=NULL WHERE strait_code=$1",
            (strait_code,),
        )
        await self.g.broadcast_log(
            "strait",
            f"🌊 تنگه «{s['name_fa']}» دوباره باز شد.",
        )
        return f"✅ تنگه «{s['name_fa']}» باز شد."

    async def submit_law(
        self, code: str, pid: int, title: str, body: str,
        target_country: str | None = None, banned_item: str | None = None,
    ) -> str:
        await self._assert_owner(code, pid)
        title = (title or "").strip()[:80]
        body = (body or "").strip()[:1500]
        if len(title) < 3 or len(body) < 20:
            raise ControlError("عنوان یا متن قانون کافی نیست.")
        day = datetime.now(TEHRAN).date().isoformat()
        drow = await self.db.fetchrow(
            "SELECT count FROM ng_law_daily WHERE country_code=$1 AND day=$2", (code, day)
        )
        cnt = int(drow["count"]) if drow else 0
        if cnt >= 3:
            raise ControlError("سقف ۳ قانون در روز برای این کشور پر شده است.")
        now = datetime.now(timezone.utc).isoformat()
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_laws")
        lid = int(nid["id"])
        await self.db.execute(
            """
            INSERT INTO ng_laws
            (id, country_code, player_id, title, body, target_country, banned_item, status, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'pending',$8)
            """,
            (lid, code, pid, title, body, target_country, banned_item, now),
        )
        if drow:
            await self.db.execute(
                "UPDATE ng_law_daily SET count=$1 WHERE country_code=$2 AND day=$3",
                (cnt + 1, code, day),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_law_daily (country_code, day, count) VALUES ($1,$2,1)",
                (code, day),
            )
        # پاداش نقدی ثبت قانون — یک‌بار به خزانه (جدا از درآمد روزانه)
        reward = float(LAW_REGISTER_REWARD)
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (code,)
        )
        if not c:
            raise ControlError("کشور یافت نشد")
        new_treas = float(c["treasury"] or 0) + reward
        await self.db.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (new_treas, code),
        )
        try:
            await self.g.ledger_write(
                "law_register", reward, pid, from_c=None, to_c=code,
                reason=f"پاداش ثبت قانون #{lid}",
            )
        except Exception:
            try:
                await self.g.log_activity(
                    "economy", f"پاداش ثبت قانون #{lid}: +{int(reward):,}", code, pid
                )
            except Exception:
                pass
        try:
            await self.g._owner_inbox(
                "law", lid, f"قانون — {await self.g.country_label(code)}", f"{title}\n\n{body}"
            )
        except Exception:
            pass
        return (
            f"✅ قانون «{title}» ثبت شد و برای بررسی سازمان ملل ارسال گردید." + "\n"
            + f"شناسه: #{lid}" + "\n"
            + f"💰 پاداش ثبت: +{int(reward):,} به خزانه" + "\n"
            + f"موجودی جدید خزانه: {int(new_treas):,}" + "\n"
            + "(این مبلغ جدا از درآمد روزانه است)"
        )

    async def review_law(
        self, lid: int, actor: int, approve: bool, income_bonus: float = 0.0
    ) -> str:
        if not self.g.is_owner(actor):
            raise ControlError("فقط سازمان ملل / مالک")
        law = await self.db.fetchrow("SELECT * FROM ng_laws WHERE id=$1", (lid,))
        if not law or law["status"] != "pending":
            raise ControlError("قانون یافت نشد یا بررسی شده")
        now = datetime.now(timezone.utc).isoformat()
        if not approve:
            await self.db.execute(
                "UPDATE ng_laws SET status='rejected', reviewed_at=$1, reviewed_by=$2 WHERE id=$3",
                (now, actor, lid),
            )
            return f"❌ قانون #{lid} رد شد."
        income_bonus = max(0.0, min(5_000_000.0, float(income_bonus or 0)))
        await self.db.execute(
            "UPDATE ng_laws SET status='approved', income_bonus=$1, reviewed_at=$2, reviewed_by=$3 WHERE id=$4",
            (income_bonus, now, actor, lid),
        )
        # create sanction if target+item
        if law.get("target_country") and law.get("banned_item"):
            sid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_sanctions")
            await self.db.execute(
                """
                INSERT INTO ng_sanctions
                (id, source_country, target_country, kind, item_code, active, law_id, created_at)
                VALUES ($1,$2,$3,'item_ban',$4,1,$5,$6)
                """,
                (
                    int(sid["id"]),
                    law["country_code"],
                    law["target_country"],
                    law["banned_item"],
                    lid,
                    now,
                ),
            )
        await self.g.broadcast_log(
            "law",
            f"📜 قانون «{law['title']}» از {await self.g.country_label(law['country_code'])} تصویب شد.",
        )
        return f"✅ قانون #{lid} تصویب شد." + (f"\n📈 پاداش درآمد روزانه: {int(income_bonus):,}" if income_bonus else "")


    async def pending_laws(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_laws WHERE status='pending' ORDER BY id DESC LIMIT 30"
        )

    async def active_laws_for(self, code: str) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_laws WHERE country_code=$1 AND status='approved' ORDER BY id DESC LIMIT 20",
            (code,),
        )

    async def is_trade_blocked(self, buyer: str, seller: str, item_code: str) -> str | None:
        rows = await self.db.fetch(
            "SELECT * FROM ng_sanctions WHERE active=1 AND kind='item_ban'"
        )
        for r in rows:
            if r["target_country"] == seller and (not r.get("item_code") or r["item_code"] == item_code):
                # buyer is source of sanction? or anyone blocked from buying from target
                if r["source_country"] == buyer or True:
                    # item ban: nobody can buy banned item from target if source law from any
                    # Spec: US bans buying oil from Iran → block trades where seller is IR and item matches
                    if r["target_country"] == seller and (
                        not r.get("item_code") or r["item_code"] == item_code
                    ):
                        return f"تحریم فعال: خرید {item_code} از {seller} ممنوع است (قانون #{r.get('law_id')})."
        # general trade sanctions
        gen = await self.db.fetch(
            "SELECT * FROM ng_sanctions WHERE active=1 AND kind='trade' AND target_country=$1",
            (seller,),
        )
        if gen:
            return f"تحریم تجاری علیه {seller} فعال است."
        return None

    async def law_income_bonus(self, code: str) -> float:
        rows = await self.db.fetch(
            "SELECT income_bonus FROM ng_laws WHERE country_code=$1 AND status='approved'",
            (code,),
        )
        return sum(float(r["income_bonus"] or 0) for r in rows)

    async def tick_satisfaction_events(self, code: str) -> str | None:
        """Possible revolt / leader change when satisfaction low. Returns event message or None."""
        c = await self.ensure_control(code)
        sat = float(c["satisfaction"])
        if sat > 40:
            return None
        # probability scales
        if sat <= 30:
            p = 0.12
        else:
            p = 0.04
        if random.random() > p:
            return None
        # revolt: lose ~30% military inventory, new leader name flavor
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        for r in inv:
            meta = self.g._cat.get(r["item_code"], {})
            if meta.get("category") in ("ground", "air", "sea", "missile", "defense", "antiship"):
                left = float(r["quantity"]) * 0.7
                if left < 0.5:
                    await self.db.execute(
                        "DELETE FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                        (code, r["item_code"]),
                    )
                else:
                    await self.db.execute(
                        "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                        (left, code, r["item_code"]),
                    )
        # bump satisfaction slightly after crisis
        await self.db.execute(
            "UPDATE ng_country_control SET satisfaction=$1 WHERE country_code=$2",
            (min(100.0, sat + 15), code),
        )
        country = await self.db.fetchrow(
            "SELECT name_fa, leader_fa FROM ng_countries WHERE country_code=$1", (code,)
        )
        new_leader = f"شورای موقت {country['name_fa']}"
        try:
            await self.db.execute(
                "UPDATE ng_countries SET leader_fa=$1 WHERE country_code=$2",
                (new_leader, code),
            )
        except Exception:
            pass
        msg = (
            f"⚠️ بحران داخلی در {country['name_fa']}\n"
            f"نارضایتی مردم به شورش انجامید. حدود ۳۰٪ تجهیزات نظامی از دست رفت.\n"
            f"رهبری به «{new_leader}» واگذار شد. بازیکن همچنان مالک کشور است."
        )
        await self.g.broadcast_log("revolt", msg)
        return msg
