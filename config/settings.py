"""Environment-based configuration. No secrets hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    bale_token: str
    database_mode: str  # postgres | sqlite
    database_url: str
    sqlite_path: Path
    log_level: str
    world_start_date: str
    real_days_per_game_year: int

    @property
    def is_postgres(self) -> bool:
        return self.database_mode == "postgres"

    @property
    def is_sqlite(self) -> bool:
        return self.database_mode == "sqlite"


def load_settings() -> Settings:
    mode = (os.getenv("DATABASE_MODE") or "sqlite").strip().lower()
    if mode not in ("postgres", "sqlite"):
        raise ValueError(
            f"Invalid DATABASE_MODE={mode!r}. Use 'postgres' or 'sqlite'."
        )

    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if mode == "postgres" and not db_url:
        raise ValueError(
            "DATABASE_MODE=postgres requires DATABASE_URL. "
            "Refusing to fall back to SQLite."
        )

    sqlite_path = Path(os.getenv("SQLITE_PATH") or "db/world_war.db")
    if not sqlite_path.is_absolute():
        sqlite_path = ROOT / sqlite_path

    return Settings(
        bale_token=(os.getenv("BALE_TOKEN") or "").strip(),
        database_mode=mode,
        database_url=db_url,
        sqlite_path=sqlite_path,
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        world_start_date=os.getenv("WORLD_START_DATE") or "2020-01-01",
        real_days_per_game_year=int(os.getenv("REAL_DAYS_PER_GAME_YEAR") or "15"),
    )
