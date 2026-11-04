"""Database factory — explicit mode, no silent fallback."""
from __future__ import annotations

from database.interface import Database
from database.postgres import PostgresDatabase
from database.sqlite import SQLiteDatabase
from config.settings import Settings


async def create_database(settings: Settings) -> Database:
    if settings.is_postgres:
        db: Database = PostgresDatabase(settings.database_url)
    elif settings.is_sqlite:
        db = SQLiteDatabase(settings.sqlite_path)
    else:
        raise ValueError(f"Unknown DATABASE_MODE={settings.database_mode}")
    await db.connect()
    await db.migrate()
    return db
