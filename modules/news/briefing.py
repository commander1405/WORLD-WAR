"""Persian initial country briefing from historical baseline."""
from __future__ import annotations

import json
from typing import Any

from database.interface import Database
from engine.world_engine import WorldEngine


def _jlist(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


async def build_initial_briefing(db: Database, world: WorldEngine, country_code: str) -> str:
    code = country_code.upper()
    gdate = await world.current_game_date()
    b = await db.fetchrow(
        "SELECT * FROM country_baselines WHERE country_code = $1", (code,)
    )
    c = await db.fetchrow(
        "SELECT * FROM countries WHERE country_code = $1", (code,)
    )
    if not b or not c:
        return "کشور یافت نشد."

    flag = b.get("flag") or c.get("flag") or ""
    name = b.get("name_fa") or b.get("name_en") or code
    pop = b.get("population_ref")
    gdp = b.get("gdp_ref")
    # population_ref column stores number in our seed insert
    pop_n = pop
    gdp_n = gdp
    meta = {}
    try:
        meta = json.loads(b.get("meta_json") or "{}")
    except Exception:
        meta = {}

    langs = "، ".join(_jlist(b.get("languages_json"))) or "نامشخص"
    sectors = "، ".join(_jlist(b.get("sectors_json"))) or "نامشخص"
    orgs = "، ".join(_jlist(b.get("organizations_json"))) or "نامشخص"
    resources = "، ".join(_jlist(b.get("resources_json"))) or "نامشخص"

    def fmt_num(x):
        if x is None:
            return "نامشخص"
        try:
            return f"{float(x):,.0f}"
        except Exception:
            return str(x)

    lines = [
        f"📜 گزارش اولیه کشور {flag} {name}",
        f"📅 تاریخ بازی: {gdate.isoformat()}",
        "",
        f"🏛 نظام حکومتی: {b.get('government_type') or 'نامشخص'}",
        f"👤 رهبر در ۱ ژانویه ۲۰۲۰: {b.get('leader_name') or 'نامشخص'} ({b.get('leader_title') or 'سمت نامشخص'})",
        f"🏙 پایتخت: {b.get('capital') or 'نامشخص'}",
        f"👥 جمعیت (مرجع نزدیک ۲۰۱۹/۲۰۲۰): {fmt_num(pop_n)} — مرجع: {meta.get('population_ref') or b.get('reference_date') or 'نامشخص'}",
        f"💰 GDP اسمی (مرجع): {fmt_num(gdp_n)} USD — {meta.get('gdp_ref') or 'نامشخص'}",
        f"💵 واحد پول: {b.get('currency_name') or ''} ({b.get('currency_code') or 'نامشخص'})",
        f"🗣 زبان‌ها: {langs}",
        f"🏭 بخش‌های مهم اقتصادی: {sectors}",
        f"⛏ منابع: {resources}",
        f"🌐 عضویت‌ها/سازمان‌ها: {orgs}",
        f"☢ وضعیت NPT: {b.get('npt_status') or 'نامشخص'}",
        "",
        f"🤝 روابط/ائتلاف‌ها (در حد مستند شده): {b.get('allies_note') or 'نامشخص'}",
        f"⚠️ تنش‌ها در آستانه ۲۰۲۰: {b.get('tensions_2020') or 'نامشخص'}",
        "",
        "📌 زمینه جهانی ۱ ژانویه ۲۰۲۰: پیش از همه‌گیری جهانی کووید-۱۹ به‌عنوان رویداد غالب؛ رقابت راهبردی آمریکا–چین؛ تداوم منازعات منطقه‌ای در خاورمیانه و اروپای شرقی.",
        "",
        f"منبع/اطمینان: {b.get('source_note') or 'نامشخص'} | confidence={b.get('confidence') or 'n/a'}",
        "اعداد آمار دقیق ساعت صفر ۲۰۲۰-۰۱-۰۱ نیستند؛ از مراجع سالانه نزدیک استفاده شده است.",
    ]
    return "\n".join(lines)
