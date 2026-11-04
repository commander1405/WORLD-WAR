"""Bale UI — Phase 4 Persian gameplay menus."""
from __future__ import annotations

import logging

from bot.ui import views
from bot.ui.keyboards import (
    BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MARKET, BTN_TRADE, BTN_BUILD, BTN_DEF,
    BTN_DIPLO, BTN_WORLD, BTN_CAB, BTN_LOG, BTN_HELP, BTN_PICK, BTN_SET, MAIN_LABELS,
    main_reply_keyboard, country_pick_keyboard, my_country_menu, economy_menu,
    cabinet_menu, world_menu, confirm_claim, build_menu, defense_menu, settings_menu,
    shop_categories_kb, shop_items_kb, shop_item_actions, cart_kb, market_list_kb,
    inv_sell_kb, trade_menu_kb, trade_res_kb, trade_offers_kb, crisis_targets_kb,
    inline_rows, back_home_row,
)
from engine.country_engine import CountryClaimError
from modules.markets.service import MarketError
from modules.trade.service import TradeError, TRADEABLE

log = logging.getLogger(__name__)
_PAGE: dict[int, int] = {}
_PENDING_APPOINT: dict[int, str] = {}
_PENDING_TRADE: dict[int, dict] = {}
_PENDING_LIST: dict[int, dict] = {}


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


def _uid(obj) -> int | None:
    author = getattr(obj, "author", None) or getattr(obj, "from_user", None) or getattr(obj, "user", None)
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


async def _reply(message, text, components=None):
    await message.reply(str(text)[:3500], components=components or main_reply_keyboard())


async def _cb_answer(cq):
    bot = getattr(cq, "bot", None)
    msg = getattr(cq, "message", None)
    if bot is None and msg is not None and hasattr(msg, "get_bot"):
        try:
            bot = msg.get_bot()
        except Exception:
            bot = None
    for name in ("answer", "answer_callback_query"):
        fn = getattr(cq, name, None)
        if callable(fn):
            try:
                res = fn()
                if hasattr(res, "__await__"):
                    await res
            except Exception:
                pass
            return
        if bot and hasattr(bot, name):
            try:
                res = getattr(bot, name)(getattr(cq, "id", ""))
                if hasattr(res, "__await__"):
                    await res
            except Exception:
                pass
            return


async def _edit_or_reply(cq, text, components=None):
    await _cb_answer(cq)
    msg = getattr(cq, "message", None)
    if msg is not None:
        await msg.reply(str(text)[:3500], components=components or main_reply_keyboard())


async def _pack(db, code):
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
    market = app_ctx["market"]
    trade = app_ctx["trade"]

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
            gdate = await world.current_game_date()

            # pending typed inputs
            if pid in _PENDING_APPOINT and text not in MAIN_LABELS:
                portfolio = _PENDING_APPOINT.pop(pid)
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                await _reply(message, await management.appoint_minister(code, portfolio, text, pid), cabinet_menu())
                return

            if pid in _PENDING_LIST and text not in MAIN_LABELS:
                st = _PENDING_LIST[pid]
                if st.get("step") == "qty":
                    try:
                        qty = float(text)
                    except ValueError:
                        await _reply(message, "تعداد را عددی بنویسید.")
                        return
                    st["qty"] = qty
                    st["step"] = "price"
                    await _reply(message, "قیمت واحد پیشنهادی را بنویسید:")
                    return
                if st.get("step") == "price":
                    try:
                        price = float(text)
                    except ValueError:
                        await _reply(message, "قیمت را عددی بنویسید.")
                        return
                    code = await owned(pid)
                    _PENDING_LIST.pop(pid, None)
                    try:
                        msg = await market.create_listing(code, st["item"], st["qty"], price, pid)
                    except MarketError as e:
                        msg = f"❌ {e}"
                    await _reply(message, msg, market_list_kb(await market.list_market()))
                    return

            if pid in _PENDING_TRADE and text not in MAIN_LABELS:
                st = _PENDING_TRADE[pid]
                if st.get("step") == "target":
                    target = text.strip().upper()
                    st["target"] = target
                    st["step"] = "qty"
                    await _reply(message, "مقدار منبع را بنویسید:")
                    return
                if st.get("step") == "qty":
                    try:
                        st["qty"] = float(text)
                    except ValueError:
                        await _reply(message, "مقدار عددی بنویسید.")
                        return
                    st["step"] = "price"
                    await _reply(message, "مبلغ کل قرارداد را بنویسید:")
                    return
                if st.get("step") == "price":
                    try:
                        price = float(text)
                    except ValueError:
                        await _reply(message, "مبلغ عددی بنویسید.")
                        return
                    code = await owned(pid)
                    _PENDING_TRADE.pop(pid, None)
                    try:
                        msg = await trade.create_offer(code, st["target"], st["res"], st["qty"], price, pid)
                    except TradeError as e:
                        msg = f"❌ {e}"
                    await _reply(message, msg, trade_menu_kb())
                    return

            if text in ("/start", "شروع", "منو", "menu", "start"):
                await _reply(message, views.welcome_text(gdate))
                return
            if text in (BTN_HELP, "/help", "راهنما"):
                await _reply(message, views.help_text(), settings_menu())
                return
            if text == BTN_SET:
                await _reply(message, "⚙ تنظیمات", settings_menu())
                return
            if text == BTN_PICK:
                p = await players.get(pid)
                if p and p.get("country_code"):
                    await _reply(message, "شما هم‌اکنون یک کشور دارید.")
                    return
                rows = await countries.list_countries()
                _PAGE[pid] = 0
                await _reply(message, "🗺 یک کشور آزاد انتخاب کنید:", country_pick_keyboard(rows, 0))
                return
            if text == BTN_MY:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                c, b, e = await _pack(db, code)
                inv = await market.inventory(code)
                extra = "\n".join(
                    f"• {i.get('name_fa', i['item_code'])}: {int(float(i['quantity']))}"
                    for i in inv if str(i["item_code"]).startswith("res_")
                ) or "• منبع ذخیره‌شده ندارید"
                text_out = views.overview_card(c, b, e, gdate) + "\n\n📦 منابع:\n" + extra
                await _reply(message, text_out, my_country_menu())
                return
            if text == BTN_ECO:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                _, b, e = await _pack(db, code)
                await _reply(message, views.economy_base_card(b or {}, e), economy_menu())
                return
            if text == BTN_SHOP:
                if not await owned(pid):
                    await _reply(message, views.need_country())
                    return
                await _reply(message, "🛒 فروشگاه کشور\nدسته را انتخاب کنید:", shop_categories_kb())
                return
            if text == BTN_INV:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                await _reply(message, await market.inventory_text(code), inv_sell_kb(await market.inventory(code)))
                return
            if text == BTN_MARKET:
                if not await owned(pid):
                    await _reply(message, views.need_country())
                    return
                listings = await market.list_market(page=0)
                await _reply(message, "🌐 بازار آزاد جهانی", market_list_kb(listings, 0))
                return
            if text == BTN_TRADE:
                if not await owned(pid):
                    await _reply(message, views.need_country())
                    return
                await _reply(message, "🚢 تجارت جهانی منابع", trade_menu_kb())
                return
            if text == BTN_BUILD:
                if not await owned(pid):
                    await _reply(message, views.need_country())
                    return
                await _reply(message, views.build_card(), build_menu())
                return
            if text == BTN_DEF:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                await _reply(message, await market.military_text(code), defense_menu())
                return
            if text == BTN_DIPLO:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                _, b, _ = await _pack(db, code)
                await _reply(message, views.relations_card(b or {}), inline_rows([[("🌐 پیمان‌ها", "my:orgs")], back_home_row()]))
                return
            if text == BTN_CAB:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                rows = await db.fetch("SELECT * FROM cabinet_members WHERE country_code=$1 ORDER BY portfolio", (code,))
                await _reply(message, views.cabinet_card(rows), cabinet_menu())
                return
            if text == BTN_WORLD:
                items = await db.fetch("SELECT headline FROM news_items ORDER BY real_time DESC LIMIT 6")
                await _reply(message, views.news_card(items, gdate), world_menu())
                return
            if text == BTN_LOG:
                code = await owned(pid)
                if not code:
                    await _reply(message, views.need_country())
                    return
                await _reply(message, await market.activity_text(code))
                return
        except Exception:
            log.exception("on_message error")
            try:
                await message.reply("خطایی رخ داد.", components=main_reply_keyboard())
            except Exception:
                pass

    @bot.listen("on_callback")
    async def on_callback(cq):
        try:
            data = (getattr(cq, "data", None) or "").strip()
            pid = _uid(cq)
            if not pid or not data:
                return
            await players.register_or_update(pid)
            gdate = await world.current_game_date()
            code = await owned(pid)

            if data in ("nav:home", "nav:back"):
                await _edit_or_reply(cq, views.welcome_text(gdate))
                return
            if data == "nav:help":
                await _edit_or_reply(cq, views.help_text(), settings_menu())
                return
            if data == "nav:about":
                await _edit_or_reply(cq, "🕹 جنگ جهانی — شبیه‌سازی مدیریت کشورها از ۲۰۲۰", settings_menu())
                return

            # claims
            if data.startswith("claim:page:"):
                page = int(data.split(":")[-1])
                rows = await countries.list_countries()
                await _edit_or_reply(cq, "🗺 انتخاب کشور:", country_pick_keyboard(rows, page))
                return
            if data.startswith("claim:busy:"):
                await _edit_or_reply(cq, "این کشور گرفته شده است.")
                return
            if data.startswith("claim:ask:"):
                ccode = data.split(":")[-1]
                _, b, _ = await _pack(db, ccode)
                await _edit_or_reply(cq, views.claim_confirm((b or {}).get("flag") or "", (b or {}).get("name_fa") or ccode), confirm_claim(ccode))
                return
            if data.startswith("claim:yes:"):
                ccode = data.split(":")[-1]
                try:
                    await countries.claim_country(pid, ccode)
                except CountryClaimError as e:
                    await _edit_or_reply(cq, f"ناموفق: {e}")
                    return
                if not await players.briefing_sent(pid):
                    await players.set_briefing_sent(pid)
                c, b, e = await _pack(db, ccode)
                await _edit_or_reply(cq, "✅ ثبت شد\n\n" + views.overview_card(c, b, e, gdate), my_country_menu())
                return

            # shop
            if data.startswith("shop:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data == "shop:cart":
                    text, _, items = await market.cart_view(pid)
                    await _edit_or_reply(cq, text, cart_kb(items))
                    return
                if data == "shop:checkout":
                    try:
                        msg = await market.checkout(pid, code)
                    except MarketError as e:
                        msg = f"❌ {e}"
                    await _edit_or_reply(cq, msg, shop_categories_kb())
                    return
                if data.startswith("shop:cat:"):
                    cat = data.split(":")[-1]
                    items = await market.list_category(cat)
                    await _edit_or_reply(cq, "محصولات:", shop_items_kb(items))
                    return
                if data.startswith("shop:item:"):
                    ic = data.split(":")[-1]
                    it = market.item(ic)
                    text = f"{it['name_fa']}\n{it['description_fa']}\nقیمت واحد: {int(it['unit_price']):,}\nحداکثر سفارش: {it['max_per_order']}"
                    await _edit_or_reply(cq, text, shop_item_actions(ic))
                    return
                if data.startswith("shop:add:"):
                    _, _, ic, qty = data.split(":", 3)
                    msg = await market.cart_add(pid, ic, float(qty))
                    await _edit_or_reply(cq, msg, shop_item_actions(ic))
                    return
                if data.startswith("shop:del:"):
                    ic = data.split(":")[-1]
                    msg = await market.cart_set(pid, ic, 0)
                    text, _, items = await market.cart_view(pid)
                    await _edit_or_reply(cq, msg + "\n\n" + text, cart_kb(items))
                    return

            # market
            if data.startswith("mkt:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data.startswith("mkt:page:"):
                    page = int(data.split(":")[-1])
                    await _edit_or_reply(cq, "🌐 بازار آزاد", market_list_kb(await market.list_market(page=page), page))
                    return
                if data.startswith("mkt:buy:"):
                    lid = int(data.split(":")[-1])
                    try:
                        msg = await market.buy_listing(lid, code, pid)
                    except MarketError as e:
                        msg = f"❌ {e}"
                    await _edit_or_reply(cq, msg, market_list_kb(await market.list_market()))
                    return
                if data == "mkt:sellmenu":
                    await _edit_or_reply(cq, "کالا برای فروش:", inv_sell_kb(await market.inventory(code)))
                    return
                if data.startswith("mkt:sell:"):
                    ic = data.split(":")[-1]
                    _PENDING_LIST[pid] = {"item": ic, "step": "qty"}
                    await _edit_or_reply(cq, "تعداد فروش را بنویسید:")
                    return
                if data == "mkt:mine":
                    rows = await db.fetch(
                        "SELECT * FROM market_listings WHERE seller_country=$1 AND active=1", (code,)
                    )
                    lines = ["آگهی‌های من"] + [f"#{r['id']} {r['item_code']} × {int(float(r['quantity']))}" for r in rows]
                    kb_rows = [[(f"لغو #{r['id']}", f"mkt:cancel:{r['id']}")] for r in rows]
                    kb_rows.append(back_home_row())
                    await _edit_or_reply(cq, "\n".join(lines) if rows else "آگهی فعالی ندارید", inline_rows(kb_rows))
                    return
                if data.startswith("mkt:cancel:"):
                    lid = int(data.split(":")[-1])
                    try:
                        msg = await market.cancel_listing(lid, code)
                    except MarketError as e:
                        msg = f"❌ {e}"
                    await _edit_or_reply(cq, msg)

            # trade
            if data.startswith("trd:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data == "trd:list":
                    offers = await trade.list_for(code)
                    lines = ["پیشنهادها"]
                    for o in offers:
                        lines.append(
                            f"#{o['id']} {o['from_country']}→{o['to_country']} "
                            f"{TRADEABLE.get(o['resource_code'], o['resource_code'])} "
                            f"× {int(float(o['quantity']))} | {o['status']}"
                        )
                    await _edit_or_reply(cq, "\n".join(lines), trade_offers_kb(offers, code))
                    return
                if data == "trd:new":
                    await _edit_or_reply(cq, "منبع را انتخاب کنید:", trade_res_kb())
                    return
                if data.startswith("trd:res:"):
                    res = data.split(":")[-1]
                    _PENDING_TRADE[pid] = {"res": res, "step": "target"}
                    await _edit_or_reply(cq, "کد کشور مقصد را بنویسید (مثلا IR):")
                    return
                if data.startswith("trd:ok:"):
                    try:
                        msg = await trade.accept(int(data.split(":")[-1]), code, pid)
                    except TradeError as e:
                        msg = f"❌ {e}"
                    await _edit_or_reply(cq, msg, trade_menu_kb())
                    return
                if data.startswith("trd:no:"):
                    try:
                        msg = await trade.reject(int(data.split(":")[-1]), code)
                    except TradeError as e:
                        msg = f"❌ {e}"
                    await _edit_or_reply(cq, msg, trade_menu_kb())
                    return

            # my / eco / cab / world / def (reuse prior patterns)
            if data.startswith("my:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                c, b, e = await _pack(db, code)
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
                elif data == "my:inv":
                    await _edit_or_reply(cq, await market.inventory_text(code), my_country_menu())
                elif data == "my:mil":
                    await _edit_or_reply(cq, await market.military_text(code), my_country_menu())
                elif data == "my:sectors":
                    secs = await db.fetch("SELECT * FROM production_sectors WHERE country_code=$1", (code,))
                    await _edit_or_reply(cq, views.sectors_card(secs), my_country_menu())
                return

            if data.startswith("eco:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                e = await db.fetchrow("SELECT * FROM country_economy WHERE country_code=$1", (code,))
                tax = float((e or {}).get("tax_rate") or 0.15)
                spend = float((e or {}).get("public_spending_rate") or 0.12)
                if data == "eco:status":
                    _, b, e = await _pack(db, code)
                    await _edit_or_reply(cq, views.economy_base_card(b or {}, e), economy_menu())
                elif data == "eco:tax_up":
                    await _edit_or_reply(cq, await management.set_tax_rate(code, min(0.5, tax + 0.02), pid), economy_menu())
                elif data == "eco:tax_down":
                    await _edit_or_reply(cq, await management.set_tax_rate(code, max(0.0, tax - 0.02), pid), economy_menu())
                elif data == "eco:spend_up":
                    await _edit_or_reply(cq, await management.set_spending_rate(code, min(0.5, spend + 0.02), pid), economy_menu())
                elif data == "eco:spend_down":
                    await _edit_or_reply(cq, await management.set_spending_rate(code, max(0.0, spend - 0.02), pid), economy_menu())
                elif data == "eco:tick":
                    r = await management.apply_budget_tick(code)
                    await _edit_or_reply(cq, f"✅ دوره بودجه | خزانه {int(r['treasury']):,}", economy_menu())
                return

            if data.startswith("cab:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data == "cab:list":
                    rows = await db.fetch("SELECT * FROM cabinet_members WHERE country_code=$1", (code,))
                    await _edit_or_reply(cq, views.cabinet_card(rows), cabinet_menu())
                elif data.startswith("cab:app:"):
                    _PENDING_APPOINT[pid] = data.split(":")[-1]
                    await _edit_or_reply(cq, "نام وزیر را بنویسید:", cabinet_menu())
                return

            if data.startswith("def:"):
                if not code:
                    await _edit_or_reply(cq, views.need_country())
                    return
                if data == "def:status":
                    await _edit_or_reply(cq, await market.military_text(code), defense_menu())
                elif data == "def:crisis":
                    rows = await countries.list_countries()
                    await _edit_or_reply(cq, "کشور هدف مدیریت بحران:", crisis_targets_kb(rows, code))
                elif data.startswith("def:crisis:"):
                    target = data.split(":")[-1]
                    await _edit_or_reply(cq, await market.crisis_resolve(code, target, pid), defense_menu())
                return

            if data.startswith("world:"):
                if data == "world:news":
                    items = await db.fetch("SELECT headline FROM news_items ORDER BY real_time DESC LIMIT 8")
                    await _edit_or_reply(cq, views.news_card(items, gdate), world_menu())
                elif data == "world:date":
                    from bot.ui.format import fa_date
                    await _edit_or_reply(cq, "تاریخ جهان\n" + fa_date(gdate), world_menu())
                elif data.startswith("world:list:"):
                    page = int(data.split(":")[-1])
                    rows = await countries.list_countries()
                    await _edit_or_reply(cq, views.world_list_card(rows, page), world_menu())
                return
        except Exception:
            log.exception("on_callback error")

    log.info(
        "handlers on_message=%s on_callback=%s",
        len(getattr(bot, "events", {}).get("on_message") or []),
        len(getattr(bot, "events", {}).get("on_callback") or []),
    )
