-- Phase 2: briefing flag and richer baseline columns (safe additive)

-- SQLite / Postgres portable ALTER is limited; use new columns via re-seed table pattern where needed.
-- Add columns if missing is handled in application seed for portability.

CREATE TABLE IF NOT EXISTS player_flags (
    player_id INTEGER PRIMARY KEY,
    initial_briefing_sent INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);
