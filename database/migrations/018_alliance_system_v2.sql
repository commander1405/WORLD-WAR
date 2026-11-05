-- Alliance System 2.0 — real alliances (separate from peace treaties)

CREATE TABLE IF NOT EXISTS ng_alliances (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    founder_country TEXT NOT NULL,
    founder_player_id INTEGER NOT NULL,
    max_members INTEGER NOT NULL,
    treasury_cap REAL NOT NULL,
    treasury REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    dissolved_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_alliance_members (
    alliance_id INTEGER NOT NULL,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL,
    PRIMARY KEY (alliance_id, country_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ng_am_country ON ng_alliance_members(country_code);

CREATE TABLE IF NOT EXISTS ng_alliance_tx (
    id INTEGER PRIMARY KEY,
    alliance_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    actor_player_id INTEGER,
    country_code TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_alliance_exits (
    id INTEGER PRIMARY KEY,
    alliance_id INTEGER NOT NULL,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    exited_at TEXT NOT NULL,
    member_snapshot TEXT
);

-- player shop penalty for alliance betrayal (ISO timestamp)
-- stored as key on ng_players if column missing we use parallel table
CREATE TABLE IF NOT EXISTS ng_player_flags (
    player_id INTEGER PRIMARY KEY,
    shop_penalty_until TEXT,
    last_alliance_exit_at TEXT,
    last_exit_alliance_id INTEGER
);
