"""Financial support (حمایت مالی) system for WORLD WAR."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")

DEFAULT_INTRO = (
    "می‌توانی به‌صورت دلخواه از توسعه WORLD WAR حمایت کنی 💎\n\n"
    "حمایت کاملاً اختیاری است و استفاده از بازی هیچ نیازی به پرداخت ندارد."
)
DEFAULT_INSTRUCTIONS = (
    "مراحل داخل ربات را دنبال کن. از ثبت درخواست الکی خودداری کن."
)
DEFAULT_CARD = "—"
DEFAULT_CARD_NAME = "—"

METHOD_GIFT = "gift"
METHOD_CARD = "card"
METHOD_FA = {
    METHOD_GIFT: "پاکت هدیه",
    METHOD_CARD: "کارت‌به‌کارت",
}

MAX_REQUESTS_PER_DAY = 3
COOLDOWN_HOURS = 3


class DonationError(Exception):
    pass


class DonationService:
    def __init__(self, game: Any):
        self.g = game
        self.db = game.db

    async def ensure_tables(self) -> None:
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS ng_donations (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                amount REAL NOT NULL,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER,
                show_name INTEGER NOT NULL DEFAULT 1,
                method TEXT DEFAULT 'card'
            )
            """
        )
        for sql in (
            "ALTER TABLE ng_donations ADD COLUMN method TEXT DEFAULT 'card'",
            "ALTER TABLE ng_donations ADD COLUMN show_name INTEGER NOT NULL DEFAULT 1",
            """CREATE TABLE IF NOT EXISTS ng_donation_limits (
                player_id INTEGER PRIMARY KEY,
                cooldown_until TEXT,
                day_key TEXT,
                day_count INTEGER NOT NULL DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS idx_ng_donations_status ON ng_donations(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_ng_donations_player_day ON ng_donations(player_id, created_at)",
        ):
            try:
                await self.db.execute(sql)
            except Exception:
                pass
        defaults = {
            "donation_card": DEFAULT_CARD,
            "donation_card_name": DEFAULT_CARD_NAME,
            "donation_intro": DEFAULT_INTRO,
            "donation_instructions": DEFAULT_INSTRUCTIONS,
            "donations_total": "0",
        }
        for k, v in defaults.items():
            row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", (k,))
            if not row:
                try:
                    await self.db.execute(
                        "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", (k, v)
                    )
                except Exception:
                    pass

    async def _get(self, key: str, default: str = "") -> str:
        return await self.g.get_setting(key, default)

    async def _set_raw(self, key: str, value: str) -> None:
        row = await self.db.fetchrow("SELECT key FROM ng_bot_settings WHERE key=$1", (key,))
        if row:
            await self.db.execute(
                "UPDATE ng_bot_settings SET value=$1 WHERE key=$2", (value, key)
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_bot_settings (key, value) VALUES ($1,$2)", (key, value)
            )

    async def config(self) -> dict:
        return {
            "card": await self._get("donation_card", DEFAULT_CARD),
            "card_name": await self._get("donation_card_name", DEFAULT_CARD_NAME),
            "intro": await self._get("donation_intro", DEFAULT_INTRO),
            "instructions": await self._get("donation_instructions", DEFAULT_INSTRUCTIONS),
            "total": float(await self._get("donations_total", "0") or 0),
        }

    async def intro_text(self) -> str:
        """Short confirmation prompt — full stats stay in owner panel."""
        return (
            "💎 حمایت مالی WORLD WAR\n\n"
            "آیا واقعاً از حمایت کردن مطمئنی؟\n"
            "از دادن درخواست الکی خودداری کنید.\n\n"
            "حمایت کاملاً اختیاری است."
        )

    async def stats(self) -> dict:
        total_setting = float(await self._get("donations_total", "0") or 0)
        pending = await self.db.fetchrow(
            "SELECT COUNT(*) AS c FROM ng_donations WHERE status='pending'"
        )
        approved = await self.db.fetchrow(
            "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM ng_donations WHERE status='approved'"
        )
        rejected = await self.db.fetchrow(
            "SELECT COUNT(*) AS c FROM ng_donations WHERE status='rejected'"
        )
        db_sum = float((approved or {}).get("s") or 0)
        return {
            "total_approved": max(total_setting, db_sum) if total_setting else db_sum,
            "count_approved": int((approved or {}).get("c") or 0),
            "count_pending": int((pending or {}).get("c") or 0),
            "count_rejected": int((rejected or {}).get("c") or 0),
        }

    def _tehran_day_key(self) -> str:
        return datetime.now(TEHRAN).date().isoformat()

    async def assert_can_request(self, player_id: int) -> None:
        """Block if under cooldown or already used daily quota."""
        pid = int(player_id)
        now = datetime.now(timezone.utc)
        row = await self.db.fetchrow(
            "SELECT * FROM ng_donation_limits WHERE player_id=$1", (pid,)
        )
        if row and row.get("cooldown_until"):
            try:
                until = datetime.fromisoformat(str(row["cooldown_until"]).replace("Z", "+00:00"))
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                if until > now:
                    left = int((until - now).total_seconds())
                    h, m = left // 3600, (left % 3600) // 60
                    raise DonationError(
                        f"به‌خاطر درخواست‌های زیاد، تا {h} ساعت و {m} دقیقه "
                        "نمی‌توانی درخواست حمایت جدید ثبت کنی."
                    )
            except DonationError:
                raise
            except Exception:
                pass

        day = self._tehran_day_key()
        # count requests created today (Tehran calendar via created_at approximate ISO)
        # Also use limit table day_count when same day
        count = 0
        try:
            rows = await self.db.fetch(
                "SELECT created_at FROM ng_donations WHERE player_id=$1", (pid,)
            )
            for r in rows:
                ca = str(r.get("created_at") or "")
                try:
                    dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt.astimezone(TEHRAN).date().isoformat() == day:
                        count += 1
                except Exception:
                    if ca.startswith(day):
                        count += 1
        except Exception:
            log.exception("count donations today")

        if count >= MAX_REQUESTS_PER_DAY:
            until = (now + timedelta(hours=COOLDOWN_HOURS)).isoformat()
            try:
                if row:
                    await self.db.execute(
                        "UPDATE ng_donation_limits SET cooldown_until=$1, day_key=$2, day_count=$3 WHERE player_id=$4",
                        (until, day, count, pid),
                    )
                else:
                    await self.db.execute(
                        "INSERT INTO ng_donation_limits (player_id, cooldown_until, day_key, day_count) VALUES ($1,$2,$3,$4)",
                        (pid, until, day, count),
                    )
            except Exception:
                log.exception("set donation cooldown")
            raise DonationError(
                f"امروز بیش از {MAX_REQUESTS_PER_DAY} درخواست حمایت ثبت کرده‌ای.\n"
                f"تا {COOLDOWN_HOURS} ساعت از ثبت درخواست جدید محرومی."
            )

    async def submit(
        self,
        player_id: int,
        amount: float,
        *,
        username: str | None = None,
        display_name: str | None = None,
        note: str | None = None,
        show_name: bool = True,
        method: str = METHOD_CARD,
    ) -> dict:
        await self.assert_can_request(player_id)
        amount = float(amount)
        if amount < 1000:
            raise DonationError("حداقل مبلغ حمایت ۱٬۰۰۰ تومان است.")
        if amount > 50_000_000_000:
            raise DonationError("مبلغ بیش از حد بزرگ است.")
        method = method if method in (METHOD_GIFT, METHOD_CARD) else METHOD_CARD
        now = datetime.now(timezone.utc).isoformat()
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_donations")
        did = int(nid["id"])
        await self.db.execute(
            """
            INSERT INTO ng_donations
            (id, player_id, username, display_name, amount, note, status, created_at, show_name, method)
            VALUES ($1,$2,$3,$4,$5,$6,'pending',$7,$8,$9)
            """,
            (
                did,
                int(player_id),
                (username or "")[:80],
                (display_name or "")[:120],
                amount,
                (note or "")[:500],
                now,
                1 if show_name else 0,
                method,
            ),
        )
        # bump day counter
        day = self._tehran_day_key()
        try:
            lim = await self.db.fetchrow(
                "SELECT * FROM ng_donation_limits WHERE player_id=$1", (int(player_id),)
            )
            if lim and lim.get("day_key") == day:
                await self.db.execute(
                    "UPDATE ng_donation_limits SET day_count=COALESCE(day_count,0)+1 WHERE player_id=$1",
                    (int(player_id),),
                )
            else:
                await self.db.execute(
                    """
                    INSERT INTO ng_donation_limits (player_id, cooldown_until, day_key, day_count)
                    VALUES ($1,NULL,$2,1)
                    ON CONFLICT(player_id) DO UPDATE SET day_key=$2, day_count=1, cooldown_until=NULL
                    """,
                    (int(player_id), day),
                )
        except Exception:
            log.exception("donation day counter")

        uname = (username or "").lstrip("@")
        method_fa = METHOD_FA.get(method, method)
        owner_body = (
            f"💎 درخواست حمایت جدید #{did}\n\n"
            f"روش: {method_fa}\n"
            f"کاربر: {display_name or username or player_id}\n"
            f"آیدی: {player_id}\n"
            f"یوزرنیم: @{uname if uname else '—'}\n"
            f"مبلغ: {int(amount):,} تومان\n"
            f"نمایش نام: {'بله' if show_name else 'خیر'}\n\n"
            f"{'ادعا کرده در پیوی برای شما پاکت هدیه زده است.' if method == METHOD_GIFT else 'ادعا کرده کارت‌به‌کارت واریز کرده است.'}\n"
            "آیا تأیید می‌کنی؟"
        )
        try:
            await self.g._owner_inbox(
                "donation",
                did,
                f"حمایت مالی — #{did}",
                owner_body,
            )
        except Exception:
            log.exception("donation owner inbox")
        return await self.get(did)

    async def get(self, did: int) -> Optional[dict]:
        return await self.db.fetchrow("SELECT * FROM ng_donations WHERE id=$1", (int(did),))

    async def list_by_status(self, status: str, limit: int = 30) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_donations WHERE status=$1 ORDER BY id DESC LIMIT $2",
            (status, int(limit)),
        )

    async def review(self, did: int, actor: int, approve: bool) -> dict:
        if not self.g.is_owner(actor):
            raise DonationError("فقط مالک می‌تواند درخواست را بررسی کند.")
        async with self.db.transaction() as tx:
            row = await tx.fetchrow("SELECT * FROM ng_donations WHERE id=$1", (int(did),))
            if not row:
                raise DonationError("درخواست یافت نشد.")
            if row["status"] != "pending":
                raise DonationError("این درخواست قبلاً بررسی شده است.")
            now = datetime.now(timezone.utc).isoformat()
            status = "approved" if approve else "rejected"
            await tx.execute(
                """
                UPDATE ng_donations
                SET status=$1, reviewed_at=$2, reviewed_by=$3
                WHERE id=$4 AND status='pending'
                """,
                (status, now, int(actor), int(did)),
            )
            check = await tx.fetchrow("SELECT * FROM ng_donations WHERE id=$1", (int(did),))
            if not check or check["status"] != status:
                raise DonationError("خطا در ثبت نتیجه بررسی.")
            if approve:
                cur = float(await self._get("donations_total", "0") or 0)
                # prefer DB sum of approved for integrity
                try:
                    srow = await tx.fetchrow(
                        "SELECT COALESCE(SUM(amount),0) AS s FROM ng_donations WHERE status='approved'"
                    )
                    new_total = float((srow or {}).get("s") or 0)
                except Exception:
                    new_total = cur + float(row["amount"] or 0)
                exists = await tx.fetchrow(
                    "SELECT key FROM ng_bot_settings WHERE key='donations_total'"
                )
                if exists:
                    await tx.execute(
                        "UPDATE ng_bot_settings SET value=$1 WHERE key='donations_total'",
                        (str(int(new_total)),),
                    )
                else:
                    await tx.execute(
                        "INSERT INTO ng_bot_settings (key, value) VALUES ('donations_total',$1)",
                        (str(int(new_total)),),
                    )
        return await self.get(did)

    async def set_total_manual(self, actor: int, amount: float) -> str:
        if not self.g.is_owner(actor):
            raise DonationError("فقط مالک")
        await self._set_raw("donations_total", str(int(amount)))
        try:
            await self.g.admin_log(actor, "donations_total", str(int(amount)))
        except Exception:
            pass
        return f"✅ مجموع حمایت‌های نمایشی روی {int(amount):,} تومان تنظیم شد."

    async def set_field(self, actor: int, field: str, value: str) -> str:
        if not self.g.is_owner(actor):
            raise DonationError("فقط مالک")
        mapping = {
            "card": "donation_card",
            "card_name": "donation_card_name",
            "intro": "donation_intro",
            "instructions": "donation_instructions",
        }
        key = mapping.get(field)
        if not key:
            raise DonationError("فیلد نامعتبر")
        await self._set_raw(key, str(value)[:2000])
        try:
            await self.g.admin_log(actor, "donation_set", key)
        except Exception:
            pass
        return "✅ ذخیره شد."

    def announcement_text(self, donation: dict) -> str:
        amount = int(float(donation.get("amount") or 0))
        show = int(donation.get("show_name") or 0) == 1
        name = (donation.get("display_name") or donation.get("username") or "").strip()
        uname = (donation.get("username") or "").lstrip("@")
        method = METHOD_FA.get(str(donation.get("method") or ""), "حمایت")
        if show and name:
            who = name
            if uname:
                who = f"{name} (@{uname})"
        elif show and uname:
            who = f"@{uname}"
        else:
            who = "یک کاربر"
        return (
            f"💎 حمایت مالی جدید\n\n"
            f"{who} به مبلغ {amount:,} تومان حمایت کرد.\n"
            f"روش: {method}\n\n"
            "از حمایت شما سپاسگزاریم 🙏"
        )

    def method_label(self, method: str) -> str:
        return METHOD_FA.get(method, method or "—")

    def owner_review_text(self, donation: dict) -> str:
        uname = (donation.get("username") or "").lstrip("@")
        method = self.method_label(str(donation.get("method") or ""))
        claim = (
            "این شخص ادعا کرده در پیوی برای شما پاکت هدیه زده است."
            if str(donation.get("method")) == METHOD_GIFT
            else "این شخص ادعا کرده کارت‌به‌کارت واریز کرده است."
        )
        return (
            f"💎 درخواست حمایت #{donation.get('id')}\n\n"
            f"{claim}\n"
            f"یوزرنیم: @{uname if uname else '—'}\n"
            f"آیدی: {donation.get('player_id')}\n"
            f"نام: {donation.get('display_name') or '—'}\n"
            f"مبلغ: {int(float(donation.get('amount') or 0)):,} تومان\n"
            f"روش: {method}\n"
            f"نمایش نام: {'بله' if int(donation.get('show_name') or 0) else 'خیر'}\n\n"
            "آیا تأیید می‌کنی؟"
        )
