
CREATE TABLE IF NOT EXISTS ng_finance_ops (
    op_key TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    delta REAL NOT NULL,
    actor_id INTEGER,
    reason TEXT,
    created_at TEXT
);
