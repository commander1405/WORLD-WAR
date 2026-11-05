-- Country control, satisfaction, laws, sanctions, straits (non-destructive)

CREATE TABLE IF NOT EXISTS ng_country_control (
    country_code TEXT PRIMARY KEY,
    flights_open INTEGER NOT NULL DEFAULT 1,
    maritime_open INTEGER NOT NULL DEFAULT 1,
    internet_on INTEGER NOT NULL DEFAULT 1,
    satisfaction REAL NOT NULL DEFAULT 70,
    base_daily_income REAL NOT NULL DEFAULT 20000000,
    leader_crisis_until TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_straits (
    strait_code TEXT PRIMARY KEY,
    name_fa TEXT NOT NULL,
    controller_codes TEXT NOT NULL,
    affected_codes TEXT NOT NULL,
    closed INTEGER NOT NULL DEFAULT 0,
    closed_by TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_laws (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    target_country TEXT,
    banned_item TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    income_bonus REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by INTEGER
);

CREATE TABLE IF NOT EXISTS ng_sanctions (
    id INTEGER PRIMARY KEY,
    source_country TEXT NOT NULL,
    target_country TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'trade',
    item_code TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    law_id INTEGER,
    created_at TEXT NOT NULL,
    ends_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_law_daily (
    country_code TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (country_code, day)
);
