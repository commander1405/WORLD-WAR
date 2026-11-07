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
from modules.ng import equipment as eq
from modules.ng.legendary import LegendaryService, LegendaryError
from modules.ng.alliances import AllianceService, AllianceError, create_cost, DESTROY_WAIT_SEC
from modules.ng.control import ControlService, ControlError

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
        self.alliances = AllianceService(self)
        self.legendary = LegendaryService(self)
        self.control = ControlService(self)

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
        for stmt in (
            "ALTER TABLE ng_countries ADD COLUMN double_hp INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE ng_countries ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'country'",
            "ALTER TABLE world_meta ADD COLUMN last_daily_date TEXT",
            """CREATE TABLE IF NOT EXISTS ng_defense_hits (
                country_code TEXT PRIMARY KEY,
                hits INTEGER NOT NULL DEFAULT 0,
                break_at INTEGER NOT NULL DEFAULT 3
            )""",
        ):
            try:
                await self.db.execute(stmt)
            except Exception:
                pass
        try:
            await self.control.ensure_tables()
        except Exception:
            pass
        try:
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS ng_finance_ops (
                    op_key TEXT PRIMARY KEY,
                    country_code TEXT NOT NULL,
                    delta REAL NOT NULL,
                    actor_id INTEGER,
                    reason TEXT,
                    created_at TEXT
                )
            """)
        except Exception:
            pass
        try:
            await self.legendary.ensure_tables()
        except Exception:
            log.exception("legendary ensure")
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
        for stmt in (
            "ALTER TABLE ng_countries ADD COLUMN double_hp INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE ng_countries ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'country'",
            "ALTER TABLE world_meta ADD COLUMN last_daily_date TEXT",
            """CREATE TABLE IF NOT EXISTS ng_defense_hits (
                country_code TEXT PRIMARY KEY,
                hits INTEGER NOT NULL DEFAULT 0,
                break_at INTEGER NOT NULL DEFAULT 3
            )""",
        ):
            try:
                await self.db.execute(stmt)
            except Exception:
                pass
        try:
            await self.control.ensure_tables()
        except Exception:
            pass
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
                        category=$2, name_fa=$3, description_fa=$4,
                        max_per_order=$5, power_score=$6, daily_income=$7,
                        maintenance=$8, is_building=$9
                    WHERE item_code=$1
                    """,
                    (
                        c["item_code"], c["category"], c["name_fa"], c["description_fa"],
                        c["max_per_order"], c["power_score"],
                        c["daily_income"], c["maintenance"], c["is_building"],
                    ),
                )
            self._cat[c["item_code"]] = c
        await self._reload_catalog_prices()

    async def _seed_countries(self) -> None:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for c in data:
            exists = await self.db.fetchrow(
                "SELECT country_code FROM ng_countries WHERE country_code=$1", (c["code"],)
            )
            if exists:
                continue
            # free country — no treasury until claimed
            et = str(c.get("entity_type") or "country")
            npt = 0 if et == "group" else int(c.get("npt", 1))
            await self.db.execute(
                """
                INSERT INTO ng_countries (
                    country_code, name_fa, name_en, flag, capital_fa, leader_fa, leader_title_fa,
                    currency_code, currency_name_fa, npt_member, owner_player_id, treasury, hp, max_hp, is_destroyed, entity_type
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NULL,0,1000,1000,0,$11)
                """,
                (
                    c["code"], c["name_fa"], c["name_en"], c["flag"], c["capital_fa"],
                    c["leader_fa"], c["leader_title_fa"], c["currency_code"], c["currency_name_fa"],
                    npt, et,
                ),
            )



        # Sync entity_type / force NPT off for groups without wiping ownership
        try:
            data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            for c in data:
                et = str(c.get("entity_type") or "country")
                if et == "group":
                    await self.db.execute(
                        "UPDATE ng_countries SET entity_type='group', npt_member=0 WHERE country_code=$1",
                        (c["code"],),
                    )
                else:
                    await self.db.execute(
                        "UPDATE ng_countries SET entity_type=COALESCE(NULLIF(entity_type,''),'country') WHERE country_code=$1",
                        (c["code"],),
                    )
        except Exception:
            log.exception("entity_type sync")

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

    async def resolve_country_for_player(self, pid: int, *, include_un_for_owner: bool = False) -> Optional[str]:
        """Canonical country for a player: ownership in ng_countries wins over ng_players cache."""
        pid = int(pid)
        if include_un_for_owner and self.owner_id and pid == int(self.owner_id):
            await self.ensure_un_country()
            # Prefer real owned country if any, else UN
            owned = await self.db.fetchrow(
                "SELECT country_code FROM ng_countries WHERE owner_player_id=$1 AND country_code<>$2 AND is_destroyed=0 ORDER BY claimed_at DESC NULLS LAST",
                (pid, UN_CODE),
            )
            if owned:
                return owned["country_code"]
            return UN_CODE
        # 1) authoritative: country whose owner is this player
        owned = await self.db.fetchrow(
            """
            SELECT country_code FROM ng_countries
            WHERE owner_player_id=$1 AND country_code<>$2 AND COALESCE(is_destroyed,0)=0
            ORDER BY claimed_at DESC
            """,
            (pid, UN_CODE),
        )
        if owned:
            code = owned["country_code"]
            # heal split-brain cache
            try:
                await self.db.execute(
                    "UPDATE ng_players SET country_code=$1 WHERE player_id=$2 AND (country_code IS NULL OR country_code<>$1)",
                    (code, pid),
                )
            except Exception:
                pass
            return code
        # 2) fallback cache on player row
        p = await self.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (pid,))
        code = (p or {}).get("country_code")
        if not code or code == UN_CODE:
            return None
        c = await self.db.fetchrow(
            "SELECT owner_player_id, is_destroyed FROM ng_countries WHERE country_code=$1",
            (code,),
        )
        if not c or int(c.get("is_destroyed") or 0):
            return None
        if c.get("owner_player_id") is not None and int(c["owner_player_id"]) != pid:
            # stale cache — clear it
            try:
                await self.db.execute(
                    "UPDATE ng_players SET country_code=NULL WHERE player_id=$1", (pid,)
                )
            except Exception:
                pass
            return None
        return code

    async def player_country(self, pid: int) -> Optional[str]:
        if self.owner_id and int(pid) == int(self.owner_id):
            await self.ensure_un_country()
            return UN_CODE
        return await self.resolve_country_for_player(pid, include_un_for_owner=False)

    # ---------- claim ----------
    async def is_group(self, code: str | None) -> bool:
        if not code:
            return False
        row = await self.db.fetchrow(
            "SELECT entity_type FROM ng_countries WHERE country_code=$1", (code,)
        )
        return bool(row) and str(row.get("entity_type") or "country") == "group"

    async def list_countries(self, *, for_owner: bool = False, include_un: bool = False) -> list[dict]:
        # heal inconsistent rows: owned but marked destroyed
        try:
            await self.db.execute(
                """
                UPDATE ng_countries
                SET is_destroyed=0
                WHERE owner_player_id IS NOT NULL AND COALESCE(is_destroyed,0)=1
                """
            )
        except Exception:
            pass
        rows = await self.db.fetch(
            "SELECT * FROM ng_countries WHERE COALESCE(is_destroyed,0)=0 ORDER BY name_fa"
        )
        if for_owner or include_un:
            return rows
        return [r for r in rows if r.get("country_code") != UN_CODE]

    async def list_attack_targets(self, attacker_code: str | None, page: int = 0, page_size: int = 25) -> tuple[list[dict], int]:
        """All currently owned, living countries except attacker — always live from DB."""
        try:
            await self.db.execute(
                """
                UPDATE ng_countries
                SET is_destroyed=0
                WHERE owner_player_id IS NOT NULL AND COALESCE(is_destroyed,0)=1
                """
            )
        except Exception:
            pass
        rows = await self.db.fetch(
            """
            SELECT * FROM ng_countries
            WHERE owner_player_id IS NOT NULL
              AND COALESCE(is_destroyed,0)=0
              AND country_code <> $1
              AND country_code <> $2
            ORDER BY name_fa
            """,
            (attacker_code or "", UN_CODE),
        )
        total = len(rows)
        page = max(0, int(page))
        page_size = max(5, min(40, int(page_size)))
        start = page * page_size
        return rows[start:start + page_size], total

    async def claim(self, pid: int, code: str) -> dict:
        await self.assert_not_banned(pid)
        code = code.upper()
        if code == UN_CODE:
            raise GameError("کشور سازمان ملل فقط متعلق به مالک بازی است و قابل انتخاب نیست.")
        p = await self.touch_player(pid)
        # live ownership beats stale ng_players.country_code cache
        live = await self.resolve_country_for_player(int(pid))
        if live:
            if (p.get("country_code") or "") != live:
                await self.db.execute(
                    "UPDATE ng_players SET country_code=$1 WHERE player_id=$2",
                    (live, int(pid)),
                )
            raise GameError("شما هم‌اکنون یک کشور دارید.")
        # clear stale cache if no live ownership
        if p.get("country_code"):
            await self.db.execute(
                "UPDATE ng_players SET country_code=NULL WHERE player_id=$1",
                (int(pid),),
            )
        cd = p.get("destroy_cooldown_until")
        if cd:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(cd.replace("Z", "+00:00")):
                    raise GameError("کشور شما نابود شده است. تا ۳۰ دقیقه امکان انتخاب کشور جدید ندارید.")
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
                """
                UPDATE ng_players
                SET country_code=$1, destroy_cooldown_until=NULL
                WHERE player_id=$2
                """,
                (code, pid),
            )
        await self.log_activity("claim", f"انتخاب کشور {await self.country_name_only(code)}", code, pid)
        return await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))

    # ---------- economy / shop ----------
    async def effective_shop_multiplier(self, pid: int, country: dict) -> float:
        m = self.shop_price_multiplier(country)
        try:
            m *= await self.alliances.shop_mult_for_player(pid)
        except Exception:
            pass
        try:
            code = country.get("country_code") if country else None
            if code:
                m *= await self.control.satisfaction_shop_mult(code)
                oil = await self.control.global_oil_price_mult()
                # mild global pressure already in oil mult for energy items applied in cart later
                m *= min(1.15, 1.0 + (oil - 1.0) * 0.2)
        except Exception:
            pass
        try:
            disc = await self.get_shop_discount_pct()
            if disc > 0:
                m *= max(0.3, 1.0 - disc / 100.0)
        except Exception:
            pass
        return m

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
        meta = self._cat.get(item) or {}
        if not meta:
            raise GameError("کالا یافت نشد")
        # max_per_order = max units in ONE button press
        # cart may stack higher via repeated adds
        max_one = float(meta.get("max_per_order") or 10)
        if max_one < 1:
            max_one = 1
        cart_cap = max(max_one * 10, 50)
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 1.0
        qty = max(1.0, min(max_one, qty))
        row = await self.db.fetchrow(
            "SELECT quantity FROM ng_cart WHERE player_id=$1 AND item_code=$2", (pid, item)
        )
        prev = float(row["quantity"]) if row else 0.0
        nq = min(cart_cap, prev + qty)
        added = nq - prev
        if added <= 0:
            return (
                f"⚠ سقف سبد برای «{meta.get('name_fa')}» پر است "
                f"(حداکثر {int(cart_cap)} در سبد)."
            )
        if row:
            await self.db.execute(
                "UPDATE ng_cart SET quantity=$1 WHERE player_id=$2 AND item_code=$3",
                (nq, pid, item),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_cart (player_id, item_code, quantity) VALUES ($1,$2,$3)",
                (pid, item, nq),
            )
        note = ""
        if added + 1e-9 < qty:
            note = chr(10) + f"(درخواست {int(qty)} بود؛ به سقف سبد محدود شد)"
        return (
            f"✅ {meta.get('name_fa')} × {int(added)} به سبد اضافه شد."
            + chr(10)
            + f"جمع این کالا در سبد: {int(nq)}"
            + note
        )

    async def cart_view(self, pid: int, country_code: str) -> tuple[str, float, list]:
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (country_code,))
        mult = await self.effective_shop_multiplier(pid, c or {})
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
        try:
            disc = await self.get_shop_discount_pct()
            if disc > 0:
                lines.append(f"🏷 تخفیف سراسری فعال: {int(disc)}٪")
        except Exception:
            pass
        if mult > 1:
            lines.append("⚠ قیمت‌ها به‌خاطر نقض پیمان ۱۵٪ افزایش یافته‌اند.")
        return "\n".join(lines), total, items

    async def checkout(self, pid: int, country_code: str) -> str:
        try:
            await self.legendary.assert_can_shop(country_code)
        except LegendaryError as e:
            raise GameError(str(e)) from e
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
        label = await self.country_label(country_code)
        await self.broadcast_log("buy", f"🛒 کشور {label} یک خرید جدید انجام داد.\nمبلغ: {int(total):,}")
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
        """Pay once per Tehran calendar day.

        Base grant is protected: maintenance must not wipe the base daily income.
        Formula: base*mod + max(0,law_bonus) + max(0, buildings - maintenance)
        """
        today = datetime.now(TEHRAN).date().isoformat()
        countries = await self.db.fetch(
            "SELECT * FROM ng_countries WHERE owner_player_id IS NOT NULL AND COALESCE(is_destroyed,0)=0"
        )
        n = 0
        total_paid = 0.0
        details = []
        for c in countries:
            code = c["country_code"]
            if code == UN_CODE:
                continue
            exists = await self.db.fetchrow(
                "SELECT 1 AS x FROM ng_daily_payouts WHERE country_code=$1 AND payout_date=$2",
                (code, today),
            )
            if exists:
                continue
            try:
                ctrl = await self.control.ensure_control(code)
                base = float(ctrl.get("base_daily_income") or self.BASE_DAILY_GRANT)
                if base <= 0:
                    base = float(self.BASE_DAILY_GRANT)
                law_bonus = float(await self.control.law_income_bonus(code) or 0)
                mod = float(await self.control.income_modifier(code) or 1.0)
                if mod <= 0:
                    mod = 1.0
            except Exception:
                log.exception("daily control stats for %s", code)
                base = float(self.BASE_DAILY_GRANT)
                law_bonus = 0.0
                mod = 1.0
            try:
                await self.recalc_income(code)
            except Exception:
                log.exception("recalc_income %s", code)
            c2 = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
            if not c2:
                continue
            net_buildings = float(c2.get("daily_income") or 0) - float(c2.get("daily_expense") or 0)
            total = (base * mod) + max(0.0, law_bonus) + max(0.0, net_buildings)
            try:
                leg_m = await self.legendary.income_multiplier(code)
                total *= float(leg_m)
            except Exception:
                log.exception("legendary income mult %s", code)
            total = max(float(self.BASE_DAILY_GRANT) * 0.5 * 0.5, total)  # still non-negative floor softer when cut
            total = max(0.0, total)
            async with self.db.transaction() as tx:
                again = await tx.fetchrow(
                    "SELECT 1 AS x FROM ng_daily_payouts WHERE country_code=$1 AND payout_date=$2",
                    (code, today),
                )
                if again:
                    continue
                new_t = float(c2["treasury"] or 0) + total
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (new_t, code),
                )
                await tx.execute(
                    "INSERT INTO ng_daily_payouts (country_code, payout_date, amount) VALUES ($1,$2,$3)",
                    (code, today, total),
                )
            n += 1
            total_paid += total
            label = c2.get("name_fa") or code
            details.append(f"{label}: +{int(total):,}")
            oid = c2.get("owner_player_id")
            await self.log_activity(
                "daily",
                f"درآمد روزانه: {int(total):,} (پایه {int(base):,} × {mod:.2f})",
                code,
                int(oid) if oid else None,
            )
            try:
                await self.control.tick_satisfaction_events(code)
            except Exception:
                pass
        if n:
            sample = "\n".join(details[:12])
            more = f"\n… و {n - 12} کشور دیگر" if n > 12 else ""
            try:
                msg_lines = [
                    "💰 درآمد روزانه پرداخت شد",
                    f"تاریخ (تهران): {today}",
                    f"تعداد کشورها: {n}",
                    f"جمع کل: {int(total_paid):,}",
                    "",
                    *details[:12],
                ]
                if n > 12:
                    msg_lines.append(f"… و {n - 12} کشور دیگر")
                await self.broadcast_log("daily", chr(10).join(msg_lines))
            except Exception:
                log.exception("daily broadcast")
        return n


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
        L0 = await self.db.fetchrow("SELECT * FROM ng_market WHERE id=$1 AND active=1", (listing_id,))
        if L0:
            try:
                blocked = await self.control.is_trade_blocked(buyer, L0["seller_country"], L0["item_code"])
                if blocked:
                    raise GameError(blocked)
            except GameError:
                raise
            except Exception:
                pass
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
        raise GameError("پیمان صلح حذف شده است. از سیستم اتحاد استفاده کنید.")
        # legacy disabled
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
    ATTACK_COOLDOWN_SEC = 120  # 2 minutes for all except UN

    async def attack_cooldown_sec(self) -> int:
        """Player attack cooldown; UN bypasses separately. Owner can override via setting."""
        try:
            row = await self.db.fetchrow(
                "SELECT value FROM ng_bot_settings WHERE key=$1", ("attack_cooldown_sec",)
            )
            if row and str(row.get("value") or "").strip().isdigit():
                return max(0, min(3600, int(row["value"])))
        except Exception:
            pass
        return int(getattr(self, "ATTACK_COOLDOWN_SEC", 120) or 120)

    async def set_attack_cooldown_sec(self, actor: int, seconds: int) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        seconds = max(0, min(3600, int(seconds)))
        await self._write_setting_raw("attack_cooldown_sec", str(seconds))
        await self.admin_log(actor, "attack_cooldown", str(seconds))
        return f"✅ کول‌داون حمله بازیکنان: {seconds} ثانیه ({seconds/60:.1f} دقیقه). سازمان ملل بدون کول‌داون است."

    BASE_DAILY_GRANT = 20_000_000  # fixed daily grant per owned country (Tehran day)
    REF_INVITEE_REWARD = 2_000_000
    REF_REFERRER_REWARD = 15_000_000
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
            code_i = r["item_code"]
            meta = self._cat.get(code_i) or eq.meta(code_i)
            if not meta:
                continue
            cat = meta.get("category")
            q = float(r["quantity"])
            if cat == "defense" or str(code_i).startswith("m_sam") or code_i in ("d_radar", "d_sam"):
                total += eq.defense_power_for_unit(code_i, q)
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
        kind_factor = {"air": 1.0, "ground": 0.55, "sea": 0.45, "nuclear": 0.2}.get(attack_kind, 0.5)
        disable = await self.active_cyber_disable_ratio(code)
        bonus = 0.0
        try:
            if attack_kind in ("air", "missile", "nuke"):
                bonus += await self.control.defense_air_bonus(code)
            if attack_kind in ("sea", "naval"):
                bonus += await self.control.defense_sea_bonus(code)
        except Exception:
            pass
        effective = base * kind_factor * (1.0 - disable) + bonus
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
        # internet off on target → near-zero success
        chance = 1.0
        try:
            chance = await self.control.cyber_defense_bonus(target)
        except Exception:
            pass
        import random as _rnd
        if _rnd.random() > chance:
            await self._consume_item(attacker, "cyber_hack_def", 1)
            return "❌ عملیات سایبری تقریباً شکست خورد (اینترنت هدف قطع است یا پدافند سایبری قوی است). آیتم مصرف شد."
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
        """Return (total attack power, units) using independent item damage stats."""
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        units = []
        total = 0.0
        for r in inv:
            code_i = r["item_code"]
            meta = self._cat.get(code_i) or eq.meta(code_i)
            if not meta:
                continue
            cat = meta.get("category")
            q = float(r["quantity"])
            if q <= 0:
                continue
            ctype = eq.consumption_type(code_i)
            if ctype in ("passive", "building"):
                continue
            if cat == "missile":
                if not eq.missile_matches_kind(code_i, kind):
                    continue
            elif kind == "ground" and cat not in ("ground",):
                continue
            elif kind in ("air", "sea") and cat != kind:
                continue
            elif kind == "defense" and cat not in ("defense", "missile"):
                continue
            dmg = eq.damage_of(code_i)
            if dmg <= 0 and kind != "defense":
                continue
            power = eq.attack_power_for_unit(code_i, q)
            total += power
            units.append({
                "item_code": code_i,
                "quantity": q,
                "power": dmg,
                "consumption_type": ctype,
                "name_fa": meta.get("name_fa") or code_i,
            })
        return total, units

    async def can_attack(self, code: str, kind: str | None = None) -> tuple[bool, str]:
        if self.is_un_country(code):
            return True, ""
        try:
            await self.legendary.assert_can_attack(code)
        except LegendaryError as e:
            return False, str(e)
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
                if elapsed < await self.attack_cooldown_sec():
                    left = int(await self.attack_cooldown_sec() - elapsed)
                    return False, f"هنوز در محدودیت حمله هستید. {left} ثانیه صبر کنید."
            except Exception:
                pass
        return True, ""

    async def attack(self, attacker: str, defender: str, kind: str, percent: float, pid: int) -> str:
        un_atk = self.is_un_force(attacker, pid)
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if not un_atk and meta and int(meta.get("war_enabled") or 0) != 1:
            raise GameError("جنگ توسط سازمان ملل بسته شده است.")
        if not un_atk and await self.at_peace(attacker, defender):
            raise GameError("پیمان صلح فعال است؛ حمله ممکن نیست.")
        if not un_atk:
            try:
                await self.legendary.assert_can_attack(attacker)
            except LegendaryError as e:
                raise GameError(str(e)) from e
        if not un_atk and await self.legendary.is_immune(defender):
            raise GameError("کشور هدف مصونیت دارد؛ حمله بی‌اثر است.")
        if attacker == defender:
            raise GameError("نامعتبر")
        if kind not in ("ground", "air", "sea"):
            raise GameError("نوع درگیری نامعتبر است.")
        percent = max(10, min(100, float(percent)))
        test_atk = await self.is_test_active_for_country(attacker) or un_atk
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
                    if elapsed < await self.attack_cooldown_sec():
                        left = int(await self.attack_cooldown_sec() - elapsed)
                        raise GameError(f"محدودیت حمله: {left} ثانیه باقی مانده است.")
                except GameError:
                    raise
                except Exception:
                    pass

            # forces from inventory (locked by transaction) — independent stats
            inv = await tx.fetch(
                "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (attacker,)
            )
            units = []  # (code, qty, engage_qty)
            total_power = 0.0
            for r in inv:
                ic = r["item_code"]
                meta_i = self._cat.get(ic) or eq.meta(ic)
                if not meta_i:
                    continue
                cat = meta_i.get("category")
                q = float(r["quantity"])
                if q <= 0:
                    continue
                ctype = eq.consumption_type(ic)
                if ctype in ("passive", "building"):
                    continue
                if cat == "specialist":
                    units.append((ic, q, min(1.0, q), "specialist"))
                    continue
                if cat == "missile":
                    if not eq.missile_matches_kind(ic, kind):
                        continue
                elif kind == "ground" and cat != "ground":
                    continue
                elif kind in ("air", "sea") and cat != kind:
                    continue
                elif cat not in ("ground", "air", "sea", "missile"):
                    continue
                dmg = eq.damage_of(ic)
                if dmg <= 0:
                    continue
                eng = eq.engage_quantity(q, percent)
                if eng <= 0:
                    continue
                if eng > q:
                    eng = q
                power = eq.attack_power_for_unit(ic, eng)
                total_power += power
                units.append((ic, q, eng, ctype))

            combat_units = [u for u in units if u[3] != "specialist"]
            if (not combat_units or total_power <= 0) and un_atk:
                # سازمان ملل بدون نیاز به موجودی نیرو حمله می‌کند
                total_power = 5000.0 * (percent / 100.0)
                combat_units = []  # no inventory consumption
            if not combat_units and not un_atk:
                raise GameError("نیروی نظامی قابل‌استفاده برای این نوع حمله ندارید.")
            if total_power <= 0 and not un_atk:
                raise GameError("نیروی نظامی قابل‌استفاده برای این نوع حمله ندارید.")

            engaged_power = total_power
            # Pre-check stock before applying
            for ic, q, eng, ctype in combat_units:
                if eng > q + 1e-9:
                    raise GameError(f"موجودی {ic} کافی نیست.")

            # Specialist boost (optional one charge)
            specialist_used = []
            logistics_bonus = False
            for ic, q, eng, ctype in units:
                if ctype != "specialist":
                    continue
                if q < 1:
                    continue
                # auto-use at most one specialist charge if available
                meta_i = self._cat.get(ic) or {}
                name = meta_i.get("name_fa") or ic
                # consume 1 charge
                new_q = max(0.0, q - 1.0)
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (new_q, attacker, ic),
                )
                specialist_used.append(name)
                if ic == "sp_logistics":
                    logistics_bonus = True
                if ic == "sp_air" and kind == "air":
                    engaged_power *= 1.15
                if ic == "sp_naval" and kind == "sea":
                    engaged_power *= 1.15
                if ic == "sp_intel":
                    engaged_power *= 1.08
                break  # one specialist type per attack

            # Tentative victory for attrition rates (refined after dp)
            # First compute defender power
            dp_units = await tx.fetch(
                "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (defender,)
            )
            dp = 0.0
            for r in dp_units:
                ic = r["item_code"]
                meta_i = self._cat.get(ic) or eq.meta(ic)
                if not meta_i:
                    continue
                cat = meta_i.get("category")
                q = float(r["quantity"])
                if cat in ("defense",) or (cat == "missile" and ic.startswith("m_sam")):
                    dp += eq.defense_power_for_unit(ic, q)
                elif cat == kind:
                    dp += eq.defense_power_for_unit(ic, q) * 0.5 + eq.damage_of(ic) * q * 0.15

            ap = engaged_power
            if ap <= 0:
                raise GameError("نیروی اعزامی صفر است.")
            victory_guess = ap >= dp * 0.85

            # Consume attacker equipment according to type
            consumption_log = []
            for ic, q, eng, ctype in combat_units:
                loss = eq.consume_amount(
                    ic, eng, victory=victory_guess, specialist_bonus_logistics=logistics_bonus
                )
                if loss <= 0:
                    continue
                if loss > q:
                    loss = q
                new_q = max(0.0, q - loss)
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (new_q, attacker, ic),
                )
                nm = (self._cat.get(ic) or {}).get("name_fa") or ic
                consumption_log.append(f"{nm}: −{loss:.2f} (باقی {new_q:.2f})")

            # Defender expendable SAM may intercept and consume some
            for r in dp_units:
                ic = r["item_code"]
                if eq.consumption_type(ic) != "expendable":
                    continue
                if not str(ic).startswith("m_sam"):
                    continue
                q = float(r["quantity"])
                if q < 1:
                    continue
                use = min(q, max(1.0, q * 0.1))
                new_q = max(0.0, q - use)
                await tx.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (new_q, defender, ic),
                )
                break

            raw = (ap - dp * 0.55) * 0.35 + 15
            damage = max(5.0, min(220.0, raw))
            cover, def_meta = await self.defense_coverage(defender, kind)
            intercepted = damage * cover
            damage = max(3.0, damage - intercepted)
            victory = ap >= dp * 0.85
            result = f"پیروزی {attacker}" if victory else f"برتری دفاعی {defender}"
            # stash logs on self for report (per-call local via nonlocal later)
            self._last_combat_log = {
                "consumption": consumption_log,
                "specialists": specialist_used,
                "ap": ap,
                "dp": dp,
            }

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
                    "UPDATE ng_countries SET treasury=$1, owner_player_id=NULL, is_destroyed=0, claimed_at=NULL, hp=1000 WHERE country_code=$2",
                    (float(d_row["treasury"]) - half_money, defender),
                )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (a_treas + half_money, attacker),
                )
                prev = d_row.get("owner_player_id")
                if prev:
                    until = (now + timedelta(seconds=DESTROY_WAIT_SEC)).isoformat()
                    await tx.execute(
                        "UPDATE ng_players SET country_code=NULL, destroy_cooldown_until=$1 WHERE player_id=$2",
                        (until, int(prev)),
                    )

        atk_name = await self.country_label(attacker)
        def_name = await self.country_label(defender)
        clog = getattr(self, "_last_combat_log", {}) or {}
        cons_lines = clog.get("consumption") or []
        sp_lines = clog.get("specialists") or []
        extra_parts = []
        if cons_lines:
            extra_parts.append("📦 مصرف تجهیزات مهاجم:")
            extra_parts.extend(cons_lines[:12])
        if sp_lines:
            extra_parts.append("متخصص: " + "، ".join(sp_lines))
        if clog.get("ap") is not None:
            extra_parts.append(f"قدرت حمله: {clog['ap']:.0f} | قدرت دفاع: {clog.get('dp', 0):.0f}")
        extra = ("\n" + "\n".join(extra_parts)) if extra_parts else ""
        report = (
            f"⚔️ گزارش درگیری\n\n"
            f"مهاجم: {atk_name}\nمدافع: {def_name}\nنوع: {kind}\nشدت: {int(percent)}٪\n"
            f"نتیجه: {result}\n"
            f"خسارت نهایی: {int(damage)}\n"
            f"رهگیری پدافند: {int(intercepted)} (پوشش {cover*100:.0f}٪)\n"
            f"سلامت فعلی مدافع: {int(max(0, new_hp))}\n"
            f"غنیمت نقدی: {int(loot):,}"
            + (" (غنیمتی نبود)" if loot <= 0 and victory else "")
            + extra
        )
        await self.broadcast_log("attack", report)
        if new_hp <= 0:
            await self.alliances.on_country_destroyed(defender)
            await self.broadcast_log("destroy", f"💥 کشور {def_name} نابود شد.")
        try:
            wear = await self.apply_defense_wear(defender)
            if wear:
                report = report + "\n\n⚠️ " + wear
        except Exception:
            pass
        try:
            warn = await self.alliances.check_betrayal_on_attack(pid, attacker, defender)
            if warn:
                report = report + "\n\n" + warn
        except Exception:
            pass
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
        if len(body) < 50:
            raise GameError("متن بیانیه باید حداقل ۵۰ کاراکتر باشد.")
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
        if await self.get_owner_away():
            return await self.review_statement(sid, True, self.owner_id)
        await self._owner_inbox("statement", sid, f"بیانیه — {name}", owner_body)
        return "✅ بیانیه برای بررسی مالک ارسال شد."

    async def review_statement(self, sid: int, approve: bool, actor: int) -> str:
        if not self.owner_id or int(actor) != int(self.owner_id):
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

    def is_un_country(self, code: str | None) -> bool:
        return (code or "").upper() == UN_CODE

    def is_un_force(self, code: str | None, pid: int | None = None) -> bool:
        """سازمان ملل (مالک) همیشه مجاز به عملیات نظامی/اتمی است."""
        if not self.is_un_country(code):
            return False
        if pid is None:
            return True
        return self.is_owner(int(pid))


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


    @staticmethod
    def parse_money_amount(text: str) -> float:
        if text is None:
            raise GameError("مبلغ نامعتبر است")
        s = str(text).strip().replace(",", "").replace("،", "").replace(" ", "")
        trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        s = s.translate(trans)
        if not s or s in {".", "+", "-"}:
            raise GameError("مبلغ نامعتبر است")
        try:
            return float(s)
        except ValueError as e:
            raise GameError("مبلغ را به عدد بنویسید. مثال: 5000000") from e

    async def adjust_treasury(
        self,
        country_code: str,
        delta: float,
        *,
        actor: int,
        reason: str,
        allow_negative: bool = False,
        op_key: str | None = None,
    ) -> dict:
        """Single source of truth for country treasury changes."""
        code = (country_code or "").strip().upper()
        delta = float(delta)
        if delta == 0:
            raise GameError("مبلغ صفر نامعتبر است")
        if not code:
            raise GameError("کشور نامعتبر است")
        async with self.db.transaction() as tx:
            if op_key:
                try:
                    exists = await tx.fetchrow(
                        "SELECT 1 AS x FROM ng_finance_ops WHERE op_key=$1", (op_key,)
                    )
                    if exists:
                        raise GameError("این عملیات قبلاً ثبت شده است.")
                except GameError:
                    raise
                except Exception:
                    pass
            c = await tx.fetchrow(
                "SELECT country_code, treasury, name_fa, currency_name_fa, owner_player_id FROM ng_countries WHERE country_code=$1",
                (code,),
            )
            if not c:
                raise GameError(f"کشور «{code}» در دیتابیس یافت نشد")
            before = float(c["treasury"] or 0)
            after = before + delta
            if after < -0.0001 and not allow_negative:
                raise GameError(
                    f"موجودی کافی نیست. موجودی فعلی: {int(before):,} — درخواست: {int(delta):+,}"
                )
            after = max(0.0, after) if not allow_negative else after
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (after, code),
            )
            check = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (code,)
            )
            if check is None or abs(float(check["treasury"]) - after) > 0.01:
                raise GameError("خطا در ذخیره موجودی؛ عملیات لغو شد.")
            if op_key:
                try:
                    await tx.execute(
                        "INSERT INTO ng_finance_ops (op_key, country_code, delta, actor_id, reason, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
                        (op_key, code, delta, actor, reason, datetime.now(timezone.utc).isoformat()),
                    )
                except Exception:
                    pass
        try:
            await self.ledger_write(
                reason or "adjust", abs(delta), actor,
                to_c=code if delta > 0 else None,
                from_c=code if delta < 0 else None,
                reason=reason,
            )
        except Exception:
            log.exception("ledger adjust_treasury")
        try:
            await self.admin_log(actor, "treasury", f"{code} {delta:+.0f} {before:.0f}->{after:.0f} {reason}")
        except Exception:
            pass
        return {
            "code": code,
            "before": before,
            "after": after,
            "delta": delta,
            "name_fa": c.get("name_fa") or code,
            "currency": c.get("currency_name_fa") or "",
            "owner_player_id": c.get("owner_player_id"),
        }

    async def admin_money(self, actor: int, code: str, amount: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        res = await self.adjust_treasury(code, float(amount), actor=actor, reason="admin_money")
        return "\n".join([
            "✅ پول با موفقیت در دیتابیس ثبت شد.",
            f"کشور: {res['name_fa']} ({res['code']})",
            f"بازیکن مالک کشور: {res['owner_player_id'] or '—'}",
            f"قبل: {int(res['before']):,} {res['currency']}",
            f"تغییر: {int(res['delta']):+,} {res['currency']}",
            f"موجودی جدید: {int(res['after']):,} {res['currency']}",
        ])

    async def admin_give_all_players(self, actor: int, amount: float) -> str:
        """Owner grants the same amount to every owned player country (not UN)."""
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ باید مثبت باشد")
        if amount > 5_000_000_000:
            raise GameError("سقف هر واریز همگانی ۵ میلیارد است")
        rows = await self.db.fetch(
            "SELECT country_code, name_fa, owner_player_id, treasury FROM ng_countries "
            "WHERE owner_player_id IS NOT NULL AND country_code<>$1 AND COALESCE(is_destroyed,0)=0",
            (UN_CODE,),
        )
        if not rows:
            raise GameError("هیچ کشور بازیکنی یافت نشد")
        ok, fail = 0, 0
        for r in rows:
            try:
                await self.adjust_treasury(
                    r["country_code"], amount, actor=actor, reason=f"give_all:{actor}"
                )
                ok += 1
            except Exception:
                log.exception("give_all %s", r["country_code"])
                fail += 1
        try:
            await self.broadcast_log(
                "admin",
                chr(10).join([
                    "💵 واریز همگانی توسط سازمان ملل",
                    f"مبلغ هر کشور: {int(amount):,}",
                    f"موفق: {ok} | ناموفق: {fail}",
                ]),
            )
        except Exception:
            pass
        await self.admin_log(actor, "give_all", f"amount={amount} ok={ok} fail={fail}")
        return chr(10).join([
            "✅ واریز همگانی انجام شد.",
            f"مبلغ هر کشور: {int(amount):,}",
            f"موفق: {ok}",
            f"ناموفق: {fail}",
        ])

    async def admin_give_to_player(self, actor: int, target_pid: int, amount: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("برای افزودن، مبلغ باید مثبت باشد")
        target_pid = int(target_pid)
        code = await self.resolve_country_for_player(target_pid)
        if not code:
            raise GameError(
                f"بازیکن {target_pid} کشور معتبری ندارد یا مالکیت کشور هم‌خوان نیست."
            )
        res = await self.adjust_treasury(
            code, amount, actor=actor, reason=f"give_to_player:{target_pid}"
        )
        try:
            await self.log_activity(
                "admin_grant",
                f"سازمان ملل {int(amount):,} به خزانه کشور شما افزود. موجودی: {int(res['after']):,}",
                code,
                target_pid,
            )
        except Exception:
            pass
        return "\n".join([
            f"✅ واریز موفق به بازیکن {target_pid}",
            f"کشور: {res['name_fa']} ({res['code']})",
            f"قبل: {int(res['before']):,}",
            f"واریز: +{int(amount):,}",
            f"موجودی جدید (از دیتابیس): {int(res['after']):,}",
        ])

    async def admin_take_from_player(self, actor: int, target_pid: int, amount: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        amount = float(amount)
        if amount <= 0:
            raise GameError("مبلغ باید مثبت باشد")
        target_pid = int(target_pid)
        code = await self.resolve_country_for_player(target_pid)
        if not code:
            raise GameError(f"بازیکن {target_pid} کشور معتبری ندارد.")
        res = await self.adjust_treasury(
            code, -amount, actor=actor, reason=f"take_from_player:{target_pid}"
        )
        return "\n".join([
            f"✅ برداشت موفق از بازیکن {target_pid}",
            f"کشور: {res['name_fa']} ({res['code']})",
            f"قبل: {int(res['before']):,}",
            f"برداشت: -{int(amount):,}",
            f"موجودی جدید: {int(res['after']):,}",
        ])


    async def full_reset(self, actor: int, confirm_phrase: str) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        if confirm_phrase.strip() != "ریست کامل جهان":
            raise GameError("عبارت تأیید نادرست است.")
        tables = [
            "ng_cart","ng_market","ng_peace","ng_statements","ng_daily_payouts",
            "ng_activity","ng_admin_log","ng_buildings","ng_inventory","ng_players",
            "ng_workshop","ng_workshop_jobs","ng_npt_requests","ng_owner_inbox","ng_war_state","ng_test_mode","ng_finance_ledger","ng_player_activity","ng_cyber_effects","ng_referrals","ng_alliances","ng_alliance_members","ng_alliance_tx","ng_alliance_exits","ng_player_flags","ng_country_control","ng_laws","ng_sanctions","ng_law_daily","ng_defense_hits",
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
        dbl = int(c.get("double_hp") or 0) == 1
        hp_line = f"❤️ سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}"
        if dbl:
            hp_line += " ×۲"
        dbl_line = "جان ۲ برابر: فعال ✅" if dbl else "جان ۲ برابر: غیرفعال"
        parts = [
            f"{c.get('flag') or ''} {c['name_fa']}",
            f"👑 رهبر: {c['leader_fa']} ({c['leader_title_fa']})",
            f"🏙 پایتخت: {c['capital_fa']}",
            f"💵 پول: {c['currency_name_fa']}",
            f"💰 خزانه: {int(float(c['treasury'])):,}",
            f"📈 درآمد روزانه: {int(float(c['daily_income'])):,}",
            f"📉 هزینه روزانه: {int(float(c['daily_expense'])):,}",
            hp_line,
            f"🧬 {dbl_line}",
            f"☢ {npt}",
            f"بازیکن: {'دارد' if c.get('owner_player_id') else 'آزاد'}",
        ]
        try:
            oid = c.get("owner_player_id")
            if oid:
                parts.append("")
                parts.append(await self.legendary.profile_items_text(int(oid)))
        except Exception:
            log.exception("country_card legendary")
        return "\n".join(parts)


    async def add_inventory(self, country_code: str, item_code: str, qty: float, tx=None) -> None:
        """Add stock; specialists grant 2 charges per purchased unit."""
        db = tx or self.db
        meta = self._cat.get(item_code) or eq.meta(item_code) or {}
        add = float(qty)
        if meta.get("consumption_type") == "specialist" or meta.get("category") == "specialist":
            add = float(qty) * eq.SPECIALIST_CHARGES_PER_UNIT
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (country_code, item_code),
        )
        if inv:
            await db.execute(
                "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                (float(inv["quantity"]) + add, country_code, item_code),
            )
        else:
            await db.execute(
                "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                (country_code, item_code, add),
            )

    async def inventory_text(self, code: str) -> str:
        rows = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
            (code,),
        )
        lines = ["📦 انبار نظامی و تجهیزات", ""]
        if not rows:
            lines.append("خالی")
            return "\n".join(lines)
        by_cat: dict = {}
        for r in rows:
            meta = self._cat.get(r["item_code"]) or eq.meta(r["item_code"]) or {
                "name_fa": r["item_code"], "category": "other"
            }
            cat = meta.get("category") or "other"
            by_cat.setdefault(cat, []).append((meta, r))
        order = ["ground", "air", "sea", "missile", "defense", "specialist", "cyber", "nuclear", "mine", "infra", "other"]
        for cat in order:
            items = by_cat.get(cat)
            if not items:
                continue
            lines.append(CAT_FA.get(cat, cat))
            for meta, r in items:
                q = float(r["quantity"])
                ctype = eq.consumption_type(r["item_code"])
                if ctype == "specialist":
                    extra = f" | شارژ باقیمانده: {int(q)} (هر خرید=۲ استفاده)"
                elif ctype == "expendable":
                    extra = " | مصرفی"
                elif ctype == "sortie":
                    extra = " | مأموریتی"
                else:
                    extra = ""
                dmg, dfn = eq.damage_of(r["item_code"]), eq.defense_of(r["item_code"])
                lines.append(
                    f"• {meta.get('name_fa')}: {q:g} | آسیب {dmg:g} | دفاع {dfn:g}{extra}"
                )
            lines.append("")
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


    async def _reload_catalog_prices(self) -> None:
        """Sync in-memory catalog prices from DB (owner overrides)."""
        try:
            rows = await self.db.fetch("SELECT item_code, unit_price, name_fa, category, description_fa, max_per_order, power_score, daily_income, maintenance, is_building FROM ng_shop_catalog")
        except Exception:
            return
        for r in rows:
            code = r["item_code"]
            base = dict(self._cat.get(code) or {})
            base.update({
                "item_code": code,
                "unit_price": float(r["unit_price"]),
                "name_fa": r.get("name_fa") or base.get("name_fa") or code,
                "category": r.get("category") or base.get("category") or "misc",
                "description_fa": r.get("description_fa") or base.get("description_fa") or "",
                "max_per_order": float(r.get("max_per_order") or base.get("max_per_order") or 10),
                "power_score": float(r.get("power_score") or base.get("power_score") or 0),
                "daily_income": float(r.get("daily_income") or base.get("daily_income") or 0),
                "maintenance": float(r.get("maintenance") or base.get("maintenance") or 0),
                "is_building": int(r.get("is_building") or base.get("is_building") or 0),
            })
            self._cat[code] = base

    async def get_shop_discount_pct(self) -> float:
        """Global shop discount %. Catalog base prices are never mutated."""
        try:
            row = await self.db.fetchrow(
                "SELECT value FROM ng_bot_settings WHERE key=$1", ("shop_discount_pct",)
            )
            val = (row["value"] if row else "0") or "0"
            return max(0.0, min(70.0, float(val)))
        except Exception:
            return 0.0

    async def _write_setting_raw(self, key: str, value: str) -> None:
        """Persist setting without min-length checks used for message texts."""
        value = str(value)
        row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", (key,))
        if row:
            await self.db.execute(
                "UPDATE ng_bot_settings SET value=$1 WHERE key=$2", (value, key)
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", (key, value)
            )

    async def set_shop_discount(self, actor: int, pct: float) -> str:
        """Single global runtime discount. Off restores base prices automatically."""
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        pct = float(pct)
        allowed = {0, 10, 20, 30, 40, 50, 60, 70}
        if pct not in allowed:
            raise GameError("تخفیف باید یکی از ۰/۱۰/۲۰/۳۰/۴۰/۵۰/۶۰/۷۰ باشد.")
        await self._write_setting_raw("shop_discount_pct", str(int(pct)))
        if pct <= 0:
            await self.admin_log(actor, "shop_discount", "off")
            return (
                "✅ تخفیف سراسری فروشگاه خاموش شد."
                + "\n"
                + "همه کالاها دوباره با قیمت پایه (بدون تخفیف) محاسبه می‌شوند."
            )
        await self.admin_log(actor, "shop_discount", f"{int(pct)}%")
        return (
            f"✅ تخفیف سراسری {int(pct)}٪ فعال شد."
            + "\n"
            + "قیمت پایه کالاها در دیتابیس تغییر نکرد."
            + "\n"
            + "تخفیف فقط هنگام نمایش و خرید اعمال می‌شود."
            + "\n"
            + "آیتم‌های جدید و قیمت‌های ویرایش‌شده هم شامل می‌شوند."
            + "\n"
            + "فقط یک تخفیف همزمان فعال است."
        )

    async def set_item_unit_price(self, actor: int, item_code: str, price: float) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        item_code = (item_code or "").strip()
        price = float(price)
        if price < 0:
            raise GameError("قیمت نمی‌تواند منفی باشد.")
        if price > 10_000_000_000:
            raise GameError("قیمت بیش از حد بزرگ است.")
        row = await self.db.fetchrow(
            "SELECT * FROM ng_shop_catalog WHERE item_code=$1", (item_code,)
        )
        if not row:
            raise GameError("آیتم در فروشگاه یافت نشد.")
        await self.db.execute(
            "UPDATE ng_shop_catalog SET unit_price=$1 WHERE item_code=$2",
            (price, item_code),
        )
        if item_code in self._cat:
            self._cat[item_code] = {**self._cat[item_code], "unit_price": price}
        else:
            await self._reload_catalog_prices()
        await self.admin_log(actor, "shop_price", f"{item_code}={int(price)}")
        name = row.get("name_fa") or item_code
        return f"✅ قیمت «{name}» ثبت شد: {int(price):,}"

    async def list_catalog_by_category(self, category: str | None = None) -> list[dict]:
        await self._reload_catalog_prices()
        if category:
            rows = await self.db.fetch(
                "SELECT * FROM ng_shop_catalog WHERE category=$1 ORDER BY name_fa",
                (category,),
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM ng_shop_catalog ORDER BY category, name_fa"
            )
        disc = await self.get_shop_discount_pct()
        out = []
        for r in rows:
            base = float(r["unit_price"])
            eff = base * (1.0 - disc / 100.0) if disc else base
            out.append({**dict(r), "unit_price": base, "price_eff": eff, "discount_pct": disc})
        return out

    async def world_status_text(self, *, for_owner: bool = False) -> str:
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        countries = await self.list_countries(for_owner=for_owner)
        free = sum(1 for c in countries if not c.get("owner_player_id") and c.get("country_code") != UN_CODE)
        owned = sum(1 for c in countries if c.get("owner_player_id") and c.get("country_code") != UN_CODE)
        war = "فعال ⚔️" if meta and int(meta.get("war_enabled") or 0) else "غیرفعال 🕊"
        nuke = "فعال" if meta and int(meta.get("nuclear_enabled") or 0) else "غیرفعال"
        started = (meta or {}).get("started_at") or "—"
        try:
            dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            started_fa = dt.astimezone(TEHRAN).strftime("%Y/%m/%d %H:%M")
        except Exception:
            started_fa = str(started)[:19]
        total = 31 if for_owner else 30
        lines = [
            "🌍 گزارش وضعیت جهان",
            "",
            "━━━━━━━━━━━━━━",
            "🗺 اطلاعات جهان",
            f"👥 کشورهای ثبت‌شده: {total}",
            f"🟢 کشورهای دارای رهبر: {owned}",
            f"⚪ کشورهای آزاد: {free}",
            f"⚔️ وضعیت جنگ: {war}",
            f"☢ سیستم هسته‌ای: {nuke}",
            "",
            "━━━━━━━━━━━━━━",
            "📊 وضعیت کلی",
            f"🔄 تعداد بازنشانی‌ها: {int((meta or {}).get('reset_count') or 0)}",
            f"🕒 آغاز جهان (تهران): {started_fa}",
        ]
        return "\n".join(lines)

    async def economy_card(self, code: str) -> str:
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        if not c:
            return "کشور یافت نشد"
        try:
            ctrl = await self.control.ensure_control(code)
            base = float(ctrl["base_daily_income"])
            mod = await self.control.income_modifier(code)
            law_b = await self.control.law_income_bonus(code)
            sat = float(ctrl["satisfaction"])
        except Exception:
            base, mod, law_b, sat = 20_000_000.0, 1.0, 0.0, 70.0
        net = float(c["daily_income"]) - float(c["daily_expense"])
        est = (base + law_b + net) * mod
        title = await self.country_label(code)
        lines = [
            f"🏛 وضعیت اقتصادی {title}",
            "",
            "━━━━━━━━━━━━━━",
            "💰 خزانه کل:",
            f"{int(float(c['treasury'])):,} {c.get('currency_name_fa') or ''}",
            "",
            f"📈 درآمد ساختمان‌ها: {int(float(c['daily_income'])):,}",
            f"📉 هزینه نگهداری: {int(float(c['daily_expense'])):,}",
            f"🏛 درآمد پایه: {int(base):,}",
            f"📜 پاداش قوانین: {int(law_b):,}",
            f"⚙️ ضریب شرایط: {mod:.2f}",
            f"⚖️ برآورد خالص روزانه: {int(est):,}",
            "",
            f"❤️ سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}",
            f"😊 رضایت مردم: {sat:.0f}/100",
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
        short_ok = {
            "shop_discount_pct", "war_enabled", "nuclear_enabled",
            "log_level", "daily_paid_date",
        }
        if key not in short_ok:
            if len(value) < 3:
                raise GameError("متن خیلی کوتاه است.")
            if len(value) > 3500:
                raise GameError("متن خیلی بلند است.")
        elif len(value) > 3500:
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

    async def _has_any_refinery(self, tx, code: str) -> bool:
        """Accept any shop refinery variant + legacy codes."""
        codes = (
            "b_refinery",
            "b_refinery_s",
            "b_refinery_m",
            "b_refinery_l",
            "b_oil_field",
        )
        for ic in codes:
            inv = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                (code, ic),
            )
            if inv and float(inv.get("quantity") or 0) >= 1:
                return True
            b = await tx.fetchrow(
                "SELECT id FROM ng_buildings WHERE country_code=$1 AND building_code=$2 AND COALESCE(active,1)=1",
                (code, ic),
            )
            if b:
                return True
        invs = await tx.fetch(
            "SELECT item_code, quantity FROM ng_inventory WHERE country_code=$1 AND quantity>0",
            (code,),
        )
        for r in invs:
            if "refinery" in str(r["item_code"]).lower() and float(r.get("quantity") or 0) >= 1:
                return True
        return False

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
            if not await self._has_any_refinery(tx, code):
                raise GameError(
                    "برای تولید اورانیوم به پالایشگاه نیاز دارید "
                    "(کوچک / متوسط / بزرگ از فروشگاه زیرساخت)."
                )
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
        if await self.is_group(code):
            raise GameError("گروهک‌ها امکان عضویت یا درخواست NPT ندارند.")
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
            ("b_refinery_s", 1),
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
        un_atk = self.is_un_force(attacker, pid)
        if not un_atk:
            try:
                await self.legendary.assert_can_nuke(attacker)
                await self.legendary.assert_can_attack(attacker)
            except LegendaryError as e:
                raise GameError(str(e)) from e
            if await self.legendary.is_immune(defender):
                raise GameError("کشور هدف مصونیت دارد؛ حمله اتمی بی‌اثر است.")
        """Abstract nuclear strike: consumes 1 bomb, deals 25-35% max_hp damage."""
        meta = await self.db.fetchrow("SELECT * FROM world_meta WHERE id=1")
        if not un_atk and meta and int(meta.get("war_enabled") or 0) != 1:
            raise GameError("جنگ توسط سازمان ملل بسته شده است.")
        if not un_atk and meta and int(meta.get("nuclear_enabled") or 0) != 1:
            raise GameError("قابلیت هسته‌ای بازی توسط سازمان ملل غیرفعال است. از /panel آن را فعال کنید.")
        if await self.at_peace(attacker, defender):
            raise GameError("پیمان صلح فعال است؛ حمله ممکن نیست.")
        if attacker == defender:
            raise GameError("نامعتبر")
        test_atk = await self.is_test_active_for_country(attacker) or un_atk
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
                    if elapsed < await self.attack_cooldown_sec():
                        raise GameError(f"محدودیت حمله: {int(await self.attack_cooldown_sec() - elapsed)} ثانیه.")
                except GameError:
                    raise
                except Exception:
                    pass
            bomb = await tx.fetchrow(
                "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='item_atom_bomb'",
                (attacker,),
            )
            bq = float(bomb["quantity"]) if bomb else 0.0
            if bq < 1 and not un_atk:
                raise GameError("بمب اتم در انبار ندارید.")
            if bq >= 1:
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
                    "UPDATE ng_countries SET owner_player_id=NULL, is_destroyed=0, claimed_at=NULL, hp=1000 WHERE country_code=$1",
                    (defender,),
                )
                if prev:
                    until = (now + timedelta(seconds=DESTROY_WAIT_SEC)).isoformat()
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
            await self.alliances.on_country_destroyed(defender)
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
        """Always refresh country from live ownership so owner panel stays accurate."""
        rows = await self.db.fetch("SELECT * FROM ng_players ORDER BY player_id")
        enriched: list[dict] = []
        for raw in rows:
            p = dict(raw)
            pid = int(p["player_id"])
            try:
                live = await self.resolve_country_for_player(
                    pid, include_un_for_owner=(self.owner_id and pid == int(self.owner_id))
                )
            except Exception:
                live = p.get("country_code")
            # keep ng_players.country_code in sync with reality
            cached = p.get("country_code")
            if live and cached != live:
                try:
                    await self.db.execute(
                        "UPDATE ng_players SET country_code=$1 WHERE player_id=$2",
                        (live, pid),
                    )
                except Exception:
                    pass
                p["country_code"] = live
            elif not live and cached:
                try:
                    await self.db.execute(
                        "UPDATE ng_players SET country_code=NULL WHERE player_id=$1",
                        (pid,),
                    )
                except Exception:
                    pass
                p["country_code"] = None
            else:
                p["country_code"] = live or cached
            # human label
            if p.get("country_code"):
                try:
                    p["country_label"] = await self.country_label(p["country_code"])
                except Exception:
                    p["country_label"] = str(p["country_code"])
            else:
                p["country_label"] = "بدون کشور"
            enriched.append(p)
        # players with country first, then by id
        enriched.sort(
            key=lambda x: (0 if x.get("country_code") else 1, int(x["player_id"]))
        )
        total = len(enriched)
        page = max(0, int(page))
        start = page * self.PAGE_SIZE
        return enriched[start:start + self.PAGE_SIZE], total

    async def search_players(self, query: str, limit: int = 30) -> list[dict]:
        """Owner search by @username, display name, player id, or country."""
        q = (query or "").strip()
        if not q:
            return []
        if q.startswith("@"):
            q = q[1:].strip()
        if not q:
            return []
        # normalize persian digits
        trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        q_norm = q.translate(trans).strip()
        q_lower = q_norm.lower()

        rows = await self.db.fetch("SELECT * FROM ng_players ORDER BY player_id")
        hits: list[dict] = []
        for raw in rows:
            p = dict(raw)
            pid = int(p["player_id"])
            try:
                live = await self.resolve_country_for_player(
                    pid, include_un_for_owner=(self.owner_id and pid == int(self.owner_id))
                )
            except Exception:
                live = p.get("country_code")
            p["country_code"] = live
            if live:
                try:
                    p["country_label"] = await self.country_label(live)
                except Exception:
                    p["country_label"] = str(live)
                try:
                    p["country_name"] = await self.country_name_only(live)
                except Exception:
                    p["country_name"] = str(live)
            else:
                p["country_label"] = "بدون کشور"
                p["country_name"] = ""

            un = str(p.get("username") or "").lstrip("@").lower()
            dn = str(p.get("display_name") or "").lower()
            pid_s = str(pid)
            cc = str(p.get("country_code") or "").lower()
            cn = str(p.get("country_name") or "").lower()
            cl = str(p.get("country_label") or "").lower()

            matched = False
            if q_lower in un or un == q_lower:
                matched = True
            elif q_lower in dn:
                matched = True
            elif q_norm.isdigit() and (pid_s == q_norm or pid_s.endswith(q_norm)):
                matched = True
            elif q_lower in cc or q_lower in cn or q_lower in cl:
                matched = True
            if matched:
                hits.append(p)
            if len(hits) >= max(1, min(50, int(limit))):
                break
        return hits


    @staticmethod
    def format_tehran_time(ts) -> str:
        """Human-readable Tehran time relative to now."""
        if not ts or ts in ("—", "-", "None"):
            return "اطلاعاتی ثبت نشده"
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local = dt.astimezone(TEHRAN)
            now = datetime.now(TEHRAN)
            delta = now.date() - local.date()
            tstr = local.strftime("%H:%M")
            if delta.days == 0:
                return f"امروز، ساعت {tstr}"
            if delta.days == 1:
                return f"دیروز، ساعت {tstr}"
            if delta.days < 7:
                return f"{delta.days} روز پیش، ساعت {tstr}"
            if delta.days < 30:
                weeks = max(1, delta.days // 7)
                return f"{weeks} هفته پیش ({local.strftime('%Y/%m/%d')} ساعت {tstr})"
            return f"{local.strftime('%Y/%m/%d')} ساعت {tstr}"
        except Exception:
            return "اطلاعاتی ثبت نشده"

    async def npt_status_text(self, code: str | None, player_id: int | None = None) -> str:
        if not code:
            return "غیرعضو NPT"
        c = await self.db.fetchrow(
            "SELECT npt_member FROM ng_countries WHERE country_code=$1", (code,)
        )
        member = int((c or {}).get("npt_member") or 0) == 1
        pending = await self.db.fetchrow(
            """
            SELECT request_type, status, created_at FROM ng_npt_requests
            WHERE country_code=$1 AND status='pending'
            ORDER BY id DESC LIMIT 1
            """,
            (code,),
        )
        if pending:
            rt = pending.get("request_type") or "join"
            if rt in ("leave", "exit", "withdraw"):
                return "درخواست خروج از NPT — در انتظار تأیید"
            return "درخواست عضویت NPT — در انتظار تأیید"
        if member:
            return "عضو فعال NPT"
        # latest rejected
        rejected = await self.db.fetchrow(
            """
            SELECT request_type, status, created_at FROM ng_npt_requests
            WHERE country_code=$1 AND status IN ('rejected','denied')
            ORDER BY id DESC LIMIT 1
            """,
            (code,),
        )
        if rejected:
            return "غیرعضو NPT (آخرین درخواست رد شده)"
        return "غیرعضو NPT"

    async def player_admin_card(self, target_id: int) -> str:
        target_id = int(target_id)
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (target_id,))
        if not p:
            raise GameError("بازیکن یافت نشد")
        # live ownership resolution
        code = await self.resolve_country_for_player(target_id)
        if not code:
            code = p.get("country_code")
        c = None
        if code:
            c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
            # verify ownership match when possible
            if c and c.get("owner_player_id") and int(c["owner_player_id"]) != target_id and code != UN_CODE:
                # prefer actual owned country
                owned = await self.db.fetchrow(
                    "SELECT * FROM ng_countries WHERE owner_player_id=$1 AND country_code<>$2",
                    (target_id, UN_CODE),
                )
                if owned:
                    c = owned
                    code = owned["country_code"]

        banned = int(p.get("is_banned") or 0) == 1
        ban = "مسدود 🚫" if banned else "آزاد ✅"
        ban_reason = (p.get("ban_reason") or "").strip() or "—"
        if banned and p.get("banned_until"):
            ban += f" (تا {self.format_tehran_time(p.get('banned_until'))})"

        country_name = "بدون کشور"
        treas = 0
        hp_line = "❤️ HP کشور: —"
        if c:
            country_name = f"{c.get('flag') or ''} {c.get('name_fa') or code}".strip()
            treas = float(c.get("treasury") or 0)
            hp = float(c.get("hp") or 0)
            max_hp = float(c.get("max_hp") or 1000) or 1000
            dbl = " ×۲" if int(c.get("double_hp") or 0) else ""
            hp_line = f"❤️ HP کشور: {int(hp)} / {int(max_hp)}{dbl}"

        npt = await self.npt_status_text(code, target_id)

        # military equipment count (combat categories)
        eq_count = 0
        if code:
            inv = await self.db.fetch(
                "SELECT item_code, quantity FROM ng_inventory WHERE country_code=$1 AND quantity>0",
                (code,),
            )
            combat_cats = {"ground", "air", "sea", "missile", "defense", "specialist"}
            for r in inv:
                meta = self._cat.get(r["item_code"]) or {}
                if meta.get("category") in combat_cats:
                    eq_count += int(float(r["quantity"]))

        # alliances
        ally_n = 0
        ally_names = []
        try:
            mems = await self.db.fetch(
                "SELECT alliance_id FROM ng_alliance_members WHERE player_id=$1 OR country_code=$2",
                (target_id, code or ""),
            )
            ids = {int(m["alliance_id"]) for m in mems}
            ally_n = len(ids)
            for aid in list(ids)[:3]:
                a = await self.db.fetchrow(
                    "SELECT name, status FROM ng_alliances WHERE id=$1", (aid,)
                )
                if a:
                    ally_names.append(f"{a['name']} ({a.get('status') or '—'})")
        except Exception:
            pass
        ally_line = f"{ally_n}"
        if ally_names:
            ally_line += " — " + "، ".join(ally_names)

        # active wars approximation: recent attacks involving country in last 24h
        wars = 0
        if code:
            try:
                rows = await self.db.fetch(
                    "SELECT id, summary, created_at FROM ng_activity WHERE kind='attack' ORDER BY id DESC LIMIT 50"
                )
                now = datetime.now(timezone.utc)
                for r in rows:
                    sm = r.get("summary") or ""
                    if code not in sm and (c and (c.get("name_fa") or "") not in sm):
                        continue
                    try:
                        dt = datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if (now - dt).total_seconds() <= 86400:
                            wars += 1
                    except Exception:
                        pass
            except Exception:
                wars = 0

        last_seen = self.format_tehran_time(p.get("last_seen_at"))
        act = await self.db.fetchrow(
            "SELECT last_start_at, start_count FROM ng_player_activity WHERE player_id=$1",
            (target_id,),
        )
        last_start = self.format_tehran_time((act or {}).get("last_start_at"))
        start_count = int((act or {}).get("start_count") or 0)

        lines = [
            "👤 مدیریت کاربر",
            f"شناسه: `{target_id}`",
            f"نام کاربری: @{p.get('username') or '—'}",
            f"نام نمایشی: {p.get('display_name') or '—'}",
            f"کشور: {country_name}",
            f"وضعیت حساب: {ban}",
            f"دلیل مسدودیت: {ban_reason}",
            f"💰 موجودی: {int(treas):,}",
            f"NPT: {npt}",
            f"🪖 تجهیزات نظامی: {eq_count}",
            f"⚔️ درگیری‌های ۲۴س اخیر: {wars}",
            f"🤝 اتحادها: {ally_line}",
            hp_line,
            f"آخرین فعالیت: {last_seen}",
            f"آخرین /start: {last_start}",
        ]
        if start_count:
            lines.append(f"تعداد /start: {start_count}")
        try:
            lines.append("")
            lines.append(await self.legendary.admin_player_legendary_block(target_id))
        except Exception:
            log.exception("admin legendary block")
        return chr(10).join(lines)

    async def list_owned_countries_hp(self, page: int = 0, page_size: int = 12) -> tuple[str, int]:
        """Owner view: HP of all player-owned countries, sorted high→low."""
        rows = await self.db.fetch(
            """
            SELECT country_code, name_fa, flag, hp, max_hp, double_hp, owner_player_id
            FROM ng_countries
            WHERE owner_player_id IS NOT NULL AND country_code<>$1 AND COALESCE(is_destroyed,0)=0
            ORDER BY hp DESC, name_fa ASC
            """,
            (UN_CODE,),
        )
        total = len(rows)
        page = max(0, int(page))
        start = page * page_size
        chunk = rows[start:start + page_size]
        lines = ["❤️ وضعیت HP کشورها", f"تعداد: {total}", ""]
        if not chunk:
            lines.append("کشوری با بازیکن یافت نشد.")
        for r in chunk:
            flag = r.get("flag") or ""
            name = r.get("name_fa") or r["country_code"]
            hp = int(float(r.get("hp") or 0))
            mx = int(float(r.get("max_hp") or 1000) or 1000)
            dbl = " ×۲" if int(r.get("double_hp") or 0) else ""
            lines.append(f"{flag} {name} — HP: {hp} / {mx}{dbl}")
        pages = max(1, (total + page_size - 1) // page_size)
        lines.append("")
        lines.append(f"صفحه {page + 1} از {pages}")
        return chr(10).join(lines), total


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


    async def admin_set_hp(self, actor: int, target_player_id: int, hp: float) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        code = await self.resolve_country_for_player(int(target_player_id))
        if not code:
            raise GameError("این بازیکن کشور فعالی ندارد")
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
        )
        if not c:
            raise GameError("کشور یافت نشد")
        max_hp = float(c.get("max_hp") or 1000)
        if max_hp <= 0:
            max_hp = 1000.0
        hp = float(hp)
        if hp < 0:
            raise GameError("HP نمی‌تواند منفی باشد")
        if hp > max_hp * 2:
            # soft cap: allow up to 2x max for owner events, but warn
            raise GameError(f"حداکثر مجاز برای تنظیم: {int(max_hp * 2)}")
        await self.db.execute(
            "UPDATE ng_countries SET hp=$1, is_destroyed=0 WHERE country_code=$2",
            (hp, code),
        )
        await self.admin_log(actor, "set_hp", f"{code}={hp}/{max_hp}")
        label = await self.country_label(code)
        return f"✅ HP «{label}» روی {int(hp)} تنظیم شد (حداکثر پایه: {int(max_hp)})."


    async def admin_set_npt(self, actor: int, code: str, member: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        if member and await self.is_group(code):
            raise GameError("گروهک‌ها عضو NPT نمی‌شوند")
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
        res = await self.adjust_treasury(code, -amount, actor=actor, reason=reason)
        return f"✅ {int(amount):,} از {res['name_fa']} کسر شد. موجودی جدید: {int(res['after']):,}"

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


    # ---------- alliances (active peace) ----------

    async def set_double_hp(self, actor: int, code: str, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("فقط مالک")
        # ensure column exists (SQLite/Postgres)
        try:
            await self.db.execute(
                "ALTER TABLE ng_countries ADD COLUMN double_hp INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
        if not c:
            raise GameError("کشور یافت نشد")
        try:
            cur = int(c.get("double_hp") or 0) == 1
        except Exception:
            cur = False
        if enabled and cur:
            return "جان ۲ برابر از قبل فعال است."
        if not enabled and not cur:
            return "جان ۲ برابر از قبل غیرفعال است."
        hp = float(c["hp"])
        mx = float(c["max_hp"])
        if enabled:
            new_mx = mx * 2
            new_hp = min(hp * 2, new_mx)
            flag = 1
            msg = f"✅ جان ۲ برابر برای {c['name_fa']} فعال شد.\nسلامت: {int(new_hp)}/{int(new_mx)} ×۲"
        else:
            new_mx = max(1.0, mx / 2.0)
            new_hp = min(hp / 2.0 if cur else hp, new_mx)
            # when disabling, scale current hp back proportionally
            new_hp = min(hp / 2.0, new_mx)
            flag = 0
            msg = f"✅ جان ۲ برابر برای {c['name_fa']} غیرفعال شد.\nسلامت: {int(new_hp)}/{int(new_mx)}"
        await self.db.execute(
            "UPDATE ng_countries SET hp=$1, max_hp=$2, double_hp=$3 WHERE country_code=$4",
            (new_hp, new_mx, flag, code),
        )
        await self.admin_log(actor, "double_hp", f"{code}={flag}")
        return msg

    async def apply_defense_wear(self, code: str) -> str | None:
        """After being attacked, accumulate hits; every 3–5 hits destroy 1 defense unit."""
        import random
        row = await self.db.fetchrow(
            "SELECT * FROM ng_defense_hits WHERE country_code=$1", (code,)
        )
        if not row:
            break_at = random.randint(3, 5)
            try:
                await self.db.execute(
                    "INSERT INTO ng_defense_hits (country_code, hits, break_at) VALUES ($1,$2,$3)",
                    (code, 1, break_at),
                )
            except Exception:
                pass
            return None
        hits = int(row["hits"]) + 1
        break_at = int(row["break_at"] or 3)
        if hits < break_at:
            await self.db.execute(
                "UPDATE ng_defense_hits SET hits=$1 WHERE country_code=$2",
                (hits, code),
            )
            return None
        inv = await self.db.fetch(
            "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
        )
        defense = []
        for r in inv:
            meta = self._cat.get(r["item_code"], {})
            if meta.get("category") == "defense":
                defense.append(r)
        broken_name = None
        if defense:
            defense.sort(key=lambda r: -float(r["quantity"]))
            victim = defense[0]
            meta = self._cat.get(victim["item_code"], {})
            broken_name = meta.get("name_fa") or victim["item_code"]
            left = float(victim["quantity"]) - 1
            if left <= 0:
                await self.db.execute(
                    "DELETE FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
                    (code, victim["item_code"]),
                )
            else:
                await self.db.execute(
                    "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
                    (left, code, victim["item_code"]),
                )
        new_break = random.randint(3, 5)
        await self.db.execute(
            "UPDATE ng_defense_hits SET hits=0, break_at=$1 WHERE country_code=$2",
            (new_break, code),
        )
        if broken_name:
            return f"پدافند «{broken_name}» پس از فشار حملات از بین رفت و باید دوباره خریداری شود."
        return None

    async def list_alliances(self) -> list[dict]:
        return await self.alliances.list_active()

    async def alliance_detail_text(self, peace_id: int) -> str:
        p = await self.db.fetchrow("SELECT * FROM ng_peace WHERE id=$1", (peace_id,))
        if not p:
            raise GameError("اتحاد یافت نشد")
        a = await self.country_label(p["country_a"])
        b = await self.country_label(p["country_b"])
        return (
            f"🤝 جزئیات اتحاد #{p['id']}\n\n"
            f"کشور اول: {a}\n"
            f"کشور دوم: {b}\n"
            f"وضعیت: {p['status']}\n"
            f"نوع: پیمان صلح / اتحاد موقت\n"
            f"مدت توافق: {p.get('duration_hours')} ساعت\n"
            f"شروع: {p.get('started_at') or '—'}\n"
            f"پایان: {p.get('ends_at') or '—'}\n"
            f"درخواست‌دهنده: {p.get('requested_by') or '—'}"
        )

    async def alliances_summary_text(self) -> str:
        rows = await self.list_alliances()
        lines = [f"🤝 مدیریت اتحادها", f"تعداد اتحاد فعال: {len(rows)}", ""]
        for p in rows[:40]:
            a = await self.country_name_only(p["country_a"])
            b = await self.country_name_only(p["country_b"])
            lines.append(f"#{p['id']} {a} ↔ {b}")
        if not rows:
            lines.append("اتحاد فعالی ثبت نشده است.")
        return "\n".join(lines)

    async def get_owner_away(self) -> bool:
        v = await self.get_setting("owner_away", "0")
        return str(v) in ("1", "true", "yes", "on")

    async def set_owner_away(self, actor: int, enabled: bool) -> str:
        if not self.is_owner(actor):
            raise GameError("مجاز نیستید")
        val = "1" if enabled else "0"
        row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", ("owner_away",))
        if row:
            await self.db.execute(
                "UPDATE ng_bot_settings SET value=$1 WHERE key=$2", (val, "owner_away")
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", ("owner_away", val)
            )
        await self.admin_log(actor, "owner_away", val)
        if enabled:
            return "🔕 حالت «در دسترس نیستم» فعال شد. بیانیه‌ها خودکار منتشر می‌شوند."
        return "🔔 حالت «در دسترس نیستم» غیرفعال شد. بیانیه‌ها نیاز به تأیید دارند."

    def _make_ref_code(self, pid: int) -> str:
        return f"WW{int(pid)}"

    async def ensure_referral_row(self, pid: int) -> dict:
        row = await self.db.fetchrow("SELECT * FROM ng_referrals WHERE player_id=$1", (pid,))
        if row:
            return row
        code = self._make_ref_code(pid)
        await self.db.execute(
            "INSERT INTO ng_referrals (player_id, referral_code) VALUES ($1,$2)",
            (pid, code),
        )
        return await self.db.fetchrow("SELECT * FROM ng_referrals WHERE player_id=$1", (pid,))

    async def referral_panel_text(self, pid: int, bot_username: str | None = None) -> str:
        row = await self.ensure_referral_row(pid)
        code = row["referral_code"]
        kids = await self.db.fetch(
            "SELECT player_id FROM ng_referrals WHERE referrer_id=$1", (pid,)
        )
        names = []
        for k in kids[:30]:
            p = await self.db.fetchrow(
                "SELECT username, display_name FROM ng_players WHERE player_id=$1",
                (k["player_id"],),
            )
            names.append((p or {}).get("display_name") or (p or {}).get("username") or str(k["player_id"]))
        referrer_txt = "بدون دعوت‌کننده"
        if row.get("referrer_id"):
            rp = await self.db.fetchrow(
                "SELECT username, display_name FROM ng_players WHERE player_id=$1",
                (int(row["referrer_id"]),),
            )
            referrer_txt = (rp or {}).get("display_name") or (rp or {}).get("username") or str(row["referrer_id"])
        link_line = f"لینک: https://ble.ir/{bot_username}?start={code}" if bot_username else ""
        lines = [
            "هی! می‌دونستی می‌تونی با دعوت دوستات هم خودت و هم دوستت پول بگیرین؟ 😍",
            "",
            f"کد دعوت شما: {code}",
        ]
        if link_line:
            lines.append(link_line)
        lines += [
            "",
            f"تعداد زیرمجموعه‌ها: {len(kids)} نفر",
            f"شما زیرمجموعه چه کسی هستید؟ {referrer_txt}",
            "",
            "افرادی که دعوت کرده‌اید:",
        ]
        if names:
            lines.extend(f"• {n}" for n in names)
        else:
            lines.append("هنوز کسی با کد شما وارد نشده.")
        return "\n".join(lines)

    async def apply_referral_code(self, pid: int, code: str) -> str:
        code = (code or "").strip().upper()
        if not code:
            raise GameError("کد خالی است")
        me = await self.ensure_referral_row(pid)
        if me.get("referrer_id"):
            raise GameError("شما قبلاً دعوت‌کننده ثبت کرده‌اید.")
        if str(me.get("referral_code") or "").upper() == code:
            raise GameError("نمی‌توانید کد خودتان را وارد کنید.")
        all_r = await self.db.fetch("SELECT * FROM ng_referrals")
        owner_row = next((r for r in all_r if str(r.get("referral_code") or "").upper() == code), None)
        if not owner_row:
            raise GameError("کد دعوت نامعتبر است.")
        rid = int(owner_row["player_id"])
        if rid == int(pid):
            raise GameError("نمی‌توانید کد خودتان را وارد کنید.")
        rp = await self.db.fetchrow("SELECT player_id FROM ng_players WHERE player_id=$1", (rid,))
        if not rp:
            raise GameError("دعوت‌کننده معتبر نیست.")
        my_code = await self.player_country(pid)
        ref_code_c = await self.player_country(rid)
        if not my_code:
            raise GameError("ابتدا کشور انتخاب کنید، بعد کد دعوت را وارد کنید.")
        if not ref_code_c:
            raise GameError("دعوت‌کننده هنوز کشور ندارد؛ بعداً تلاش کنید.")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            cur = await tx.fetchrow("SELECT * FROM ng_referrals WHERE player_id=$1", (pid,))
            if cur and cur.get("referrer_id"):
                raise GameError("قبلاً ثبت شده")
            await tx.execute(
                "UPDATE ng_referrals SET referrer_id=$1, bound_at=$2, invitee_reward=$3, referrer_reward=$4 WHERE player_id=$5",
                (rid, now, self.REF_INVITEE_REWARD, self.REF_REFERRER_REWARD, pid),
            )
            me_c = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (my_code,))
            ref_c = await tx.fetchrow("SELECT treasury FROM ng_countries WHERE country_code=$1", (ref_code_c,))
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(me_c["treasury"]) + self.REF_INVITEE_REWARD, my_code),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(ref_c["treasury"]) + self.REF_REFERRER_REWARD, ref_code_c),
            )
        try:
            await self.ledger_write("referral_invitee", self.REF_INVITEE_REWARD, pid, to_c=my_code, reason=code)
            await self.ledger_write("referral_referrer", self.REF_REFERRER_REWARD, rid, to_c=ref_code_c, reason=code)
        except Exception:
            pass
        await self.log_activity("referral", f"کد {code} توسط {pid}", my_code, pid)
        try:
            await self.log_activity(
                "dm_notice",
                f"🎁 یک نفر با کد دعوت شما وارد شد و {int(self.REF_REFERRER_REWARD):,} به خزانه‌تان اضافه شد.",
                player_id=rid,
            )
        except Exception:
            pass
        return (
            f"✅ کد دعوت ثبت شد.\n"
            f"پاداش شما: {int(self.REF_INVITEE_REWARD):,}\n"
            f"پاداش دعوت‌کننده: {int(self.REF_REFERRER_REWARD):,}"
        )

    async def referral_stats_text(self) -> str:
        rows = await self.db.fetch("SELECT * FROM ng_referrals WHERE referrer_id IS NOT NULL")
        total = len(rows)
        paid = sum(float(r.get("invitee_reward") or 0) + float(r.get("referrer_reward") or 0) for r in rows)
        counts: dict = {}
        for r in rows:
            rid = int(r["referrer_id"])
            counts[rid] = counts.get(rid, 0) + 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:10]
        lines = [
            "📊 آمار دعوت",
            f"دعوت‌های موفق: {total}",
            f"مجموع پاداش پرداخت‌شده: {int(paid):,}",
            "",
            "برترین دعوت‌کنندگان:",
        ]
        if not top:
            lines.append("—")
        for rid, n in top:
            p = await self.db.fetchrow(
                "SELECT username, display_name FROM ng_players WHERE player_id=$1", (rid,)
            )
            name = (p or {}).get("display_name") or (p or {}).get("username") or str(rid)
            lines.append(f"• {name}: {n} نفر")
        return "\n".join(lines)

