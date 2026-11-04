"""New Generation Persian button UI."""
from __future__ import annotations

import logging
import re

from bale import MenuKeyboardMarkup, MenuKeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from modules.ng.catalog import CATALOG, CAT_FA
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

MAIN = [BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MKT, BTN_TRADE, BTN_DIPLO, BTN_PEACE, BTN_ATTACK, BTN_STMT, BTN_WORLD, BTN_REPORT, BTN_PICK]


def main_kb(is_owner=False):
    kb = MenuKeyboardMarkup()
    rows = [
        [BTN_MY, BTN_ECO],
        [BTN_SHOP, BTN_INV],
        [BTN_MKT, BTN_TRADE],
        [BTN_DIPLO, BTN_PEACE],
        [BTN_ATTACK, BTN_STMT],
        [BTN_WORLD, BTN_REPORT],
        [BTN_PICK],
    ]
    if is_owner:
        rows.append([BTN_OWNER])
    for i, row in enumerate(rows, 1):
        for t in row:
            kb.add(MenuKeyboardButton(t), row=i)
    return kb


def ik(rows):
    kb = InlineKeyboardMarkup()
    for ri, row in enumerate(rows, 1):
        for label, data in row:
            kb.add(InlineKeyboardButton(label, callback_data=str(data)[:64]), row=ri)
    return kb


def back():
    return [("🔙 بازگشت", "ng:home")]


_pending: dict[int, dict] = {}


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
    return getattr(u, "username", None), ((getattr(u, "first_name", None) or "") + " " + (getattr(u, "last_name", None) or "")).strip() or None


async def reply(msg, text, kb=None):
    await msg.reply(str(text)[:3500], components=kb)


def register_handlers(bot, app_ctx: dict):
    game = app_ctx["game"]
    settings = app_ctx["settings"]

    async def ensure(pid, username=None, display=None):
        await game.touch_player(pid, username, display)
        await game.assert_not_banned(pid)

    @bot.listen("on_ready")
    async def on_ready():
        log.info("NG bot ready")

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
            await ensure(pid, username, display)
            owner = game.is_owner(pid)
            code = await game.player_country(pid)

            # pending flows
            if pid in _pending:
                st = _pending[pid]
                if st.get("kind") == "statement":
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
                if st.get("kind") == "aid_money_amount":
                    try:
                        amount = float(text.replace(",", ""))
                        msg = await game.aid_money(code, st["dst"], amount, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    _pending.pop(pid, None)
                    await reply(message, msg, main_kb(owner))
                    return
                if st.get("kind") == "reset_phrase":
                    _pending.pop(pid, None)
                    try:
                        msg = await game.full_reset(pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if st.get("kind") == "mkt_qty":
                    try:
                        st["qty"] = float(text)
                        st["kind"] = "mkt_price"
                        await reply(message, "قیمت واحد را بنویسید:")
                    except ValueError:
                        await reply(message, "عدد وارد کنید")
                    return
                if st.get("kind") == "mkt_price":
                    try:
                        price = float(text)
                        msg = await game.market_create(code, st["item"], st["qty"], price, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    _pending.pop(pid, None)
                    await reply(message, msg, main_kb(owner))
                    return

            if text in ("/start", "شروع", "منو"):
                await reply(
                    message,
                    "🕹 جنگ جهانی — نسل جدید\nکشور خود را اداره کنید، اقتصاد بسازید، دیپلماسی و جنگ را مدیریت کنید.\nهمه چیز با دکمه انجام می‌شود.",
                    main_kb(owner),
                )
                return

            if text == BTN_PICK:
                if code:
                    await reply(message, "شما کشور دارید.", main_kb(owner))
                    return
                rows = await game.list_countries()
                btns = []
                for c in rows:
                    if c.get("owner_player_id"):
                        btns.append([(f"❌ {c['flag']} {c['name_fa']}", f"ng:busy")])
                    else:
                        btns.append([(f"✅ {c['flag']} {c['name_fa']}", f"ng:claim:{c['country_code']}")])
                btns.append(back())
                await reply(message, "کشور آزاد را انتخاب کنید:", ik(btns))
                return

            if text == BTN_MY:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                await reply(message, await game.country_card(code), main_kb(owner))
                return

            if text == BTN_ECO:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                await reply(
                    message,
                    f"💰 اقتصاد\nخزانه: {int(c['treasury']):,}\nدرآمد روزانه: {int(c['daily_income']):,}\nهزینه: {int(c['daily_expense']):,}\nمالیات: {float(c['tax_rate'])*100:.0f}٪",
                    main_kb(owner),
                )
                return

            if text == BTN_SHOP:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = [[(name, f"ng:shop:{cat}")] for cat, name in CAT_FA.items()]
                rows.append([("🛒 سبد", "ng:cart"), ("✅ تسویه", "ng:checkout")])
                rows.append(back())
                await reply(message, "🛒 فروشگاه", ik(rows))
                return

            if text == BTN_INV:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                inv = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
                )
                rows = [[(f"{game._cat.get(r['item_code'],{}).get('name_fa', r['item_code'])}", f"ng:sell:{r['item_code']}")] for r in inv[:15]]
                rows.append(back())
                await reply(message, await game.inventory_text(code), ik(rows) if inv else main_kb(owner))
                return

            if text == BTN_MKT:
                listings = await game.market_list()
                rows = [[(f"#{L['id']} {L['item_code']} @ {int(float(L['unit_price'])):,}", f"ng:mbuy:{L['id']}")] for L in listings]
                rows.append(back())
                await reply(message, "🌐 بازار آزاد", ik(rows) if listings else main_kb(owner))
                return

            if text == BTN_TRADE:
                await reply(message, "🚢 برای کمک مالی/نظامی از روابط خارجی استفاده کنید.", main_kb(owner))
                return

            if text == BTN_DIPLO:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                countries = await game.list_countries()
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aid:{c['country_code']}")] for c in countries if c["country_code"] != code and c.get("owner_player_id")]
                rows.append(back())
                await reply(message, "کمک مالی به کشور:", ik(rows))
                return

            if text == BTN_PEACE:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                countries = await game.list_countries()
                rows = [[(c["name_fa"], f"ng:peace:{c['country_code']}:6")] for c in countries if c["country_code"] != code]
                rows.append(back())
                await reply(message, "درخواست صلح ۶ ساعته برای:", ik(rows))
                return

            if text == BTN_ATTACK:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                countries = await game.list_countries()
                rows = [[(c["name_fa"], f"ng:atk:{c['country_code']}")] for c in countries if c["country_code"] != code and c.get("owner_player_id")]
                rows.append(back())
                await reply(message, "هدف حمله:", ik(rows))
                return

            if text == BTN_STMT:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "statement"}
                await reply(message, "متن بیانیه رسمی را بنویسید و ارسال کنید:")
                return

            if text == BTN_WORLD:
                free = sum(1 for c in await game.list_countries() if not c.get("owner_player_id"))
                await reply(message, f"🌍 جهان\nکشورهای آزاد: {free}\nزمان شروع از راه‌اندازی نسخه جدید محاسبه می‌شود.", main_kb(owner))
                return

            if text == BTN_REPORT:
                if not code:
                    await reply(message, "ابتدا کشور انتخاب کنید.", main_kb(owner))
                    return
                rows = await game.db.fetch(
                    "SELECT * FROM ng_activity WHERE country_code=$1 ORDER BY id DESC", (code,)
                )
                lines = ["📊 گزارش‌ها"] + [f"• {r['summary']}" for r in rows[:12]]
                await reply(message, "\n".join(lines), main_kb(owner))
                return

            if text == BTN_OWNER and owner:
                rows = [
                    [("باز کردن جنگ", "ng:owar:1"), ("بستن جنگ", "ng:owar:0")],
                    [("فعال‌سازی هسته‌ای بازی", "ng:onuke:1"), ("غیرفعال هسته‌ای", "ng:onuke:0")],
                    [("بیانیه‌های در انتظار", "ng:ostmt")],
                    [("🔴 ریست کامل جهان", "ng:oreset1")],
                    back(),
                ]
                await reply(message, "🛡 پنل مالک / سازمان ملل", ik(rows))
                return

        except GameError as e:
            await reply(message, f"❌ {e}", main_kb(game.is_owner(pid) if pid else False))
        except Exception:
            log.exception("msg")
            try:
                await message.reply("خطای داخلی")
            except Exception:
                pass

    @bot.listen("on_callback")
    async def on_callback(cq):
        try:
            data = (getattr(cq, "data", None) or "").strip()
            pid = _uid(cq)
            if not pid or not data:
                return
            await ensure(pid)
            owner = game.is_owner(pid)
            code = await game.player_country(pid)
            msg = getattr(cq, "message", None)

            async def out(text, kb=None):
                if msg:
                    await msg.reply(str(text)[:3500], components=kb or main_kb(owner))

            if data == "ng:home":
                await out("منوی اصلی")
                return
            if data == "ng:busy":
                await out("این کشور دارای بازیکن است.")
                return
            if data.startswith("ng:claim:"):
                ccode = data.split(":")[-1]
                try:
                    c = await game.claim(pid, ccode)
                    await out("✅ کشور شما ثبت شد\n\n" + await game.country_card(c["country_code"]))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:shop:"):
                cat = data.split(":")[-1]
                items = [c for c in CATALOG if c["category"] == cat]
                rows = [[(f"{i['name_fa']} — {int(i['unit_price']):,}", f"ng:item:{i['item_code']}")] for i in items]
                rows.append([("🛒 سبد", "ng:cart")])
                rows.append(back())
                await out("محصولات:", ik(rows))
                return
            if data.startswith("ng:item:"):
                ic = data.split(":")[-1]
                it = game._cat[ic]
                rows = [[("＋۱", f"ng:add:{ic}:1"), ("＋۵", f"ng:add:{ic}:5")], [("سبد", "ng:cart"), ("تسویه", "ng:checkout")], back()]
                await out(f"{it['name_fa']}\n{it['description_fa']}\nقیمت: {int(it['unit_price']):,}", ik(rows))
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
                rows = [[("✅ تسویه حساب", "ng:checkout")], back()]
                await out(text, ik(rows))
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
            if data.startswith("ng:sell:"):
                if not code:
                    await out("کشور ندارید")
                    return
                _pending[pid] = {"kind": "mkt_qty", "item": data.split(":")[-1]}
                await out("تعداد برای فروش در بازار را بنویسید:")
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
            if data.startswith("ng:aid:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                _pending[pid] = {"kind": "aid_money_amount", "dst": dst}
                await out("مبلغ کمک مالی را بنویسید:")
                return
            if data.startswith("ng:peace:"):
                if not code:
                    await out("کشور ندارید")
                    return
                parts = data.split(":")
                dst, hours = parts[2], float(parts[3])
                try:
                    await out(await game.peace_request(code, dst, hours, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:atk:"):
                if not code:
                    await out("کشور ندارید")
                    return
                dst = data.split(":")[-1]
                rows = [
                    [("زمینی ۵۰٪", f"ng:fight:{dst}:ground:50"), ("هوایی ۵۰٪", f"ng:fight:{dst}:air:50")],
                    [("دریایی ۵۰٪", f"ng:fight:{dst}:sea:50"), ("زمینی ۱۰۰٪", f"ng:fight:{dst}:ground:100")],
                    back(),
                ]
                await out("نوع و شدت عملیات:", ik(rows))
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
            if data.startswith("ng:owar:"):
                await out(await game.set_war(pid, data.endswith(":1")))
                return
            if data.startswith("ng:onuke:"):
                await out(await game.set_nuclear(pid, data.endswith(":1")))
                return
            if data == "ng:ostmt":
                rows = await game.db.fetch("SELECT * FROM ng_statements WHERE status='pending'")
                btns = []
                for s in rows[:10]:
                    btns.append([(f"✅#{s['id']}", f"ng:sapp:{s['id']}"), (f"❌#{s['id']}", f"ng:srej:{s['id']}")])
                btns.append(back())
                await out("بیانیه‌های در انتظار", ik(btns) if rows else main_kb(owner))
                return
            if data.startswith("ng:sapp:"):
                await out(await game.review_statement(int(data.split(":")[-1]), True, pid))
                return
            if data.startswith("ng:srej:"):
                await out(await game.review_statement(int(data.split(":")[-1]), False, pid))
                return
            if data == "ng:oreset1":
                rows = [[("تأیید مرحله بعد", "ng:oreset2")], back()]
                await out("⚠ همه داده‌های جهان پاک می‌شود. ادامه؟", ik(rows))
                return
            if data == "ng:oreset2":
                _pending[pid] = {"kind": "reset_phrase"}
                await out("عبارت زیر را دقیقاً بنویسید:\nریست کامل جهان")
                return
        except Exception:
            log.exception("cb")
