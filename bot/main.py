"""Bale bot handlers — registration, country selection, briefing."""
from __future__ import annotations

import logging
import re

from bot.keyboards.main_menu import MAIN_BUTTONS, main_menu_text, countries_page_text
from engine.country_engine import CountryClaimError
from modules.news.briefing import build_initial_briefing

log = logging.getLogger(__name__)

# in-memory page state per player (ephemeral)
_PAGE: dict[int, int] = {}


async def create_bot(token: str):
    if not token:
        raise ValueError("BALE_TOKEN is empty — set it in config.py or environment")
    try:
        from bale import Bot
    except ImportError as exc:
        raise RuntimeError(
            "python-bale-bot is not installed. pip install -r requirements.txt"
        ) from exc
    bot = Bot(token)
    log.info("Bale Bot instance created")
    return bot


def _author_id(message) -> int | None:
    author = getattr(message, "author", None) or getattr(message, "from_user", None)
    if author is None:
        return None
    return int(getattr(author, "user_id", None) or getattr(author, "id", None) or 0) or None


def _author_names(message) -> tuple[str | None, str | None]:
    author = getattr(message, "author", None) or getattr(message, "from_user", None)
    if author is None:
        return None, None
    username = getattr(author, "username", None)
    first = getattr(author, "first_name", None) or ""
    last = getattr(author, "last_name", None) or ""
    display = (first + " " + last).strip() or None
    return username, display


def register_handlers(bot, app_ctx: dict) -> None:
    try:
        from bale import Message
    except ImportError:
        log.warning("Bale types unavailable — handlers not registered")
        return

    players = app_ctx["players"]
    countries = app_ctx["countries"]
    world = app_ctx["world"]
    db = app_ctx["db"]

    @bot.listen("message")
    async def on_message(message: Message):
        text = (getattr(message, "content", None) or getattr(message, "text", None) or "")
        text = str(text).strip()
        if not text:
            return
        pid = _author_id(message)
        if not pid:
            return
        username, display = _author_names(message)
        await players.register_or_update(pid, username=username, display_name=display)

        lower = text.lower()
        if text in ("/start", "start", "شروع", "منو") or lower == "menu":
            await message.reply(main_menu_text())
            return
        if text in ("/status", "status"):
            ok = await db.health_check()
            mode = app_ctx["settings"].database_mode
            await message.reply(f"وضعیت پایگاه‌داده: {'سالم' if ok else 'خطا'}\nحالت: {mode}")
            return

        if text == "تنظیمات":
            await message.reply(
                "تنظیمات\n"
                f"شناسه شما: {pid}\n"
                "زبان رابط: فارسی\n"
                "برای بازگشت: منو"
            )
            return

        if text in ("روابط خارجی", "اقتصاد"):
            await message.reply("این بخش در فازهای بعدی فعال می‌شود.\nبازگشت: منو")
            return

        if text == "اخبار":
            gdate = await world.current_game_date()
            await message.reply(
                f"📰 اخبار جهان\nتاریخ بازی: {gdate.isoformat()}\n"
                "هنوز رویداد پویای جدیدی ثبت نشده است.\nبازگشت: منو"
            )
            return

        if text in ("کشور من", "وضعیت کشور"):
            p = await players.get(pid)
            code = p.get("country_code") if p else None
            if not code:
                await message.reply("هنوز کشوری ندارید. از «انتخاب کشور» استفاده کنید.")
                return
            report = await build_initial_briefing(db, world, code)
            await message.reply(report[:3500])
            return

        if text == "انتخاب کشور" or lower.startswith("countries"):
            p = await players.get(pid)
            if p and p.get("country_code"):
                await message.reply(
                    f"شما قبلاً کشور {p['country_code']} را در اختیار دارید.\nبازگشت: منو"
                )
                return
            rows = await countries.list_countries()
            _PAGE[pid] = 0
            await message.reply(countries_page_text(rows, 0))
            return

        if lower in ("next", "prev"):
            rows = await countries.list_countries()
            page = _PAGE.get(pid, 0)
            if lower == "next":
                page += 1
            else:
                page = max(0, page - 1)
            max_page = max(0, (len(rows) - 1) // 10)
            page = min(page, max_page)
            _PAGE[pid] = page
            await message.reply(countries_page_text(rows, page))
            return

        m = re.match(r"^(?:claim|انتخاب)\s+([A-Za-z]{2})$", text, re.I)
        if m:
            code = m.group(1).upper()
            try:
                claimed = await countries.claim_country(
                    pid, code, username=username, display_name=display
                )
            except CountryClaimError as exc:
                await message.reply(f"❌ ادعا ناموفق: {exc}")
                return
            briefing = await build_initial_briefing(db, world, code)
            await players.set_briefing_sent(pid)
            await message.reply(
                f"✅ کشور {claimed.get('flag') or ''} {claimed.get('name_fa') or code} برای شما ثبت شد.\n\n"
                + briefing[:3200]
            )
            return

        if text in MAIN_BUTTONS:
            await message.reply(main_menu_text())
            return
