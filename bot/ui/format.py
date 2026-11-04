"""Persian display helpers — numbers, dates, labels (UI only)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

GOV = {
    "Islamic Republic": "جمهوری اسلامی",
    "Socialist republic (one-party)": "جمهوری سوسیالیستی (تک‌حزبی)",
    "Federal parliamentary republic": "جمهوری فدرال پارلمانی",
    "Constitutional monarchy / parliamentary": "پادشاهی مشروطه پارلمانی",
    "Presidential republic": "جمهوری ریاستی",
    "Absolute monarchy": "پادشاهی مطلقه",
    "One-party socialist state": "دولت سوسیالیستی تک‌حزبی",
    "Semi-presidential republic": "جمهوری نیمه‌ریاستی",
    "Federal semi-presidential republic": "جمهوری فدرال نیمه‌ریاستی",
    "Parliamentary republic": "جمهوری پارلمانی",
    "Parliamentary constitutional monarchy": "پادشاهی مشروطه پارلمانی",
    "Federal presidential republic": "جمهوری فدرال ریاستی",
    "Federal parliamentary constitutional monarchy": "پادشاهی مشروطه فدرال پارلمانی",
    "Federal monarchy": "پادشاهی فدرال",
}

TITLE = {
    "President": "رئیس‌جمهور",
    "Prime Minister": "نخست‌وزیر",
    "King": "پادشاه",
    "Chancellor": "صدر اعظم",
    "Supreme Leader": "رهبر عالی",
    "President / CPC General Secretary": "رئیس‌جمهور / دبیرکل حزب",
}

NPT = {
    "NPT party": "عضو پیمان منع گسترش سلاح‌های هسته‌ای",
    "NPT nuclear-weapon state": "عضو پیمان منع گسترش — دارندۀ سلاح هسته‌ای",
    "not an NPT party": "غیرعضو پیمان منع گسترش سلاح‌های هسته‌ای",
    "withdrew from NPT (historical)": "خروج تاریخی از پیمان منع گسترش",
    "NPT party (non-nuclear after denuclearization)": "عضو پیمان پس از خلع سلاح هسته‌ای",
    "NPT party (voluntarily denuclearized historically)": "عضو پیمان پس از خلع سلاح داوطلبانه",
}

SECTOR = {
    "agriculture": "کشاورزی",
    "industry": "صنعت",
    "services": "خدمات",
    "energy": "انرژی",
    "oil and gas": "نفت و گاز",
    "manufacturing": "تولید صنعتی",
    "technology": "فناوری",
    "mining": "معدن",
    "defense industry": "صنایع دفاعی",
    "finance": "مالی",
    "tourism": "گردشگری",
    "textiles": "نساجی",
    "construction": "ساخت‌وساز",
    "petrochemicals": "پتروشیمی",
    "electronics": "الکترونیک",
    "automotive": "خودرو",
    "shipbuilding": "کشتی‌سازی",
    "resources": "منابع",
    "state industry": "صنعت دولتی",
    "military": "نظامی",
    "infrastructure": "زیرساخت",
    "IT": "فناوری اطلاعات",
    "aerospace": "هوافضا",
    "luxury": "کالاهای لوکس",
    "education": "آموزش",
    "logistics": "لجستیک",
}

PORTFOLIO = {
    "finance": "دارایی",
    "defense": "دفاع",
    "foreign": "امور خارجه",
    "interior": "کشور",
    "economy": "اقتصاد",
}

ORG = {
    "UN": "سازمان ملل متحد",
    "OPEC": "اوپک",
    "ECO": "اکو",
    "WTO": "سازمان تجارت جهانی",
    "SCO": "سازمان همکاری شانگهای",
    "BRICS": "بریکس",
    "NATO": "ناتو",
    "OECD": "سازمان همکاری و توسعه اقتصادی",
    "G7": "گروه هفت",
    "G20": "گروه بیست",
    "EU": "اتحادیه اروپا",
    "OIC": "سازمان همکاری اسلامی",
    "ASEAN": "آسه‌آن",
    "AU": "اتحادیه آفریقا",
    "Arab League": "اتحادیه عرب",
    "GCC": "شورای همکاری خلیج فارس",
    "Commonwealth": "مشترک‌المنافع",
    "EAEU": "اتحادیه اقتصادی اوراسیا",
    "Mercosur": "مرکوسور",
    "USMCA": "توافق آمریکا–مکزیک–کانادا",
    "ECOWAS": "اکوواس",
    "Five Eyes": "پنج چشم",
}


def fa_digits(value: Any) -> str:
    return str(value).translate(_DIGITS)


def fa_int(n: Optional[float], approx: bool = True) -> str:
    if n is None:
        return "نامشخص"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "نامشخص"
    if n >= 1_000_000_000_000:
        s = f"{n/1_000_000_000_000:.1f} تریلیون"
    elif n >= 1_000_000_000:
        s = f"{n/1_000_000_000:.0f} میلیارد"
    elif n >= 1_000_000:
        s = f"{n/1_000_000:.0f} میلیون"
    else:
        s = f"{n:,.0f}"
    s = fa_digits(s.replace(",", "٬"))
    return f"حدود {s}" if approx else s


def fa_date(d: date | str) -> str:
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except Exception:
            return fa_digits(d)
    months = [
        "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
        "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
    ]
    return fa_digits(f"{d.day} {months[d.month-1]} {d.year}")


def t_gov(s: Optional[str]) -> str:
    return GOV.get(s or "", s or "نامشخص")


def t_title(s: Optional[str]) -> str:
    return TITLE.get(s or "", s or "سمت نامشخص")


def t_npt(s: Optional[str]) -> str:
    return NPT.get(s or "", s or "نامشخص")


def t_sector(s: str) -> str:
    return SECTOR.get(s, s)


def t_portfolio(s: str) -> str:
    return PORTFOLIO.get(s, s)


def t_org(s: str) -> str:
    return ORG.get(s, s)


def status_dot(level: str) -> str:
    return {"good": "🟢", "mid": "🟡", "bad": "🔴", "info": "🔵"}.get(level, "⚪")
