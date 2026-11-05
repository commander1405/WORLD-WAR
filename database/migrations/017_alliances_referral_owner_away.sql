-- Referral system + owner away mode (world_meta column via settings table)

CREATE TABLE IF NOT EXISTS ng_referrals (
    player_id INTEGER PRIMARY KEY,
    referrer_id INTEGER,
    referral_code TEXT NOT NULL UNIQUE,
    bound_at TEXT,
    invitee_reward REAL NOT NULL DEFAULT 0,
    referrer_reward REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ng_referrals_referrer ON ng_referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_ng_referrals_code ON ng_referrals(referral_code);

-- owner_away stored in bot_settings key owner_away = '1'/'0'
