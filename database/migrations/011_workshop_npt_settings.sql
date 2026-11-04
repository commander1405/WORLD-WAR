-- Workshop, NPT requests, bot settings texts

CREATE TABLE IF NOT EXISTS ng_workshop (
    country_code TEXT PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 1,
    tech_level INTEGER NOT NULL DEFAULT 0,
    upgraded_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_workshop_jobs (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    job_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finishes_at TEXT NOT NULL,
    cost REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS ng_npt_requests (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer_id INTEGER
);

CREATE TABLE IF NOT EXISTS ng_bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_owner_inbox (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id INTEGER,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);
