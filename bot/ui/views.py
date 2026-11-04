"""Persian player-facing views — full data, friendly layout."""
from __future__ import annotations

import json
from typing import Any, Optional

from bot.ui.format import (
    SECTOR,
    fa_date,
    fa_digits,
    fa_int,
    t_gov,
    t_title,
    t_npt,
    t_sector,
    t_portfolio,
    t_org,
    status_dot,
)


def _jlist(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


def welcome_text(game_date) -> str:
    return (
        "🕹 به «جنگ جهانی» خوش آمدید\n"
        "بازی مدیریت کشور و سیاست جهان\n\n"
        f"📅 تاریخ جهان: {fa_date(game_date)}\n\n"
        "از دکمه‌های پایین صفحه استفاده کنید.\n"
        "اگر هنوز کشور ندارید: «انتخاب کشور»"
    )


def help_text() -> str:
    return (
        "📖 راهنمای بازی\n\n"
        "🏛 کشور من — وضعیت کشور و جزئیات\n"
        "💰 اقتصاد — مالیات، مخارج، سرمایه‌گذاری\n"
        "🏗 ساخت‌وساز — پروژه‌های زیرساختی\n"
        "🤝 روابط خارجی — تنش‌ها و ائتلاف‌ها\n"
        "🛡 دفاع و امنیت — ثبات و سیاست دفاعی\n"
        "🏛 دولت و کابینه — وزیران\n"
        "🌍 جهان — اخبار و کشورهای دیگر\n"
        "🗺 انتخاب کشور — فقط یک‌بار برای هر بازیکن\n\n"
        "⏱ زمان بازی از ۱ ژانویه ۲۰۲۰ شروع می‌شود؛\n"
        "هر ۱۵ روز واقعی تقریباً برابر یک سال بازی است.\n\n"
        "همه کارها با دکمه انجام می‌شود."
    )


def overview_card(country: dict, baseline: dict, economy: Optional[dict], game_date) -> str:
    flag = baseline.get("flag") or country.get("flag") or ""
    name = baseline.get("name_fa") or country.get("name_fa") or country.get("name_en")
    pop = baseline.get("population_ref") or country.get("population")
    gdp_show = (economy or {}).get("gdp") or baseline.get("gdp_ref")
    sat = float((economy or {}).get("public_satisfaction") or 50)
    stab = float((economy or {}).get("stability") or country.get("stability") or 50)
    eco_lvl = "خوب" if sat >= 60 else ("متوسط" if sat >= 40 else "ضعیف")
    stab_lvl = "پایدار" if stab >= 60 else ("حساس" if stab >= 40 else "ناپایدار")
    res = _jlist(baseline.get("resources_json"))
    res_lvl = "غنی" if len(res) >= 3 else ("متوسط" if res else "محدود")
    pop_n = float(pop or 0)
    pop_lvl = "زیاد" if pop_n >= 80_000_000 else ("متوسط" if pop_n >= 20_000_000 else "کم")

    return (
        f"{flag} {name}\n"
        f"📅 {fa_date(game_date)}\n\n"
        f"👑 رهبر: {baseline.get('leader_name') or 'نامشخص'}\n"
        f"🏷 سمت: {t_title(baseline.get('leader_title'))}\n"
        f"🏛 نظام: {t_gov(baseline.get('government_type'))}\n"
        f"🏙 پایتخت: {baseline.get('capital') or 'نامشخص'}\n"
        f"👥 جمعیت: {fa_int(pop)}\n"
        f"💰 اقتصاد: {fa_int(gdp_show)} دلار\n"
        f"💵 پول ملی: {baseline.get('currency_name') or baseline.get('currency_code') or 'نامشخص'}\n\n"
        f"📊 وضعیت کشور:\n"
        f"{status_dot('good' if sat >= 60 else 'mid' if sat >= 40 else 'bad')} اقتصاد: {eco_lvl}\n"
        f"{status_dot('good' if stab >= 60 else 'mid' if stab >= 40 else 'bad')} ثبات داخلی: {stab_lvl}\n"
        f"{status_dot('good' if len(res) >= 3 else 'mid')} منابع طبیعی: {res_lvl}\n"
        f"{status_dot('info')} جمعیت: {pop_lvl}\n\n"
        "از دکمه‌های زیر برای جزئیات بیشتر استفاده کنید."
    )


def politics_card(baseline: dict) -> str:
    langs = "، ".join(_jlist(baseline.get("languages_json"))) or "نامشخص"
    return (
        "🏛 سیاست و حکومت\n\n"
        f"نظام حکومتی: {t_gov(baseline.get('government_type'))}\n"
        f"رهبر در آغاز بازی: {baseline.get('leader_name') or 'نامشخص'}\n"
        f"سمت: {t_title(baseline.get('leader_title'))}\n"
        f"پایتخت: {baseline.get('capital') or 'نامشخص'}\n"
        f"زبان‌ها: {langs}\n"
        f"منطقه: {baseline.get('region') or 'نامشخص'}"
    )


def economy_base_card(baseline: dict, economy: Optional[dict]) -> str:
    e = economy or {}
    tax = float(e.get("tax_rate") or 0) * 100
    spend = float(e.get("public_spending_rate") or 0) * 100
    sat = int(float(e.get("public_satisfaction") or 0))
    sectors = "، ".join(t_sector(s) for s in _jlist(baseline.get("sectors_json"))) or "نامشخص"
    resources = "، ".join(SECTOR.get(r, r) for r in _jlist(baseline.get("resources_json"))) or "نامشخص"
    gdp_now = e.get("gdp")
    treas = e.get("treasury")
    return (
        "💰 اطلاعات اقتصادی\n\n"
        f"اقتصاد پایه: {fa_int(baseline.get('gdp_ref'))} دلار\n"
        f"اقتصاد فعلی بازی: {fa_int(gdp_now, approx=False) if gdp_now is not None else '—'}\n"
        f"خزانه: {fa_int(treas, approx=False) if treas is not None else '—'}\n"
        f"مالیات: {fa_digits(str(int(tax)))}٪\n"
        f"مخارج عمومی: {fa_digits(str(int(spend)))}٪\n"
        f"رضایت مردم: {fa_digits(str(sat))}\n"
        f"بخش‌های مهم: {sectors}\n"
        f"منابع: {resources}\n"
        f"واحد پول: {baseline.get('currency_name') or baseline.get('currency_code') or 'نامشخص'}"
    )


def orgs_card(baseline: dict) -> str:
    orgs = "\n".join(f"• {t_org(o)}" for o in _jlist(baseline.get("organizations_json"))) or "• نامشخص"
    return (
        "🌐 سازمان‌ها و پیمان‌ها\n\n"
        f"{t_npt(baseline.get('npt_status'))}\n\n"
        f"عضویت‌ها:\n{orgs}"
    )


def relations_card(baseline: dict) -> str:
    return (
        "🤝 روابط خارجی و تنش‌ها\n\n"
        f"ائتلاف‌ها و مشارکت‌ها:\n{baseline.get('allies_note') or 'اطلاعات کافی ثبت نشده'}\n\n"
        f"تنش‌ها در آغاز ۲۰۲۰:\n{baseline.get('tensions_2020') or 'اطلاعات کافی ثبت نشده'}"
    )


def sectors_card(sectors: list[dict]) -> str:
    if not sectors:
        return "🏭 بخش تولید\nهنوز داده‌ای نیست."
    lines = ["🏭 تولید و سرمایه‌گذاری", ""]
    for s in sectors:
        level = int(float(s.get("output_level") or 0))
        lines.append(
            f"• {t_sector(s['sector_code'])}: سطح {fa_digits(str(level))} | "
            f"سرمایه {fa_int(s.get('investment'), approx=False)}"
        )
    return "\n".join(lines)


def cabinet_card(rows: list[dict]) -> str:
    if not rows:
        return "🏛 کابینه خالی است.\nبا دکمه‌های انتصاب وزیر انتخاب کنید."
    lines = ["🏛 دولت و کابینه", ""]
    for r in rows:
        lines.append(
            f"• {t_portfolio(r['portfolio'])}: {r['minister_name']} "
            f"(توانایی {fa_digits(int(r.get('competence') or 0))})"
        )
    return "\n".join(lines)


def world_list_card(rows: list[dict], page: int, per: int = 10) -> str:
    chunk = rows[page * per : (page + 1) * per]
    lines = ["🗺 کشورهای جهان", ""]
    for r in chunk:
        flag = r.get("flag") or ""
        name = r.get("name_fa") or r.get("name_en")
        st = "بازیکن" if r.get("owner_player_id") else "هوش مصنوعی"
        lines.append(f"{flag} {name} — {st}")
    return "\n".join(lines)


def news_card(items: list[dict], game_date) -> str:
    lines = ["📰 اخبار جهان", f"📅 {fa_date(game_date)}", ""]
    if not items:
        lines.append("خبر تازه‌ای نیست.")
    else:
        for it in items:
            lines.append(f"• {it.get('headline')}")
    return "\n".join(lines)


def need_country() -> str:
    return "هنوز کشوری ندارید.\nاز دکمه «انتخاب کشور» یکی را بردارید."


def claim_confirm(flag: str, name: str) -> str:
    return (
        f"آیا می‌خواهید رهبری {flag} {name} را بپذیرید؟\n"
        "هر بازیکن فقط یک کشور می‌تواند داشته باشد."
    )


def defense_card(economy: Optional[dict], baseline: dict) -> str:
    stab = float((economy or {}).get("stability") or 50)
    return (
        "🛡 دفاع و امنیت\n\n"
        f"ثبات داخلی: {fa_digits(f'{stab:.0f}')}\n"
        "سیاست دفاعی در سطح کلان و انتزاعی است.\n"
        f"زمینه امنیتی آغاز بازی:\n{baseline.get('tensions_2020') or 'ثبت نشده'}"
    )


def build_card() -> str:
    return (
        "🏗 ساخت‌وساز\n\n"
        "پروژه‌های زیرساختی از محل خزانه تأمین می‌شوند.\n"
        "با سرمایه‌گذاری روی بخش‌های اقتصادی در منوی اقتصاد،\n"
        "سطح تولید کشور افزایش می‌یابد.\n\n"
        "دکمه‌های زیر میان‌بر سرمایه‌گذاری هستند."
    )
