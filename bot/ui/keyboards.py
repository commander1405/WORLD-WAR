"""Reply + Inline keyboards — Phase 4."""
from __future__ import annotations

from bale import (
    MenuKeyboardMarkup,
    MenuKeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from modules.markets.catalog import CATEGORY_FA

BTN_MY = "🏛 کشور من"
BTN_ECO = "💰 اقتصاد"
BTN_SHOP = "🛒 فروشگاه"
BTN_INV = "📦 انبار من"
BTN_MARKET = "🌐 بازار آزاد"
BTN_TRADE = "🚢 تجارت جهانی"
BTN_BUILD = "🏗 ساخت‌وساز"
BTN_DEF = "🛡 مدیریت دفاعی"
BTN_DIPLO = "🤝 روابط خارجی"
BTN_WORLD = "🌍 جهان"
BTN_CAB = "🏛 دولت و کابینه"
BTN_LOG = "📜 گزارش فعالیت‌ها"
BTN_HELP = "📖 راهنمای بازی"
BTN_PICK = "🗺 انتخاب کشور"
BTN_SET = "⚙ تنظیمات"

MAIN_LABELS = [
    BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MARKET, BTN_TRADE,
    BTN_BUILD, BTN_DEF, BTN_DIPLO, BTN_WORLD, BTN_CAB, BTN_LOG,
    BTN_HELP, BTN_PICK, BTN_SET,
]


def main_reply_keyboard() -> MenuKeyboardMarkup:
    kb = MenuKeyboardMarkup()
    rows = [
        [BTN_MY, BTN_ECO],
        [BTN_SHOP, BTN_INV],
        [BTN_MARKET, BTN_TRADE],
        [BTN_BUILD, BTN_DEF],
        [BTN_DIPLO, BTN_WORLD],
        [BTN_CAB, BTN_LOG],
        [BTN_PICK, BTN_HELP],
    ]
    for r_i, row in enumerate(rows, start=1):
        for text in row:
            kb.add(MenuKeyboardButton(text), row=r_i)
    return kb


def inline_rows(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for r_i, row in enumerate(buttons, start=1):
        for label, data in row:
            if not label:
                continue
            kb.add(InlineKeyboardButton(label, callback_data=str(data)[:64]), row=r_i)
    return kb


def back_home_row():
    return [("🔙 بازگشت", "nav:back"), ("🏠 خانه", "nav:home")]


def shop_categories_kb():
    rows = []
    pair = []
    for code, name in CATEGORY_FA.items():
        pair.append((name, f"shop:cat:{code}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([("🛒 سبد خرید", "shop:cart"), ("✅ تسویه حساب", "shop:checkout")])
    rows.append(back_home_row())
    return inline_rows(rows)


def shop_items_kb(items: list[dict]):
    rows = [[(f"{it['name_fa']} — {int(it['unit_price']):,}", f"shop:item:{it['item_code']}")] for it in items]
    rows.append([("🛒 سبد", "shop:cart")])
    rows.append(back_home_row())
    return inline_rows(rows)


def shop_item_actions(item_code: str):
    return inline_rows([
        [("＋۱", f"shop:add:{item_code}:1"), ("＋۵", f"shop:add:{item_code}:5"), ("＋۱۰", f"shop:add:{item_code}:10")],
        [("🛒 سبد", "shop:cart"), ("✅ تسویه", "shop:checkout")],
        back_home_row(),
    ])


def cart_kb(items: list[dict]):
    rows = []
    for it in items:
        code = it["item_code"]
        rows.append([(f"🗑 {it.get('name_fa', code)}", f"shop:del:{code}")])
    rows.append([("✅ تسویه حساب", "shop:checkout")])
    rows.append(back_home_row())
    return inline_rows(rows)


def market_list_kb(listings: list[dict], page: int = 0):
    rows = []
    for L in listings:
        rows.append([(f"خرید #{L['id']} — {int(float(L['unit_price'])):,}", f"mkt:buy:{L['id']}")])
    nav = []
    if page > 0:
        nav.append(("◀️", f"mkt:page:{page-1}"))
    nav.append(("▶️", f"mkt:page:{page+1}"))
    rows.append(nav)
    rows.append([("آگهی‌های من", "mkt:mine"), ("ثبت آگهی از انبار", "mkt:sellmenu")])
    rows.append(back_home_row())
    return inline_rows(rows)


def inv_sell_kb(items: list[dict]):
    rows = [[(f"{it.get('name_fa', it['item_code'])} ({int(float(it['quantity']))})", f"mkt:sell:{it['item_code']}")] for it in items[:12]]
    rows.append(back_home_row())
    return inline_rows(rows)


def trade_menu_kb():
    return inline_rows([
        [("📥 پیشنهادهای من", "trd:list"), ("📤 پیشنهاد جدید", "trd:new")],
        back_home_row(),
    ])


def trade_res_kb():
    from modules.trade.service import TRADEABLE
    rows = [[(name, f"trd:res:{code}")] for code, name in TRADEABLE.items()]
    rows.append(back_home_row())
    return inline_rows(rows)


def trade_offers_kb(offers: list[dict], my_country: str):
    rows = []
    for o in offers:
        if o["to_country"] == my_country and o["status"] == "pending":
            rows.append([
                (f"✅ قبول #{o['id']}", f"trd:ok:{o['id']}"),
                (f"❌ رد #{o['id']}", f"trd:no:{o['id']}"),
            ])
        else:
            rows.append([(f"#{o['id']} {o['status']}", f"trd:view:{o['id']}")])
    rows.append(back_home_row())
    return inline_rows(rows)


def country_pick_keyboard(rows: list[dict], page: int, per_page: int = 8) -> InlineKeyboardMarkup:
    start = page * per_page
    chunk = rows[start : start + per_page]
    btns: list[list[tuple[str, str]]] = []
    for r in chunk:
        code = r["country_code"]
        flag = r.get("flag") or ""
        name = r.get("name_fa") or r.get("name_en") or code
        if r.get("owner_player_id"):
            btns.append([(f"❌ {flag} {name}", f"claim:busy:{code}")])
        else:
            btns.append([(f"✅ {flag} {name}", f"claim:ask:{code}")])
    nav = []
    if page > 0:
        nav.append(("◀️ قبل", f"claim:page:{page-1}"))
    if start + per_page < len(rows):
        nav.append(("بعد ▶️", f"claim:page:{page+1}"))
    if nav:
        btns.append(nav)
    btns.append(back_home_row())
    return inline_rows(btns)


def my_country_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📋 نمای کلی", "my:overview"), ("🏛 سیاست", "my:politics")],
        [("💰 اقتصاد", "my:economy"), ("📦 منابع انبار", "my:inv")],
        [("🌐 پیمان‌ها", "my:orgs"), ("🤝 روابط", "my:relations")],
        [("🛡 نظامی", "my:mil"), ("🏭 تولید", "my:sectors")],
        back_home_row(),
    ])


def economy_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📊 وضعیت بودجه", "eco:status")],
        [("➕ مالیات", "eco:tax_up"), ("➖ مالیات", "eco:tax_down")],
        [("➕ مخارج", "eco:spend_up"), ("➖ مخارج", "eco:spend_down")],
        [("⏱ دوره بودجه", "eco:tick")],
        back_home_row(),
    ])


def cabinet_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📋 کابینه", "cab:list")],
        [("انتصاب دارایی", "cab:app:finance"), ("انتصاب دفاع", "cab:app:defense")],
        [("انتصاب خارجه", "cab:app:foreign"), ("انتصاب اقتصاد", "cab:app:economy")],
        back_home_row(),
    ])


def world_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📰 اخبار", "world:news"), ("🗺 کشورها", "world:list:0")],
        [("🕰 تاریخ جهان", "world:date")],
        back_home_row(),
    ])


def confirm_claim(code: str) -> InlineKeyboardMarkup:
    return inline_rows([[("✅ تأیید", f"claim:yes:{code}"), ("❌ انصراف", "claim:page:0")]])


def build_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("نفت — پالایشگاه", "shop:item:bld_refinery"), ("نیروگاه", "shop:item:bld_power")],
        [("انرژی صلح‌آمیز", "shop:item:bld_uranium_plant"), ("انبار منابع", "shop:item:bld_warehouse")],
        [("🛒 فروشگاه زیرساخت", "shop:cat:infra")],
        back_home_row(),
    ])


def defense_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📊 وضعیت نیروها", "def:status"), ("⚖️ مدیریت بحران", "def:crisis")],
        [("🛒 خرید تجهیزات", "shop:cat:defense")],
        back_home_row(),
    ])


def crisis_targets_kb(rows: list[dict], my_code: str):
    btns = []
    for r in rows:
        code = r["country_code"]
        if code == my_code:
            continue
        name = r.get("name_fa") or code
        btns.append([(name, f"def:crisis:{code}")])
        if len(btns) >= 10:
            break
    btns.append(back_home_row())
    return inline_rows(btns)


def settings_menu() -> InlineKeyboardMarkup:
    return inline_rows([[("📖 راهنما", "nav:help"), ("ℹ️ درباره", "nav:about")], back_home_row()])
