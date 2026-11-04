-- Country management: cabinet, policies, budget, satisfaction

CREATE TABLE IF NOT EXISTS cabinet_members (
    country_code TEXT NOT NULL,
    portfolio TEXT NOT NULL,
    minister_name TEXT NOT NULL,
    competence REAL NOT NULL DEFAULT 50,
    appointed_at TEXT,
    PRIMARY KEY (country_code, portfolio)
);

CREATE TABLE IF NOT EXISTS country_policies (
    country_code TEXT NOT NULL,
    policy_key TEXT NOT NULL,
    policy_value REAL NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (country_code, policy_key)
);

CREATE TABLE IF NOT EXISTS country_economy (
    country_code TEXT PRIMARY KEY,
    treasury REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.15,
    public_spending_rate REAL NOT NULL DEFAULT 0.12,
    gdp REAL NOT NULL DEFAULT 0,
    public_satisfaction REAL NOT NULL DEFAULT 50,
    stability REAL NOT NULL DEFAULT 50,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS production_sectors (
    country_code TEXT NOT NULL,
    sector_code TEXT NOT NULL,
    output_level REAL NOT NULL DEFAULT 50,
    investment REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (country_code, sector_code)
);
