import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.ui.format import fa_digits, fa_int, fa_date, t_gov, t_npt, t_org
from bot.ui.views import overview_card, orgs_card, help_text, economy_base_card
from bot.ui.keyboards import main_reply_keyboard, country_pick_keyboard, my_country_menu


def test_fa_digits():
    assert fa_digits("2020") == "۲۰۲۰"
    assert "میلیون" in fa_int(83_000_000) or "۸۳" in fa_int(83_000_000)


def test_labels_persian():
    assert "جمهوری" in t_gov("Islamic Republic")
    assert "پیمان" in t_npt("NPT party")
    assert "سازمان ملل" in t_org("UN")


def test_overview_has_sections_no_confidence():
    country = {"name_fa": "ایران", "population": 83e6, "stability": 50, "flag": "🇮🇷"}
    baseline = {
        "flag": "🇮🇷",
        "name_fa": "ایران",
        "leader_name": "حسن روحانی",
        "leader_title": "President",
        "government_type": "Islamic Republic",
        "capital": "تهران",
        "population_ref": 83e6,
        "gdp_ref": 258e9,
        "currency_name": "ریال",
        "resources_json": '["oil","gas"]',
        "npt_status": "NPT party",
        "organizations_json": '["UN","OPEC"]',
        "allies_note": "همکاری‌های منطقه‌ای",
        "tensions_2020": "تنش‌های منطقه‌ای",
    }
    text = overview_card(country, baseline, {"public_satisfaction": 55, "stability": 50, "gdp": 258e9}, date(2020, 1, 1))
    assert "ایران" in text
    assert "حسن روحانی" in text
    assert "confidence" not in text.lower()
    assert "World Bank" not in text
    org = orgs_card(baseline)
    assert "منع گسترش" in org or "پیمان" in org
    assert "سازمان ملل" in org


def test_keyboards_build():
    kb = main_reply_keyboard()
    assert kb is not None
    rows = [
        {"country_code": "IR", "name_fa": "ایران", "flag": "🇮🇷", "owner_player_id": None},
        {"country_code": "US", "name_fa": "آمریکا", "flag": "🇺🇸", "owner_player_id": 1},
    ]
    ik = country_pick_keyboard(rows, 0)
    assert ik is not None
    assert my_country_menu() is not None
    assert "راهنما" in help_text()
