"""New Generation — complete Persian button UI."""
from __future__ import annotations

import logging

from pathlib import Path

from bale import (
    MenuKeyboardMarkup,
    MenuKeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from modules.ng.catalog import CATALOG, CAT_FA, items_in_category
from modules.ng.guide import guide_menu_rows, guide_page, GUIDE_SECTIONS
from modules.ng.game import GameError
from modules.ng.alliances import AllianceError, create_cost, RENAME_COST
from modules.ng.control import ControlError

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
BTN_ALLY = "🤝 اتحادها"
BTN_CTRL = "🏛 کنترل کشور"
BTN_TREATY = "⚖ پیمان‌ها"
BTN_WALLET = "💰 کیف پول"

_pending: dict[int, dict] = {}


def main_kb(is_owner: bool = False) -> MenuKeyboardMarkup:
    kb = MenuKeyboardMarkup()
    rows = [
        [BTN_REF, BTN_ALLY],
        [BTN_MY, BTN_ECO],
        [BTN_WORKSHOP, BTN_SHOP],
        [BTN_INV, BTN_MKT],
        [BTN_TRADE, BTN_DIPLO],
        [BTN_TREATY, BTN_WALLET],
        [BTN_ATTACK, BTN_STMT],
        [BTN_WORLD, BTN_REPORT],
        [BTN_ABOUT, BTN_GUIDE],
        [BTN_PICK],
    ]
    # dedupe texts while preserving order (fixes accidental double wallet)
    seen = set()
    clean = []
    for row in rows:
        nr = []
        for t in row:
            if t and t not in seen:
                seen.add(t)
                nr.append(t)
        if nr:
            clean.append(nr)
    for i, row in enumerate(clean, 1):
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


def cancel_row():
    return [("❌ انصراف", "ng:cancel"), ("🔙 منوی اصلی", "ng:home")]


MENU_TEXTS = {
    BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MKT, BTN_TRADE, BTN_DIPLO,
    BTN_PEACE, BTN_ATTACK, BTN_STMT, BTN_WORLD, BTN_REPORT, BTN_PICK,
    BTN_OWNER, BTN_WORKSHOP, BTN_ABOUT, BTN_GUIDE, BTN_REF, BTN_ALLY, BTN_CTRL, BTN_TREATY, BTN_WALLET,
    "/start", "شروع", "منو", "menu", "/admin", "/owner", "/panel",
}


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


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _extract_chat_id(target_msg):
    if target_msg is None:
        return None
    chat = getattr(target_msg, "chat", None)
    if chat is not None:
        cid = getattr(chat, "id", None) or getattr(chat, "chat_id", None)
        if cid is not None:
            return cid
    return getattr(target_msg, "chat_id", None)


def legendary_image_path(image_path):
    if not image_path:
        return None
    p = Path(str(image_path))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def load_photo_input(photo_path):
    """Local file as bytes for first-time upload."""
    if photo_path is None:
        return None
    p = Path(photo_path)
    if not p.exists() or not p.is_file():
        log.warning("legendary image missing: %s", p)
        return None
    data = p.read_bytes()
    if not data:
        log.warning("legendary image empty: %s", p)
        return None
    return InputFile(data, file_name=p.name)


def extract_photo_file_id(message) -> str | None:
    """Pick largest photo size file_id from a sent Message."""
    if message is None:
        return None
    photos = getattr(message, "photos", None) or getattr(message, "photo", None)
    if not photos:
        return None
    try:
        items = list(photos)
    except TypeError:
        items = [photos]
    best = None
    best_area = -1
    for ph in items:
        fid = getattr(ph, "file_id", None) or getattr(ph, "id", None)
        if not fid:
            continue
        w = int(getattr(ph, "width", 0) or 0)
        h = int(getattr(ph, "height", 0) or 0)
        area = w * h
        if area >= best_area:
            best_area = area
            best = str(fid)
    return best


async def send_photo_with_caption(
    target_msg, bot, photo_path, caption: str, kb=None, *, file_id: str | None = None
):
    """Send photo by cached file_id when possible so clients need not re-download."""
    caption = str(caption or "")[:1024]
    sent = None
    # 1) Prefer cached file_id (no re-upload)
    if file_id:
        try:
            photo = InputFile(str(file_id))
            if target_msg is not None and hasattr(target_msg, "reply_photo"):
                sent = await target_msg.reply_photo(photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent) or file_id
            chat_id = _extract_chat_id(target_msg)
            if chat_id is not None and bot is not None:
                sent = await bot.send_photo(chat_id, photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent) or file_id
        except Exception:
            log.exception("send by cached file_id failed; will re-upload")

    # 2) Upload local bytes once
    photo = load_photo_input(photo_path)
    if photo is not None:
        try:
            if target_msg is not None and hasattr(target_msg, "reply_photo"):
                sent = await target_msg.reply_photo(photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent)
        except Exception:
            log.exception("reply_photo failed path=%s", photo_path)
        try:
            chat_id = _extract_chat_id(target_msg)
            if chat_id is not None and bot is not None:
                photo2 = load_photo_input(photo_path)
                if photo2 is not None:
                    sent = await bot.send_photo(chat_id, photo2, caption=caption, components=kb)
                    return True, extract_photo_file_id(sent)
        except Exception:
            log.exception("bot.send_photo failed path=%s", photo_path)

    # 3) Text fallback
    try:
        if target_msg is not None:
            note = "\n\n(عکس آیتم روی سرور پیدا نشد)" if photo is None else ""
            await target_msg.reply((caption + note)[:3500], components=kb)
            return False, None
    except Exception:
        log.exception("photo fallback text failed")
    return False, None


async def send_legendary_shop(target_msg, bot, game, pid: int, out_text=None):
    defs = await game.legendary.list_defs()
    bal = await game.legendary.ensure_wallet(pid)
    intro = (
        "🎁 فروشگاه آیتم‌های لجندری" + "\n"
        + f"کیف پول شما: {int(bal):,} تومان" + "\n\n"
        + "هر آیتم جداگانه با عکس ارسال می‌شود. عکس‌ها پس از اولین بار از سرور Bale کش می‌شوند."
    )
    if out_text is not None:
        await out_text(intro)
    elif target_msg is not None:
        await target_msg.reply(intro)
    for d in defs:
        code = str(d["item_code"])
        card = game.legendary.card_text(d, bal)
        owned = await game.legendary.owns_item(pid, code)
        if owned:
            kb = ik([[("✔️ خریداری شده", "ng:legowned:" + code)]])
        else:
            kb = ik([[("✅ خرید این آیتم", "ng:legbuy:" + code)]])
        img = legendary_image_path(d.get("image_path"))
        cache_key = f"legendary:{code}"
        cached_id = await game.legendary.get_media_file_id(cache_key)
        ok, new_fid = await send_photo_with_caption(
            target_msg, bot, img, card, kb, file_id=cached_id
        )
        if new_fid and new_fid != cached_id:
            try:
                await game.legendary.set_media_file_id(cache_key, new_fid)
            except Exception:
                log.exception("cache file_id failed for %s", code)
        log.info(
            "legendary card item=%s ok=%s cached=%s new_fid=%s owned=%s",
            code, ok, bool(cached_id), bool(new_fid), owned,
        )


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
            # Direct money ops (bypass pending — more reliable)
            if owner and (text.startswith("/give ") or text.startswith("پول ")):
                try:
                    parts = text.split()
                    if len(parts) < 3:
                        await reply(message, "فرمت:\n/give شناسه مبلغ\nیا:\nپول شناسه مبلغ\nمثال: پول 123456 5000000")
                        return
                    tid = int(float(str(parts[1]).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))))
                    amount = game.parse_money_amount(parts[2])
                    msg = await game.admin_give_to_player(pid, tid, amount)
                    await reply(message, msg, main_kb(True))
                except GameError as e:
                    await reply(message, f"❌ {e}")
                except Exception:
                    log.exception("direct give")
                    await reply(message, "❌ خطا در واریز")
                return
            if owner and (text.startswith("/take ") or text.startswith("برداشت ")):
                try:
                    parts = text.split()
                    if len(parts) < 3:
                        await reply(message, "فرمت:\n/take شناسه مبلغ\nمثال: /take 123456 1000000")
                        return
                    tid = int(float(str(parts[1]).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))))
                    amount = game.parse_money_amount(parts[2])
                    msg = await game.admin_take_from_player(pid, tid, amount)
                    await reply(message, msg, main_kb(True))
                except GameError as e:
                    await reply(message, f"❌ {e}")
                except Exception:
                    log.exception("direct take")
                    await reply(message, "❌ خطا در برداشت")
                return

            if text in ("/admin", "/owner", "/panel"):
                if not owner:
                    await reply(message, "❌ دسترسی مجاز نیست.")
                    return
                rows = [
                    [("بازیکنان", "ng:o:players"), ("وضعیت جهان", "ng:o:world")],
                    [("🌐 مدیریت اتحادها", "ng:oally"), ("📊 آمار دعوت", "ng:orefstats")],
                    [("💵 پول همگانی", "ng:ogiveall"), ("💰 پرداخت درآمد روزانه", "ng:odaily")],
                    [("جنگ باز", "ng:owar:1"), ("جنگ بسته", "ng:owar:0")],
                    [("هسته‌ای فعال", "ng:onuke:1"), ("هسته‌ای خاموش", "ng:onuke:0")],
                    [("بیانیه‌ها", "ng:ostmt"), ("درخواست‌های NPT", "ng:onpt")],
                    [("📜 قوانین در انتظار", "ng:olaws")],
                    [("🔕 در دسترس نیستم", "ng:oaway")],
                    [("تنظیم لاگ‌ها", "ng:ologs")],
                    [("📝 پیام /start", "ng:ostart"), ("ℹ️ درباره ما", "ng:oabout")],
                    [("🧪 حساب تستی", "ng:otest"), ("⚙️ عضویت اجباری", "ng:oforce")],
                    [("بن کاربر", "ng:oban"), ("آنبن کاربر", "ng:ounban")],
                    [("تغییر پول کشور", "ng:omoney")],
                    [("💰 گرفتن مالیات", "ng:otax"), ("⚖️ محکوم کردن کشور", "ng:ocondemn")],
                    [("❤️ دیدن HP ها", "ng:ohp"), ("🧬 جان ۲ برابر کشورها", "ng:odblhp")],
                    [("🎁 مدیریت لجندری", "ng:oleg"), ("💰 شارژ کیف پول", "ng:owallet")],
                    [("⚙️ قیمت و استفاده لجندری", "ng:olegprices")],
                    [("🏷 قیمت فروشگاه", "ng:oprices"), ("🏷 تخفیف فروشگاه", "ng:odiscount")],
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
                # cancel pending if user pressed a main menu button
                if text in MENU_TEXTS or (text.startswith("/") and kind and kind.startswith("ally")):
                    _pending.pop(pid, None)
                    # fall through to normal menu handling below
                elif kind == "ally_name":
                    name = text.strip()[:40]
                    if len(name) < 3:
                        await reply(
                            message,
                            "نام اتحاد حداقل ۳ حرف باشد.\nدوباره بنویسید:",
                            ik([cancel_row()]),
                        )
                        return
                    st["name"] = name
                    st["kind"] = "ally_members"
                    _pending[pid] = dict(st)
                    await reply(
                        message,
                        f"نام: {name}\n\nظرفیت اعضا را وارد کنید (عدد بین ۲ تا ۲۰):",
                        ik([cancel_row()]),
                    )
                    return
                elif kind == "ally_members":
                    try:
                        mm = int(text.strip().replace(",", "").replace("،", ""))
                    except Exception:
                        await reply(message, "فقط عدد وارد کنید (۲ تا ۲۰):", ik([cancel_row()]))
                        return
                    if mm < 2 or mm > 20:
                        await reply(message, "ظرفیت اعضا باید بین ۲ تا ۲۰ باشد:", ik([cancel_row()]))
                        return
                    st["max_members"] = mm
                    st["kind"] = "ally_cap"
                    _pending[pid] = dict(st)
                    await reply(
                        message,
                        f"ظرفیت اعضا: {mm}\n\nظرفیت خزانه را وارد کنید (مثلاً 100000000):",
                        ik([cancel_row()]),
                    )
                    return
                elif kind == "ally_cap":
                    raw = text.replace(",", "").replace("،", "").replace(" ", "").strip()
                    try:
                        tc = float(raw)
                    except Exception:
                        await reply(message, "عدد معتبر برای ظرفیت خزانه وارد کنید:", ik([cancel_row()]))
                        return
                    if tc < 50_000_000:
                        await reply(message, "حداقل ظرفیت خزانه ۵۰٬۰۰۰٬۰۰۰ است:", ik([cancel_row()]))
                        return
                    st["treasury_cap"] = tc
                    name = st.get("name") or "?"
                    mm = int(st.get("max_members") or 2)
                    cost = create_cost(mm, tc)
                    st["kind"] = "ally_confirm"
                    st["cost"] = cost
                    _pending[pid] = dict(st)
                    rows = [
                        [("✅ تأیید و ساخت اتحاد", "ng:acreateyes")],
                        cancel_row(),
                    ]
                    preview = (
                        "📋 پیش‌نمایش اتحاد\n\n"
                        f"نام: {name}\n"
                        f"ظرفیت اعضا: {mm}\n"
                        f"ظرفیت خزانه: {int(tc):,}\n"
                        f"هزینه نهایی: {cost:,}\n\n"
                        "اگر درست است «تأیید و ساخت اتحاد» را بزنید."
                    )
                    await reply(message, preview, ik(rows))
                    return
                elif kind == "ally_confirm":
                    name = st.get("name") or "?"
                    mm = int(st.get("max_members") or 2)
                    tc = float(st.get("treasury_cap") or 100_000_000)
                    cost = int(st.get("cost") or create_cost(mm, tc))
                    rows = [
                        [("✅ تأیید و ساخت اتحاد", "ng:acreateyes")],
                        cancel_row(),
                    ]
                    await reply(
                        message,
                        (
                            "لطفاً از دکمه‌ها استفاده کنید.\n\n"
                            f"نام: {name}\n"
                            f"ظرفیت: {mm}\n"
                            f"خزانه: {int(tc):,}\n"
                            f"هزینه: {cost:,}"
                        ),
                        ik(rows),
                    )
                    return
                elif kind == "ally_deposit":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.alliances.deposit(pid, code, float(text.replace(",","")))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_withdraw":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.alliances.withdraw(pid, float(text.replace(",","")))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_rename":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.alliances.rename(pid, text.strip())
                    except (AllianceError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_emembers":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        msg = await game.alliances.expand_members(pid, int(raw))
                        _pending.pop(pid, None)
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}\nدوباره عدد بزرگ‌تر از ظرفیت فعلی را بفرستید."
                    await reply(message, msg, main_kb(owner) if "✅" in str(msg) else None)
                    return
                if kind == "ally_etreasury":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.alliances.expand_treasury(pid, float(text.replace(",","")))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_pay":
                    st["pay_country"] = st.get("pay_country")
                    try:
                        amount = float(text.replace(",",""))
                        msg = await game.alliances.pay_member(pid, st["pay_country"], amount)
                    except (AllianceError, GameError, ValueError, KeyError) as e:
                        msg = f"❌ {e}"
                    _pending.pop(pid, None)
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "set_shop_price":
                    st = _pending.pop(pid, {})
                    try:
                        price = float(text.replace(",", "").replace("،", "").strip())
                        msg = await game.set_item_unit_price(pid, st.get("item"), price)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception:
                        msg = "❌ عدد معتبر وارد کنید."
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "law_title":
                    st["title"] = text.strip()[:80]
                    st["kind"] = "law_body"
                    _pending[pid] = st
                    await reply(message, "متن کامل قانون را بنویسید (حداقل ۲۰ کاراکتر):", ik([cancel_row()]))
                    return
                if kind == "law_body":
                    st = _pending.pop(pid, {})
                    if not code:
                        await reply(message, "کشور ندارید", main_kb(owner))
                        return
                    try:
                        msg = await game.control.submit_law(code, pid, st.get("title") or "قانون", text)
                    except ControlError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "law_bonus":
                    st = _pending.pop(pid, {})
                    try:
                        bonus = float(text.replace(",", "").strip() or 0)
                    except Exception:
                        bonus = 0
                    try:
                        msg = await game.control.review_law(int(st["law_id"]), pid, True, bonus)
                    except ControlError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
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
                if kind == "owner_give_all":
                    try:
                        amount = game.parse_money_amount(text)
                        msg = await game.admin_give_all_players(pid, amount)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}")
                    except Exception:
                        log.exception("owner_give_all")
                        await reply(message, "❌ خطا در واریز همگانی")
                    return
                if kind == "admin_money":
                    try:
                        parts = text.replace("،", " ").replace(",", " ").split()
                        if len(parts) < 2:
                            await reply(message, "فرمت: کدکشور مبلغ\nمثال: IR 5000000", ik([cancel_row()]))
                            return
                        ccode = parts[0].upper()
                        amount = game.parse_money_amount(parts[1])
                        msg = await game.admin_money(pid, ccode, amount)
                        _pending.pop(pid, None)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception as e:
                        log.exception("admin_money pending")
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner) if "موفق" in str(msg) or "✅" in str(msg) else None)
                    if "✅" not in str(msg) and pid in _pending:
                        await reply(message, "دوباره مبلغ را بفرستید یا لغو کنید.", ik([cancel_row()]))
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
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("tid") or 0)
                        if not tid:
                            _pending.pop(pid, None)
                            await reply(message, "❌ شناسه بازیکن نامعتبر", main_kb(owner))
                            return
                        msg = await game.admin_give_to_player(pid, tid, amount)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}\nدوباره مبلغ را بفرستید یا لغو کنید.", ik([cancel_row()]))
                    except Exception:
                        log.exception("user_give_money")
                        await reply(message, "❌ خطا در افزودن پول. دوباره تلاش کنید.", ik([cancel_row()]))
                    return
                if kind == "user_take_money":
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("tid") or 0)
                        if not tid:
                            _pending.pop(pid, None)
                            await reply(message, "❌ شناسه بازیکن نامعتبر", main_kb(owner))
                            return
                        msg = await game.admin_take_from_player(pid, tid, amount)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}\nدوباره مبلغ را بفرستید.", ik([cancel_row()]))
                    except Exception:
                        log.exception("user_take_money")
                        await reply(message, "❌ خطا در برداشت پول.", ik([cancel_row()]))
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
                if kind == "owner_wallet_charge":
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("target"))
                        if amount <= 0:
                            await reply(message, "❌ مبلغ باید بزرگ‌تر از صفر باشد.", ik([cancel_row()]))
                            return
                        msg = await game.legendary.admin_charge_wallet(pid, tid, amount)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_wallet_charge")
                        await reply(message, f"❌ خطا در شارژ کیف پول: {e}", ik([cancel_row()]))
                    return
                if kind == "owner_leg_price":
                    try:
                        price = game.parse_money_amount(text)
                        ic = st.get("item")
                        msg = await game.legendary.set_price(pid, ic, price)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_leg_price")
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    return
                if kind == "owner_leg_uses":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        uses = int(float(raw.replace(",", "").replace("،", "").replace(" ", "")))
                        ic = st.get("item")
                        msg = await game.legendary.set_uses(pid, ic, uses)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_leg_uses")
                        await reply(message, "❌ عدد استفاده نامعتبر است. مثال: 20", ik([cancel_row()]))
                    return
                if kind == "owner_set_hp":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        hp = float(raw.replace(",", "").replace("،", ""))
                        tid = int(st.get("target"))
                        msg = await game.admin_set_hp(pid, tid, hp)
                        _pending.pop(pid, None)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_set_hp")
                        await reply(message, "❌ عدد HP نامعتبر است", ik([cancel_row()]))
                    return

            # ---- main menu ----
            if text in ("/start", "شروع", "منو", "menu"):
                _pending.pop(pid, None)
                try:
                    await game.record_start(pid)
                except Exception:
                    log.exception("record_start")
                start_msg = await game.get_setting("start_message", game.DEFAULT_START)
                await reply(message, start_msg, main_kb(owner))
                return

            if text == BTN_PICK:
                if code:
                    await reply(message, "شما هم‌اکنون یک کشور/گروهک دارید.", main_kb(owner))
                    return
                countries = await game.list_countries()
                free_c = [c for c in countries if not c.get("owner_player_id") and str(c.get("entity_type") or "country") != "group"]
                free_g = [c for c in countries if not c.get("owner_player_id") and str(c.get("entity_type") or "") == "group"]
                rows = []
                if free_c:
                    rows.append([("—— کشورها ——", "ng:noop")])
                for c in free_c[:40]:
                    rows.append([(f"{c.get('flag','')} {c['name_fa']}", f"ng:claim:{c['country_code']}")])
                if free_g:
                    rows.append([("—— گروهک‌ها ——", "ng:noop")])
                    for c in free_g:
                        rows.append([(f"⬛ {c['name_fa']}", f"ng:claim:{c['country_code']}")])
                rows.append(back_row())
                if not free_c and not free_g:
                    await reply(message, "همه کشورها و گروهک‌ها انتخاب شده‌اند.", main_kb(owner))
                else:
                    await reply(
                        message,
                        chr(10).join([
                            "🗺 انتخاب کنید:",
                            "کشورها و گروهک‌های آزاد را می‌بینید.",
                            "گروهک‌ها عضو NPT نمی‌شوند.",
                        ]),
                        ik(rows),
                    )
                return

            if text == BTN_MY:
                if not code:
                    await reply(message, "ابتدا «انتخاب کشور» را بزنید.", main_kb(owner))
                    return
                card = await game.country_card(code)
                rows = [
                    [("🏛 کنترل کشور", "ng:ctrl")],
                    [("📦 انبار", "ng:go:inv"), ("💰 اقتصاد", "ng:go:eco")],
                    [("📜 گزارش", "ng:go:rep")],
                    back_row(),
                ]
                await reply(message, card, ik(rows))
                return

            if text == BTN_CTRL:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                try:
                    text_c = await game.control.panel_text(code)
                except Exception:
                    log.exception("control panel")
                    text_c = "کنترل کشور"
                rows = [
                    [("📜 تصویب قوانین", "ng:ctrl:laws")],
                    [("🌊 کنترل تنگه‌ها", "ng:ctrl:straits")],
                    [("✈️ پروازها", "ng:ctrl:flights"), ("🚢 دریایی", "ng:ctrl:maritime")],
                    [("🌐 اینترنت", "ng:ctrl:net")],
                    back_row(),
                ]
                await reply(message, text_c, ik(rows))
                return

            if text == BTN_ECO:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                await reply(message, await game.economy_card(code), main_kb(owner))
                return


            if text == BTN_WALLET:
                try:
                    txt = await game.legendary.wallet_text(pid)
                except Exception:
                    log.exception("wallet")
                    txt = "خطا در کیف پول"
                rows = [
                    [("💳 واریز به کیف پول", "ng:wallet_deposit")],
                    [("🎁 فروشگاه لجندری", "ng:legshop")],
                    [("🎁 استفاده از آیتم", "ng:leguse")],
                    back_row(),
                ]
                await reply(message, txt, ik(rows))
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
                rows.append([("🎁 آیتم‌های لجندری", "ng:legshop")])
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
                await reply(
                    message,
                    "پیمان صلح حذف شده است.\nبه‌جای آن از «🤝 اتحادها» استفاده کنید.",
                    main_kb(owner),
                )
                return


            if text == BTN_ATTACK:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                meta = await game.db.fetchrow("SELECT war_enabled FROM world_meta WHERE id=1")
                war_on = bool(meta and int(meta.get("war_enabled") or 0))
                rows = []
                if war_on:
                    rows.append([("⚔️ حمله نظامی", "ng:atkmenu")])
                    rows.append([("💻 هک و امنیت", "ng:cyber")])
                    rows.append([("🛡 وضعیت پدافند من", "ng:mydef")])
                rows.append([("🎁 استفاده از آیتم لجندری", "ng:leguse")])
                rows.append(back_row())
                if war_on:
                    head = "⚔️ عملیات نظامی و سایبری:"
                else:
                    head = (
                        "⚠️ وضعیت جنگ در جهان بسته است." + "\n"
                        + "حمله نظامی / هک / پدافند فعلاً غیرفعال است." + "\n\n"
                        + "می‌توانید از آیتم‌های لجندری استفاده کنید:"
                    )
                await reply(message, head, ik(rows))
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


            if text == BTN_ALLY:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                mem = await game.alliances.member_of(code)
                if mem:
                    a = await game.alliances.get(mem["alliance_id"])
                    mems = await game.alliances.members(mem["alliance_id"])
                    labels = {}
                    for m in mems:
                        labels[m["country_code"]] = await game.country_label(m["country_code"])
                    text_a = game.alliances.card_text(a, mems, labels)
                    rows = [
                        [("👥 اعضا", f"ng:amembers:{a['id']}"), ("🏦 خزانه", f"ng:atreasure:{a['id']}")],
                        [("🚪 خروج از اتحاد", "ng:aleave")],
                    ]
                    if mem.get("role") == "founder":
                        rows.insert(1, [("⚙️ مدیریت", f"ng:amgmt:{a['id']}")])
                        rows.insert(2, [("💸 تقسیم مساوی خزانه", "ng:asplit")])
                    rows.append(back_row())
                    await reply(message, text_a, ik(rows))
                else:
                    allies = await game.alliances.list_active()
                    rows = [[("➕ ساخت اتحاد", "ng:acreate")]]
                    for a in allies[:25]:
                        mems = await game.alliances.members(a["id"])
                        rows.append([(f"{a['name']} ({len(mems)}/{a['max_members']})", f"ng:aview:{a['id']}")])
                    rows.append(back_row())
                    await reply(message, "🤝 اتحادها — فهرست فعال یا ساخت اتحاد جدید:", ik(rows))
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
                body = str(text)[:3500]
                comp = kb if kb is not None else main_kb(owner)
                try:
                    if msg is not None:
                        await msg.reply(body, components=comp)
                        return
                except Exception:
                    log.exception("out.reply failed")
                try:
                    chat = getattr(msg, "chat", None) if msg is not None else None
                    chat_id = getattr(chat, "id", None) or getattr(chat, "chat_id", None)
                    if chat_id is not None:
                        await bot.send_message(chat_id, body, components=comp)
                except Exception:
                    log.exception("out.send_message failed")


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
            if data.startswith("ng:o") or data.startswith("ng:owar") or data.startswith("ng:onuke") or data.startswith("ng:ostmt") or data.startswith("ng:onpt") or data.startswith("ng:ologs") or data.startswith("ng:ostart") or data.startswith("ng:oabout") or data.startswith("ng:oban") or data.startswith("ng:ounban") or data.startswith("ng:omoney") or data.startswith("ng:oreset") or data.startswith("ng:sapp") or data.startswith("ng:srej") or data.startswith("ng:nptok") or data.startswith("ng:nptno") or data.startswith("ng:logtoggle") or data.startswith("ng:otest") or data.startswith("ng:oforce") or data.startswith("ng:ou") or data.startswith("ng:otax") or data.startswith("ng:ocondemn") or data.startswith("ng:oureset") or data.startswith("ng:oally") or data.startswith("ng:oaway") or data.startswith("ng:orefstats") or data.startswith("ng:odbl") or data.startswith("ng:oudbl") or data.startswith("ng:olaws") or data.startswith("ng:lawok") or data.startswith("ng:lawno") or data.startswith("ng:oprice") or data.startswith("ng:odisc") or data.startswith("ng:ogiveall") or data.startswith("ng:odaily") or data.startswith("ng:ohp") or data.startswith("ng:osethp") or data.startswith("ng:oleg") or data.startswith("ng:owallet") or data.startswith("ng:olegprices"):
                if not owner:
                    await out("❌ دسترسی مجاز نیست.")
                    return
            elif data not in (
                "ng:home", "ng:cancel", "ng:joincheck", "ng:guide",
                "ng:acreate", "ng:acreateyes",
            ) and not data.startswith("ng:joinlink") and not data.startswith("ng:guide:") and not data.startswith("ng:a"):
                # ng:a* alliance flows allowed so user is not stuck mid-create
                if not await require_membership(pid, cq, True):
                    return

            if data in ("ng:home", "ng:busy", "ng:cancel"):
                _pending.pop(pid, None)
                await out(
                    "منوی اصلی — وضعیت قبلی لغو شد." if data != "ng:busy" else "این کشور دارای بازیکن است.",
                    main_kb(owner),
                )
                return

            # ---- Alliance System 2.0 callbacks ----
            if data == "ng:acreate":
                if not code:
                    await out("ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                if await game.alliances.member_of(code):
                    await out("شما هم‌اکنون عضو یک اتحاد هستید.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "ally_name"}
                await out(
                    "🏗 ساخت اتحاد\n\nنام اتحاد را بنویسید (حداقل ۳ حرف):",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:acreateyes":
                st = dict(_pending.get(pid) or {})
                if not code:
                    _pending.pop(pid, None)
                    await out("ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                name = (st.get("name") or "").strip()
                if not name or st.get("kind") not in ("ally_confirm", "ally_cap", None) and not st.get("max_members"):
                    # still try if we have name+members+cap
                    pass
                if not name or st.get("max_members") is None or st.get("treasury_cap") is None:
                    # keep pending if partial so user can restart cleanly
                    _pending.pop(pid, None)
                    rows = [[("➕ ساخت اتحاد", "ng:acreate")], cancel_row()]
                    await out(
                        "❌ اطلاعات ساخت ناقص یا منقضی شده.\nدوباره «➕ ساخت اتحاد» را بزنید.",
                        ik(rows),
                    )
                    return
                try:
                    mm = int(st.get("max_members") or 2)
                    tc = float(st.get("treasury_cap") or 100_000_000)
                    msg = await game.alliances.create(pid, code, name, mm, tc)
                    _pending.pop(pid, None)
                    await out(msg, main_kb(owner))
                except (AllianceError, GameError) as e:
                    # keep data so user can fix money and retry
                    st["kind"] = "ally_confirm"
                    _pending[pid] = st
                    rows = [
                        [("✅ تلاش دوباره", "ng:acreateyes")],
                        [("➕ شروع مجدد", "ng:acreate")],
                        cancel_row(),
                    ]
                    await out(f"❌ ساخت انجام نشد:\n{e}", ik(rows))
                except Exception as e:
                    _pending.pop(pid, None)
                    log.exception("alliance create")
                    await out(f"❌ خطای سیستمی ساخت اتحاد.\nدوباره تلاش کنید.", main_kb(owner))
                return
            if data.startswith("ng:aview:"):
                aid = int(data.split(":")[-1])
                a = await game.alliances.get(aid)
                if not a or a.get("status") != "active":
                    await out("اتحاد یافت نشد")
                    return
                mems = await game.alliances.members(aid)
                labels = {}
                for m in mems:
                    labels[m["country_code"]] = await game.country_label(m["country_code"])
                text_a = game.alliances.card_text(a, mems, labels)
                rows = [[("➕ عضویت در اتحاد", f"ng:ajoin:{aid}")], back_row()]
                await out(text_a, ik(rows))
                return
            if data.startswith("ng:ajoin:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.alliances.join(pid, code, int(data.split(":")[-1])))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:aleave":
                rows = [[("✅ تأیید خروج", "ng:aleaveyes"), ("❌ انصراف", "ng:home")]]
                await out("از اتحاد خارج می‌شوید؟", ik(rows))
                return
            if data == "ng:aleaveyes":
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.alliances.leave(pid, code))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:atreasure:"):
                rows = [
                    [("➕ واریز", "ng:adep"), ("➖ برداشت (بنیان‌گذار)", "ng:awith")],
                    [("💸 تقسیم مساوی", "ng:asplit")],
                    back_row(),
                ]
                await out("🏦 خزانه اتحاد", ik(rows))
                return
            if data == "ng:adep":
                _pending[pid] = {"kind": "ally_deposit"}
                await out("مبلغ واریز را وارد کنید:")
                return
            if data == "ng:awith":
                _pending[pid] = {"kind": "ally_withdraw"}
                await out("مبلغ برداشت را وارد کنید:")
                return
            if data == "ng:asplit":
                try:
                    await out(await game.alliances.equal_split(pid))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:amembers:"):
                aid = int(data.split(":")[-1])
                mems = await game.alliances.members(aid)
                lines = ["👥 اعضای اتحاد"]
                for m in mems:
                    role = "👑 بنیان‌گذار" if m["role"] == "founder" else "عضو"
                    label = await game.country_label(m["country_code"])
                    lines.append(f"{role}: {label}")
                await out("\n".join(lines))
                return
            if data.startswith("ng:amgmt:"):
                aid = int(data.split(":")[-1])
                rows = [
                    [("✏️ تغییر نام", "ng:arename")],
                    [("⬆️ ظرفیت اعضا", "ng:aemembers"), ("⬆️ ظرفیت خزانه", "ng:aetreasury")],
                    [("🚫 اخراج عضو", f"ng:akicklist:{aid}")],
                    [("🗑 انحلال اتحاد", f"ng:adissolve:{aid}")],
                    back_row(),
                ]
                await out("⚙️ مدیریت اتحاد", ik(rows))
                return
            if data == "ng:arename":
                _pending[pid] = {"kind": "ally_rename"}
                await out(f"نام جدید را بنویسید (هزینه {RENAME_COST:,}):")
                return
            if data == "ng:aemembers":
                _pending[pid] = {"kind": "ally_emembers"}
                await out("ظرفیت جدید اعضا (بزرگ‌تر از فعلی):")
                return
            if data == "ng:aetreasury":
                _pending[pid] = {"kind": "ally_etreasury"}
                await out("ظرفیت جدید خزانه:")
                return
            if data.startswith("ng:akicklist:"):
                aid = int(data.split(":")[-1])
                mems = await game.alliances.members(aid)
                rows = []
                for m in mems:
                    if m["role"] == "founder":
                        continue
                    label = await game.country_label(m["country_code"])
                    rows.append([(f"اخراج {label}", f"ng:akick:{m['country_code']}")])
                rows.append(back_row())
                await out("عضو برای اخراج:", ik(rows) if rows else main_kb(owner))
                return
            if data.startswith("ng:akick:"):
                try:
                    await out(await game.alliances.kick(pid, data.split(":")[-1]))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:adissolve:"):
                aid = int(data.split(":")[-1])
                rows = [[("✅ تأیید انحلال", f"ng:adissolveyes:{aid}"), ("❌ انصراف", "ng:home")]]
                await out("اتحاد منحل شود؟ خزانه به بنیان‌گذار برمی‌گردد.", ik(rows))
                return
            if data.startswith("ng:adissolveyes:"):
                try:
                    await out(await game.alliances.dissolve(pid, int(data.split(":")[-1]), is_owner=owner))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oally":
                allies = await game.alliances.list_active()
                lines = [f"🌐 اتحادهای فعال: {len(allies)}"]
                rows = []
                for a in allies[:30]:
                    mems = await game.alliances.members(a["id"])
                    lines.append(
                        f"#{a['id']} {a['name']} | {len(mems)}/{a['max_members']} | خزانه {int(float(a['treasury'])):,}"
                    )
                    rows.append([
                        (f"جزئیات {a['name']}", f"ng:oallyv:{a['id']}"),
                        (f"منحل #{a['id']}", f"ng:oallyd:{a['id']}"),
                    ])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:oallyv:"):
                aid = int(data.split(":")[-1])
                a = await game.alliances.get(aid)
                if not a:
                    await out("نیست")
                    return
                mems = await game.alliances.members(aid)
                labels = {m["country_code"]: await game.country_label(m["country_code"]) for m in mems}
                await out(game.alliances.card_text(a, mems, labels))
                return
            if data.startswith("ng:oallyd:"):
                try:
                    await out(await game.alliances.dissolve(pid, int(data.split(":")[-1]), is_owner=True))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
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
                items = await game.list_catalog_by_category(cat)
                title = CAT_FA.get(cat, cat)
                if not items:
                    await out(f"در دسته «{title}» محصولی نیست. ربات را یک‌بار ری‌استارت کنید.")
                    return
                disc = await game.get_shop_discount_pct()
                rows = []
                for i in items:
                    p = int(float(i.get("price_eff") or i["unit_price"]))
                    tag = f" (−{int(disc)}٪)" if disc else ""
                    rows.append([(f"{i['name_fa']} — {p:,}{tag}", f"ng:item:{i['item_code']}")])
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
                rows.append([("🎁 آیتم‌های لجندری", "ng:legshop")])
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await out("🛒 فروشگاه — دسته را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:item:"):
                ic = data.split(":")[-1]
                await game._reload_catalog_prices()
                it = game._cat.get(ic) or {}
                if not it:
                    await out("آیتم یافت نشد")
                    return
                disc = await game.get_shop_discount_pct()
                base = float(it.get("unit_price") or 0)
                eff = base * (1 - disc / 100.0) if disc else base
                price_line = f"قیمت: {int(eff):,}"
                if disc:
                    price_line += f" (پایه {int(base):,} با تخفیف {int(disc)}٪)"
                rows = [
                    [("＋۱", f"ng:add:{ic}:1"), ("＋۵", f"ng:add:{ic}:5"), ("＋۱۰", f"ng:add:{ic}:10")],
                    [("سبد", "ng:cart"), ("تسویه", "ng:checkout")],
                    back_row(),
                ]
                await out(
                    f"{it.get('name_fa')}\n{it.get('description_fa')}\n{price_line}\n"
                    f"درآمد روزانه: {int(float(it.get('daily_income') or 0)):,}\n"
                    f"نگهداری: {int(float(it.get('maintenance') or 0)):,}",
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

            # peace removed — redirect to alliances
            if data.startswith("ng:peace"):
                await out("پیمان صلح حذف شده. از منوی 🤝 اتحادها استفاده کنید.")
                return



            if data == "ng:noop":
                await out("این فقط یک عنوان است.")
                return

            
            # ---- legendary items ----
            if data == "ng:wallet_deposit":
                await out(
                    "💳 شارژ کیف پول\n\n"
                    "لطفاً برای شارژ کیف پول خود از طریق آیدی زیر به مالک پیام دهید و درخواست شارژ کنید.\n\n"
                    "آیدی مالک: @commander04",
                    ik([back_row()]),
                )
                return
            if data == "ng:legshop":
                await send_legendary_shop(msg, bot, game, pid, out_text=out)
                return
            if data.startswith("ng:legowned:"):
                await out(
                    "✔️ این آیتم را قبلاً خریداری کرده‌اید و هنوز استفاده باقی دارد."
                    + "\n"
                    + "نیازی به خرید مجدد نیست. پس از اتمام استفاده‌ها دوباره می‌توانید بخرید."
                )
                return
            if data.startswith("ng:legitem:"):
                code_i = data.split(":")[-1]
                d = await game.legendary.get_def(code_i)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                bal = await game.legendary.ensure_wallet(pid)
                owned = await game.legendary.owns_item(pid, code_i)
                if owned:
                    kb = ik([[("✔️ خریداری شده", f"ng:legowned:{code_i}")]])
                else:
                    kb = ik([[("✅ خرید این آیتم", f"ng:legbuy:{code_i}")]])
                cache_key = f"legendary:{code_i}"
                cached_id = await game.legendary.get_media_file_id(cache_key)
                ok, new_fid = await send_photo_with_caption(
                    msg, bot, legendary_image_path(d.get("image_path")),
                    game.legendary.card_text(d, bal), kb, file_id=cached_id,
                )
                if new_fid and new_fid != cached_id:
                    try:
                        await game.legendary.set_media_file_id(cache_key, new_fid)
                    except Exception:
                        log.exception("cache file_id")
                return
            if data.startswith("ng:legbuy:"):
                code_i = data.split(":")[-1]
                try:
                    if await game.legendary.owns_item(pid, code_i):
                        await out(
                            "✔️ این آیتم را قبلاً خریده‌اید و هنوز استفاده باقی دارد."
                            + "\n"
                            + "تا تمام شدن استفاده‌ها خرید مجدد ممکن نیست.",
                            ik([
                                [("🎁 بازگشت به فروشگاه لجندری", "ng:legshop")],
                                [("🎁 استفاده از آیتم", "ng:leguse")],
                                back_row(),
                            ]),
                        )
                        return
                    result = await game.legendary.buy(pid, code_i)
                    await out(
                        result,
                        ik([
                            [("🎁 بازگشت به فروشگاه لجندری", "ng:legshop")],
                            [("🎁 استفاده از آیتم", "ng:leguse")],
                            back_row(),
                        ]),
                    )
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:leguse":
                summary = await game.legendary.inventory_summary(pid)
                if not summary:
                    await out("آیتم لجندری قابل‌استفاده‌ای ندارید.", ik([back_row()]))
                    return
                rows = []
                lines = ["🎁 لیست آیتم‌های لجندری شما:", ""]
                for s in summary:
                    lines.append(f"• {s['name_fa']} | موجودی:{s['stacks']} | استفاده:{s['uses_left']}")
                    rows.append([(f"{s['name_fa']} ({s['uses_left']})", f"ng:legpick:{s['item_code']}")])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:legpick:"):
                code_i = data.split(":")[-1]
                d = await game.legendary.get_def(code_i)
                if not d:
                    await out("آیتم نامعتبر")
                    return
                mode = d.get("target_mode") or "other"
                if mode == "self":
                    rows = [[("✅ تأیید استفاده روی کشور خودم", f"ng:leggo:{code_i}:SELF")], back_row()]
                    await out(
                        f"{d['name_fa']}\n{d['power_fa']}\n\nروی کشور خودتان اعمال می‌شود. تأیید؟",
                        ik(rows),
                    )
                    return
                countries = [
                    c for c in await game.list_countries()
                    if c.get("owner_player_id") and c["country_code"] != code
                ]
                rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:leggo:{code_i}:{c['country_code']}")] for c in countries[:30]]
                rows.append(back_row())
                await out(f"{d['name_fa']}\n{d['power_fa']}\n\nهدف را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:leggo:"):
                parts = data.split(":")
                if len(parts) < 4:
                    await out("❌ درخواست نامعتبر است. دوباره از منوی آیتم لجندری شروع کنید.")
                    return
                code_i = parts[2]
                tgt = parts[3]
                if not code:
                    await out("❌ ابتدا باید کشور داشته باشید.")
                    return
                if tgt == "SELF":
                    tgt = code
                if not code_i:
                    await out("❌ آیتم نامعتبر")
                    return
                try:
                    result = await game.legendary.use_item(pid, code_i, tgt)
                    try:
                        summary = await game.legendary.inventory_summary(pid)
                        left_line = ""
                        for s in summary:
                            if s["item_code"] == code_i:
                                left_line = chr(10) + f"📦 باقی‌مانده این آیتم: {s['uses_left']} استفاده"
                                break
                        if not left_line:
                            left_line = chr(10) + "📦 این آیتم دیگر استفاده باقی‌مانده ندارد (تمام شد)."
                        result = result + left_line
                    except Exception:
                        pass
                    await out(
                        result,
                        ik([
                            [("🎁 استفاده دوباره", "ng:leguse")],
                            back_row(),
                        ]),
                    )
                except Exception as e:
                    log.exception("leggo use_item %s -> %s", code_i, tgt)
                    await out(f"❌ {e}")
                return

            # owner legendary mgmt
            if data == "ng:oleg" or data.startswith("ng:oleg:"):
                page = 0
                if data.startswith("ng:oleg:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                players, total = await game.list_players_page(page)
                rows = []
                for p in players:
                    name = p.get("display_name") or p.get("username") or str(p["player_id"])
                    rows.append([(f"{name} ({p['player_id']})", f"ng:olegp:{p['player_id']}")])
                nav = []
                if page > 0:
                    nav.append(("⬅️", f"ng:oleg:{page-1}"))
                if (page + 1) * game.PAGE_SIZE < total:
                    nav.append(("➡️", f"ng:oleg:{page+1}"))
                if nav:
                    rows.append(nav)
                rows.append(back_row())
                await out("🎁 مدیریت آیتم لجندری — بازیکن را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:olegp:"):
                tid = int(data.split(":")[-1])
                try:
                    block = await game.legendary.admin_player_legendary_block(tid)
                except Exception as e:
                    block = str(e)
                defs = await game.legendary.list_defs()
                rows = [[(f"➕ {d['name_fa']}", f"ng:oleggive:{tid}:{d['item_code']}")] for d in defs[:5]]
                rows.append([("➖ حذف سماور", f"ng:olegdel:{tid}:leg_samovar")])
                rows.append([("💰 شارژ کیف پول", f"ng:owalletsel:{tid}")])
                rows.append([("👤 پروفایل", f"ng:ou:{tid}")])
                rows.append(back_row())
                await out(f"بازیکن {tid}\n{block}", ik(rows))
                return
            if data.startswith("ng:oleggive:"):
                _, _, tid, ic = data.split(":", 3)
                try:
                    msg = await game.legendary.admin_give_item(pid, int(tid), ic, 1)
                    await out(msg)
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:olegdel:"):
                _, _, tid, ic = data.split(":", 3)
                try:
                    msg = await game.legendary.admin_remove_item(pid, int(tid), ic, 1)
                    await out(msg)
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:owallet" or data.startswith("ng:owallet:"):
                page = 0
                if data.startswith("ng:owallet:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                page = max(0, page)
                players, total = await game.list_players_page(page)
                page_size = getattr(game, "PAGE_SIZE", 8) or 8
                pages = max(1, (total + page_size - 1) // page_size)
                if page >= pages and total > 0:
                    page = pages - 1
                    players, total = await game.list_players_page(page)
                rows = []
                for p in players:
                    name = p.get("display_name") or p.get("username") or "بدون‌نام"
                    cc = p.get("country_code") or "—"
                    pid_s = p.get("player_id")
                    rows.append([(f"{name} | {cc} | {pid_s}", f"ng:owalletsel:{pid_s}")])
                nav = []
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:owallet:{page-1}"))
                if (page + 1) * page_size < total:
                    nav.append(("بعدی ➡️", f"ng:owallet:{page+1}"))
                if nav:
                    rows.append(nav)
                rows.append(back_row())
                await out(
                    "💰 شارژ کیف پول" + "\n"
                    + f"صفحه {page+1}/{pages} — کل بازیکن: {total}" + "\n"
                    + "بازیکن را انتخاب کنید:",
                    ik(rows),
                )
                return
            if data.startswith("ng:owalletsel:"):
                tid = int(data.split(":")[-1])
                if not game.is_owner(pid):
                    await out("❌ فقط مالک")
                    return
                bal = await game.legendary.ensure_wallet(tid)
                p = await game.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (tid,))
                name = (p or {}).get("display_name") or (p or {}).get("username") or str(tid)
                cc = (p or {}).get("country_code") or "—"
                _pending[pid] = {"kind": "owner_wallet_charge", "target": tid}
                await out(
                    "💰 شارژ کیف پول" + "\n"
                    + f"بازیکن: {name}" + "\n"
                    + f"شناسه: {tid}" + "\n"
                    + f"کشور: {cc}" + "\n"
                    + f"موجودی فعلی: {int(bal):,} تومان" + "\n\n"
                    + "مبلغ شارژ را به عدد بفرستید." + "\n"
                    + "مثال: 2000",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:olegprices":
                defs = await game.legendary.list_defs()
                rows = []
                for d in defs:
                    uses = int(d.get("uses_per_unit") or 20)
                    rows.append([(
                        f"{d['name_fa']} | {int(float(d['price'])):,}ت | {uses}بار",
                        f"ng:olegcfg:{d['item_code']}",
                    )])
                rows.append(back_row())
                await out(
                    "⚙️ تنظیم فروشگاه لجندری" + "\n"
                    + "آیتم را انتخاب کنید (قیمت / تعداد استفاده):",
                    ik(rows),
                )
                return
            if data.startswith("ng:olegcfg:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                uses = int(d.get("uses_per_unit") or 20)
                await out(
                    f"🎁 {d['name_fa']}" + "\n"
                    + f"قیمت فعلی: {int(float(d['price'])):,} تومان" + "\n"
                    + f"استفاده فعلی هر خرید: {uses} بار" + "\n\n"
                    + "کدام را تغییر می‌دهید؟",
                    ik([
                        [("💰 تغییر قیمت", f"ng:olegprice:{ic}")],
                        [("🔢 تغییر تعداد استفاده", f"ng:oleguses:{ic}")],
                        back_row(),
                    ]),
                )
                return
            if data.startswith("ng:olegprice:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                _pending[pid] = {"kind": "owner_leg_price", "item": ic}
                await out(
                    f"قیمت فعلی {d['name_fa']}: {int(float(d['price'])):,} تومان" + "\n"
                    + "قیمت جدید را بنویسید:",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:oleguses:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                uses = int(d.get("uses_per_unit") or 20)
                _pending[pid] = {"kind": "owner_leg_uses", "item": ic}
                await out(
                    f"تعداد استفاده فعلی {d['name_fa']}: {uses} بار" + "\n"
                    + "عدد جدید را بنویسید (۱ تا ۱۰۰۰)." + "\n"
                    + "مثال: 20",
                    ik([cancel_row()]),
                )
                return

            # cyber / defense status
            if data == "ng:cyber" or data.startswith("ng:cyber:"):
                if not code:
                    await out("ابتدا کشور/گروهک انتخاب کنید.")
                    return
                if data == "ng:cyber":
                    rows = [
                        [("🛡 هکر پدافند", "ng:cyber:hackdef")],
                        [("💰 هکر دارایی", "ng:cyber:hackasset")],
                        [("📊 وضعیت پدافند من", "ng:mydef")],
                        back_row(),
                    ]
                    await out(
                        chr(10).join([
                            "💻 هک و امنیت",
                            "هکر پدافند: اختلال موقت ۳۰٪ پدافند هدف (۲ دقیقه)",
                            "هکر دارایی: گزارش دارایی‌های هدف (بدون تغییر)",
                        ]),
                        ik(rows),
                    )
                    return
                action = data.split(":")[-1]
                countries = [
                    c for c in await game.list_countries()
                    if c.get("owner_player_id") and c["country_code"] != code
                ]
                if action == "hackdef":
                    rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:chdef:{c['country_code']}")] for c in countries[:30]]
                    rows.append(back_row())
                    await out("هدف هکر پدافند را انتخاب کنید:", ik(rows))
                    return
                if action == "hackasset":
                    rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:chasset:{c['country_code']}")] for c in countries[:30]]
                    rows.append(back_row())
                    await out("هدف هکر دارایی را انتخاب کنید:", ik(rows))
                    return
                return
            if data.startswith("ng:chdef:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                try:
                    await out(await game.hack_defense(code, dst, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:chasset:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                try:
                    await out(await game.hack_assets(code, dst, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:mydef":
                if not code:
                    await out("ابتدا کشور/گروهک انتخاب کنید.")
                    return
                try:
                    await out(await game.cyber_status_text(code), ik([
                        [("💻 هک و امنیت", "ng:cyber")],
                        back_row(),
                    ]))
                except Exception as e:
                    log.exception("mydef")
                    await out(f"❌ {e}")
                return

            # attack
            if data == "ng:atkmenu" or data.startswith("ng:atk:") or data.startswith("ng:fight:") or data.startswith("ng:nuke"):
                meta = await game.db.fetchrow("SELECT war_enabled FROM world_meta WHERE id=1")
                if not meta or not int(meta.get("war_enabled") or 0):
                    await out(
                        "⚠️ امکان انجام حمله وجود ندارد.\n\nدر حال حاضر وضعیت جنگ در جهان بسته است.\nسازمان ملل باید جنگ را فعال کند."
                    )
                    return
            if data == "ng:atkmenu":
                if not code:
                    await out("کشور ندارید")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:atk:{c['country_code']}")] for c in countries[:30]]
                rows.append(back_row())
                await out("هدف حمله را انتخاب کنید:", ik(rows))
                return
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
                    "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code='nuke_bomb'",
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
                if await game.is_group(code):
                    await out("گروهک‌ها امکان NPT ندارند.")
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
                        cname = p.get("country_label") or (
                            await game.country_name_only(p.get("country_code"))
                            if p.get("country_code") else "بدون کشور"
                        )
                        un = p.get("display_name") or p.get("username") or "بدون‌نام"
                        pid_s = p["player_id"]
                        label = f"{un} | {cname} | {pid_s}"
                        rows.append([(label[:48], f"ng:ou:{pid_s}")])
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
            if data == "ng:ogiveall":
                _pending[pid] = {"kind": "owner_give_all"}
                await out(
                    "💵 واریز همگانی به همه کشورهای بازیکن\n"
                    "مبلغ یکسان برای هر کشور را بنویسید:\n"
                    "مثال: 5000000",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:odaily":
                try:
                    n = await game.daily_payout_all()
                    if n:
                        await out(f"✅ درآمد روزانه برای {n} کشور پرداخت شد و در گروه اعلام می‌شود.")
                    else:
                        today = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Tehran")).date().isoformat()
                        await out(f"ℹ️ امروز ({today}) همه کشورها قبلاً درآمد روزانه را گرفته‌اند یا کشوری برای پرداخت نیست.")
                except Exception as e:
                    log.exception("odaily")
                    await out(f"❌ {e}")
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




            # ---- Country control ----
            if data == "ng:ctrl":
                if not code:
                    await out("کشور ندارید")
                    return
                text_c = await game.control.panel_text(code)
                rows = [
                    [("📜 تصویب قوانین", "ng:ctrl:laws")],
                    [("🌊 کنترل تنگه‌ها", "ng:ctrl:straits")],
                    [("✈️ پروازها", "ng:ctrl:flights"), ("🚢 دریایی", "ng:ctrl:maritime")],
                    [("🌐 اینترنت", "ng:ctrl:net")],
                    back_row(),
                ]
                await out(text_c, ik(rows))
                return
            if data == "ng:ctrl:flights":
                rows = [[("✈️ باز کردن", "ng:ctrl:fly:1"), ("⛔ توقف", "ng:ctrl:fly:0")], back_row()]
                await out("مدیریت پروازها:", ik(rows))
                return
            if data.startswith("ng:ctrl:fly:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.control.toggle_flights(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:maritime":
                rows = [[("🚢 باز کردن", "ng:ctrl:sea:1"), ("⛔ توقف", "ng:ctrl:sea:0")], back_row()]
                await out("مدیریت سفر دریایی:", ik(rows))
                return
            if data.startswith("ng:ctrl:sea:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.control.toggle_maritime(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:net":
                rows = [[("🌐 وصل", "ng:ctrl:net:1"), ("⛔ قطع", "ng:ctrl:net:0")], back_row()]
                await out("مدیریت اینترنت:", ik(rows))
                return
            if data.startswith("ng:ctrl:net:") and data.count(":") == 3:
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.control.toggle_internet(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:straits":
                if not code:
                    await out("کشور ندارید")
                    return
                rows = []
                straits = await game.control.list_controllable_straits(code)
                if not straits:
                    await out("کشور شما اختیار کنترل هیچ تنگه استراتژیکی را ندارد.", ik([back_row()]))
                    return
                for s in straits:
                    st = "بسته ⛔" if int(s["closed"]) else "باز ✅"
                    rows.append([(f"{s['name_fa']} ({st})", f"ng:strait:{s['strait_code']}")])
                rows.append(back_row())
                await out("تنگه‌های تحت اختیار شما:", ik(rows))
                return
            if data.startswith("ng:strait:") and data.count(":") == 2:
                sc = data.split(":")[-1]
                rows = [
                    [("⛔ بستن تنگه", f"ng:straitclose:{sc}"), ("✅ باز کردن", f"ng:straitopen:{sc}")],
                    back_row(),
                ]
                await out("عملیات تنگه:", ik(rows))
                return
            if data.startswith("ng:straitclose:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.control.toggle_strait(code, pid, data.split(":")[-1], True))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:straitopen:"):
                if not code:
                    await out("کشور ندارید")
                    return
                try:
                    await out(await game.control.toggle_strait(code, pid, data.split(":")[-1], False))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:laws":
                rows = [
                    [("✍️ قانون جدید", "ng:lawnew")],
                    [("📋 قوانین فعال من", "ng:lawmine")],
                    back_row(),
                ]
                await out("📜 تصویب قوانین\nهر کشور حداکثر ۳ قانون در روز می‌تواند ثبت کند.", ik(rows))
                return
            if data == "ng:lawnew":
                _pending[pid] = {"kind": "law_title"}
                await out("عنوان قانون را بنویسید:", ik([cancel_row()]))
                return
            if data == "ng:lawmine":
                if not code:
                    await out("کشور ندارید")
                    return
                laws = await game.control.active_laws_for(code)
                if not laws:
                    await out("قانون فعالی ندارید.")
                    return
                lines = ["قوانین فعال:"]
                for L in laws:
                    lines.append(f"• #{L['id']} {L['title']} (+{int(float(L['income_bonus'] or 0)):,}/روز)")
                await out("\n".join(lines))
                return
            if data == "ng:olaws":
                laws = await game.control.pending_laws()
                rows = []
                lines = [f"📜 قوانین در انتظار: {len(laws)}"]
                for L in laws[:20]:
                    name = await game.country_label(L["country_code"])
                    lines.append(f"#{L['id']} {name}: {L['title']}")
                    rows.append([
                        (f"✅ #{L['id']}", f"ng:lawok:{L['id']}"),
                        (f"❌ #{L['id']}", f"ng:lawno:{L['id']}"),
                    ])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:lawok:"):
                lid = int(data.split(":")[-1])
                _pending[pid] = {"kind": "law_bonus", "law_id": lid}
                await out("در صورت تمایل، پاداش درآمد روزانه این قانون را به عدد بنویسید (۰ تا ۵ میلیون). برای بدون پاداش ۰ بفرستید:")
                return
            if data.startswith("ng:lawno:"):
                try:
                    await out(await game.control.review_law(int(data.split(":")[-1]), pid, False))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:go:eco":
                if not code:
                    await out("کشور ندارید")
                    return
                await out(await game.economy_card(code))
                return



            if data == "ng:oprices":
                rows = []
                pair = []
                for cat, name in CAT_FA.items():
                    pair.append((name, f"ng:opricecat:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append(back_row())
                await out("🏷 قیمت فروشگاه\nدسته را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:opricecat:"):
                cat = data.split(":")[-1]
                items = await game.list_catalog_by_category(cat)
                rows = []
                for i in items[:40]:
                    rows.append([(
                        f"{i['name_fa']} | {int(float(i['unit_price'])):,}",
                        f"ng:opriceitem:{i['item_code']}",
                    )])
                rows.append([("⬅️ دسته‌ها", "ng:oprices")])
                rows.append(back_row())
                await out(f"آیتم‌های {CAT_FA.get(cat, cat)} — روی مورد بزنید تا قیمت جدید بدهید:", ik(rows))
                return
            if data.startswith("ng:opriceitem:"):
                ic = data.split(":")[-1]
                await game._reload_catalog_prices()
                it = game._cat.get(ic) or {}
                _pending[pid] = {"kind": "set_shop_price", "item": ic}
                await out(
                    f"قیمت فعلی «{it.get('name_fa', ic)}»: {int(float(it.get('unit_price') or 0)):,}\n"
                    f"قیمت جدید را به عدد بنویسید:",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:odiscount":
                cur = await game.get_shop_discount_pct()
                rows = [
                    [("۱۰٪", "ng:odiscon:10"), ("۲۰٪", "ng:odiscon:20")],
                    [("۳۰٪", "ng:odiscon:30"), ("۴۰٪", "ng:odiscon:40")],
                    [("۵۰٪", "ng:odiscon:50"), ("۶۰٪", "ng:odiscon:60")],
                    [("۷۰٪", "ng:odiscon:70")],
                    [("❌ غیرفعال کردن تخفیف", "ng:odiscoff")],
                    back_row(),
                ]
                st = f"فعال: {int(cur)}٪" if cur else "هیچ تخفیفی فعال نیست"
                await out(f"🏷 تخفیف سراسری فروشگاه\nوضعیت: {st}\nفقط یک تخفیف همزمان مجاز است.", ik(rows))
                return
            if data.startswith("ng:odiscon:"):
                pct = float(data.split(":")[-1])
                try:
                    await out(await game.set_shop_discount(pid, pct))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:odiscoff":
                try:
                    await out(await game.set_shop_discount(pid, 0))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            # ---- Double HP (owner only) ----
            if data == "ng:odblhp":
                countries = await game.list_countries()
                owned = [c for c in countries if c.get("owner_player_id")]
                if not owned:
                    await out("هیچ کشور دارای مالکی نیست.", main_kb(owner))
                    return
                rows = []
                for c in owned[:35]:
                    try:
                        on = int(c.get("double_hp") or 0) == 1
                    except Exception:
                        on = False
                    mark = "✅×۲" if on else "—"
                    rows.append([(
                        f"{mark} {c.get('flag') or ''} {c['name_fa']}".strip(),
                        f"ng:odbl:{c['country_code']}",
                    )])
                rows.append(back_row())
                await out("🧬 جان ۲ برابر\nکشور را انتخاب کنید:", ik(rows))
                return

            if data.startswith("ng:odbl:") and data.count(":") == 2 and not data.startswith("ng:odblon") and not data.startswith("ng:odbloff"):
                code = data.split(":")[-1]
                c = await game.db.fetchrow(
                    "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
                )
                if not c:
                    await out("کشور یافت نشد")
                    return
                on = int(c.get("double_hp") or 0) == 1
                st = "فعال ✅" if on else "غیرفعال"
                rows = [
                    [
                        ("✅ فعال کردن ×۲", f"ng:odblon:{code}"),
                        ("❌ خاموش کردن", f"ng:odbloff:{code}"),
                    ],
                    back_row(),
                ]
                await out(
                    f"{c.get('flag') or ''} {c['name_fa']}\n"
                    f"جان ۲ برابر: {st}\n"
                    f"سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}",
                    ik(rows),
                )
                return

            if data.startswith("ng:odblon:"):
                code = data.split(":")[-1]
                try:
                    await out(await game.set_double_hp(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("double_hp on")
                    await out("❌ خطا در فعال‌سازی جان ۲ برابر")
                return

            if data.startswith("ng:odbloff:"):
                code = data.split(":")[-1]
                try:
                    await out(await game.set_double_hp(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("double_hp off")
                    await out("❌ خطا در خاموش کردن جان ۲ برابر")
                return

            if data.startswith("ng:oudblon:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow(
                    "SELECT country_code FROM ng_players WHERE player_id=$1", (tid,)
                )
                code = (p or {}).get("country_code")
                if not code:
                    await out("این کاربر کشور ندارد.")
                    return
                try:
                    await out(await game.set_double_hp(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("oudbl on")
                    await out("❌ خطا در فعال‌سازی جان ۲ برابر")
                return

            if data.startswith("ng:oudbloff:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow(
                    "SELECT country_code FROM ng_players WHERE player_id=$1", (tid,)
                )
                code = (p or {}).get("country_code")
                if not code:
                    await out("این کاربر کشور ندارد.")
                    return
                try:
                    await out(await game.set_double_hp(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("oudbl off")
                    await out("❌ خطا در خاموش کردن جان ۲ برابر")
                return

            if data == "ng:ohp" or data.startswith("ng:ohp:"):
                page = 0
                if data.startswith("ng:ohp:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                text_hp, total = await game.list_owned_countries_hp(page=page, page_size=12)
                nav = []
                pages = max(1, (total + 11) // 12)
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:ohp:{page-1}"))
                if page + 1 < pages:
                    nav.append(("بعدی ➡️", f"ng:ohp:{page+1}"))
                rows = []
                if nav:
                    rows.append(nav)
                rows.append([("🛡 بازگشت پنل مالک", "ng:opanel")])
                await out(text_hp, ik(rows))
                return
            if data == "ng:opanel":
                rows = [
                    [("بازیکنان", "ng:o:players"), ("وضعیت جهان", "ng:o:world")],
                    [("💵 پول همگانی", "ng:ogiveall"), ("💰 پرداخت درآمد روزانه", "ng:odaily")],
                    [("❤️ دیدن HP ها", "ng:ohp"), ("🧬 جان ۲ برابر کشورها", "ng:odblhp")],
                    [("🎁 مدیریت لجندری", "ng:oleg"), ("💰 شارژ کیف پول", "ng:owallet")],
                    [("⚙️ قیمت و استفاده لجندری", "ng:olegprices")],
                    [("⬅️ بستن", "ng:home")],
                ]
                await out("🛡 پنل مالک / سازمان ملل", ik(rows))
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
                    [("❤️ تنظیم HP", f"ng:osethp:{tid}")],
                    [("💵 دادن پول", f"ng:ougive:{tid}"), ("💸 گرفتن پول", f"ng:outake:{tid}")],
                    [("🧾 مالیات از کاربر", f"ng:outax:{tid}")],
                    [("🧬 جان ×۲ روشن", f"ng:oudblon:{tid}"), ("🧬 جان ×۲ خاموش", f"ng:oudbloff:{tid}")],
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
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("کشور نامشخص / مالکیت هم‌خوان نیست")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, currency_name_fa, owner_player_id FROM ng_countries WHERE country_code=$1",
                    (code,),
                )
                cname = await game.country_label(code)
                await out(
                    f"💰 موجودی {cname}\nکد: {code}\nمالک: {c.get('owner_player_id')}\n"
                    f"خزانه: {int(float(c['treasury'])):,} {c.get('currency_name_fa') or ''}"
                )
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
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("این کاربر کشور معتبری ندارد؛ اول باید کشور انتخاب کند.")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, name_fa, currency_name_fa, owner_player_id FROM ng_countries WHERE country_code=$1",
                    (code,),
                )
                _pending[pid] = {"kind": "user_give_money", "code": code, "tid": tid}
                await out(
                    f"💵 افزودن پول به {(c or {}).get('name_fa') or code}\n"
                    f"موجودی فعلی: {int(float((c or {}).get('treasury') or 0)):,}\n\n"
                    f"مبلغ را به عدد بنویسید (مثال: 5000000):",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:outake:"):
                tid = int(data.split(":")[-1])
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("این کاربر کشور معتبری ندارد.")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, name_fa, owner_player_id FROM ng_countries WHERE country_code=$1", (code,)
                )
                _pending[pid] = {"kind": "user_take_money", "code": code, "tid": tid}
                await out(
                    f"💸 برداشت از {(c or {}).get('name_fa') or code}\n"
                    f"موجودی فعلی: {int(float((c or {}).get('treasury') or 0)):,}\n\n"
                    f"مبلغ برداشت را بنویسید:",
                    ik([cancel_row()]),
                )
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
