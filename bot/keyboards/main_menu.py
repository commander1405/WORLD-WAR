"""Persian menu helpers."""
from __future__ import annotations

MAIN_BUTTONS = [
    "کشور من",
    "وضعیت کشور",
    "مدیریت کشور",
    "انتخاب کشور",
    "اخبار",
    "روابط خارجی",
    "اقتصاد",
    "تنظیمات",
]


def main_menu_text() -> str:
    return (
        "🎮 منوی اصلی WORLD WAR\n"
        "• کشور من\n"
        "• وضعیت کشور\n"
        "• مدیریت کشور\n"
        "• انتخاب کشور\n"
        "• اخبار\n"
        "• روابط خارجی (به‌زودی)\n"
        "• اقتصاد (میانبر مدیریت)\n"
        "• تنظیمات\n"
        "بازگشت همیشه با: منو"
    )


def countries_page_text(rows: list[dict], page: int, per_page: int = 10) -> str:
    start = page * per_page
    chunk = rows[start : start + per_page]
    lines = [f"🌍 انتخاب کشور (صفحه {page + 1})", "برای انتخاب: claim CODE مثلاً claim IR", ""]
    for r in chunk:
        flag = r.get("flag") or ""
        name = r.get("name_fa") or r.get("name_en") or r.get("country_code")
        code = r.get("country_code")
        status = "❌ گرفته‌شده" if r.get("owner_player_id") else "✅ آزاد"
        lines.append(f"{flag} {name} ({code}) — {status}")
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    lines.append("")
    lines.append(f"صفحه {page + 1}/{total_pages} — next / prev")
    lines.append("بازگشت: منو")
    return "\n".join(lines)


def management_help() -> str:
    return (
        "🏛 مدیریت کشور — دستورات واقعی:\n"
        "• داشبورد (یا «مدیریت کشور»)\n"
        "• مالیات 0.15   ← نرخ ۰ تا ۰.۵\n"
        "• مخارج 0.12\n"
        "• سرمایه‌گذاری industry 1000\n"
        "• انتصاب finance علی رضایی\n"
        "• برکناری finance\n"
        "• تیک اقتصادی   ← یک دوره بودجه\n"
        "بازگشت: منو"
    )
