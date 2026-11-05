-- Temporary cyber effects on countries (defense disruption)
CREATE TABLE IF NOT EXISTS ng_cyber_effects (
    id INTEGER PRIMARY KEY,
    target_country TEXT NOT NULL,
    effect_type TEXT NOT NULL,
    source_country TEXT,
    actor_id INTEGER,
    strength REAL NOT NULL DEFAULT 0.3,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ng_cyber_target_ends ON ng_cyber_effects(target_country, ends_at);
