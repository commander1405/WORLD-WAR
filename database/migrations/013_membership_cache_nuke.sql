CREATE TABLE IF NOT EXISTS ng_member_cache (
    player_id INTEGER NOT NULL,
    chat_id TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    PRIMARY KEY (player_id, chat_id)
);
