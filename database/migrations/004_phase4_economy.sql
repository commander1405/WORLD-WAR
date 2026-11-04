-- Phase 4: shop, inventory, marketplace, trade, buildings, activity log

CREATE TABLE IF NOT EXISTS shop_catalog (
    item_code TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name_fa TEXT NOT NULL,
    description_fa TEXT NOT NULL,
    unit_price REAL NOT NULL,
    max_per_order INTEGER NOT NULL DEFAULT 50,
    power_score REAL NOT NULL DEFAULT 0,
    maintenance_cost REAL NOT NULL DEFAULT 0,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS inventory_items (
    country_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (country_code, item_code)
);

CREATE TABLE IF NOT EXISTS cart_items (
    player_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (player_id, item_code)
);

CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY,
    seller_country TEXT NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trade_offers (
    id INTEGER PRIMARY KEY,
    from_country TEXT NOT NULL,
    to_country TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    quantity REAL NOT NULL,
    total_price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS country_buildings (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    building_code TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    built_at TEXT NOT NULL,
    last_produced_at TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    country_code TEXT,
    player_id INTEGER,
    game_date TEXT,
    real_time TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS military_status (
    country_code TEXT PRIMARY KEY,
    readiness REAL NOT NULL DEFAULT 40,
    defense_budget_rate REAL NOT NULL DEFAULT 0.05,
    ground_power REAL NOT NULL DEFAULT 0,
    air_power REAL NOT NULL DEFAULT 0,
    sea_power REAL NOT NULL DEFAULT 0,
    defense_power REAL NOT NULL DEFAULT 0,
    updated_at TEXT
);
