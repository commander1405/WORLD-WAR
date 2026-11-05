-- Owner panel users, activity, finance ledger

CREATE TABLE IF NOT EXISTS ng_finance_ledger (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    from_country TEXT,
    to_country TEXT,
    amount REAL NOT NULL,
    actor_id INTEGER,
    reason TEXT,
    created_at TEXT NOT NULL
);

-- optional columns via separate table for start tracking (portable)
CREATE TABLE IF NOT EXISTS ng_player_activity (
    player_id INTEGER PRIMARY KEY,
    last_start_at TEXT,
    start_count INTEGER NOT NULL DEFAULT 0
);
