"""Configuration: env vars override optional local config.py values."""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _load_local_config():
    path = ROOT / "config.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ww_local_config", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass(frozen=True)
class Settings:
    bale_token: str
    owner_id: int
    database_mode: str
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


def _get(local, name: str, default: str = "") -> str:
    env = os.getenv(name)
    if env is not None and str(env).strip() != "":
        return str(env).strip()
    if local is not None and hasattr(local, name):
        val = getattr(local, name)
        if val is None:
            return default
        return str(val).strip()
    return default


def load_settings() -> Settings:
    local = _load_local_config()

    mode = _get(local, "DATABASE_MODE", "sqlite").lower()
    if mode not in ("postgres", "sqlite"):
        raise ValueError(f"Invalid DATABASE_MODE={mode!r}. Use 'postgres' or 'sqlite'.")

    db_url = _get(local, "DATABASE_URL", "")
    if mode == "postgres" and not db_url:
        raise ValueError(
            "DATABASE_MODE=postgres requires DATABASE_URL. "
            "Refusing to fall back to SQLite."
        )

    token = _get(local, "BALE_TOKEN", "")
    owner_raw = _get(local, "OWNER_ID", "0")
    try:
        owner_id = int(owner_raw or "0")
    except ValueError as exc:
        raise ValueError("OWNER_ID must be an integer") from exc

    sqlite_path = Path(_get(local, "SQLITE_PATH", "db/world_war.db") or "db/world_war.db")
    if not sqlite_path.is_absolute():
        sqlite_path = ROOT / sqlite_path

    return Settings(
        bale_token=token,
        owner_id=owner_id,
        database_mode=mode,
        database_url=db_url,
        sqlite_path=sqlite_path,
        log_level=(_get(local, "LOG_LEVEL", "INFO") or "INFO").upper(),
        world_start_date=_get(local, "WORLD_START_DATE", "2020-01-01") or "2020-01-01",
        real_days_per_game_year=int(_get(local, "REAL_DAYS_PER_GAME_YEAR", "15") or "15"),
    )
