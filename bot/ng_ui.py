"""New Generation — complete Persian button UI."""
from __future__ import annotations

import logging

from bale import (
    MenuKeyboardMarkup,
    MenuKeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from modules.ng.catalog import CATALOG, CAT_FA, items_in_category
from modules.ng.guide import guide_menu_rows, guide_page, GUIDE_SECTIONS
from modules.ng.game import GameError

log = logging.getLogger(__name__)

BTN_MY = "🏛 کشور من"
BTN_ECO = "💰 اقتصاد"
BTN_SHOP = "🛒 فروشگاه"
BTN_INV = "📦 انبار من"
BTN_MKT = "🌐 بازار آزاد"
BTN_TRADE = "🚢 تجارت جهانی"
BTN_DIPLO = "🤝 روابط خارجی"
BTN_PEACE = "🕊 پیمان صلح"
BTN_ATTACK = "⚔️ حمله"
BTN_STMT = "📜 بیانیه رسمی"
BTN_WORLD = "🌍 جهان"
BTN_REPORT = "📊 گزارش‌ها"
BTN_PICK = "🗺 انتخاب کشور"
BTN_OWNER = "🛡 پنل مالک"
BTN_WORKSHOP = "🏭 کارگاه"
BTN_ABOUT = "ℹ️ درباره ما"
BTN_GUIDE = "📖 راهنمای بازی"
BTN_REF = "🎁 دعوت کردن"
BTN_TREATY = "⚖ پیمان‌ها"

_pending: dict[int, dict] = {}


def main_kb(is_owner: bool = False) -> MenuKeyboardMarkup:
    kb = MenuKeyboardMarkup()
    rows = [
        [BTN_REF],
        [BTN_MY, BTN_ECO],
        [BTN_WORKSHOP, BTN_SHOP],
        [BTN_INV, BTN_MKT],
        [BTN_TRADE, BTN_DIPLO],
        [BTN_PEACE, BTN_TREATY],
        [BTN_ATTACK, BTN_STMT],
        [BTN_WORLD, BTN_REPORT],
        [BTN_ABOUT, BTN_GUIDE],
        [BTN_PICK],
    ]
    for i, row in enumerate(rows, 1):
        for t in row:
            kb.add(MenuKeyboardButton(t), row=i)
    return kb


def ik(rows: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for ri, row in enumerate(rows, 1):
        for label, data in row:
            if label:
                kb.add(InlineKeyboardButton(str(label)[:64], callback_data=str(data)[:64]), row=ri)
    return kb


def back_row():
    return [("🔙 بازگشت", "ng:home")]


async def create_bot(token: str):
    from bale import Bot
    return Bot(token)


def _uid(obj):
    u = getattr(obj, "author", None) or getattr(obj, "from_user", None) or getattr(obj, "user", None)
    if not u:
        return None
    raw = getattr(u, "user_id", None) or getattr(u, "id", None)
    try:
        return int(raw)
    except Exception:
        return None


def _text(m):
    t = getattr(m, "content", None)
    if t is None:
        t = getattr(m, "text", None)
    return str(t or "").strip()


def _names(m):
    u = getattr(m, "author", None) or getattr(m, "from_user", None)
    if not u:
        return None, None
    un = getattr(u, "username", None)
    dn = f"{getattr(u, 'first_name', None) or ''} {getattr(u, 'last_name', None) or ''}".strip() or None
    return un, dn


async def reply(msg, text, kb=None):
    await msg.reply(str(text)[:3500], components=kb)


def register_handlers(bot, app_ctx: dict):
    game = app_ctx["game"]
    settings = app_ctx["settings"]
    # optional: store last group send helper
    app_ctx.setdefault("group_send", None)

    async def ensure(pid, username=None, display=None):
        await game.touch_player(pid, username, display)
        await game.assert_not_banned(pid)

    async def require_membership(pid, message_or_cq, is_callback=False):
        """Return True if allowed; otherwise send join prompt and return False."""
        if not await game.membership_enabled():
            return True
        if game.is_owner(pid):
            return True
        if await game.is_test_mode(pid):
            return True
        chats = await game.active_forced_chats()
        if not chats:
            return True
        missing = []
        api_errors = []
        for ch in chats:
            cid = ch["chat_id"]
            ok, detail = await game.verify_membership(bot, pid, cid)
            if ok:
                continue
            if detail == "api_error":
                api_errors.append(ch)
            else:
                missing.append(ch)
        # If API cannot verify but user was recently verified, trust cache
        if missing or api_errors:
            # still blocked if confirmed not member
            if missing:
                pass
            elif api_errors and not missing:
                # soft-allow if all are API errors and at least one cache hit attempted
                # re-check cache only
                still = []
                for ch in api_errors:
                    if not await game.membership_cache_ok(pid, ch["chat_id"]):
                        still.append(ch)
                if not still:
                    return True
                missing = still
        if not missing and not api_errors:
            return True
        if not missing and api_errors:
            # cannot verify - ask owner to make bot admin; block with clear message
            text = (
                "⚠️ ربات نتوانست عضویت شما را از API بررسی کند.\\n"
                "معمولاً به این دلیل است که ربات در گروه ادمین نیست.\\n"
                "پس از ادمین شدن ربات، دوباره «تأیید عضویت» را بزنید."
            )
            rows = [[("✅ تلاش مجدد تأیید عضویت", "ng:joincheck")]]
            target_rows = rows
            lines = [text]
            for ch in api_errors:
                link = ch.get("invite_link") or ""
                lines.append(f"• {ch.get('title') or ch['chat_id']}: {link}")
            body = "\\n".join(lines)
            if is_callback:
                msg = getattr(message_or_cq, "message", None)
                if msg:
                    await msg.reply(body[:3500], components=ik(target_rows))
            else:
                await reply(message_or_cq, body, ik(target_rows))
            return False
        rows = []
        for ch in missing:
            rows.append([(f"عضویت در {ch.get('title') or ch['chat_id']}", f"ng:joinlink:{ch['id']}")])
        rows.append([("✅ تأیید عضویت", "ng:joincheck")])
        lines = [
            "برای استفاده از ربات، ابتدا در گروه رسمی WORLD WAR عضو شوید.",
            "پس از عضویت، دکمه تأیید را بزنید.",
            "",
        ]
        for ch in missing:
            link = ch.get("invite_link") or ""
            lines.append(f"• {ch.get('title') or ch['chat_id']}: {link}")
        body = "\\n".join(lines)
        if is_callback:
            msg = getattr(message_or_cq, "message", None)
            if msg:
                await msg.reply(body[:3500], components=ik(rows))
        else:
            await reply(message_or_cq, body, ik(rows))
        return False


    @bot.listen("on_ready")
    async def on_ready():
        log.info("NG UI ready")

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
            try:
                await ensure(pid, username, display)
            except GameError as e:
                await reply(message, f"❌ {e}")
                return
            owner = game.is_owner(pid)
            # owner panel commands only
            if text in ("/admin", "/owner", "/panel"):
                if not owner:
                    await reply(message, "❌ دسترسی مجاز نیست.")
                    return
                rows = [
                    [("بازیکنان", "ng:o:players"), ("وضعیت جهان", "ng:o:world")],
                    [("🤝 مدیریت اتحادها", "ng:oally"), ("📊 آمار دعوت", "ng:orefstats")],
                    [("جنگ باز", "ng:owar:1"), ("جنگ بسته", "ng:owar:0")],
                    [("هسته‌ای فعال", "ng:onuke:1"), ("هسته‌ای خاموش", "ng:onuke:0")],
                    [("بیانیه‌ها", "ng:ostmt"), ("درخواست‌های NPT", "ng:onpt")],
                    [("🔕 در دسترس نیستم", "ng:oaway")],
                    [("تنظیم لاگ‌ها", "ng:ologs")],
                    [("📝 پیام /start", "ng:ostart"), ("ℹ️ درباره ما", "ng:oabout")],
                    [("🧪 حساب تستی", "ng:otest"), ("⚙️ عضویت اجباری", "ng:oforce")],
                    [("بن کاربر", "ng:oban"), ("آنبن کاربر", "ng:ounban")],
                    [("تغییر پول کشور", "ng:omoney")],
                    [("💰 گرفتن مالیات", "ng:otax"), ("⚖️ محکوم کردن کشور", "ng:ocondemn")],
                    [("🔴 ریست کامل جهان", "ng:oreset1")],
                ]
                await reply(message, "🛡 پنل مالک / سازمان ملل\nدستورات: /admin /owner /panel", ik(rows))
                return
            if text not in ("/start", "شروع", "منو", "menu") and text not in (BTN_ABOUT, BTN_GUIDE, BTN_REF):
                if not await require_membership(pid, message, False):
                    return
            owner = game.is_owner(pid)
            code = await game.player_country(pid)

            # ---- pending typed flows ----
            if pid in _pending:
                st = _pending[pid]
                kind = st.get("kind")
                if kind == "ref_code":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.apply_referral_code(pid, text.strip())
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "statement":
                    _pending.pop(pid, None)
                    if not code:
                        await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                        return
                    try:
                        msg = await game.submit_statement(code, pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "aid_money_amount":
                    _pending.pop(pid, None)
                    try:
                        amount = float(text.replace(",", "").replace("،", ""))
                        msg = await game.aid_money(code, st["dst"], amount, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "aid_army_qty":
                    _pending.pop(pid, None)
                    try:
                        qty = float(text.replace(",", ""))
                        msg = await game.aid_army(code, st["dst"], st["item"], qty, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "mkt_qty":
                    try:
                        st["qty"] = float(text.replace(",", ""))
                        st["kind"] = "mkt_price"
                        await reply(message, "قیمت واحد پیشنهادی را بنویسید:")
                    except ValueError:
                        await reply(message, "یک عدد معتبر بنویسید.")
                    return
                if kind == "mkt_price":
                    _pending.pop(pid, None)
                    try:
                        price = float(text.replace(",", ""))
                        msg = await game.market_create(code, st["item"], st["qty"], price, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ban_user":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.ban_user(pid, text, "پنل مالک")
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "unban_user":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.unban_user(pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "admin_money":
                    _pending.pop(pid, None)
                    try:
                        parts = text.split()
                        ccode, amount = parts[0].upper(), float(parts[1])
                        msg = await game.admin_money(pid, ccode, amount)
                    except Exception as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "reset_phrase":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.full_reset(pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return

                if kind == "global_tax_amount":
                    _pending.pop(pid, None)
                    try:
                        amount = float(text.replace(",", "").replace("،", ""))
                        result = await game.global_tax(pid, amount)
                        msg = (
                            f"✅ مالیات سراسری انجام شد\n"
                            f"مبلغ هر نفر: {int(result['amount']):,}\n"
                            f"تعداد مشمول: {result['taxed']}\n"
                            f"ردشده (موجودی کم): {result['skipped']}\n"
                            f"جمع واریز به سازمان ملل: {int(result['collected']):,}"
                        )
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "user_give_money":
                    _pending.pop(pid, None)
                    try:
                        amount = float(text.replace(",", "").replace("،", ""))
                        code = st["code"]
                        msg = await game.admin_money(pid, code, amount)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "user_take_money":
                    _pending.pop(pid, None)
                    try:
                        amount = float(text.replace(",", "").replace("،", ""))
                        msg = await game.admin_take_money(pid, st["code"], amount)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "user_tax":
                    _pending.pop(pid, None)
                    try:
                        amount = float(text.replace(",", "").replace("،", ""))
                        msg = await game.admin_tax_user(pid, st["code"], amount)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "condemn_speech":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.condemn_country(pid, st["code"], text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return

                if kind == "edit_start":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.set_setting(pid, "start_message", text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "edit_about":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.set_setting(pid, "about_message", text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return

            # ---- main menu ----
            if text in ("/start", "شروع", "منو", "menu"):
                try:
                    await game.record_start(pid)
                except Exception:
                    log.exception("record_start")
                start_msg = await game.get_setting("start_message", game.DEFAULT_START)
                await reply(message, start_msg, main_kb(owner))
                return

            if text == BTN_PICK:
                if code:
                    await reply(message, "شما هم‌اکنون یک کشور دارید.", main_kb(owner))
                    return
                rows = []
                for c in await game.list_countries():
                    if c.get("owner_player_id"):
                        rows.append([(f"❌ {c['flag']} {c['name_fa']} (دارای بازیکن)", "ng:busy")])
                    else:
                        rows.append([(f"✅ {c['flag']} {c['name_fa']}", f"ng:claim:{c['country_code']}")])
                rows.append(back_row())
                await reply(message, "🗺 کشور آزاد را انتخاب کنید:", ik(rows))
                return

            if text == BTN_MY:
                if not code:
                    await reply(message, "ابتدا «انتخاب کشور» را بزنید.", main_kb(owner))
                    return
                card = await game.country_card(code)
                rows = [
                    [("📦 انبار", "ng:go:inv"), ("💰 اقتصاد", "ng:go:eco")],
                    [("📜 گزارش", "ng:go:rep")],
                    back_row(),
                ]
                await reply(message, card, ik(rows))
                return

            if text == BTN_ECO:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                await reply(
                    message,
                    f"💰 اقتصاد {c['name_fa']}\n"
                    f"خزانه: {int(float(c['treasury'])):,} {c['currency_name_fa']}\n"
                    f"درآمد روزانه: {int(float(c['daily_income'])):,}\n"
                    f"هزینه نگهداری: {int(float(c['daily_expense'])):,}\n"
                    f"خالص روزانه: {int(float(c['daily_income'])-float(c['daily_expense'])):,}\n"
                    f"سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}",
                    main_kb(owner),
                )
                return

            if text == BTN_SHOP:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    log.exception("shop catalog seed")
                rows = []
                pair = []
                for cat, name in CAT_FA.items():
                    n = len(items_in_category(cat))
                    pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await reply(
                    message,
                    "🛒 فروشگاه\n\nدسته را انتخاب کنید.\nاولین ردیف: 💻 هک و امنیت — هکر پدافند و هکر دارایی\nسپس موشک‌ها، هوایی، دریایی، زمینی و پدافند.",
                    ik(rows),
                )
                return

            if text == BTN_INV:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                inv = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
                    (code,),
                )
                rows = []
                for r in inv[:20]:
                    name = game._cat.get(r["item_code"], {}).get("name_fa", r["item_code"])
                    rows.append([(f"فروش بازار: {name}", f"ng:sell:{r['item_code']}")])
                rows.append(back_row())
                await reply(message, await game.inventory_text(code), ik(rows) if inv else main_kb(owner))
                return

            if text == BTN_MKT:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                listings = await game.market_list(0)
                rows = []
                for L in listings:
                    name = game._cat.get(L["item_code"], {}).get("name_fa", L["item_code"])
                    rows.append([(
                        f"#{L['id']} {name} ×{int(float(L['quantity']))} | {int(float(L['unit_price'])):,}",
                        f"ng:mbuy:{L['id']}",
                    )])
                rows.append([("آگهی‌های من", "ng:mmine")])
                rows.append(back_row())
                await reply(message, "🌐 بازار آزاد جهانی", ik(rows))
                return

            if text == BTN_TRADE:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = [
                    [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                    back_row(),
                ]
                await reply(message, "🚢 تجارت و کمک بین کشورها", ik(rows))
                return

            if text == BTN_DIPLO:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = [
                    [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                    [("🕊 مدیریت صلح", "ng:peace:menu")],
                    back_row(),
                ]
                await reply(message, "🤝 روابط خارجی", ik(rows))
                return

            if text == BTN_PEACE:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = [
                    [("ارسال درخواست صلح", "ng:peace:new"), ("درخواست‌های ورودی", "ng:peace:inbox")],
                    [("پیمان‌های فعال", "ng:peace:active")],
                    back_row(),
                ]
                await reply(message, "🕊 پیمان صلح", ik(rows))
                return

            if text == BTN_ATTACK:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = [
                    [("⚔️ حمله نظامی", "ng:atkmenu")],
                    [("💻 هک و امنیت", "ng:cyber")],
                    [("🛡 وضعیت پدافند من", "ng:mydef")],
                    back_row(),
                ]
                await reply(message, "⚔️ عملیات نظامی و سایبری:", ik(rows))
                return

            if text == BTN_STMT:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "statement"}
                await reply(message, "متن بیانیه رسمی را بنویسید و ارسال کنید:", main_kb(owner))
                return

            if text == BTN_WORLD:
                await reply(message, await game.world_status_text(for_owner=owner), main_kb(owner))
                return

            if text == BTN_REPORT:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = await game.db.fetch(
                    "SELECT * FROM ng_activity WHERE country_code=$1 ORDER BY id DESC", (code,)
                )
                lines = ["📊 گزارش فعالیت‌ها"] + [f"• {r['summary'][:120]}" for r in rows[:15]]
                if len(lines) == 1:
                    lines.append("هنوز گزارشی نیست.")
                await reply(message, "\n".join(lines), main_kb(owner))
                return


            if text == BTN_WORKSHOP:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                await game.complete_due_jobs(code)
                rows = [
                    [("📊 وضعیت کارگاه", "ng:ws:status")],
                    [("⚛ تولید اورانیوم", "ng:ws:uranium"), ("🔬 فناوری صلح‌آمیز", "ng:ws:research")],
                    [("⬆️ ارتقای کارگاه", "ng:ws:upgrade")],
                    [("💣 ساخت بمب اتم", "ng:ws:bomb")],
                    back_row(),
                ]
                await reply(message, await game.workshop_status(code), ik(rows))
                return

            if text == BTN_ABOUT:
                about = await game.get_setting("about_message", game.DEFAULT_ABOUT)
                await reply(message, about, main_kb(owner))
                return

            if text == BTN_REF:
                text_r = await game.referral_panel_text(pid)
                rows = [
                    [("📋 نمایش کد دعوت", "ng:refcode")],
                    [("🎟 کد دعوت دارید؟", "ng:refenter")],
                    back_row(),
                ]
                await reply(message, text_r, ik(rows))
                return

            if text == BTN_GUIDE:
                rows = guide_menu_rows()
                await reply(
                    message,
                    "📖 راهنمای بازی\n\nبخش موردنظر را انتخاب کنید. همه توضیحات بر اساس امکانات واقعی بازی نوشته شده‌اند.",
                    ik(rows),
                )
                return

            if text == BTN_TREATY:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو NPT" if int(c["npt_member"]) else "غیرعضو NPT"
                rows = [
                    [("عضویت در NPT", "ng:npt:join"), ("خروج از NPT", "ng:npt:leave")],
                    back_row(),
                ]
                await reply(message, f"⚖ پیمان‌ها\nوضعیت فعلی: {st}", ik(rows))
                return

            # Owner panel is command-only: /admin /owner /panel

        except Exception:
            log.exception("on_message")
            try:
                await message.reply("خطای داخلی. دوباره تلاش کنید.", components=main_kb(False))
            except Exception:
                pass

    @bot.listen("on_callback")
    async def on_callback(cq):
        try:
            data = (getattr(cq, "data", None) or "").strip()
            pid = _uid(cq)
            if not pid or not data:
                return
            try:
                await ensure(pid)
            except GameError as e:
                msg = getattr(cq, "message", None)
                if msg:
                    await msg.reply(f"❌ {e}")
                return
            owner = game.is_owner(pid)
            code = await game.player_country(pid)

            msg = getattr(cq, "message", None)

            async def out(text, kb=None):
                if msg is not None:
                    await msg.reply(str(text)[:3500], components=kb or main_kb(owner))


            if data == "ng:guide" or data.startswith("ng:guide:"):
                if data == "ng:guide":
                    rows = guide_menu_rows()
                    await out(
                        "📖 راهنمای بازی\n\nبخش موردنظر را انتخاب کنید.",
                        ik(rows),
                    )
                    return
                parts = data.split(":")
                section = parts[2] if len(parts) > 2 else ""
                page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                text, rows = guide_page(section, page)
                await out(text, ik(rows))
                return

            # owner callbacks — server-side authorization
            if data.startswith("ng:o") or data.startswith("ng:owar") or data.startswith("ng:onuke") or data.startswith("ng:ostmt") or data.startswith("ng:onpt") or data.startswith("ng:ologs") or data.startswith("ng:ostart") or data.startswith("ng:oabout") or data.startswith("ng:oban") or data.startswith("ng:ounban") or data.startswith("ng:omoney") or data.startswith("ng:oreset") or data.startswith("ng:sapp") or data.startswith("ng:srej") or data.startswith("ng:nptok") or data.startswith("ng:nptno") or data.startswith("ng:logtoggle") or data.startswith("ng:otest") or data.startswith("ng:oforce") or data.startswith("ng:ou") or data.startswith("ng:otax") or data.startswith("ng:ocondemn") or data.startswith("ng:oureset") or data.startswith("ng:oally") or data.startswith("ng:oaway") or data.startswith("ng:orefstats"):
                if not owner:
                    await out("❌ دسترسی مجاز نیست.")
                    return
            elif data not in ("ng:home", "ng:joincheck", "ng:guide") and not data.startswith("ng:joinlink") and not data.startswith("ng:guide:"):
                if not await require_membership(pid, cq, True):
                    return

            if data in ("ng:home", "ng:busy"):
                await out("منوی اصلی" if data == "ng:home" else "این کشور دارای بازیکن است.")
                return

            if data.startswith("ng:claim:"):
                try:
                    c = await game.claim(pid, data.split(":")[-1])
                    await out("✅ کشور ثبت شد\n\n" + await game.country_card(c["country_code"]))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data.startswith("ng:go:"):
                if not code:
                    await out("کشور ندارید")
                    return
                go = data.split(":")[-1]
                if go == "inv":
                    await out(await game.inventory_text(code))
                elif go == "eco":
                    c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                    await out(f"خزانه: {int(float(c['treasury'])):,}\nدرآمد: {int(float(c['daily_income'])):,}")
                elif go == "rep":
                    rows = await game.db.fetch(
                        "SELECT summary FROM ng_activity WHERE country_code=$1 ORDER BY id DESC", (code,)
                    )
                    await out("\n".join(["گزارش"] + [f"• {r['summary'][:100]}" for r in rows[:10]]))
                return

            # shop
            if data.startswith("ng:shop:"):
                cat = data.split(":")[-1]
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    log.exception("shop catalog seed")
                items = items_in_category(cat)
                title = CAT_FA.get(cat, cat)
                if not items:
                    await out(f"در دسته «{title}» محصولی نیست. ربات را یک‌بار ری‌استارت کنید.")
                    return
                rows = []
                for i in items:
                    rows.append([(f"{i['name_fa']} — {int(i['unit_price']):,}", f"ng:item:{i['item_code']}")])
                rows.append([("🛒 سبد", "ng:cart"), ("⬅️ دسته‌ها", "ng:shophome")])
                rows.append(back_row())
                await out(f"🛒 {title}\n{len(items)} محصول:", ik(rows))
                return
            if data == "ng:shophome":
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    pass
                rows = []
                pair = []
                for cat, name in CAT_FA.items():
                    n = len(items_in_category(cat))
                    pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await out("🛒 فروشگاه — دسته را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:item:"):
                ic = data.split(":")[-1]
                it = game._cat[ic]
                rows = [
                    [("＋۱", f"ng:add:{ic}:1"), ("＋۵", f"ng:add:{ic}:5"), ("＋۱۰", f"ng:add:{ic}:10")],
                    [("سبد", "ng:cart"), ("تسویه", "ng:checkout")],
                    back_row(),
                ]
                await out(
                    f"{it['name_fa']}\n{it['description_fa']}\nقیمت: {int(it['unit_price']):,}\n"
                    f"درآمد روزانه: {int(it['daily_income']):,}\nنگهداری: {int(it['maintenance']):,}",
                    ik(rows),
                )
                return
            if data.startswith("ng:add:"):
                _, _, ic, q = data.split(":")
                await out(await game.cart_add(pid, ic, float(q)))
                return
            if data == "ng:cart":
                if not code:
                    await out("کشور ندارید")
                    return
                text, _, items = await game.cart_view(pid, code)
                rows = [[(f"🗑 {it['name_fa']}", f"ng:cdel:{it['item_code']}")] for it in items]
                rows.append([("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await out(text, ik(rows))
                return
            if data.startswith("ng:cdel:"):
                ic = data.split(":")[-1]
                msg_t = await game.cart_set(pid, ic, 0)
                if code:
                    text, _, items = await game.cart_view(pid, code)
                    rows = [[(f"🗑 {it['name_fa']}", f"ng:cdel:{it['item_code']}")] for it in items]
                    rows.append([("✅ تسویه", "ng:checkout")])
                    rows.append(back_row())
                    await out(msg_t + "\n\n" + text, ik(rows))
                else:
                    await out(msg_t)
                return
            if data == "ng:checkout":
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.checkout(pid, code))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            # market
            if data.startswith("ng:sell:"):
                if not code:
                    await out("کشور ندارید")
                    return
                _pending[pid] = {"kind": "mkt_qty", "item": data.split(":")[-1]}
                await out("تعداد برای فروش را بنویسید:")
                return
            if data.startswith("ng:mbuy:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.market_buy(int(data.split(":")[-1]), code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:mmine":
                if not code:
                    await out("کشور ندارید")
                    return
                rows_db = await game.db.fetch(
                    "SELECT * FROM ng_market WHERE seller_country=$1 AND active=1", (code,)
                )
                lines = ["آگهی‌های من"] + [
                    f"#{r['id']} {r['item_code']} ×{int(float(r['quantity']))}" for r in rows_db
                ]
                btns = [[(f"لغو #{r['id']}", f"ng:mcancel:{r['id']}")] for r in rows_db]
                btns.append(back_row())
                await out("\n".join(lines) if rows_db else "آگهی فعالی ندارید", ik(btns))
                return
            if data.startswith("ng:mcancel:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.market_cancel(int(data.split(":")[-1]), code))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            # trade / aid
            if data == "ng:trade:money":
                if not code:
                    await out("کشور ندارید")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aidm:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("مقصد کمک مالی:", ik(rows))
                return
            if data == "ng:trade:army":
                if not code:
                    await out("کشور ندارید")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aida:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("مقصد کمک نظامی:", ik(rows))
                return
            if data.startswith("ng:aidm:"):
                if not code:
                    await out("کشور ندارید")
                    return
                _pending[pid] = {"kind": "aid_money_amount", "dst": data.split(":")[-1]}
                await out("مبلغ کمک را بنویسید:")
                return
            if data.startswith("ng:aida:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                inv = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
                )
                mil = [r for r in inv if game._cat.get(r["item_code"], {}).get("category") in ("ground", "air", "sea", "defense")]
                rows = [[(game._cat.get(r["item_code"], {}).get("name_fa", r["item_code"]), f"ng:aiditem:{dst}:{r['item_code']}")] for r in mil]
                rows.append(back_row())
                await out("تجهیزات برای ارسال:", ik(rows) if mil else main_kb(owner))
                return
            if data.startswith("ng:aiditem:"):
                _, _, dst, item = data.split(":")
                _pending[pid] = {"kind": "aid_army_qty", "dst": dst, "item": item}
                await out("تعداد را بنویسید:")
                return

            # peace
            if data == "ng:peace:menu":
                rows = [
                    [("ارسال درخواست", "ng:peace:new"), ("ورودی‌ها", "ng:peace:inbox")],
                    [("فعال", "ng:peace:active")],
                    back_row(),
                ]
                await out("🕊 مدیریت صلح", ik(rows))
                return
            if data == "ng:peace:new":
                if not code:
                    await out("کشور ندارید")
                    return
                countries = [c for c in await game.list_countries() if c["country_code"] != code]
                rows = []
                for c in countries:
                    rows.append([(f"{c['name_fa']} — ۶س", f"ng:peaceq:{c['country_code']}:6")])
                    rows.append([(f"{c['name_fa']} — ۱۲س", f"ng:peaceq:{c['country_code']}:12")])
                rows.append(back_row())
                await out("کشور و مدت صلح:", ik(rows))
                return
            if data.startswith("ng:peaceq:"):
                if not code:
                    await out("کشور ندارید")
                    return
                _, _, dst, hours = data.split(":")
                try:
                    await out(await game.peace_request(code, dst, float(hours), pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:peace:inbox":
                if not code:
                    await out("کشور ندارید")
                    return
                pend = await game.pending_peace_for(code)
                rows = []
                lines = ["درخواست‌های صلح"]
                for p in pend:
                    lines.append(f"#{p['id']} {p['country_a']}↔{p['country_b']} ({p['duration_hours']}س)")
                    if p["country_b"] == code or p["country_a"] == code:
                        rows.append([
                            (f"✅ قبول #{p['id']}", f"ng:peaceok:{p['id']}"),
                            (f"❌ رد #{p['id']}", f"ng:peaceno:{p['id']}"),
                        ])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data == "ng:peace:active":
                if not code:
                    await out("کشور ندارید")
                    return
                act = await game.active_peace_for(code)
                lines = ["پیمان‌های فعال"]
                rows = []
                for p in act:
                    lines.append(f"#{p['id']} {p['country_a']}↔{p['country_b']} تا {p.get('ends_at')}")
                    rows.append([(f"پایان پیمان #{p['id']}", f"ng:peacebrk:{p['id']}")])
                rows.append(back_row())
                await out("\n".join(lines) if act else "پیمان فعالی نیست", ik(rows))
                return
            if data.startswith("ng:peaceok:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.peace_accept(int(data.split(":")[-1]), code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:peaceno:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.peace_reject(int(data.split(":")[-1]), code))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:peacebrk:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.peace_break(int(data.split(":")[-1]), code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return


            if data == "ng:atkmenu":
                if not code:
                    await out("کشور ندارید")
                    return
                ok, reason = await game.can_attack(code)
                if not ok:
                    await out(f"❌ {reason}")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:atk:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("⚔️ هدف حمله نظامی:", ik(rows) if countries else main_kb(owner))
                return
            if data == "ng:cyber":
                if not code:
                    await out("کشور ندارید")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:cybertgt:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("💻 کشور هدف عملیات سایبری:", ik(rows) if countries else main_kb(owner))
                return
            if data.startswith("ng:cybertgt:"):
                if not code:
                    await out("کشور ندارید")
                    return
                tgt = data.split(":")[-1]
                label = await game.country_label(tgt)
                rows = [
                    [("🛡 هکر پدافند", f"ng:cyberdef:{tgt}")],
                    [("💰 هکر دارایی", f"ng:cyberasset:{tgt}")],
                    back_row(),
                ]
                await out(f"💻 عملیات سایبری علیه {label}:", ik(rows))
                return
            if data.startswith("ng:cyberdef:"):
                if not code:
                    await out("کشور ندارید")
                    return
                tgt = data.split(":")[-1]
                try:
                    await out(await game.hack_defense(code, tgt, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:cyberasset:"):
                if not code:
                    await out("کشور ندارید")
                    return
                tgt = data.split(":")[-1]
                try:
                    await out(await game.hack_assets(code, tgt, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:mydef":
                if not code:
                    await out("کشور ندارید")
                    return
                await out(await game.cyber_status_text(code))
                return

            # attack
            if data.startswith("ng:atk:"):
                if not code:
                    await out("کشور ندارید")
                    return
                ok, reason = await game.can_attack(code)
                if not ok:
                    await out(f"❌ {reason}")
                    return
                dst = data.split(":")[-1]
                rows = []
                for kind, label in (("ground", "زمینی"), ("air", "هوایی"), ("sea", "دریایی")):
                    pwr, _ = await game.available_force(code, kind)
                    if pwr > 0:
                        rows.append([(f"{label} ۳۰٪", f"ng:fight:{dst}:{kind}:30"), (f"{label} ۵۰٪", f"ng:fight:{dst}:{kind}:50")])
                        rows.append([(f"{label} ۱۰۰٪", f"ng:fight:{dst}:{kind}:100")])
                # atomic option if has bomb
                bombs = await game.db.fetchrow(
                    "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='item_atom_bomb'",
                    (code,),
                )
                if bombs and float(bombs["quantity"]) >= 1:
                    rows.append([("☢️ حمله با بمب اتم", f"ng:nuke:{dst}")])
                if not rows:
                    await out("❌ هیچ نیروی قابل‌استفاده‌ای برای انواع حمله ندارید.")
                    return
                rows.append(back_row())
                dst_name = await game.country_label(dst)
                await out(f"عملیات علیه {dst_name} — فقط انواع دارای نیرو:", ik(rows))
                return
            if data.startswith("ng:fight:"):
                if not code:
                    await out("کشور ندارید")
                    return
                _, _, dst, kind, pct = data.split(":")
                try:
                    await out(await game.attack(code, dst, kind, float(pct), pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:nuke:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                rows = [[("✅ تأیید حمله اتمی", f"ng:nukego:{dst}"), ("❌ انصراف", "ng:home")]]
                await out(
                    f"⚠️ حمله اتمی به {dst}\n"
                    "یک بمب اتم از انبار مصرف می‌شود.\n"
                    "۲۵ تا ۳۵ درصد سلامت کشور هدف به‌صورت تصادفی کاهش می‌یابد.\n"
                    "ادامه؟",
                    ik(rows),
                )
                return
            if data.startswith("ng:nukego:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.attack_nuclear(code, data.split(":")[-1], pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            # owner panel

            # workshop
            if data.startswith("ng:ws:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    if data == "ng:ws:status":
                        await out(await game.workshop_status(code), ik([
                            [("⚛ اورانیوم", "ng:ws:uranium"), ("🔬 تحقیق", "ng:ws:research")],
                            [("⬆️ ارتقا", "ng:ws:upgrade")], back_row()
                        ]))
                    elif data == "ng:ws:uranium":
                        await out(await game.start_uranium_job(code, pid))
                    elif data == "ng:ws:research":
                        await out(await game.start_research_job(code, pid))
                    elif data == "ng:ws:upgrade":
                        await out(await game.workshop_upgrade(code, pid))
                    elif data == "ng:ws:bomb":
                        await out(await game.craft_atom_bomb(code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data.startswith("ng:npt:"):
                if not code:
                    await out("کشور ندارید")
                    return
                action = data.split(":")[-1]
                rows = [[("✅ تأیید درخواست", f"ng:nptgo:{action}"), ("❌ انصراف", "ng:home")]]
                label = "عضویت در NPT" if action == "join" else "خروج از NPT"
                await out(f"آیا از ارسال درخواست «{label}» مطمئن هستید؟\nپس از ارسال، مالک باید تأیید کند.", ik(rows))
                return
            if data.startswith("ng:nptgo:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.request_npt_change(code, pid, data.split(":")[-1]))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:onpt":
                rows_db = await game.pending_npt_list()
                btns = []
                lines = ["درخواست‌های NPT"]
                for r in rows_db[:15]:
                    label = "عضویت" if r["request_type"] == "join" else "خروج"
                    cn = await game.country_name_only(r["country_code"])
                    lines.append(f"#{r['id']} {cn} — {label} — بازیکن {r['player_id']}")
                    btns.append([
                        (f"✅#{r['id']}", f"ng:nptok:{r['id']}"),
                        (f"❌#{r['id']}", f"ng:nptno:{r['id']}"),
                    ])
                btns.append(back_row())
                await out("\n".join(lines) if rows_db else "درخواست معلقی نیست", ik(btns))
                return
            if data.startswith("ng:nptok:"):
                try:
                    await out(await game.review_npt(int(data.split(":")[-1]), True, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:nptno:"):
                try:
                    await out(await game.review_npt(int(data.split(":")[-1]), False, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:ostart":
                cur = await game.get_setting("start_message", game.DEFAULT_START)
                rows = [
                    [("✏️ ویرایش", "ng:ostart:edit"), ("↩️ پیش‌فرض", "ng:ostart:reset")],
                    back_row(),
                ]
                await out("📝 پیام /start فعلی:\n\n" + cur[:1500], ik(rows))
                return
            if data == "ng:ostart:edit":
                _pending[pid] = {"kind": "edit_start"}
                await out("متن جدید خوشامدگویی را ارسال کنید:")
                return
            if data == "ng:ostart:reset":
                try:
                    await out(await game.reset_setting(pid, "start_message"))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oabout":
                cur = await game.get_setting("about_message", game.DEFAULT_ABOUT)
                rows = [
                    [("✏️ ویرایش", "ng:oabout:edit"), ("↩️ پیش‌فرض", "ng:oabout:reset")],
                    back_row(),
                ]
                await out("ℹ️ متن درباره ما:\n\n" + cur[:1500], ik(rows))
                return
            if data == "ng:oabout:edit":
                _pending[pid] = {"kind": "edit_about"}
                await out("متن جدید درباره ما را ارسال کنید:")
                return
            if data == "ng:oabout:reset":
                try:
                    await out(await game.reset_setting(pid, "about_message"))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:oally":
                rows_db = await game.list_alliances()
                text = await game.alliances_summary_text()
                rows = []
                for p in rows_db[:20]:
                    a = await game.country_name_only(p["country_a"])
                    b = await game.country_name_only(p["country_b"])
                    rows.append([(f"#{p['id']} {a}↔{b}", f"ng:oally:{p['id']}")])
                rows.append(back_row())
                await out(text, ik(rows))
                return
            if data.startswith("ng:oally:"):
                try:
                    await out(await game.alliance_detail_text(int(data.split(":")[-1])))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oaway":
                cur = await game.get_owner_away()
                rows = [
                    [("🔕 فعال کردن", "ng:oaway:1"), ("🔔 خاموش کردن", "ng:oaway:0")],
                    back_row(),
                ]
                st = "فعال" if cur else "غیرفعال"
                await out(f"وضعیت «در دسترس نیستم»: {st}", ik(rows))
                return
            if data.startswith("ng:oaway:"):
                en = data.endswith(":1")
                try:
                    await out(await game.set_owner_away(pid, en))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:orefstats":
                await out(await game.referral_stats_text())
                return
            if data == "ng:refcode":
                row = await game.ensure_referral_row(pid)
                code = row["referral_code"]
                await out(
                    "📋 کد دعوت شما:\n\n"
                    + code
                    + "\n\nاین کد را کپی کنید و برای دوستتان بفرستید.\n"
                    "(ربات‌ها مستقیماً کلیپ‌بورد گوشی را کنترل نمی‌کنند.)"
                )
                return
            if data == "ng:refenter":
                _pending[pid] = {"kind": "ref_code"}
                await out("لطفاً کد دعوت دوستت رو وارد کن:")
                return

            if data == "ng:o:players" or data.startswith("ng:o:players:"):
                page = 0
                if data.startswith("ng:o:players:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                try:
                    stats = await game.player_stats()
                    players, total = await game.list_players_page(page)
                    pages = max(1, (total + game.PAGE_SIZE - 1) // game.PAGE_SIZE)
                    lines = [
                        "👥 کاربران",
                        f"مجموع ثبت‌نام‌شده: {stats['total']}",
                        f"فعال امروز (/start): {stats['active_today']}",
                        f"صفحه {page+1}/{pages}",
                        "",
                    ]
                    rows = []
                    for p in players:
                        cc = p.get("country_code")
                        cname = await game.country_name_only(cc) if cc else "نامشخص"
                        un = p.get("username") or p["player_id"]
                        label = f"{un} | {cname}"
                        rows.append([(label[:40], f"ng:ou:{p['player_id']}")])
                    nav = []
                    if page > 0:
                        nav.append(("⬅️ قبلی", f"ng:o:players:{page-1}"))
                    if (page + 1) * game.PAGE_SIZE < total:
                        nav.append(("بعدی ➡️", f"ng:o:players:{page+1}"))
                    if nav:
                        rows.append(nav)
                    rows.append(back_row())
                    await out("\n".join(lines), ik(rows))
                except Exception as e:
                    log.exception("players panel")
                    await out(f"❌ خطا در بخش کاربران: {e}")
                return

            if data == "ng:o:world":
                await out(await game.world_status_text(for_owner=owner))
                return
            if data.startswith("ng:owar:"):
                await out(await game.set_war(pid, data.endswith(":1")))
                return
            if data.startswith("ng:onuke:"):
                await out(await game.set_nuclear(pid, data.endswith(":1")))
                return
            if data == "ng:ostmt":
                rows_db = await game.db.fetch("SELECT * FROM ng_statements WHERE status='pending'")
                btns = []
                for s in rows_db[:15]:
                    cn = await game.country_name_only(s["country_code"])
                    btns.append([
                        (f"✅#{s['id']} {cn}", f"ng:sapp:{s['id']}"),
                        (f"❌#{s['id']}", f"ng:srej:{s['id']}"),
                    ])
                btns.append(back_row())
                await out("بیانیه‌های در انتظار", ik(btns) if rows_db else main_kb(owner))
                return
            if data.startswith("ng:sapp:"):
                try:
                    await out(await game.review_statement(int(data.split(":")[-1]), True, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:srej:"):
                try:
                    await out(await game.review_statement(int(data.split(":")[-1]), False, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ologs":
                flags = await game.get_log_flags()
                rows = []
                for k, v in flags.items():
                    rows.append([(f"{'🟢' if v else '🔴'} {k}", f"ng:logtoggle:{k}")])
                rows.append(back_row())
                await out("تنظیم انواع لاگ (لمس = تغییر وضعیت):", ik(rows))
                return
            if data.startswith("ng:logtoggle:"):
                kind = data.split(":")[-1]
                flags = await game.get_log_flags()
                try:
                    await out(await game.set_log_flag(pid, kind, not flags.get(kind, True)))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oban":
                _pending[pid] = {"kind": "ban_user"}
                await out("آیدی عددی یا @username بازیکن را بفرستید:")
                return
            if data == "ng:ounban":
                _pending[pid] = {"kind": "unban_user"}
                await out("آیدی عددی یا @username برای رفع بن:")
                return
            if data == "ng:omoney":
                _pending[pid] = {"kind": "admin_money"}
                await out("فرمت: CODE مبلغ\nمثال: IR 1000000")
                return
            if data == "ng:oreset1":
                await out(
                    "⚠ تمام داده‌های جهان پاک می‌شود.\nادامه؟",
                    ik([[("تأیید مرحله بعد", "ng:oreset2")], back_row()]),
                )
                return
            if data == "ng:oreset2":
                _pending[pid] = {"kind": "reset_phrase"}
                await out("عبارت زیر را دقیق بنویسید:\nریست کامل جهان")
                return


            if data == "ng:joincheck":
                if await require_membership(pid, cq, True):
                    await out("✅ عضویت تأیید شد. منوی اصلی در دسترس است.", main_kb(owner))
                return
            if data.startswith("ng:joinlink:"):
                chats = await game.list_forced_chats()
                cid = int(data.split(":")[-1])
                ch = next((c for c in chats if int(c["id"]) == cid), None)
                if ch:
                    await out(f"لینک عضویت:\n{ch.get('invite_link') or ch['chat_id']}")
                return


            if data.startswith("ng:ou:"):
                tid = int(data.split(":")[-1])
                try:
                    card = await game.player_admin_card(tid)
                except GameError as e:
                    await out(f"❌ {e}")
                    return
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code") or ""
                rows = [
                    [("🚫 بن", f"ng:ouban:{tid}"), ("✅ آن‌بن", f"ng:ouunban:{tid}")],
                    [("📦 دارایی‌ها", f"ng:ouinv:{tid}"), ("💰 پول", f"ng:oum:{tid}")],
                    [("NPT وضعیت", f"ng:ounpt:{tid}")],
                    [("➕ NPT", f"ng:ounptadd:{tid}"), ("➖ NPT", f"ng:ounptdel:{tid}")],
                    [("💵 دادن پول", f"ng:ougive:{tid}"), ("💸 گرفتن پول", f"ng:outake:{tid}")],
                    [("🧾 مالیات از کاربر", f"ng:outax:{tid}")],
                    [("♻️ ریست کردن کاربر", f"ng:oureset:{tid}")],
                    [("⬅️ لیست کاربران", "ng:o:players:0")],
                ]
                await out(card, ik(rows))
                return

            if data.startswith("ng:oureset:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (tid,))
                if not p:
                    await out("بازیکن یافت نشد")
                    return
                code = p.get("country_code")
                cname = await game.country_label(code) if code else "بدون کشور"
                rows = [
                    [("✅ تأیید ریست", f"ng:ouresetgo:{tid}"), ("❌ انصراف", f"ng:ou:{tid}")],
                ]
                text = (
                    f"آیا مطمئن هستید؟\n\nکاربر: {tid}\nکشور: {cname}\n\n"
                    "با ریست کردن این کاربر:\n"
                    "• کشور فعلی او آزاد می‌شود.\n"
                    "• مالکیت کشور حذف می‌شود.\n"
                    "• دارایی‌ها و پیشرفت کشور بازنشانی می‌شود.\n"
                    "• کاربر بدون کشور از ابتدا شروع می‌کند.\n"
                    "• بن بودن تغییر نمی‌کند.\n"
                    "• لاگ‌ها و سوابق مالی حفظ می‌شوند.\n\n"
                    "این عملیات قابل بازگشت نیست."
                )
                await out(text, ik(rows))
                return
            if data.startswith("ng:ouresetgo:"):
                tid = int(data.split(":")[-1])
                try:
                    await out(await game.reset_player(pid, tid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data.startswith("ng:ouban:"):
                tid = int(data.split(":")[-1])
                try:
                    await out(await game.ban(pid, tid, "پنل مالک"))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ouunban:"):
                tid = int(data.split(":")[-1])
                try:
                    await out(await game.unban(pid, tid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ouinv:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                await out(await game.inventory_text(code))
                return
            if data.startswith("ng:oum:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                c = await game.db.fetchrow("SELECT treasury, currency_name_fa FROM ng_countries WHERE country_code=$1", (code,))
                cname = await game.country_label(code)
                await out(f"💰 موجودی {cname}: {int(float(c['treasury'])):,} {c.get('currency_name_fa') or ''}")
                return
            if data.startswith("ng:ounpt:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                c = await game.db.fetchrow("SELECT npt_member, name_fa FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو" if int(c["npt_member"]) else "غیرعضو"
                await out(f"NPT — {c['name_fa']}: {st}")
                return
            if data.startswith("ng:ounptadd:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                try:
                    await out(await game.admin_set_npt(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ounptdel:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                try:
                    await out(await game.admin_set_npt(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ougive:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                _pending[pid] = {"kind": "user_give_money", "code": code}
                await out("مبلغ افزودن پول را بنویسید:")
                return
            if data.startswith("ng:outake:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                _pending[pid] = {"kind": "user_take_money", "code": code}
                await out("مبلغ برداشت را بنویسید:")
                return
            if data.startswith("ng:outax:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                _pending[pid] = {"kind": "user_tax", "code": code}
                await out("مبلغ مالیات اختصاصی را بنویسید:")
                return

            if data == "ng:otax":
                _pending[pid] = {"kind": "global_tax_amount"}
                await out("لطفاً مبلغ مالیات را به عدد وارد کنید:\nمثال: 10000")
                return
            if data == "ng:ocondemn":
                countries = [c for c in await game.list_countries(for_owner=True) if c.get("country_code") != "UN"]
                rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:ocondemn:{c['country_code']}")] for c in countries[:30]]
                rows.append(back_row())
                await out("کشور هدف محکومیت را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:ocondemn:"):
                code = data.split(":")[-1]
                _pending[pid] = {"kind": "condemn_speech", "code": code}
                await out("لطفاً متن سخنرانی سازمان ملل را بنویسید:")
                return

            if data == "ng:otest":
                active = await game.is_test_mode(pid)
                rows = [
                    [("🟢 فعال‌سازی تست", "ng:otest:on") if not active else ("🔴 خاموش کردن تست", "ng:otest:off")],
                    back_row(),
                ]
                await out(f"🧪 حساب تستی: {'فعال' if active else 'خاموش'}", ik(rows))
                return
            if data == "ng:otest:on":
                try:
                    await out(await game.enable_test_mode(pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:otest:off":
                try:
                    await out(await game.disable_test_mode(pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:oforce":
                enabled = await game.membership_enabled()
                chats = await game.list_forced_chats()
                lines = [f"عضویت اجباری: {'فعال' if enabled else 'خاموش'}", ""]
                for c in chats:
                    lines.append(f"#{c['id']} {c['title']} ({c['kind']}) {c['chat_id']} {'🟢' if int(c['active']) else '🔴'}")
                rows = [
                    [("فعال", "ng:oforce:on"), ("خاموش", "ng:oforce:off")],
                    [("افزودن @warworld3", "ng:oforce:adddefault")],
                ]
                for c in chats:
                    rows.append([(f"حذف #{c['id']}", f"ng:oforce:del:{c['id']}")])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data == "ng:oforce:on":
                await out(await game.set_membership_enabled(pid, True))
                return
            if data == "ng:oforce:off":
                await out(await game.set_membership_enabled(pid, False))
                return
            if data == "ng:oforce:adddefault":
                try:
                    await out(await game.add_forced_chat(pid, "@warworld3", "WORLD WAR", "https://ble.ir/warworld3", "group"))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:oforce:del:"):
                try:
                    await out(await game.remove_forced_chat(pid, int(data.split(":")[-1])))
                except GameError as e:
                    await out(f"❌ {e}")
                return

        except Exception:
            log.exception("on_callback")
