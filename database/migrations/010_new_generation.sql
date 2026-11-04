-- WORLD WAR New Generation schema (additive / IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS world_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    started_at TEXT NOT NULL,
    war_enabled INTEGER NOT NULL DEFAULT 1,
    nuclear_enabled INTEGER NOT NULL DEFAULT 0,
    log_flags_json TEXT,
    main_group_id TEXT,
    reset_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_players (
    player_id INTEGER PRIMARY KEY,
    username TEXT,
    display_name TEXT,
    country_code TEXT,
    is_banned INTEGER NOT NULL DEFAULT 0,
    ban_reason TEXT,
    banned_until TEXT,
    destroy_cooldown_until TEXT,
    joined_at TEXT,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_countries (
    country_code TEXT PRIMARY KEY,
    name_fa TEXT NOT NULL,
    name_en TEXT,
    flag TEXT,
    capital_fa TEXT,
    leader_fa TEXT,
    leader_title_fa TEXT,
    currency_code TEXT NOT NULL,
    currency_name_fa TEXT NOT NULL,
    npt_member INTEGER NOT NULL DEFAULT 1,
    owner_player_id INTEGER,
    treasury REAL NOT NULL DEFAULT 0,
    daily_income REAL NOT NULL DEFAULT 0,
    daily_expense REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.1,
    hp REAL NOT NULL DEFAULT 1000,
    max_hp REAL NOT NULL DEFAULT 1000,
    is_destroyed INTEGER NOT NULL DEFAULT 0,
    peace_penalty_until TEXT,
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_inventory (
    country_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (country_code, item_code)
);

CREATE TABLE IF NOT EXISTS ng_buildings (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    building_code TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    built_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ng_shop_catalog (
    item_code TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name_fa TEXT NOT NULL,
    description_fa TEXT NOT NULL,
    unit_price REAL NOT NULL,
    max_per_order INTEGER NOT NULL DEFAULT 50,
    power_score REAL NOT NULL DEFAULT 0,
    daily_income REAL NOT NULL DEFAULT 0,
    maintenance REAL NOT NULL DEFAULT 0,
    is_building INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_cart (
    player_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, item_code)
);

CREATE TABLE IF NOT EXISTS ng_market (
    id INTEGER PRIMARY KEY,
    seller_country TEXT NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_peace (
    id INTEGER PRIMARY KEY,
    country_a TEXT NOT NULL,
    country_b TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_hours REAL NOT NULL,
    started_at TEXT,
    ends_at TEXT,
    requested_by TEXT,
    broken_by TEXT
);

CREATE TABLE IF NOT EXISTS ng_statements (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_daily_payouts (
    country_code TEXT NOT NULL,
    payout_date TEXT NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (country_code, payout_date)
);

CREATE TABLE IF NOT EXISTS ng_activity (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    country_code TEXT,
    player_id INTEGER,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS ng_admin_log (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
