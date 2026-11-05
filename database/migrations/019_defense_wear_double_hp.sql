-- Defense durability + double HP flag

CREATE TABLE IF NOT EXISTS ng_defense_hits (
    country_code TEXT PRIMARY KEY,
    hits INTEGER NOT NULL DEFAULT 0,
    break_at INTEGER NOT NULL DEFAULT 3
);

-- double_hp: 0 or 1 — when 1, max_hp/hp already scaled x2
