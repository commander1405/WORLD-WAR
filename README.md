# WORLD WAR

Multiplayer geopolitical & country-management simulation bot for **Bale**.

- Shared world on **Railway + PostgreSQL**
- Local world on **Android / Pydroid3 + SQLite**
- Explicit `DATABASE_MODE` — **no silent fallback**

## Game clock

- Epoch: **2020-01-01**
- **15 real days = 1 in-game year**
- Server-authoritative (`world_state` table)

## Setup

### Pydroid3 / local SQLite

```bash
pip install -r requirements.txt
cp .env.example .env
# BALE_TOKEN=...
# DATABASE_MODE=sqlite
python main.py
```

Creates `db/world_war.db` automatically.

### Railway + PostgreSQL

1. Create Railway project + PostgreSQL plugin.
2. Set env:
   - `DATABASE_MODE=postgres`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `BALE_TOKEN=...`
3. Deploy from this repo (`Procfile` worker).

If PostgreSQL is unreachable, the process **exits with error** (does not switch to SQLite).

## Tests

```bash
pip install pytest aiosqlite
pytest -q
```

## Structure

See `bot/`, `engine/`, `database/`, `modules/` for modular layout.

## License

Private / project license TBD by owner.
