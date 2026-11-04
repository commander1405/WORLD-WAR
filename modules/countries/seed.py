"""Load historical country baselines and mutable country rows."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from database.interface import Database

log = logging.getLogger(__name__)
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "countries" / "seed_2020.json"


async def ensure_schema_extras(db: Database) -> None:
    """Best-effort additive columns for both backends."""
    # player briefing flag table created by migration 002
    stmts = [
        "ALTER TABLE country_baselines ADD COLUMN leader_name TEXT",
        "ALTER TABLE country_baselines ADD COLUMN leader_title TEXT",
        "ALTER TABLE country_baselines ADD COLUMN government_type TEXT",
        "ALTER TABLE country_baselines ADD COLUMN flag TEXT",
        "ALTER TABLE country_baselines ADD COLUMN languages_json TEXT",
        "ALTER TABLE country_baselines ADD COLUMN resources_json TEXT",
        "ALTER TABLE country_baselines ADD COLUMN sectors_json TEXT",
        "ALTER TABLE country_baselines ADD COLUMN organizations_json TEXT",
        "ALTER TABLE country_baselines ADD COLUMN npt_status TEXT",
        "ALTER TABLE country_baselines ADD COLUMN tensions_2020 TEXT",
        "ALTER TABLE country_baselines ADD COLUMN allies_note TEXT",
        "ALTER TABLE country_baselines ADD COLUMN source_url TEXT",
        "ALTER TABLE country_baselines ADD COLUMN currency_name TEXT",
        "ALTER TABLE countries ADD COLUMN flag TEXT",
    ]
    for s in stmts:
        try:
            await db.execute(s)
        except Exception:
            pass  # column exists


def load_seed_file() -> dict:
    with open(SEED_PATH, encoding="utf-8") as f:
        return json.load(f)


async def seed_countries(db: Database) -> int:
    """Insert baselines + countries if missing. Returns number of country rows ensured."""
    await ensure_schema_extras(db)
    data = load_seed_file()
    count = 0
    for c in data["countries"]:
        code = c["country_code"]
        existing = await db.fetchrow(
            "SELECT country_code FROM country_baselines WHERE country_code = $1",
            (code,),
        )
        payload = (
            code,
            c.get("name_en"),
            c.get("name_fa"),
            c.get("region"),
            c.get("capital"),
            c.get("population"),
            c.get("gdp_usd"),
            c.get("currency_code"),
            c.get("population_ref") or c.get("gdp_ref") or "2019",
            c.get("source_name"),
            c.get("confidence"),
            json.dumps({
                "gdp_ref": c.get("gdp_ref"),
                "population_ref": c.get("population_ref"),
            }, ensure_ascii=False),
        )
        if not existing:
            await db.execute(
                """
                INSERT INTO country_baselines (
                    country_code, name_en, name_fa, region, capital,
                    population_ref, gdp_ref, currency_code, reference_date,
                    source_note, confidence, meta_json
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'2020-01-01',$9,$10,$11)
                """,
                payload,
            )
        # update extended fields (may fail if columns missing on very old DB)
        try:
            await db.execute(
                """
                UPDATE country_baselines SET
                    leader_name=$1, leader_title=$2, government_type=$3, flag=$4,
                    languages_json=$5, resources_json=$6, sectors_json=$7,
                    organizations_json=$8, npt_status=$9, tensions_2020=$10,
                    allies_note=$11, source_url=$12, currency_name=$13,
                    source_note=COALESCE(source_note, $14),
                    confidence=COALESCE(confidence, $15)
                WHERE country_code=$16
                """,
                (
                    c.get("leader_name"),
                    c.get("leader_title"),
                    c.get("government_type"),
                    c.get("flag"),
                    json.dumps(c.get("languages") or [], ensure_ascii=False),
                    json.dumps(c.get("resources") or [], ensure_ascii=False),
                    json.dumps(c.get("sectors") or [], ensure_ascii=False),
                    json.dumps(c.get("organizations") or [], ensure_ascii=False),
                    c.get("npt_status"),
                    c.get("tensions_2020"),
                    c.get("allies_note"),
                    c.get("source_url"),
                    c.get("currency_name"),
                    c.get("source_name"),
                    c.get("confidence"),
                    code,
                ),
            )
        except Exception as exc:
            log.debug("extended baseline update skipped for %s: %s", code, exc)

        crow = await db.fetchrow(
            "SELECT country_code FROM countries WHERE country_code = $1", (code,)
        )
        if not crow:
            await db.execute(
                """
                INSERT INTO countries (
                    country_code, controlled_by, name_en, name_fa, population, treasury, stability, flag
                ) VALUES ($1,'ai',$2,$3,$4,0,50,$5)
                """,
                (
                    code,
                    c.get("name_en"),
                    c.get("name_fa"),
                    c.get("population"),
                    c.get("flag"),
                ),
            )
        count += 1
    log.info("Seeded/ensured %s countries", count)
    return count
