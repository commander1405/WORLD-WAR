"""Bale UI — Persian reply + inline keyboards (python-bale-bot 2.5.0)."""
from __future__ import annotations

import logging
import re

from bot.ui.keyboards import (
    BTN_MY, BTN_ECO, BTN_BUILD, BTN_DIPLO, BTN_DEF, BTN_CAB,
    BTN_WORLD, BTN_SET, BTN_HELP, BTN_PICK, MAIN_LABELS,
    main_reply_keyboard, country_pick_keyboard, my_country_menu,
    economy_menu, cabinet_menu, world_menu, confirm_claim,
    build_menu, defense_menu, settings_menu, inline_rows, back_home_row,
)
from bot.ui import views
from engine.country_engine import CountryClaimError

log = logging.getLogger(__name__)
_PAGE: dict[int, int] = {}
# pending minister appointment: player_id -> portfolio
_PENDING_APPOINT: dict[int, str] = {}


async def create_bot(token: str):
    if not token:
        raise ValueError("BALE_TOKEN is empty")
    from bale import Bot
    bot = Bot(token)
    log.info("Bale Bot instance created")
    return bot


def _text(message) -> str:
    t = getattr(message, "content", None)
    if t is None:
        t = getattr(message, "text", None)
    return str(t or "").strip()


def _uid(message) -> int | None:
    author = getattr(message, "author", None) or getattr(message, "from_user", None)
    if not author:
        return None
    raw = getattr(author, "user_id", None) or getattr(author, "id", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _names(message):
    author = getattr(message, "author", None) or getattr(message, "from_user", None)
    if not author:
        return None, None
    username = getattr(author, "username", None)
    first = getattr(author, "first_name", None) or ""
    last = getattr(author, "last_name", None) or ""
    return username, ((first + " " + last).strip() or None)


def _cb_uid(cq) -> int | None:
    user = getattr(cq, "from_user", None) or getattr(cq, "user", None)
    if not user:
        return None
    raw = getattr(user, "user_id", None) or getattr(user, "id", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def _reply(message, text, components=None):
    await message.reply(text[:3500], components=components or main_reply_keyboard())


async def _edit_or_reply(cq, text, components=None):
    """Prefer answering via message reply; callback answer if available."""
    msg = getattr(cq, "message", None)
    bot = getattr(cq, "bot", None) or (msg.get_bot() if msg and hasattr(msg, "get_bot") else None)
    # try answer callback to stop loading animation
    for name in ("answer", "answer_callback_query"):
        fn = getattr(cq, name, None) or (getattr(bot, name, None) if bot else None)
        if callable(fn):
            try:
                res = fn(getattr(cq, "id", None) or "")
                if hasattr(res, "__await__"):
                    await res
            except Exception:
                pass
            break
    if msg is not None:
        await msg.reply(text[:3500], components=components or main_reply_keyboard())


async def _load_country_pack(db, code: str):
    c = await db.fetchrow("SELECT * FROM countries WHERE country_code=$1", (code,))
    b = await db.fetchrow("SELECT * FROM country_baselines WHERE country_code=$1", (code,))
    e = await db.fetchrow("SELECT * FROM country_economy WHERE country_code=$1", (code,))
    return c, b, e


def register_handlers(bot, app_ctx: dict) -> None:
    players = app_ctx["players"]
    countries = app_ctx["countries"]
    world = app_ctx["world"]
    db = app_ctx["db"]
    management = app_ctx["management"]

    async def owned(pid: int):
        p = await players.get(pid)
        return (p or {}).get("country_code")

    @bot.listen("on_ready")
    async def on_ready():
        log.info("Bale on_ready — polling active")

    @bot.listen("on_message")
    async def on_message(message):
        try:
            text = _text(message)
            if not text:
                return
            pid = _uid(message)
            if not pid:
                return
            username, display = _names(message)
            await players.register_or_update(pid, username=username, display_name=display)
            log.info("on_message id=%s text=%r", pid, text[:60])

            # pending minister name entry (only typed flow)
            if pid in _PENDING_APPOINT and not text.startswith(("🏛", "💰", "🏗", "🤝", "🛡", "🌍", "⚙", "📖", "🗺")):
                portfolio = _PENDING_APPOINT.pop(pid)
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                msg = await management.appoint_minister(code, portfolio, text, pid)
                await _reply(message, msg, cabinet_menu())
                return

            gdate = await world.current_game_date()

            if text in ("/start", "شروع", "منو", "menu", "start"):
                await _reply(message, views.welcome_text(gdate), main_reply_keyboard())
                return

            if text == BTN_HELP or text in ("/help", "راهنما"):
                await _reply(message, views.help_text(), settings_menu())
                return

            if text == BTN_SET:
                await _reply(message, "⚙ تنظیمات", settings_menu())
                return

            if text == BTN_PICK:
                p = await players.get(pid)
                if p and p.get("country_code"):
                    await _reply(message, f"شما هم‌اکنون رهبر یک کشور هستید.")
                    return
                rows = await countries.list_countries()
                _PAGE[pid] = 0
                await _reply(
                    message,
                    "🗺 یک کشور آزاد انتخاب کنید:",
                    country_pick_keyboard(rows, 0),
                )
                return

            if text == BTN_MY:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                c, b, e = await _load_country_pack(db, code)
                if not c or not b:
                    await _reply(message, "کشور یافت نشد.")
                    return
                await _reply(message, views.overview_card(c, b, e, gdate), my_country_menu())
                return

            if text == BTN_ECO:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                c, b, e = await _load_country_pack(db, code)
                await _reply(message, views.economy_base_card(b or {}, e), economy_menu())
                return

            if text == BTN_BUILD:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                await _reply(message, views.build_card(), build_menu())
                return

            if text == BTN_DIPLO:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                _, b, _ = await _load_country_pack(db, code)
                await _reply(
                    message,
                    views.relations_card(b or {}),
                    inline_rows([[("🌐 پیمان‌ها", "my:orgs")], back_home_row()]),
                )
                return

            if text == BTN_DEF:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                _, b, e = await _load_country_pack(db, code)
                await _reply(message, views.defense_card(e, b or {}), defense_menu())
                return

            if text == BTN_CAB:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                rows = await db.fetch(
                    "SELECT * FROM cabinet_members WHERE country_code=$1 ORDER BY portfolio",
                    (code,),
                )
                await _reply(message, views.cabinet_card(rows), cabinet_menu())
                return

            if text == BTN_WORLD:
                await _reply(
                    message,
                    views.news_card(
                        await db.fetch(
                            "SELECT headline FROM news_items ORDER BY real_time DESC LIMIT 6"
                        ),
                        gdate,
                    ),
                    world_menu(),
                )
                return

            if text in MAIN_LABELS:
                await _reply(message, views.welcome_text(gdate))
                return

            # owner-only text commands still allowed but not advertised
            if text.startswith("/status"):
                ok = await db.health_check()
                await _reply(message, f"پایگاه‌داده: {'سالم' if ok else 'خطا'}")
        except Exception:
            log.exception("on_message error")
            try:
                await message.reply("خطایی رخ داد. دوباره تلاش کنید.", components=main_reply_keyboard())
            except Exception:
                pass

    @bot.listen("on_callback")
    async def on_callback(cq):
        try:
            data = (getattr(cq, "data", None) or "").strip()
            pid = _cb_uid(cq)
            if not pid or not data:
                return
            await players.register_or_update(pid)
            log.info("on_callback id=%s data=%r", pid, data[:60])
            gdate = await world.current_game_date()

            if data in ("nav:home", "nav:back"):
                await _edit_or_reply(cq, views.welcome_text(gdate), main_reply_keyboard())
                return
            if data in ("nav:help",):
                await _edit_or_reply(cq, views.help_text(), settings_menu())
                return
            if data == "nav:about":
                await _edit_or_reply(
                    cq,
                    "🕹 جنگ جهانی\nشبیه‌سازی مدیریت کشورها از ۱ ژانویه ۲۰۲۰\nزمان سرور پایدار است.",
                    settings_menu(),
                )
                return

            # --- claim flow ---
            if data.startswith("claim:page:"):
                page = int(data.split(":")[-1])
                rows = await countries.list_countries()
                _PAGE[pid] = page
                await _edit_or_reply(cq, "🗺 انتخاب کشور:", country_pick_keyboard(rows, page))
                return
            if data.startswith("claim:busy:"):
                await _edit_or_reply(cq, "این کشور قبلاً گرفته شده است.")
                return
            if data.startswith("claim:ask:"):
                code = data.split(":")[-1]
                c, b, _ = await _load_country_pack(db, code)
                name = (b or {}).get("name_fa") or code
                flag = (b or {}).get("flag") or ""
                await _edit_or_reply(cq, views.claim_confirm(flag, name), confirm_claim(code))
                return
            if data.startswith("claim:yes:"):
                code = data.split(":")[-1]
                p = await players.get(pid)
                if p and p.get("country_code"):
                    await _edit_or_reply(cq, "شما قبلاً کشور دارید.")
                    return
                try:
                    claimed = await countries.claim_country(pid, code)
                except CountryClaimError as exc:
                    await _edit_or_reply(cq, f"انتخاب ممکن نشد: {exc}")
                    return
                c, b, e = await _load_country_pack(db, code)
                if not await players.briefing_sent(pid):
                    await players.set_briefing_sent(pid)
                text = views.overview_card(c, b, e, gdate)
                await _edit_or_reply(cq, "✅ کشور شما ثبت شد.\n\n" + text, my_country_menu())
                return

            code = await owned(pid)

            # --- my country subviews (need ownership) ---
            if data.startswith("my:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                c, b, e = await _load_country_pack(db, code)
                if data == "my:overview":
                    await _edit_or_reply(cq, views.overview_card(c, b, e, gdate), my_country_menu())
                elif data == "my:politics":
                    await _edit_or_reply(cq, views.politics_card(b or {}), my_country_menu())
                elif data == "my:economy":
                    await _edit_or_reply(cq, views.economy_base_card(b or {}, e), my_country_menu())
                elif data == "my:orgs":
                    await _edit_or_reply(cq, views.orgs_card(b or {}), my_country_menu())
                elif data == "my:relations":
                    await _edit_or_reply(cq, views.relations_card(b or {}), my_country_menu())
                elif data == "my:sectors":
                    secs = await db.fetch(
                        "SELECT * FROM production_sectors WHERE country_code=$1 ORDER BY sector_code",
                        (code,),
                    )
                    await _edit_or_reply(cq, views.sectors_card(secs), my_country_menu())
                return

            # --- economy actions ---
            if data.startswith("eco:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                e = await db.fetchrow("SELECT * FROM country_economy WHERE country_code=$1", (code,))
                tax = float((e or {}).get("tax_rate") or 0.15)
                spend = float((e or {}).get("public_spending_rate") or 0.12)
                msg = ""
                if data == "eco:status":
                    _, b, e = await _load_country_pack(db, code)
                    await _edit_or_reply(cq, views.economy_base_card(b or {}, e), economy_menu())
                    return
                if data == "eco:tax_up":
                    msg = await management.set_tax_rate(code, min(0.5, tax + 0.02), pid)
                elif data == "eco:tax_down":
                    msg = await management.set_tax_rate(code, max(0.0, tax - 0.02), pid)
                elif data == "eco:spend_up":
                    msg = await management.set_spending_rate(code, min(0.5, spend + 0.02), pid)
                elif data == "eco:spend_down":
                    msg = await management.set_spending_rate(code, max(0.0, spend - 0.02), pid)
                elif data == "eco:tick":
                    r = await management.apply_budget_tick(code)
                    msg = (
                        f"✅ دوره بودجه انجام شد\n"
                        f"خزانه: {int(r['treasury']):,}\nرضایت: {r['satisfaction']:.0f}"
                    )
                elif data == "eco:inv_industry":
                    msg = await management.invest(code, "industry", 1000, pid)
                elif data == "eco:inv_agri":
                    msg = await management.invest(code, "agriculture", 1000, pid)
                await _edit_or_reply(cq, msg or "انجام شد", economy_menu())
                return

            if data.startswith("build:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                sector = {"infra": "services", "factory": "industry", "social": "services"}.get(
                    data.split(":")[-1], "industry"
                )
                msg = await management.invest(code, sector, 1500, pid)
                await _edit_or_reply(cq, msg, build_menu())
                return

            if data.startswith("cab:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data == "cab:list":
                    rows = await db.fetch(
                        "SELECT * FROM cabinet_members WHERE country_code=$1 ORDER BY portfolio",
                        (code,),
                    )
                    await _edit_or_reply(cq, views.cabinet_card(rows), cabinet_menu())
                    return
                if data.startswith("cab:app:"):
                    portfolio = data.split(":")[-1]
                    _PENDING_APPOINT[pid] = portfolio
                    await _edit_or_reply(
                        cq,
                        f"نام وزیر را برای «{portfolio}» بنویسید و ارسال کنید.",
                        cabinet_menu(),
                    )
                    return
                if data.startswith("cab:dis:"):
                    portfolio = data.split(":")[-1]
                    msg = await management.dismiss_minister(code, portfolio, pid)
                    await _edit_or_reply(cq, msg, cabinet_menu())
                    return

            if data.startswith("def:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                _, b, e = await _load_country_pack(db, code)
                await _edit_or_reply(cq, views.defense_card(e, b or {}), defense_menu())
                return

            if data.startswith("world:"):
                if data == "world:news":
                    items = await db.fetch(
                        "SELECT headline FROM news_items ORDER BY real_time DESC LIMIT 8"
                    )
                    await _edit_or_reply(cq, views.news_card(items, gdate), world_menu())
                elif data == "world:date":
                    from bot.ui.format import fa_date
                    await _edit_or_reply(
                        cq,
                        "تاریخ جهان\n" + fa_date(gdate) + "\nشروع بازی: ۱ ژانویه ۲۰۲۰",
                        world_menu(),
                    )
                elif data.startswith("world:list:"):
                    page = int(data.split(":")[-1])
                    rows = await countries.list_countries()
                    kb = inline_rows([
                        ([("◀️", f"world:list:{page-1}")] if page > 0 else [])
                        + ([("▶️", f"world:list:{page+1}")] if (page + 1) * 10 < len(rows) else []),
                        back_home_row(),
                    ])
                    # fix empty row
                    nav = []
                    if page > 0:
                        nav.append(("◀️ قبل", f"world:list:{page-1}"))
                    if (page + 1) * 10 < len(rows):
                        nav.append(("بعد ▶️", f"world:list:{page+1}"))
                    rows_btn = [nav] if nav else []
                    rows_btn.append(back_home_row())
                    await _edit_or_reply(
                        cq,
                        views.world_list_card(rows, page),
                        inline_rows(rows_btn),
                    )
                return
        except Exception:
            log.exception("on_callback error")

    n = len(getattr(bot, "events", {}).get("on_message") or [])
    log.info("Registered on_message=%s on_callback=%s", n, len(getattr(bot, "events", {}).get("on_callback") or []))
