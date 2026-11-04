"""Reply + Inline keyboards (python-bale-bot 2.5.0)."""
from __future__ import annotations

from bale import (
    MenuKeyboardMarkup,
    MenuKeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# Main reply keyboard labels (must match message handler)
BTN_MY = "🏛 کشور من"
BTN_ECO = "💰 اقتصاد"
BTN_BUILD = "🏗 ساخت‌وساز"
BTN_DIPLO = "🤝 روابط خارجی"
BTN_DEF = "🛡 دفاع و امنیت"
BTN_CAB = "🏛 دولت و کابینه"
BTN_WORLD = "🌍 جهان"
BTN_SET = "⚙ تنظیمات"
BTN_HELP = "📖 راهنمای بازی"
BTN_PICK = "🗺 انتخاب کشور"

MAIN_LABELS = [BTN_MY, BTN_ECO, BTN_BUILD, BTN_DIPLO, BTN_DEF, BTN_CAB, BTN_WORLD, BTN_SET, BTN_HELP, BTN_PICK]


def main_reply_keyboard() -> MenuKeyboardMarkup:
    kb = MenuKeyboardMarkup()
    rows = [
        [BTN_MY, BTN_ECO],
        [BTN_BUILD, BTN_DIPLO],
        [BTN_DEF, BTN_CAB],
        [BTN_WORLD, BTN_PICK],
        [BTN_HELP, BTN_SET],
    ]
    for r_i, row in enumerate(rows, start=1):
        for text in row:
            kb.add(MenuKeyboardButton(text), row=r_i)
    return kb


def inline_rows(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """buttons: list of rows of (label, callback_data)."""
    kb = InlineKeyboardMarkup()
    for r_i, row in enumerate(buttons, start=1):
        for label, data in row:
            kb.add(InlineKeyboardButton(label, callback_data=data[:64]), row=r_i)
    return kb


def back_home_row():
    return [("🔙 بازگشت", "nav:back"), ("🏠 خانه", "nav:home")]


def country_pick_keyboard(rows: list[dict], page: int, per_page: int = 8) -> InlineKeyboardMarkup:
    start = page * per_page
    chunk = rows[start : start + per_page]
    btns: list[list[tuple[str, str]]] = []
    for r in chunk:
        code = r["country_code"]
        flag = r.get("flag") or ""
        name = r.get("name_fa") or r.get("name_en") or code
        if r.get("owner_player_id"):
            label = f"❌ {flag} {name}"
            data = f"claim:busy:{code}"
        else:
            label = f"✅ {flag} {name}"
            data = f"claim:ask:{code}"
        btns.append([(label, data)])
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
        [("📋 نمای کلی", "my:overview"), ("🏛 سیاست و حکومت", "my:politics")],
        [("💰 اقتصاد پایه", "my:economy"), ("🌐 سازمان‌ها و پیمان‌ها", "my:orgs")],
        [("🤝 روابط و تنش‌ها", "my:relations"), ("🏭 تولید", "my:sectors")],
        back_home_row(),
    ])


def economy_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📊 وضعیت بودجه", "eco:status")],
        [("➕ افزایش مالیات", "eco:tax_up"), ("➖ کاهش مالیات", "eco:tax_down")],
        [("➕ افزایش مخارج", "eco:spend_up"), ("➖ کاهش مخارج", "eco:spend_down")],
        [("⏱ اجرای دوره بودجه", "eco:tick")],
        [("🏭 سرمایه‌گذاری صنعت", "eco:inv_industry"), ("🌾 سرمایه‌گذاری کشاورزی", "eco:inv_agri")],
        back_home_row(),
    ])


def cabinet_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📋 مشاهده کابینه", "cab:list")],
        [("انتصاب دارایی", "cab:app:finance"), ("انتصاب دفاع", "cab:app:defense")],
        [("انتصاب خارجه", "cab:app:foreign"), ("انتصاب اقتصاد", "cab:app:economy")],
        [("برکناری دارایی", "cab:dis:finance"), ("برکناری دفاع", "cab:dis:defense")],
        back_home_row(),
    ])


def world_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📰 اخبار جهان", "world:news"), ("🗺 فهرست کشورها", "world:list:0")],
        [("🕰 تاریخ جهان", "world:date")],
        back_home_row(),
    ])


def confirm_claim(code: str) -> InlineKeyboardMarkup:
    return inline_rows([
        [("✅ تأیید انتخاب", f"claim:yes:{code}"), ("❌ انصراف", "claim:page:0")],
    ])


def build_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("🛣 جاده و زیرساخت", "build:infra"), ("🏭 کارخانه", "build:factory")],
        [("🏫 آموزش و بهداشت", "build:social")],
        back_home_row(),
    ])


def defense_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📜 سیاست دفاعی", "def:policy"), ("📊 وضعیت ثبات", "def:status")],
        back_home_row(),
    ])


def settings_menu() -> InlineKeyboardMarkup:
    return inline_rows([
        [("📖 راهنما", "nav:help"), ("ℹ️ درباره بازی", "nav:about")],
        back_home_row(),
    ])
