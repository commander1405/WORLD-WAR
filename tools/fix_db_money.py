#!/usr/bin/env python3
"""Diagnose / repair WORLD WAR SQLite treasury without wiping data.

Usage (Termux, from project root):
  python tools/fix_db_money.py
  python tools/fix_db_money.py --player 123456789
  python tools/fix_db_money.py --player 123456789 --set 120000000
  python tools/fix_db_money.py --player 123456789 --add 20000000
  python tools/fix_db_money.py --heal
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import load_settings  # noqa: E402


def connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"DB not found: {path}")
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def show_player(con: sqlite3.Connection, pid: int) -> None:
    p = con.execute("SELECT * FROM ng_players WHERE player_id=?", (pid,)).fetchone()
    print("=== ng_players ===")
    if not p:
        print(f"  player {pid} NOT FOUND")
    else:
        print(f"  player_id={p['player_id']} country_code={p['country_code']!r} banned={p['is_banned']}")

    owned = con.execute(
        "SELECT country_code, name_fa, treasury, owner_player_id, is_destroyed "
        "FROM ng_countries WHERE owner_player_id=? ORDER BY country_code",
        (pid,),
    ).fetchall()
    print("=== countries owned (owner_player_id) ===")
    if not owned:
        print("  (none)")
    for r in owned:
        print(
            f"  {r['country_code']} {r['name_fa']} treasury={int(r['treasury']):,} "
            f"destroyed={r['is_destroyed']}"
        )

    if p and p["country_code"]:
        c = con.execute(
            "SELECT country_code, name_fa, treasury, owner_player_id FROM ng_countries WHERE country_code=?",
            (p["country_code"],),
        ).fetchone()
        print("=== country from players.country_code cache ===")
        if not c:
            print(f"  MISSING country {p['country_code']!r}")
        else:
            print(
                f"  {c['country_code']} {c['name_fa']} treasury={int(c['treasury']):,} "
                f"owner={c['owner_player_id']}"
            )
            if c["owner_player_id"] != pid:
                print("  *** SPLIT-BRAIN: cache country owner != this player ***")


def heal(con: sqlite3.Connection) -> int:
    n = 0
    rows = con.execute(
        "SELECT owner_player_id, country_code FROM ng_countries "
        "WHERE owner_player_id IS NOT NULL AND country_code<>'UN' AND COALESCE(is_destroyed,0)=0"
    ).fetchall()
    for r in rows:
        pid, code = int(r["owner_player_id"]), r["country_code"]
        p = con.execute("SELECT country_code FROM ng_players WHERE player_id=?", (pid,)).fetchone()
        if not p:
            continue
        if p["country_code"] != code:
            con.execute("UPDATE ng_players SET country_code=? WHERE player_id=?", (code, pid))
            print(f"  heal player {pid}: {p['country_code']!r} -> {code!r}")
            n += 1
    con.commit()
    return n


def set_treasury_for_player(con, pid: int, value=None, add=None) -> None:
    row = con.execute(
        "SELECT country_code, name_fa, treasury FROM ng_countries "
        "WHERE owner_player_id=? AND country_code<>'UN' AND COALESCE(is_destroyed,0)=0 "
        "ORDER BY claimed_at DESC",
        (pid,),
    ).fetchone()
    if not row:
        raise SystemExit(f"No owned country for player {pid}")
    code = row["country_code"]
    before = float(row["treasury"] or 0)
    if value is not None:
        after = float(value)
    elif add is not None:
        after = before + float(add)
    else:
        raise SystemExit("need --set or --add")
    if after < 0:
        raise SystemExit("treasury cannot be negative")
    con.execute("UPDATE ng_countries SET treasury=? WHERE country_code=?", (after, code))
    con.execute("UPDATE ng_players SET country_code=? WHERE player_id=?", (code, pid))
    con.commit()
    check = con.execute("SELECT treasury FROM ng_countries WHERE country_code=?", (code,)).fetchone()
    print(f"OK {code} {row['name_fa']}: {int(before):,} -> {int(check['treasury']):,}")


def list_top(con) -> None:
    print("=== top treasuries (owned countries) ===")
    rows = con.execute(
        "SELECT country_code, name_fa, treasury, owner_player_id FROM ng_countries "
        "WHERE owner_player_id IS NOT NULL AND country_code<>'UN' "
        "ORDER BY treasury DESC LIMIT 15"
    ).fetchall()
    for r in rows:
        print(f"  {r['country_code']:3} pid={r['owner_player_id']} {int(r['treasury']):>15,}  {r['name_fa']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", type=int)
    ap.add_argument("--set", type=float)
    ap.add_argument("--add", type=float)
    ap.add_argument("--heal", action="store_true")
    ap.add_argument("--db", type=str, default="")
    args = ap.parse_args()

    if args.db:
        path = Path(args.db)
    else:
        settings = load_settings()
        path = Path(settings.sqlite_path)

    print(f"DB PATH = {path}")
    print(f"exists  = {path.is_file()} size={path.stat().st_size if path.is_file() else 0}")
    for cand in (
        Path("/storage/emulated/0/worldwarbot/DB/world_war.db"),
        ROOT / "DB" / "world_war.db",
        ROOT / "db" / "world_war.db",
        Path("/storage/emulated/0/worldwarbot/world-war/db/world_war.db"),
    ):
        if cand.is_file():
            print(f"  candidate {cand} size={cand.stat().st_size}")

    con = connect(path)
    if args.heal:
        print(f"healed rows: {heal(con)}")
    if args.player and (args.set is not None or args.add is not None):
        set_treasury_for_player(con, args.player, value=args.set, add=args.add)
    if args.player:
        show_player(con, args.player)
    else:
        list_top(con)
        print("=== possible split-brain ===")
        rows = con.execute(
            """
            SELECT p.player_id, p.country_code AS cache, c.owner_player_id, c.treasury, c.name_fa
            FROM ng_players p
            LEFT JOIN ng_countries c ON c.country_code = p.country_code
            WHERE p.country_code IS NOT NULL AND p.country_code <> 'UN'
              AND (c.owner_player_id IS NULL OR c.owner_player_id <> p.player_id)
            LIMIT 30
            """
        ).fetchall()
        if not rows:
            print("  none detected")
        for r in rows:
            print(dict(r))
    con.close()


if __name__ == "__main__":
    main()
