"""Bale bot handlers — registration, country selection, management."""
from __future__ import annotations

import logging
import re

from bot.keyboards.main_menu import (
    MAIN_BUTTONS,
    main_menu_text,
    countries_page_text,
    management_help,
)
from engine.country_engine import CountryClaimError
from modules.news.briefing import build_initial_briefing

log = logging.getLogger(__name__)
_PAGE: dict[int, int] = {}


async def create_bot(token: str):
    if not token:
        raise ValueError("BALE_TOKEN is empty — set env or local config.example.py → config.py")
    from bale import Bot

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
        log.warning("Bale types unavailable")
        return

    players = app_ctx["players"]
    countries = app_ctx["countries"]
    world = app_ctx["world"]
    db = app_ctx["db"]
    management = app_ctx["management"]

    async def require_country(pid: int):
        p = await players.get(pid)
        if not p or not p.get("country_code"):
            return None
        return p["country_code"]

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
            await message.reply(f"شناسه شما: {pid}\nزبان: فارسی\nبازگشت: منو")
            return
        if text == "روابط خارجی":
            await message.reply("روابط خارجی در فاز بعد کامل می‌شود.\nبازگشت: منو")
            return
        if text == "اخبار":
            items = await db.fetch(
                "SELECT headline, game_date, country_code FROM news_items ORDER BY real_time DESC LIMIT 8"
            )
            gdate = await world.current_game_date()
            if not items:
                await message.reply(f"📰 اخبار\nتاریخ بازی: {gdate.isoformat()}\nخبری نیست.\nبازگشت: منو")
                return
            lines = [f"📰 اخبار — {gdate.isoformat()}"]
            for it in items:
                lines.append(f"• [{it.get('game_date')}] {it.get('headline')}")
            lines.append("بازگشت: منو")
            await message.reply("\n".join(lines))
            return

        if text in ("کشور من", "وضعیت کشور"):
            code = await require_country(pid)
            if not code:
                await message.reply("هنوز کشوری ندارید. «انتخاب کشور» را بزنید.")
                return
            # show dashboard (live state) not only historical briefing
            await message.reply((await management.dashboard(code))[:3500])
            return

        if text in ("مدیریت کشور", "اقتصاد"):
            code = await require_country(pid)
            if not code:
                await message.reply("ابتدا کشور انتخاب کنید.")
                return
            await message.reply(management_help() + "\n\n" + (await management.dashboard(code))[:2800])
            return

        if text == "انتخاب کشور" or lower.startswith("countries"):
            p = await players.get(pid)
            if p and p.get("country_code"):
                await message.reply(f"شما کشور {p['country_code']} را دارید.\nبازگشت: منو")
                return
            rows = await countries.list_countries()
            _PAGE[pid] = 0
            await message.reply(countries_page_text(rows, 0))
            return

        if lower in ("next", "prev"):
            rows = await countries.list_countries()
            page = _PAGE.get(pid, 0)
            page = page + 1 if lower == "next" else max(0, page - 1)
            page = min(page, max(0, (len(rows) - 1) // 10))
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
            if not await players.briefing_sent(pid):
                briefing = await build_initial_briefing(db, world, code)
                await players.set_briefing_sent(pid)
                await message.reply(
                    f"✅ کشور {claimed.get('flag') or ''} {claimed.get('name_fa') or code} ثبت شد.\n\n"
                    + briefing[:3000]
                )
            else:
                await message.reply(f"✅ کشور {code} ثبت شد.\nبازگشت: منو")
            return

        # management commands require ownership
        code = await require_country(pid)
        if code:
            m_tax = re.match(r"^مالیات\s+([0-9]*\.?[0-9]+)$", text)
            if m_tax:
                await message.reply(await management.set_tax_rate(code, float(m_tax.group(1)), pid))
                return
            m_sp = re.match(r"^مخارج\s+([0-9]*\.?[0-9]+)$", text)
            if m_sp:
                await message.reply(await management.set_spending_rate(code, float(m_sp.group(1)), pid))
                return
            m_inv = re.match(r"^سرمایه‌گذاری\s+(\w+)\s+([0-9]*\.?[0-9]+)$", text)
            if m_inv:
                await message.reply(
                    await management.invest(code, m_inv.group(1), float(m_inv.group(2)), pid)
                )
                return
            m_ap = re.match(r"^انتصاب\s+(\w+)\s+(.+)$", text)
            if m_ap:
                await message.reply(
                    await management.appoint_minister(code, m_ap.group(1), m_ap.group(2), pid)
                )
                return
            m_ds = re.match(r"^برکناری\s+(\w+)$", text)
            if m_ds:
                await message.reply(await management.dismiss_minister(code, m_ds.group(1), pid))
                return
            if text in ("تیک اقتصادی", "tick"):
                result = await management.apply_budget_tick(code)
                await message.reply(
                    f"✅ تیک بودجه\nدرآمد {result['income']:,.0f} | هزینه {result['expense']:,.0f}\n"
                    f"خزانه {result['treasury']:,.0f} | رضایت {result['satisfaction']:.1f}"
                )
                return

        if text in MAIN_BUTTONS:
            await message.reply(main_menu_text())
