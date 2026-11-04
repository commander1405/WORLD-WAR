"""Shop catalog definitions (Persian, abstract game stats)."""
from __future__ import annotations

CATALOG: list[dict] = [
    # پدافند
    {"item_code": "def_radar", "category": "defense", "name_fa": "سامانه رادار پدافندی", "description_fa": "افزایش آمادگی دفاعی کشور", "unit_price": 2500, "max_per_order": 20, "power_score": 8, "maintenance_cost": 15},
    {"item_code": "def_sam", "category": "defense", "name_fa": "سامانه پدافند هوایی", "description_fa": "تقویت پوشش دفاعی انتزاعی", "unit_price": 5000, "max_per_order": 10, "power_score": 15, "maintenance_cost": 30},
    # زمینی
    {"item_code": "gnd_infantry", "category": "ground", "name_fa": "یگان پیاده", "description_fa": "نیروی زمینی پایه", "unit_price": 800, "max_per_order": 100, "power_score": 3, "maintenance_cost": 5},
    {"item_code": "gnd_armor", "category": "ground", "name_fa": "یگان زرهی", "description_fa": "قدرت مانور زمینی", "unit_price": 3500, "max_per_order": 30, "power_score": 12, "maintenance_cost": 20},
    # هوایی
    {"item_code": "air_fighter", "category": "air", "name_fa": "اسکادران جنگنده", "description_fa": "قدرت هوایی انتزاعی", "unit_price": 8000, "max_per_order": 15, "power_score": 20, "maintenance_cost": 40},
    {"item_code": "air_transport", "category": "air", "name_fa": "هواپیمای ترابری", "description_fa": "پشتیبانی لجستیکی", "unit_price": 4000, "max_per_order": 20, "power_score": 6, "maintenance_cost": 18},
    # دریایی
    {"item_code": "sea_patrol", "category": "sea", "name_fa": "ناوچه گشتی", "description_fa": "حضور دریایی محدود", "unit_price": 6000, "max_per_order": 15, "power_score": 14, "maintenance_cost": 25},
    {"item_code": "sea_logistics", "category": "sea", "name_fa": "کشتی لجستیک", "description_fa": "پشتیبانی دریایی", "unit_price": 4500, "max_per_order": 15, "power_score": 5, "maintenance_cost": 15},
    # زیرساخت
    {"item_code": "bld_refinery", "category": "infra", "name_fa": "پالایشگاه نفت", "description_fa": "تولید نفت در هر چرخه بازی", "unit_price": 50000, "max_per_order": 3, "power_score": 0, "maintenance_cost": 200},
    {"item_code": "bld_power", "category": "infra", "name_fa": "نیروگاه", "description_fa": "تولید برق در هر چرخه", "unit_price": 35000, "max_per_order": 5, "power_score": 0, "maintenance_cost": 120},
    {"item_code": "bld_uranium_plant", "category": "infra", "name_fa": "تأسیسات انرژی هسته‌ای صلح‌آمیز", "description_fa": "مدیریت اورانیوم برای انرژی غیرنظامی", "unit_price": 80000, "max_per_order": 2, "power_score": 0, "maintenance_cost": 300},
    {"item_code": "bld_warehouse", "category": "infra", "name_fa": "انبار مرکزی منابع", "description_fa": "افزایش ظرفیت نگهداری", "unit_price": 12000, "max_per_order": 5, "power_score": 0, "maintenance_cost": 40},
    # منابع صنعتی
    {"item_code": "res_oil", "category": "resource", "name_fa": "نفت خام", "description_fa": "منبع انرژی و صادرات", "unit_price": 50, "max_per_order": 500, "power_score": 0, "maintenance_cost": 0},
    {"item_code": "res_gas", "category": "resource", "name_fa": "گاز طبیعی", "description_fa": "منبع انرژی", "unit_price": 30, "max_per_order": 500, "power_score": 0, "maintenance_cost": 0},
    {"item_code": "res_water", "category": "resource", "name_fa": "آب", "description_fa": "منبع حیاتی", "unit_price": 10, "max_per_order": 1000, "power_score": 0, "maintenance_cost": 0},
    {"item_code": "res_power", "category": "resource", "name_fa": "برق", "description_fa": "انرژی مصرفی کشور", "unit_price": 20, "max_per_order": 1000, "power_score": 0, "maintenance_cost": 0},
    {"item_code": "res_uranium", "category": "resource", "name_fa": "اورانیوم (کاربرد صلح‌آمیز)", "description_fa": "سوخت تأسیسات انرژی غیرنظامی", "unit_price": 200, "max_per_order": 100, "power_score": 0, "maintenance_cost": 0},
    {"item_code": "res_minerals", "category": "resource", "name_fa": "مواد معدنی", "description_fa": "ورودی صنعت", "unit_price": 25, "max_per_order": 500, "power_score": 0, "maintenance_cost": 0},
]

CATEGORY_FA = {
    "defense": "پدافند",
    "ground": "نیروی زمینی",
    "air": "تجهیزات هوایی",
    "sea": "تجهیزات دریایی",
    "infra": "زیرساخت‌ها",
    "resource": "منابع و تجهیزات صنعتی",
}

BUILDING_CODES = {"bld_refinery", "bld_power", "bld_uranium_plant", "bld_warehouse"}

# production per world tick per building level
BUILDING_OUTPUT = {
    "bld_refinery": ("res_oil", 25),
    "bld_power": ("res_power", 40),
    "bld_uranium_plant": ("res_uranium", 5),
}
