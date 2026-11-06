-- Legendary items, player wallet (permanent to player_id), timed effects
CREATE TABLE IF NOT EXISTS ng_legendary_defs (
    item_code TEXT PRIMARY KEY,
    name_fa TEXT NOT NULL,
    description_fa TEXT NOT NULL,
    power_fa TEXT NOT NULL,
    effect_type TEXT NOT NULL,
    target_mode TEXT NOT NULL DEFAULT 'other',
    duration_sec INTEGER NOT NULL DEFAULT 0,
    uses_per_unit INTEGER NOT NULL DEFAULT 20,
    price REAL NOT NULL DEFAULT 2000,
    image_path TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ng_player_wallet (
    player_id INTEGER PRIMARY KEY,
    balance REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_wallet_tx (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT,
    actor_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_player_legendary (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    uses_left INTEGER NOT NULL,
    acquired_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_legendary_effects (
    id INTEGER PRIMARY KEY,
    effect_type TEXT NOT NULL,
    source_player_id INTEGER,
    target_country TEXT,
    strength REAL NOT NULL DEFAULT 0,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    income_applied INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_legendary_usage_log (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    stack_id INTEGER,
    target_country TEXT,
    result TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_legendary_purchase_log (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    price REAL NOT NULL,
    uses_granted INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leg_player ON ng_player_legendary(player_id);
CREATE INDEX IF NOT EXISTS idx_leg_effects_target ON ng_legendary_effects(target_country);
CREATE INDEX IF NOT EXISTS idx_wallet_tx_player ON ng_wallet_tx(player_id);
