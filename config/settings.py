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


def _android_storage_root() -> Path | None:
    """Detect Android shared storage (Termux / Pydroid)."""
    for c in (Path("/storage/emulated/0"), Path("/sdcard")):
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def _resolve_sqlite_path(explicit: str) -> Path:
    """Prefer /storage/emulated/0/worldwarbot/DB on phone; migrate old paths."""
    import shutil

    if explicit and str(explicit).strip():
        path = Path(str(explicit).strip())
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    android = _android_storage_root()
    if android is not None:
        db_dir = android / "worldwarbot" / "DB"
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            db_dir = ROOT / "DB"
            db_dir.mkdir(parents=True, exist_ok=True)
        path = db_dir / "world_war.db"
        if not path.is_file():
            for oldp in (
                ROOT / "db" / "world_war.db",
                android / "worldwarbot" / "world-war" / "db" / "world_war.db",
                android / "worldwarbot" / "world-war" / "DB" / "world_war.db",
            ):
                try:
                    if oldp.is_file():
                        shutil.copy2(oldp, path)
                        break
                except OSError:
                    continue
        return path

    db_dir = ROOT / "DB"
    db_dir.mkdir(parents=True, exist_ok=True)
    path = db_dir / "world_war.db"
    legacy = ROOT / "db" / "world_war.db"
    if not path.is_file() and legacy.is_file():
        try:
            shutil.copy2(legacy, path)
        except OSError:
            pass
    return path



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

    # SQLite only when mode is sqlite. Never create local DB in postgres mode.
    sqlite_path = _resolve_sqlite_path(_get(local, "SQLITE_PATH", ""))

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
