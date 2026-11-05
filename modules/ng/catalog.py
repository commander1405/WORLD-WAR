"""Shop catalog — expanded military & economy (simulation-level names)."""
# Existing item_codes preserved so player inventories stay valid.

CATALOG = [
    # ---- Ground ----
    {"item_code":"g_inf","category":"ground","name_fa":"پیاده‌نظام سبک","name_en":"Light Infantry","origin_fa":"عمومی","description_fa":"نیروی پیاده پایه برای کنترل زمین","unit_price":120_000,"max_per_order":80,"power_score":2,"daily_income":0,"maintenance":800,"is_building":0},
    {"item_code":"g_inf_us","category":"ground","name_fa":"پیاده‌نظام آمریکا","name_en":"US Infantry","origin_fa":"آمریکا","description_fa":"یگان پیاده با تجهیزات استاندارد آمریکایی","unit_price":180_000,"max_per_order":60,"power_score":3,"daily_income":0,"maintenance":1200,"is_building":0},
    {"item_code":"g_inf_ru","category":"ground","name_fa":"پیاده‌نظام روسیه","name_en":"Russian Infantry","origin_fa":"روسیه","description_fa":"یگان پیاده با الگوی روسی","unit_price":160_000,"max_per_order":60,"power_score":3,"daily_income":0,"maintenance":1100,"is_building":0},
    {"item_code":"g_inf_ir","category":"ground","name_fa":"پیاده‌نظام ایران","name_en":"Iranian Infantry","origin_fa":"ایران","description_fa":"یگان پیاده با الگوی ایرانی","unit_price":150_000,"max_per_order":60,"power_score":2.5,"daily_income":0,"maintenance":1000,"is_building":0},
    {"item_code":"g_inf_de","category":"ground","name_fa":"پیاده‌نظام آلمان","name_en":"German Infantry","origin_fa":"آلمان","description_fa":"یگان پیاده با الگوی آلمانی","unit_price":175_000,"max_per_order":60,"power_score":3,"daily_income":0,"maintenance":1150,"is_building":0},
    {"item_code":"g_mech","category":"ground","name_fa":"پیاده‌نظام مکانیزه","name_en":"Mechanized Infantry","origin_fa":"عمومی","description_fa":"پیاده با خودروهای زره‌پوش","unit_price":320_000,"max_per_order":40,"power_score":5,"daily_income":0,"maintenance":2200,"is_building":0},
    {"item_code":"g_armor","category":"ground","name_fa":"تانک اصلی میدان نبرد","name_en":"Main Battle Tank","origin_fa":"عمومی","description_fa":"قدرت زرهی خط مقدم","unit_price":450_000,"max_per_order":25,"power_score":8,"daily_income":0,"maintenance":3500,"is_building":0},
    {"item_code":"g_tank_abrams","category":"ground","name_fa":"تانک آبرامز","name_en":"M1 Abrams","origin_fa":"آمریکا","description_fa":"تانک اصلی میدان نبرد آمریکایی","unit_price":900_000,"max_per_order":12,"power_score":14,"daily_income":0,"maintenance":7000,"is_building":0},
    {"item_code":"g_tank_t90","category":"ground","name_fa":"تانک تی-۹۰","name_en":"T-90","origin_fa":"روسیه","description_fa":"تانک اصلی میدان نبرد روسی","unit_price":750_000,"max_per_order":14,"power_score":12,"daily_income":0,"maintenance":6000,"is_building":0},
    {"item_code":"g_apc","category":"ground","name_fa":"خودروی زرهی","name_en":"Armored Vehicle","origin_fa":"عمومی","description_fa":"نقل‌وانتقال و پشتیبانی زرهی","unit_price":280_000,"max_per_order":30,"power_score":4,"daily_income":0,"maintenance":2000,"is_building":0},
    {"item_code":"g_arty","category":"ground","name_fa":"توپخانه","name_en":"Artillery","origin_fa":"عمومی","description_fa":"پشتیبانی آتش زمینی","unit_price":380_000,"max_per_order":20,"power_score":6,"daily_income":0,"maintenance":2800,"is_building":0},
    {"item_code":"g_eng","category":"ground","name_fa":"مهندسی و پشتیبانی زمینی","name_en":"Combat Engineers","origin_fa":"عمومی","description_fa":"پشتیبانی مهندسی و لجستیک زمینی","unit_price":220_000,"max_per_order":25,"power_score":2,"daily_income":0,"maintenance":1500,"is_building":0},

    # ---- Air ----
    {"item_code":"a_fight","category":"air","name_fa":"اسکادران جنگنده عمومی","name_en":"Fighter Squadron","origin_fa":"عمومی","description_fa":"قدرت هوایی پایه","unit_price":1_200_000,"max_per_order":12,"power_score":15,"daily_income":0,"maintenance":12000,"is_building":0},
    {"item_code":"a_f22","category":"air","name_fa":"جنگنده F-22 Raptor","name_en":"F-22 Raptor","origin_fa":"آمریکا","description_fa":"جنگنده پنهان‌کار نسل پنجم","unit_price":4_500_000,"max_per_order":4,"power_score":35,"daily_income":0,"maintenance":45000,"is_building":0},
    {"item_code":"a_f35","category":"air","name_fa":"جنگنده F-35 Lightning II","name_en":"F-35 Lightning II","origin_fa":"آمریکا","description_fa":"جنگنده چندمنظوره نسل پنجم","unit_price":3_800_000,"max_per_order":5,"power_score":30,"daily_income":0,"maintenance":38000,"is_building":0},
    {"item_code":"a_f16","category":"air","name_fa":"جنگنده F-16 Fighting Falcon","name_en":"F-16 Fighting Falcon","origin_fa":"آمریکا","description_fa":"جنگنده چندمنظوره سبک","unit_price":2_200_000,"max_per_order":8,"power_score":20,"daily_income":0,"maintenance":18000,"is_building":0},
    {"item_code":"a_f15","category":"air","name_fa":"جنگنده F-15 Eagle","name_en":"F-15 Eagle","origin_fa":"آمریکا","description_fa":"جنگنده برتری هوایی","unit_price":2_800_000,"max_per_order":6,"power_score":24,"daily_income":0,"maintenance":22000,"is_building":0},
    {"item_code":"a_su35","category":"air","name_fa":"جنگنده Su-35","name_en":"Su-35","origin_fa":"روسیه","description_fa":"جنگنده برتری هوایی روسی","unit_price":2_600_000,"max_per_order":6,"power_score":23,"daily_income":0,"maintenance":20000,"is_building":0},
    {"item_code":"a_su57","category":"air","name_fa":"جنگنده Su-57","name_en":"Su-57","origin_fa":"روسیه","description_fa":"جنگنده نسل پنجم روسی","unit_price":4_200_000,"max_per_order":4,"power_score":32,"daily_income":0,"maintenance":42000,"is_building":0},
    {"item_code":"a_b2","category":"air","name_fa":"بمب‌افکن B-2 Spirit","name_en":"B-2 Spirit","origin_fa":"آمریکا","description_fa":"بمب‌افکن پنهان‌کار راهبردی","unit_price":8_000_000,"max_per_order":2,"power_score":40,"daily_income":0,"maintenance":80000,"is_building":0},
    {"item_code":"a_b52","category":"air","name_fa":"بمب‌افکن B-52","name_en":"B-52 Stratofortress","origin_fa":"آمریکا","description_fa":"بمب‌افکن راهبردی سنگین","unit_price":5_500_000,"max_per_order":3,"power_score":28,"daily_income":0,"maintenance":50000,"is_building":0},
    {"item_code":"a_trans","category":"air","name_fa":"هواپیمای ترابری C-130","name_en":"C-130 Hercules","origin_fa":"آمریکا","description_fa":"ترابری تاکتیکی هوایی","unit_price":700_000,"max_per_order":15,"power_score":4,"daily_income":0,"maintenance":5000,"is_building":0},
    {"item_code":"a_awacs","category":"air","name_fa":"هواپیمای هشدار زودهنگام AWACS","name_en":"AWACS","origin_fa":"عمومی","description_fa":"فرماندهی و کنترل هوایی","unit_price":3_500_000,"max_per_order":3,"power_score":12,"daily_income":0,"maintenance":25000,"is_building":0},
    {"item_code":"a_recon","category":"air","name_fa":"هواپیمای شناسایی","name_en":"Reconnaissance Aircraft","origin_fa":"عمومی","description_fa":"جمع‌آوری اطلاعات هوایی","unit_price":1_100_000,"max_per_order":8,"power_score":6,"daily_income":0,"maintenance":8000,"is_building":0},
    {"item_code":"a_tanker","category":"air","name_fa":"هواپیمای سوخت‌رسان","name_en":"Aerial Tanker","origin_fa":"عمومی","description_fa":"افزایش برد عملیات هوایی","unit_price":1_800_000,"max_per_order":6,"power_score":3,"daily_income":0,"maintenance":10000,"is_building":0},

    # ---- Missiles ----
    {"item_code":"m_cruise","category":"missile","name_fa":"موشک کروز تاماهاوک","name_en":"Tomahawk Cruise Missile","origin_fa":"آمریکا","description_fa":"موشک کروز دوربرد (سطح بازی)","unit_price":1_500_000,"max_per_order":10,"power_score":18,"daily_income":0,"maintenance":2000,"is_building":0},
    {"item_code":"m_ballistic","category":"missile","name_fa":"موشک بالستیک","name_en":"Ballistic Missile","origin_fa":"عمومی","description_fa":"موشک بالستیک سطح بازی","unit_price":2_200_000,"max_per_order":6,"power_score":22,"daily_income":0,"maintenance":3000,"is_building":0},
    {"item_code":"m_antiship","category":"missile","name_fa":"موشک ضدکشتی","name_en":"Anti-Ship Missile","origin_fa":"عمومی","description_fa":"حمله به اهداف دریایی","unit_price":900_000,"max_per_order":12,"power_score":14,"daily_income":0,"maintenance":1500,"is_building":0},
    {"item_code":"m_sam_patriot","category":"missile","name_fa":"موشک پدافندی پاتریوت","name_en":"Patriot","origin_fa":"آمریکا","description_fa":"سامانه موشکی پدافند هوایی","unit_price":1_800_000,"max_per_order":8,"power_score":16,"daily_income":0,"maintenance":5000,"is_building":0},
    {"item_code":"m_sam_s400","category":"missile","name_fa":"سامانه S-400","name_en":"S-400","origin_fa":"روسیه","description_fa":"پدافند هوایی دوربرد","unit_price":2_400_000,"max_per_order":5,"power_score":20,"daily_income":0,"maintenance":7000,"is_building":0},
    {"item_code":"m_aam","category":"missile","name_fa":"موشک هوا به هوا Meteor","name_en":"Meteor AAM","origin_fa":"اروپا","description_fa":"موشک هوا به هوا دوربرد","unit_price":600_000,"max_per_order":20,"power_score":10,"daily_income":0,"maintenance":800,"is_building":0},
    {"item_code":"m_agm","category":"missile","name_fa":"موشک هوا به زمین","name_en":"Air-to-Ground Missile","origin_fa":"عمومی","description_fa":"حمله هوایی به اهداف زمینی","unit_price":550_000,"max_per_order":20,"power_score":9,"daily_income":0,"maintenance":700,"is_building":0},

    # ---- Sea ----
    {"item_code":"s_patrol","category":"sea","name_fa":"ناوچه گشتی","name_en":"Patrol Frigate","origin_fa":"عمومی","description_fa":"حضور دریایی پایه","unit_price":900_000,"max_per_order":12,"power_score":10,"daily_income":0,"maintenance":8000,"is_building":0},
    {"item_code":"s_carrier","category":"sea","name_fa":"ناو هواپیمابر Gerald R. Ford","name_en":"Gerald R. Ford Carrier","origin_fa":"آمریکا","description_fa":"ناو هواپیمابر راهبردی (سطح بازی)","unit_price":25_000_000,"max_per_order":1,"power_score":55,"daily_income":0,"maintenance":120000,"is_building":0},
    {"item_code":"s_destroyer","category":"sea","name_fa":"ناوشکن","name_en":"Destroyer","origin_fa":"عمومی","description_fa":"ناو جنگی چندمنظوره","unit_price":3_500_000,"max_per_order":6,"power_score":22,"daily_income":0,"maintenance":25000,"is_building":0},
    {"item_code":"s_frigate","category":"sea","name_fa":"ناوچه","name_en":"Frigate","origin_fa":"عمومی","description_fa":"ناوچه رزمی","unit_price":2_200_000,"max_per_order":8,"power_score":16,"daily_income":0,"maintenance":15000,"is_building":0},
    {"item_code":"s_cruiser","category":"sea","name_fa":"رزم‌ناو","name_en":"Cruiser","origin_fa":"عمومی","description_fa":"رزم‌ناو سنگین","unit_price":4_800_000,"max_per_order":4,"power_score":28,"daily_income":0,"maintenance":35000,"is_building":0},
    {"item_code":"s_sub","category":"sea","name_fa":"زیردریایی","name_en":"Submarine","origin_fa":"عمومی","description_fa":"زیردریایی چندمنظوره","unit_price":3_200_000,"max_per_order":5,"power_score":20,"daily_income":0,"maintenance":22000,"is_building":0},
    {"item_code":"s_sub_attack","category":"sea","name_fa":"زیردریایی تهاجمی","name_en":"Attack Submarine","origin_fa":"عمومی","description_fa":"شکار اهداف دریایی","unit_price":4_000_000,"max_per_order":4,"power_score":26,"daily_income":0,"maintenance":28000,"is_building":0},
    {"item_code":"s_sub_missile","category":"sea","name_fa":"زیردریایی موشک‌بر","name_en":"Missile Submarine","origin_fa":"عمومی","description_fa":"پرتاب موشک از دریا","unit_price":6_500_000,"max_per_order":2,"power_score":32,"daily_income":0,"maintenance":40000,"is_building":0},
    {"item_code":"s_logi","category":"sea","name_fa":"کشتی پشتیبانی","name_en":"Support Ship","origin_fa":"عمومی","description_fa":"لجستیک دریایی","unit_price":650_000,"max_per_order":12,"power_score":3,"daily_income":0,"maintenance":4500,"is_building":0},

    # ---- Defense ----
    {"item_code":"d_radar","category":"defense","name_fa":"رادار پدافندی","name_en":"Defense Radar","origin_fa":"عمومی","description_fa":"افزایش آمادگی دفاعی","unit_price":400_000,"max_per_order":15,"power_score":5,"daily_income":0,"maintenance":2500,"is_building":0},
    {"item_code":"d_sam","category":"defense","name_fa":"سامانه پدافند هوایی زمینی","name_en":"Ground SAM","origin_fa":"عمومی","description_fa":"پوشش دفاع هوایی","unit_price":950_000,"max_per_order":10,"power_score":12,"daily_income":0,"maintenance":7000,"is_building":0},

    # ---- Economy / infra (preserved) ----
    {"item_code":"b_mine_gold","category":"mine","name_fa":"معدن طلا","name_en":"Gold Mine","origin_fa":"عمومی","description_fa":"درآمد روزانه پایدار","unit_price":5_000_000,"max_per_order":3,"power_score":0,"daily_income":45_000,"maintenance":8000,"is_building":1},
    {"item_code":"b_mine_iron","category":"mine","name_fa":"معدن آهن","name_en":"Iron Mine","origin_fa":"عمومی","description_fa":"منبع صنعتی","unit_price":3_500_000,"max_per_order":4,"power_score":0,"daily_income":28_000,"maintenance":5000,"is_building":1},
    {"item_code":"b_mine_oil","category":"mine","name_fa":"میدان نفتی","name_en":"Oil Field","origin_fa":"عمومی","description_fa":"درآمد نفتی","unit_price":8_000_000,"max_per_order":2,"power_score":0,"daily_income":70_000,"maintenance":15000,"is_building":1},
    {"item_code":"b_refinery","category":"infra","name_fa":"پالایشگاه نفت","name_en":"Oil Refinery","origin_fa":"عمومی","description_fa":"درآمد انرژی","unit_price":12_000_000,"max_per_order":2,"power_score":0,"daily_income":95_000,"maintenance":25000,"is_building":1},
    {"item_code":"b_gas","category":"infra","name_fa":"تأسیسات گاز","name_en":"Gas Facility","origin_fa":"عمومی","description_fa":"درآمد گاز","unit_price":9_000_000,"max_per_order":2,"power_score":0,"daily_income":75_000,"maintenance":18000,"is_building":1},
    {"item_code":"b_power","category":"infra","name_fa":"نیروگاه","name_en":"Power Plant","origin_fa":"عمومی","description_fa":"تولید انرژی و درآمد","unit_price":7_500_000,"max_per_order":3,"power_score":0,"daily_income":55_000,"maintenance":12000,"is_building":1},
    {"item_code":"b_factory","category":"infra","name_fa":"کارخانه تولیدی","name_en":"Factory","origin_fa":"عمومی","description_fa":"صنعت و درآمد","unit_price":6_000_000,"max_per_order":4,"power_score":0,"daily_income":48_000,"maintenance":10000,"is_building":1},
    {"item_code":"b_farm","category":"infra","name_fa":"مجتمع کشاورزی","name_en":"Agri Complex","origin_fa":"عمومی","description_fa":"درآمد پایدار کشاورزی","unit_price":2_500_000,"max_per_order":5,"power_score":0,"daily_income":18_000,"maintenance":3000,"is_building":1},
    {"item_code":"b_nuke_peace","category":"nuclear","name_fa":"نیروگاه هسته‌ای صلح‌آمیز","name_en":"Peaceful Nuclear Plant","origin_fa":"عمومی","description_fa":"انرژی غیرنظامی — بدون کاربرد تسلیحاتی","unit_price":25_000_000,"max_per_order":1,"power_score":0,"daily_income":120_000,"maintenance":40000,"is_building":1},
    {"item_code":"sp_scientist","category":"specialist","name_fa":"دانشمند","name_en":"Scientist","origin_fa":"عمومی","description_fa":"افزایش جزئی درآمد تحقیق","unit_price":1_500_000,"max_per_order":10,"power_score":0,"daily_income":5_000,"maintenance":2000,"is_building":0},
    {"item_code":"res_uranium_90","category":"nuclear","name_fa":"اورانیوم ۹۰٪","name_en":"Uranium 90%","origin_fa":"عمومی","description_fa":"ماده بازی برای ساخت بمب اتم انتزاعی","unit_price":20_000_000,"max_per_order":20,"power_score":0,"daily_income":0,"maintenance":0,"is_building":0},
    {"item_code":"item_atom_bomb","category":"nuclear","name_fa":"بمب اتم (بازی)","name_en":"Game Atom Bomb","origin_fa":"عمومی","description_fa":"تجهیز انتزاعی حمله هسته‌ای بازی","unit_price":50_000_000,"max_per_order":5,"power_score":0,"daily_income":0,"maintenance":0,"is_building":0},
    {"item_code":"cyber_hack_def","category":"cyber","name_fa":"هکر پدافند","name_en":"Defense Hacker","origin_fa":"عمومی","description_fa":"اختلال موقت ۳۰٪ در ظرفیت پدافند هدف به مدت ۲ دقیقه","unit_price":8_000_000,"max_per_order":5,"power_score":0,"daily_income":0,"maintenance":0,"is_building":0},
    {"item_code":"cyber_hack_asset","category":"cyber","name_fa":"هکر دارایی","name_en":"Asset Hacker","origin_fa":"عمومی","description_fa":"شناسایی اطلاعات اقتصادی و نظامی کشور هدف بدون تغییر دارایی","unit_price":5_000_000,"max_per_order":8,"power_score":0,"daily_income":0,"maintenance":0,"is_building":0},
    {"item_code":"res_uranium","category":"mine","name_fa":"اورانیوم (واحد بازی)","name_en":"Uranium Unit","origin_fa":"عمومی","description_fa":"منبع صلح‌آمیز کارگاه","unit_price":50_000,"max_per_order":100,"power_score":0,"daily_income":0,"maintenance":0,"is_building":0},
]

# Ordered for shop display (military & cyber first)
CAT_FA = {
    "cyber": "💻 هک و امنیت",
    "missile": "🚀 موشک‌ها",
    "air": "✈️ نیروی هوایی",
    "sea": "🚢 نیروی دریایی",
    "ground": "🪖 نیروی زمینی",
    "defense": "🛡 پدافند",
    "mine": "⛏ معادن و منابع",
    "infra": "🏗 زیرساخت صنعتی",
    "nuclear": "☢ فناوری هسته‌ای",
    "specialist": "👨‍🔬 متخصصان",
}

def items_in_category(cat: str) -> list:
    return [c for c in CATALOG if c.get("category") == cat]
