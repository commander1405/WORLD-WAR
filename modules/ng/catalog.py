"""Shop catalog — balanced slow growth."""
CATALOG = [
    # ground
    {"item_code":"g_inf","category":"ground","name_fa":"یگان پیاده","description_fa":"نیروی زمینی پایه","unit_price":120_000,"max_per_order":50,"power_score":2,"daily_income":0,"maintenance":800,"is_building":0},
    {"item_code":"g_armor","category":"ground","name_fa":"یگان زرهی","description_fa":"قدرت زمینی پیشرفته","unit_price":450_000,"max_per_order":20,"power_score":8,"daily_income":0,"maintenance":3500,"is_building":0},
    {"item_code":"g_arty","category":"ground","name_fa":"یگان توپخانه","description_fa":"پشتیبانی آتش زمینی","unit_price":380_000,"max_per_order":20,"power_score":6,"daily_income":0,"maintenance":2800,"is_building":0},
    # air
    {"item_code":"a_fight","category":"air","name_fa":"اسکادران جنگنده","description_fa":"قدرت هوایی","unit_price":1_200_000,"max_per_order":10,"power_score":15,"daily_income":0,"maintenance":12000,"is_building":0},
    {"item_code":"a_trans","category":"air","name_fa":"هواپیمای ترابری","description_fa":"لجستیک هوایی","unit_price":700_000,"max_per_order":15,"power_score":4,"daily_income":0,"maintenance":5000,"is_building":0},
    # sea
    {"item_code":"s_patrol","category":"sea","name_fa":"ناوچه گشتی","description_fa":"حضور دریایی","unit_price":900_000,"max_per_order":12,"power_score":10,"daily_income":0,"maintenance":8000,"is_building":0},
    {"item_code":"s_logi","category":"sea","name_fa":"کشتی پشتیبانی","description_fa":"لجستیک دریایی","unit_price":650_000,"max_per_order":12,"power_score":3,"daily_income":0,"maintenance":4500,"is_building":0},
    # defense
    {"item_code":"d_radar","category":"defense","name_fa":"رادار پدافندی","description_fa":"افزایش آمادگی دفاعی","unit_price":400_000,"max_per_order":15,"power_score":5,"daily_income":0,"maintenance":2500,"is_building":0},
    {"item_code":"d_sam","category":"defense","name_fa":"سامانه پدافند هوایی","description_fa":"پوشش دفاعی","unit_price":950_000,"max_per_order":10,"power_score":12,"daily_income":0,"maintenance":7000,"is_building":0},
    # industry / mines
    {"item_code":"b_mine_gold","category":"mine","name_fa":"معدن طلا","description_fa":"درآمد روزانه پایدار","unit_price":5_000_000,"max_per_order":3,"power_score":0,"daily_income":45_000,"maintenance":8000,"is_building":1},
    {"item_code":"b_mine_diamond","category":"mine","name_fa":"معدن الماس","description_fa":"درآمد بالا، هزینه نگهداری زیاد","unit_price":8_000_000,"max_per_order":2,"power_score":0,"daily_income":70_000,"maintenance":15000,"is_building":1},
    {"item_code":"b_mine_iron","category":"mine","name_fa":"معدن آهن","description_fa":"درآمد صنعتی","unit_price":3_500_000,"max_per_order":4,"power_score":0,"daily_income":28_000,"maintenance":5000,"is_building":1},
    {"item_code":"b_mine_copper","category":"mine","name_fa":"معدن مس","description_fa":"مواد معدنی","unit_price":3_200_000,"max_per_order":4,"power_score":0,"daily_income":25_000,"maintenance":4500,"is_building":1},
    {"item_code":"b_refinery","category":"infra","name_fa":"پالایشگاه نفت","description_fa":"درآمد انرژی","unit_price":12_000_000,"max_per_order":2,"power_score":0,"daily_income":95_000,"maintenance":25000,"is_building":1},
    {"item_code":"b_gas","category":"infra","name_fa":"تأسیسات گاز","description_fa":"درآمد گاز","unit_price":9_000_000,"max_per_order":2,"power_score":0,"daily_income":75_000,"maintenance":18000,"is_building":1},
    {"item_code":"b_power","category":"infra","name_fa":"نیروگاه","description_fa":"تولید انرژی و درآمد","unit_price":7_500_000,"max_per_order":3,"power_score":0,"daily_income":55_000,"maintenance":12000,"is_building":1},
    {"item_code":"b_factory","category":"infra","name_fa":"کارخانه تولیدی","description_fa":"صنعت و درآمد","unit_price":6_000_000,"max_per_order":4,"power_score":0,"daily_income":48_000,"maintenance":10000,"is_building":1},
    {"item_code":"b_farm","category":"infra","name_fa":"مجتمع کشاورزی","description_fa":"درآمد پایدار کشاورزی","unit_price":2_500_000,"max_per_order":5,"power_score":0,"daily_income":18_000,"maintenance":3000,"is_building":1},
    {"item_code":"b_nuke_peace","category":"nuclear","name_fa":"نیروگاه هسته‌ای صلح‌آمیز","description_fa":"انرژی غیرنظامی — بدون کاربرد تسلیحاتی","unit_price":25_000_000,"max_per_order":1,"power_score":0,"daily_income":120_000,"maintenance":40000,"is_building":1},
    {"item_code":"sp_scientist","category":"specialist","name_fa":"دانشمند","description_fa":"افزایش جزئی درآمد تحقیق","unit_price":1_500_000,"max_per_order":10,"power_score":0,"daily_income":5_000,"maintenance":2000,"is_building":0},
]

CAT_FA = {
    "ground":"تجهیزات زمینی","air":"تجهیزات هوایی","sea":"تجهیزات دریایی",
    "defense":"پدافند","mine":"معادن و منابع","infra":"زیرساخت صنعتی",
    "nuclear":"فناوری هسته‌ای صلح‌آمیز","specialist":"متخصصان",
}
