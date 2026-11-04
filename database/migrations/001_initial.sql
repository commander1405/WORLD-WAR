-- WORLD WAR initial schema (portable SQL for SQLite + PostgreSQL)

CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    real_started_at TEXT NOT NULL,
    game_start_date TEXT NOT NULL,
    real_days_per_game_year INTEGER NOT NULL DEFAULT 15,
    last_tick_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS country_baselines (
    country_code TEXT PRIMARY KEY,
    name_en TEXT NOT NULL,
    name_fa TEXT,
    region TEXT,
    capital TEXT,
    population_ref REAL,
    gdp_ref REAL,
    currency_code TEXT,
    reference_date TEXT NOT NULL DEFAULT '2020-01-01',
    source_note TEXT,
    confidence TEXT,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS countries (
    country_code TEXT PRIMARY KEY,
    owner_player_id INTEGER,
    controlled_by TEXT NOT NULL DEFAULT 'ai',
    name_en TEXT NOT NULL,
    name_fa TEXT,
    population REAL,
    treasury REAL NOT NULL DEFAULT 0,
    stability REAL NOT NULL DEFAULT 50,
    prestige REAL NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_countries_owner
    ON countries(owner_player_id) WHERE owner_player_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    username TEXT,
    display_name TEXT,
    country_code TEXT,
    joined_at TEXT NOT NULL,
    last_seen_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_players_country
    ON players(country_code) WHERE country_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS resources (
    country_code TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT,
    PRIMARY KEY (country_code, resource_code)
);

CREATE TABLE IF NOT EXISTS diplomatic_relations (
    country_a TEXT NOT NULL,
    country_b TEXT NOT NULL,
    relation_score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'neutral',
    updated_at TEXT,
    PRIMARY KEY (country_a, country_b)
);

CREATE TABLE IF NOT EXISTS treaties (
    id INTEGER PRIMARY KEY,
    treaty_type TEXT NOT NULL,
    parties_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    signed_game_date TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sanctions (
    id INTEGER PRIMARY KEY,
    target_country TEXT NOT NULL,
    imposed_by TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    started_game_date TEXT,
    ended_game_date TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    game_date TEXT,
    real_time TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_player_id INTEGER,
    country_code TEXT,
    payload_json TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY,
    game_date TEXT,
    real_time TEXT NOT NULL,
    headline TEXT NOT NULL,
    body TEXT,
    country_code TEXT,
    importance INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_country ON events(country_code);
CREATE INDEX IF NOT EXISTS idx_news_country ON news_items(country_code);
