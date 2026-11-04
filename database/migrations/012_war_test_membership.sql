-- War cooldowns, test mode snapshots, forced membership

CREATE TABLE IF NOT EXISTS ng_war_state (
    country_code TEXT PRIMARY KEY,
    last_attack_at TEXT,
    attack_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_test_mode (
    player_id INTEGER PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 0,
    snapshot_json TEXT,
    activated_at TEXT
);

CREATE TABLE IF NOT EXISTS ng_forced_chats (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL,
    title TEXT NOT NULL,
    invite_link TEXT,
    kind TEXT NOT NULL DEFAULT 'group',
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ng_membership_cfg (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    force_enabled INTEGER NOT NULL DEFAULT 1
);
