"""Persian inline/reply keyboard helpers for Bale."""
from __future__ import annotations

MAIN_BUTTONS = [
    "کشور من",
    "وضعیت کشور",
    "انتخاب کشور",
    "اخبار",
    "روابط خارجی",
    "اقتصاد",
    "تنظیمات",
]


def main_menu_text() -> str:
    return (
        "🎮 منوی اصلی WORLD WAR\n"
        "یکی از گزینه‌ها را ارسال کنید:\n"
        "• کشور من\n"
        "• وضعیت کشور\n"
        "• انتخاب کشور\n"
        "• اخبار\n"
        "• روابط خارجی (به‌زودی)\n"
        "• اقتصاد (به‌زودی)\n"
        "• تنظیمات"
    )


def countries_page_text(rows: list[dict], page: int, per_page: int = 10) -> str:
    start = page * per_page
    chunk = rows[start : start + per_page]
    lines = [f"🌍 انتخاب کشور (صفحه {page + 1})", "برای انتخاب: claim CODE مثلاً claim IR", ""]
    for r in chunk:
        flag = r.get("flag") or ""
        name = r.get("name_fa") or r.get("name_en") or r.get("country_code")
        code = r.get("country_code")
        if r.get("owner_player_id"):
            status = "❌ گرفته‌شده"
        else:
            status = "✅ آزاد"
        lines.append(f"{flag} {name} ({code}) — {status}")
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    lines.append("")
    lines.append(f"صفحه {page + 1}/{total_pages} — next / prev")
    lines.append("بازگشت: منو")
    return "\n".join(lines)
