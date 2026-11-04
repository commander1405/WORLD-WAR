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

## Configuration priority

1. Environment variables (`BALE_TOKEN`, `OWNER_ID`, `DATABASE_MODE`, `DATABASE_URL`, ...)
2. Local `config.py` in project root (for Pydroid3 / manual runs)

`config.example.py` shows the shape of `config.py`.

Never log the bot token.

## New Generation (نسل جدید)

نقطه ورود: `python main.py`

- بدون کشور هوش مصنوعی؛ فقط بازیکن واقعی
- انتخاب اتمیک کشور + سرمایه اولیه متعادل ۵۰–۱۰۰ میلیون
- فروشگاه، سبد، انبار، بازار، کمک مالی، صلح، جنگ انتزاعی
- درآمد روزانه ساعت‌به‌ساعت بررسی می‌شود (تقویم تهران، یک‌بار در روز)
- پنل مالک: جنگ باز/بسته، هسته‌ای بازی، بیانیه، ریست کامل
- گروه لاگ هدف: `@warworld3` (نیازمند عضویت ربات)

`config.py` محلی (gitignore) یا env: `BALE_TOKEN`, `OWNER_ID`, `DATABASE_MODE`, `DATABASE_URL`
