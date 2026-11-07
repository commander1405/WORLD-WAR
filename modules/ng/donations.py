"""Financial support (حمایت مالی) system for WORLD WAR."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_INTRO = (
    "می‌توانی به‌صورت دلخواه از توسعه WORLD WAR حمایت کنی 💎\n\n"
    "حمایت کاملاً اختیاری است و استفاده از بازی هیچ نیازی به پرداخت ندارد."
)
DEFAULT_INSTRUCTIONS = (
    "۱) مبلغ دلخواه را به شماره کارت واریز کن.\n"
    "۲) دکمه «ثبت درخواست حمایت» را بزن و مبلغ را بنویس.\n"
    "۳) پس از بررسی مالک، نتیجه بهت اعلام می‌شود."
)
DEFAULT_CARD = "—"
DEFAULT_CARD_NAME = "—"


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
                show_name INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        try:
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ng_donations_status ON ng_donations(status, created_at)"
            )
        except Exception:
            pass
        # seed settings if missing
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
        """Write setting without owner short-text validation."""
        value = (value or "").strip()
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
        cfg = await self.config()
        stats = await self.stats()
        lines = [
            "💎 حمایت مالی WORLD WAR",
            "",
            cfg["intro"],
            "",
            "━━━━━━━━━━━━━━",
            f"💳 شماره کارت:\n`{cfg['card']}`",
            f"👤 صاحب کارت: {cfg['card_name']}",
            "",
            cfg["instructions"],
            "",
            "━━━━━━━━━━━━━━",
            f"📊 مجموع حمایت‌های تأییدشده: {int(stats['total_approved']):,} تومان",
            f"✅ تعداد تأییدشده: {stats['count_approved']}",
            f"⏳ در انتظار: {stats['count_pending']}",
        ]
        return "\n".join(lines)

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
        # Prefer manual total if set; otherwise sum of approved
        sum_approved = float((approved or {}).get("s") or 0)
        # Manual total is the public figure (can be adjusted by owner)
        return {
            "total_approved": total_setting if total_setting > 0 else sum_approved,
            "sum_approved_raw": sum_approved,
            "count_approved": int((approved or {}).get("c") or 0),
            "count_pending": int((pending or {}).get("c") or 0),
            "count_rejected": int((rejected or {}).get("c") or 0),
        }

    async def submit(
        self,
        player_id: int,
        amount: float,
        *,
        username: str | None = None,
        display_name: str | None = None,
        note: str | None = None,
        show_name: bool = True,
    ) -> dict:
        amount = float(amount)
        if amount < 1000:
            raise DonationError("حداقل مبلغ حمایت ۱٬۰۰۰ تومان است.")
        if amount > 50_000_000_000:
            raise DonationError("مبلغ بیش از حد بزرگ است.")
        now = datetime.now(timezone.utc).isoformat()
        nid = await self.db.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_donations")
        did = int(nid["id"])
        await self.db.execute(
            """
            INSERT INTO ng_donations
            (id, player_id, username, display_name, amount, note, status, created_at, show_name)
            VALUES ($1,$2,$3,$4,$5,$6,'pending',$7,$8)
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
            ),
        )
        try:
            await self.g._owner_inbox(
                "donation",
                did,
                f"حمایت مالی — #{did}",
                f"کاربر: {display_name or username or player_id}\nمبلغ: {int(amount):,} تومان",
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
                raise DonationError("بررسی همزمان ناموفق بود؛ دوباره تلاش کنید.")
            if approve:
                # increment public total once
                cur = await self._get("donations_total", "0")
                try:
                    cur_v = float(cur or 0)
                except Exception:
                    cur_v = 0.0
                # if total was never set, bootstrap from sum approved excluding this one + this
                if cur_v <= 0:
                    s = await tx.fetchrow(
                        "SELECT COALESCE(SUM(amount),0) AS s FROM ng_donations WHERE status='approved' AND id<>$1",
                        (int(did),),
                    )
                    cur_v = float((s or {}).get("s") or 0)
                new_v = cur_v + float(check["amount"])
                # write total inside same logical flow
                exists = await tx.fetchrow(
                    "SELECT key FROM ng_bot_settings WHERE key='donations_total'"
                )
                if exists:
                    await tx.execute(
                        "UPDATE ng_bot_settings SET value=$1 WHERE key='donations_total'",
                        (str(int(new_v)),),
                    )
                else:
                    await tx.execute(
                        "INSERT INTO ng_bot_settings (key, value) VALUES ('donations_total',$1)",
                        (str(int(new_v)),),
                    )
        return await self.get(did)

    async def set_total_manual(self, actor: int, amount: float) -> str:
        if not self.g.is_owner(actor):
            raise DonationError("فقط مالک")
        amount = max(0.0, float(amount))
        await self._set_raw("donations_total", str(int(amount)))
        try:
            await self.g.admin_log(actor, "donations_total", str(int(amount)))
        except Exception:
            pass
        return f"✅ مجموع حمایت‌های نمایشی روی {int(amount):,} تومان تنظیم شد."

    async def set_field(self, actor: int, field: str, value: str) -> str:
        if not self.g.is_owner(actor):
            raise DonationError("فقط مالک")
        key_map = {
            "card": "donation_card",
            "card_name": "donation_card_name",
            "intro": "donation_intro",
            "instructions": "donation_instructions",
        }
        key = key_map.get(field)
        if not key:
            raise DonationError("فیلد نامعتبر")
        value = (value or "").strip()
        if not value:
            raise DonationError("مقدار خالی است.")
        if len(value) > 3500:
            raise DonationError("متن خیلی بلند است.")
        await self._set_raw(key, value)
        try:
            await self.g.admin_log(actor, "donation_set", key)
        except Exception:
            pass
        return "✅ ذخیره شد."

    def announcement_text(self, donation: dict) -> str:
        amount = int(float(donation.get("amount") or 0))
        name = (donation.get("display_name") or donation.get("username") or "یک بازیکن").strip()
        if int(donation.get("show_name") or 1):
            who = name
        else:
            who = "یک نفر"
        return (
            f"💎 حمایت مالی جدید\n\n"
            f"{who} از WORLD WAR حمایت کرد ✨\n"
            f"💰 مبلغ: {amount:,} تومان\n\n"
            f"از حمایت شما سپاسگزاریم 🙏"
        )
