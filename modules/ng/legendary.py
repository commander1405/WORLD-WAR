"""Legendary items + permanent player wallet (New Generation)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

USES_PER_UNIT = 20

# Default catalog (prices overridable in DB)
LEGENDARY_DEFS = [
    {
        "item_code": "leg_samovar",
        "name_fa": "سماور ☕",
        "description_fa": "برای تضعیف درآمد دشمن استفاده می‌شود.",
        "power_fa": "درآمد کشور هدف در یک نوبت درآمدی ۱۰٪ کاهش می‌یابد.",
        "effect_type": "income_cut",
        "target_mode": "other",
        "duration_sec": 0,
        "price": 2500,
        "image_path": "assets/legendary/samovar.png",
    },
    {
        "item_code": "leg_anime_girl",
        "name_fa": "دختر انیمه‌ای 🌸",
        "description_fa": "برای تقویت درآمد کشور خودتان.",
        "power_fa": "درآمد کشور شما در یک نوبت درآمدی ۱۵٪ افزایش می‌یابد.",
        "effect_type": "income_boost",
        "target_mode": "self",
        "duration_sec": 0,
        "price": 3000,
        "image_path": "assets/legendary/anime_girl.png",
    },
    {
        "item_code": "leg_anime_pillow",
        "name_fa": "بالش انیمه‌ای 🛏️",
        "description_fa": "برای فلج خواب کردن حریف.",
        "power_fa": "کشور هدف ۵ دقیقه نمی‌تواند خرید یا حمله کند.",
        "effect_type": "sleep_paralysis",
        "target_mode": "other",
        "duration_sec": 300,
        "price": 4000,
        "image_path": "assets/legendary/anime_pillow.png",
    },
    {
        "item_code": "leg_military_card",
        "name_fa": "کارت پایان خدمت مهدی جهان 🎖️",
        "description_fa": "معافیت اضطراری در برابر حملات.",
        "power_fa": "کشور شما ۱۵ دقیقه در برابر حملات مصون است.",
        "effect_type": "attack_immunity",
        "target_mode": "self",
        "duration_sec": 900,
        "price": 5000,
        "image_path": "assets/legendary/military_card.png",
    },
    {
        "item_code": "leg_femboy",
        "name_fa": "فمبوی 🎀",
        "description_fa": "ممنوعیت استفاده از بمب اتم برای هدف.",
        "power_fa": "کشور هدف ۱۵ دقیقه نمی‌تواند از بمب اتم استفاده کند.",
        "effect_type": "nuke_ban",
        "target_mode": "other",
        "duration_sec": 900,
        "price": 4500,
        "image_path": "assets/legendary/femboy.png",
    },
]


class LegendaryError(Exception):
    pass


class LegendaryService:
    def __init__(self, game):
        self.g = game
        self.db = game.db

    async def ensure_tables(self) -> None:
        stmts = [
            """CREATE TABLE IF NOT EXISTS ng_legendary_defs (
                item_code TEXT PRIMARY KEY,
                name_fa TEXT NOT NULL,
                description_fa TEXT NOT NULL,
                power_fa TEXT NOT NULL,
                effect_type TEXT NOT NULL,
                target_mode TEXT NOT NULL DEFAULT 'other',
                duration_sec INTEGER NOT NULL DEFAULT 0,
                uses_per_unit INTEGER NOT NULL DEFAULT 20,
                price REAL NOT NULL DEFAULT 2000,
                image_path TEXT,
                active INTEGER NOT NULL DEFAULT 1
            )""",
            """CREATE TABLE IF NOT EXISTS ng_player_wallet (
                player_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS ng_media_cache (
                cache_key TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_wallet_tx (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                kind TEXT NOT NULL,
                reason TEXT,
                actor_id INTEGER,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_player_legendary (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
                uses_left INTEGER NOT NULL,
                acquired_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_legendary_effects (
                id INTEGER PRIMARY KEY,
                effect_type TEXT NOT NULL,
                source_player_id INTEGER,
                target_country TEXT,
                strength REAL NOT NULL DEFAULT 0,
                starts_at TEXT NOT NULL,
                ends_at TEXT,
                income_applied INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_legendary_usage_log (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
                stack_id INTEGER,
                target_country TEXT,
                result TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_legendary_purchase_log (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
                price REAL NOT NULL,
                uses_granted INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""",
        ]
        for s in stmts:
            try:
                await self.db.execute(s)
            except Exception:
                pass
        await self._seed_defs()

    async def _seed_defs(self) -> None:
        for d in LEGENDARY_DEFS:
            exists = await self.db.fetchrow(
                "SELECT item_code FROM ng_legendary_defs WHERE item_code=$1", (d["item_code"],)
            )
            if not exists:
                await self.db.execute(
                    """
                    INSERT INTO ng_legendary_defs
                    (item_code, name_fa, description_fa, power_fa, effect_type, target_mode,
                     duration_sec, uses_per_unit, price, image_path, active)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,1)
                    """,
                    (
                        d["item_code"], d["name_fa"], d["description_fa"], d["power_fa"],
                        d["effect_type"], d["target_mode"], d["duration_sec"], USES_PER_UNIT,
                        d["price"], d["image_path"],
                    ),
                )
            else:
                # refresh text/metadata but keep owner-set price
                await self.db.execute(
                    """
                    UPDATE ng_legendary_defs SET
                        name_fa=$2, description_fa=$3, power_fa=$4, effect_type=$5,
                        target_mode=$6, duration_sec=$7, uses_per_unit=$8, image_path=$9, active=1
                    WHERE item_code=$1
                    """,
                    (
                        d["item_code"], d["name_fa"], d["description_fa"], d["power_fa"],
                        d["effect_type"], d["target_mode"], d["duration_sec"], USES_PER_UNIT,
                        d["image_path"],
                    ),
                )

    # ---- wallet ----
    async def get_wallet(self, pid: int) -> float:
        row = await self.db.fetchrow(
            "SELECT balance FROM ng_player_wallet WHERE player_id=$1", (int(pid),)
        )
        return float(row["balance"]) if row else 0.0

    async def ensure_wallet(self, pid: int) -> float:
        pid = int(pid)
        row = await self.db.fetchrow(
            "SELECT balance FROM ng_player_wallet WHERE player_id=$1", (pid,)
        )
        if row:
            return float(row["balance"])
        await self.db.execute(
            "INSERT INTO ng_player_wallet (player_id, balance) VALUES ($1,0)", (pid,)
        )
        return 0.0

    async def _wallet_delta(
        self, tx, pid: int, amount: float, kind: str, reason: str, actor_id: Optional[int]
    ) -> float:
        pid = int(pid)
        amount = float(amount)
        row = await tx.fetchrow(
            "SELECT balance FROM ng_player_wallet WHERE player_id=$1", (pid,)
        )
        if not row:
            await tx.execute(
                "INSERT INTO ng_player_wallet (player_id, balance) VALUES ($1,0)", (pid,)
            )
            bal = 0.0
        else:
            bal = float(row["balance"])
        new_bal = bal + amount
        if new_bal < -1e-9:
            raise LegendaryError("موجودی کیف پول کافی نیست.")
        new_bal = max(0.0, new_bal)
        await tx.execute(
            "UPDATE ng_player_wallet SET balance=$1 WHERE player_id=$2", (new_bal, pid)
        )
        nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_wallet_tx")
        await tx.execute(
            """
            INSERT INTO ng_wallet_tx (id, player_id, amount, balance_after, kind, reason, actor_id, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            (
                int(nid["id"]), pid, amount, new_bal, kind, (reason or "")[:200],
                actor_id, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return new_bal

    async def admin_charge_wallet(self, actor: int, target_pid: int, amount: float) -> str:
        if not self.g.is_owner(actor):
            raise LegendaryError("فقط مالک مجاز است.")
        amount = float(amount)
        if amount <= 0:
            raise LegendaryError("مبلغ باید مثبت باشد.")
        if amount > 100_000_000:
            raise LegendaryError("سقف شارژ خیلی بالاست.")
        async with self.db.transaction() as tx:
            new_bal = await self._wallet_delta(
                tx, target_pid, amount, "charge", f"owner_charge:{actor}", actor
            )
        return f"✅ کیف پول شارژ شد.\nمبلغ: {int(amount):,}\nموجودی جدید: {int(new_bal):,} تومان"

    async def wallet_text(self, pid: int) -> str:
        bal = await self.ensure_wallet(pid)
        if bal <= 0:
            body = "کیف پول شما خالی است."
        else:
            body = f"کیف پول شما: {int(bal):,} تومان"
        return (
            "💰 کیف پول\n\n"
            "کیف پول برای خرید آیتم‌های لجندری و امکانات ویژه بازی قابل استفاده است.\n\n"
            f"{body}"
        )

    # ---- shop ----

    async def get_media_file_id(self, cache_key: str) -> Optional[str]:
        row = await self.db.fetchrow(
            "SELECT file_id FROM ng_media_cache WHERE cache_key=$1", (str(cache_key),)
        )
        if not row:
            return None
        fid = str(row.get("file_id") or "").strip()
        return fid or None

    async def set_media_file_id(self, cache_key: str, file_id: str) -> None:
        fid = str(file_id or "").strip()
        if not fid:
            return
        now = datetime.now(timezone.utc).isoformat()
        key = str(cache_key)
        exists = await self.db.fetchrow(
            "SELECT cache_key FROM ng_media_cache WHERE cache_key=$1", (key,)
        )
        if exists:
            await self.db.execute(
                "UPDATE ng_media_cache SET file_id=$1, updated_at=$2 WHERE cache_key=$3",
                (fid, now, key),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_media_cache (cache_key, file_id, updated_at) VALUES ($1,$2,$3)",
                (key, fid, now),
            )

    async def owns_item(self, pid: int, item_code: str) -> bool:
        """True if player has at least one usable stack of this legendary item."""
        row = await self.db.fetchrow(
            """
            SELECT 1 AS ok FROM ng_player_legendary
            WHERE player_id=$1 AND item_code=$2 AND uses_left>0
            LIMIT 1
            """,
            (int(pid), str(item_code)),
        )
        return bool(row)

    async def list_defs(self) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_legendary_defs WHERE active=1 ORDER BY name_fa"
        )
        return rows

    async def get_def(self, code: str) -> Optional[dict]:
        return await self.db.fetchrow(
            "SELECT * FROM ng_legendary_defs WHERE item_code=$1", (code,)
        )

    async def set_price(self, actor: int, item_code: str, price: float) -> str:
        if not self.g.is_owner(actor):
            raise LegendaryError("فقط مالک مجاز است.")
        price = float(price)
        if price < 0:
            raise LegendaryError("قیمت نامعتبر")
        d = await self.get_def(item_code)
        if not d:
            raise LegendaryError("آیتم یافت نشد")
        await self.db.execute(
            "UPDATE ng_legendary_defs SET price=$1 WHERE item_code=$2", (price, item_code)
        )
        return f"✅ قیمت «{d['name_fa']}» → {int(price):,} تومان"

    async def set_uses(self, actor: int, item_code: str, uses: int) -> str:
        if not self.g.is_owner(actor):
            raise LegendaryError("فقط مالک مجاز است.")
        uses = int(uses)
        if uses < 1 or uses > 1000:
            raise LegendaryError("تعداد استفاده باید بین ۱ تا ۱۰۰۰ باشد.")
        d = await self.get_def(item_code)
        if not d:
            raise LegendaryError("آیتم یافت نشد")
        await self.db.execute(
            "UPDATE ng_legendary_defs SET uses_per_unit=$1 WHERE item_code=$2",
            (uses, item_code),
        )
        return (
            f"✅ تعداد استفاده «{d['name_fa']}» → {uses} بار"
            + "\n"
            + "(برای خریدهای بعدی اعمال می‌شود؛ آیتم‌های قبلی تغییر نمی‌کنند)"
        )

    def card_text(self, d: dict, wallet: float) -> str:
        dur = int(d.get("duration_sec") or 0)
        if dur > 0:
            dur_line = f"مدت اثر: {dur // 60} دقیقه"
        else:
            dur_line = "مدت اثر: یک نوبت درآمدی"
        lines = [
            str(d.get("name_fa") or ""),
            str(d.get("description_fa") or ""),
            "",
            "قدرت:",
            str(d.get("power_fa") or ""),
            "",
            dur_line,
            f"تعداد استفاده پس از خرید: {int(d.get('uses_per_unit') or USES_PER_UNIT)} بار",
            f"قیمت: {int(float(d['price'])):,} تومان",
            f"کیف پول شما: {int(wallet):,} تومان",
        ]
        return "\n".join(lines)

    async def buy(self, pid: int, item_code: str) -> str:
        d = await self.get_def(item_code)
        if not d or not int(d.get("active") or 0):
            raise LegendaryError("آیتم در فروشگاه نیست.")
        if await self.owns_item(pid, item_code):
            raise LegendaryError(
                "این آیتم را قبلاً خریده‌اید و هنوز استفاده باقی دارد. "
                "پس از اتمام استفاده‌ها می‌توانید دوباره بخرید."
            )
        price = float(d["price"])
        uses = int(d.get("uses_per_unit") or USES_PER_UNIT)
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await self._wallet_delta(tx, pid, -price, "purchase", f"buy:{item_code}", pid)
            nid = await tx.fetchrow(
                "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_player_legendary"
            )
            await tx.execute(
                """
                INSERT INTO ng_player_legendary (id, player_id, item_code, uses_left, acquired_at)
                VALUES ($1,$2,$3,$4,$5)
                """,
                (int(nid["id"]), int(pid), item_code, uses, now),
            )
            pid2 = await tx.fetchrow(
                "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_legendary_purchase_log"
            )
            await tx.execute(
                """
                INSERT INTO ng_legendary_purchase_log (id, player_id, item_code, price, uses_granted, created_at)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                (int(pid2["id"]), int(pid), item_code, price, uses, now),
            )
        bal = await self.get_wallet(pid)
        return (
            f"✅ خرید موفق: {d['name_fa']}\n"
            f"استفاده: {uses} بار\n"
            f"مبلغ: {int(price):,}\n"
            f"کیف پول باقی‌مانده: {int(bal):,} تومان"
        )

    # ---- inventory ----
    async def inventory(self, pid: int) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT * FROM ng_player_legendary
            WHERE player_id=$1 AND uses_left>0
            ORDER BY item_code, id
            """,
            (int(pid),),
        )
        return rows

    async def inventory_summary(self, pid: int) -> list[dict]:
        """Aggregate by item_code with total stacks and uses."""
        rows = await self.inventory(pid)
        agg: dict[str, dict] = {}
        for r in rows:
            code = r["item_code"]
            if code not in agg:
                d = await self.get_def(code)
                agg[code] = {
                    "item_code": code,
                    "name_fa": (d or {}).get("name_fa") or code,
                    "stacks": 0,
                    "uses_left": 0,
                    "target_mode": (d or {}).get("target_mode") or "other",
                }
            agg[code]["stacks"] += 1
            agg[code]["uses_left"] += int(r["uses_left"])
        return list(agg.values())

    async def admin_give_item(self, actor: int, target_pid: int, item_code: str, count: int = 1) -> str:
        if not self.g.is_owner(actor):
            raise LegendaryError("فقط مالک مجاز است.")
        d = await self.get_def(item_code)
        if not d:
            raise LegendaryError("آیتم نامعتبر")
        count = max(1, min(20, int(count)))
        uses = int(d.get("uses_per_unit") or USES_PER_UNIT)
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            for _ in range(count):
                nid = await tx.fetchrow(
                    "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_player_legendary"
                )
                await tx.execute(
                    """
                    INSERT INTO ng_player_legendary (id, player_id, item_code, uses_left, acquired_at)
                    VALUES ($1,$2,$3,$4,$5)
                    """,
                    (int(nid["id"]), int(target_pid), item_code, uses, now),
                )
        return f"✅ {count}× {d['name_fa']} به بازیکن {target_pid} داده شد (هر کدام {uses} استفاده)."

    async def admin_remove_item(self, actor: int, target_pid: int, item_code: str, count: int = 1) -> str:
        if not self.g.is_owner(actor):
            raise LegendaryError("فقط مالک مجاز است.")
        count = max(1, int(count))
        rows = await self.db.fetch(
            """
            SELECT id FROM ng_player_legendary
            WHERE player_id=$1 AND item_code=$2 AND uses_left>0
            ORDER BY uses_left ASC, id ASC
            """,
            (int(target_pid), item_code),
        )
        if not rows:
            raise LegendaryError("این بازیکن چنین آیتمی ندارد.")
        removed = 0
        async with self.db.transaction() as tx:
            for r in rows[:count]:
                await tx.execute("DELETE FROM ng_player_legendary WHERE id=$1", (r["id"],))
                removed += 1
        return f"✅ {removed} موجودی «{item_code}» حذف شد."

    # ---- effects / use ----
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def active_effects(self, country: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM ng_legendary_effects WHERE target_country=$1 ORDER BY id DESC",
            (country,),
        )
        now = self._now()
        out = []
        for r in rows:
            ends = r.get("ends_at")
            if ends:
                try:
                    e = datetime.fromisoformat(str(ends).replace("Z", "+00:00"))
                    if e.tzinfo is None:
                        e = e.replace(tzinfo=timezone.utc)
                    if e <= now:
                        continue
                except Exception:
                    continue
            if r["effect_type"] in ("income_cut", "income_boost") and int(r.get("income_applied") or 0):
                continue
            out.append(r)
        return out

    async def has_effect(self, country: str, effect_type: str) -> bool:
        for e in await self.active_effects(country):
            if e["effect_type"] == effect_type:
                return True
        return False

    async def assert_can_shop(self, country: str) -> None:
        if await self.has_effect(country, "sleep_paralysis"):
            raise LegendaryError("کشور در وضعیت فلج خواب است و نمی‌تواند خرید کند.")

    async def assert_can_attack(self, country: str) -> None:
        if await self.has_effect(country, "sleep_paralysis"):
            raise LegendaryError("کشور در وضعیت فلج خواب است و نمی‌تواند حمله کند.")

    async def assert_can_nuke(self, country: str) -> None:
        if await self.has_effect(country, "nuke_ban"):
            raise LegendaryError("استفاده از بمب اتم برای این کشور موقتاً ممنوع است.")

    async def is_immune(self, country: str) -> bool:
        return await self.has_effect(country, "attack_immunity")

    async def income_multiplier(self, country: str) -> float:
        """One-shot modifiers; marks applied when consumed."""
        mult = 1.0
        rows = await self.db.fetch(
            """
            SELECT * FROM ng_legendary_effects
            WHERE target_country=$1 AND income_applied=0
              AND effect_type IN ('income_cut','income_boost')
            ORDER BY id ASC
            """,
            (country,),
        )
        applied_ids = []
        for r in rows:
            et = r["effect_type"]
            strength = float(r.get("strength") or 0)
            if et == "income_cut":
                mult *= max(0.0, 1.0 - strength)
            elif et == "income_boost":
                mult *= 1.0 + strength
            applied_ids.append(int(r["id"]))
        for i in applied_ids:
            await self.db.execute(
                "UPDATE ng_legendary_effects SET income_applied=1 WHERE id=$1", (i,)
            )
        return mult

    async def use_item(
        self, pid: int, item_code: str, target_country: Optional[str]
    ) -> str:
        d = await self.get_def(item_code)
        if not d or not int(d.get("active") or 0):
            raise LegendaryError("آیتم نامعتبر یا غیرفعال است.")
        mode = d.get("target_mode") or "other"
        own = await self.g.player_country(pid)
        if not own:
            raise LegendaryError("ابتدا باید یک کشور انتخاب کرده باشید.")

        if mode == "self":
            target_country = own
        else:
            if not target_country or target_country in ("SELF", "None", "null"):
                raise LegendaryError("کشور هدف لازم است.")
            target_country = str(target_country).upper()
            if target_country == own:
                raise LegendaryError("نمی‌توانید این آیتم را روی کشور خودتان استفاده کنید.")
            t = await self.db.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1", (target_country,)
            )
            if not t or int(t.get("is_destroyed") or 0):
                raise LegendaryError("هدف معتبر نیست یا نابود شده است.")
            if not t.get("owner_player_id"):
                raise LegendaryError("هدف بدون بازیکن است.")

        now = self._now()
        async with self.db.transaction() as tx:
            stack = await tx.fetchrow(
                """
                SELECT * FROM ng_player_legendary
                WHERE player_id=$1 AND item_code=$2 AND uses_left>0
                ORDER BY uses_left ASC, id ASC LIMIT 1
                """,
                (int(pid), item_code),
            )
            if not stack:
                raise LegendaryError("موجودی قابل‌استفاده ندارید. از فروشگاه دوباره بخرید.")
            uses_before = int(stack["uses_left"])
            uses = uses_before - 1
            if uses <= 0:
                await tx.execute(
                    "DELETE FROM ng_player_legendary WHERE id=$1", (stack["id"],)
                )
            else:
                await tx.execute(
                    "UPDATE ng_player_legendary SET uses_left=$1 WHERE id=$2",
                    (uses, stack["id"]),
                )

            et = d["effect_type"]
            strength = 0.0
            ends = None
            if et == "income_cut":
                strength = 0.10
            elif et == "income_boost":
                strength = 0.15
            elif et == "sleep_paralysis":
                ends = (now + timedelta(seconds=int(d["duration_sec"] or 300))).isoformat()
            elif et == "attack_immunity":
                ends = (now + timedelta(seconds=int(d["duration_sec"] or 900))).isoformat()
            elif et == "nuke_ban":
                ends = (now + timedelta(seconds=int(d["duration_sec"] or 900))).isoformat()
            else:
                raise LegendaryError(f"نوع اثر پشتیبانی نمی‌شود: {et}")

            eid = await tx.fetchrow(
                "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_legendary_effects"
            )
            await tx.execute(
                """
                INSERT INTO ng_legendary_effects
                (id, effect_type, source_player_id, target_country, strength, starts_at, ends_at, income_applied, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,0,$6)
                """,
                (
                    int(eid["id"]), et, int(pid), target_country, strength,
                    now.isoformat(), ends,
                ),
            )
            lid = await tx.fetchrow(
                "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_legendary_usage_log"
            )
            await tx.execute(
                """
                INSERT INTO ng_legendary_usage_log
                (id, player_id, item_code, stack_id, target_country, result, created_at)
                VALUES ($1,$2,$3,$4,$5,'ok',$6)
                """,
                (
                    int(lid["id"]), int(pid), item_code, stack["id"], target_country,
                    now.isoformat(),
                ),
            )

        label = await self.g.country_label(target_country)
        duration_txt = ""
        if ends:
            duration_txt = f"\n⏱ تا: {ends}"
        return (
            f"✅ {d['name_fa']} استفاده شد.\n"
            f"هدف: {label}\n"
            f"اثر: {d['power_fa']}\n"
            f"مصرف: ۱ از {uses_before} → باقی‌مانده این نسخه: {max(0, uses)}"
            f"{duration_txt}"
        )

    async def profile_items_text(self, pid: int) -> str:
        summary = await self.inventory_summary(pid)
        if not summary:
            return "🎁 آیتم لجندری فعال ندارد."
        lines = ["🎁 آیتم‌های لجندری:"]
        for s in summary:
            lines.append(
                f"• {s['name_fa']} — {s['stacks']} عدد | باقی‌مانده استفاده: {s['uses_left']}"
            )
        return "\n".join(lines)

    async def admin_player_legendary_block(self, pid: int) -> str:
        bal = await self.get_wallet(pid)
        items = await self.profile_items_text(pid)
        code = await self.g.player_country(pid)
        effects = []
        if code:
            for e in await self.active_effects(code):
                effects.append(f"• {e['effect_type']} روی {e.get('target_country')}")
        eff = "\n".join(effects) if effects else "اثر فعال ندارد."
        tx = await self.db.fetch(
            "SELECT * FROM ng_wallet_tx WHERE player_id=$1 ORDER BY id DESC LIMIT 5",
            (int(pid),),
        )
        tx_lines = []
        for t in tx:
            tx_lines.append(
                f"• {t['kind']} {int(float(t['amount'])):,} → موجودی {int(float(t['balance_after'])):,}"
            )
        hist = "\n".join(tx_lines) if tx_lines else "تراکنشی نیست."
        return (
            f"💰 کیف پول: {int(bal):,} تومان\n"
            f"{items}\n\n"
            f"اثرهای فعال کشور:\n{eff}\n\n"
            f"آخرین تراکنش‌های کیف پول:\n{hist}"
        )
