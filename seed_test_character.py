#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_test_character.py — One-shot helper to create the era's testuser
account + Test Jedi character against an existing DB.

WHY THIS EXISTS:
build_mos_eisley.py creates the test character as part of the full
world build, which only runs when the DB has ≤3 rooms (fresh-DB path).
On an existing DB where the world was already built — e.g. Brian's
Windows dev box after the May 18 active_era CW pivot, where the GCW
build ran and was then migrated — the test_character.yaml was never
loaded because the build path was already complete.

This script invokes the same INSERT OR IGNORE path that
build_mos_eisley.py uses, against the existing DB, without
re-running the full world build.

USAGE (PowerShell, Windows dev box):

  cd C:\\SW_MUSH
  python seed_test_character.py

  # or with a non-default DB path / era:
  python seed_test_character.py --db sw_mush.db --era clone_wars

Idempotent: re-running is safe. The underlying INSERT OR IGNORE
silently skips if the account / character already exists.
"""
import argparse
import asyncio
import json
import os
import sys

# Make project imports resolve when run from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import Database
from engine.test_character_loader import load_era_test_character


async def seed(db_path: str, era: str) -> int:
    """Returns 0 on success, non-zero on failure (CLI exit code)."""
    era_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "worlds", era,
    )
    if not os.path.isdir(era_dir):
        print(f"ERROR: era directory not found: {era_dir}")
        return 2

    # Build a room_name_map by querying the existing DB.
    db = Database(db_path)
    await db.connect()
    await db.initialize()

    try:
        rows = await db.fetchall("SELECT id, name FROM rooms")
        room_name_map = {row["name"]: row["id"] for row in rows}
        if not room_name_map:
            print(f"ERROR: no rooms found in {db_path}. Run the world "
                  f"builder first.")
            return 3

        spec = load_era_test_character(era_dir, room_name_map)
        if spec is None:
            print(f"No test_character spec for era '{era}'. Check "
                  f"era.yaml::content_refs.test_character.")
            return 4

        acct = spec["account"]
        char = spec["character"]

        # Bcrypt the plaintext password
        import bcrypt
        pw_hash = bcrypt.hashpw(
            acct["password"].encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        # Account
        await db.execute(
            """INSERT OR IGNORE INTO accounts
               (username, password_hash, is_admin, is_builder)
               VALUES (?, ?, ?, ?)""",
            (acct["username"], pw_hash,
             1 if acct["is_admin"] else 0,
             1 if acct["is_builder"] else 0),
        )
        await db.commit()
        acct_rows = await db.fetchall(
            "SELECT id FROM accounts WHERE username = ?",
            (acct["username"],),
        )
        if not acct_rows:
            print(f"ERROR: account insert failed silently.")
            return 5
        acct_id = acct_rows[0]["id"]

        # Resolve starting room → DB room_id
        start_room_id = char.get("starting_room_idx")
        if start_room_id is None:
            print(f"ERROR: starting_room {char['starting_room']!r} "
                  f"could not be resolved against current world.")
            return 6

        # Character (INSERT OR IGNORE on unique name)
        cur = await db.execute(
            """INSERT OR IGNORE INTO characters
               (account_id, name, species, template, attributes, skills,
                wound_level, character_points, force_points,
                dark_side_points, room_id, description, credits,
                equipment, inventory, faction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                acct_id,
                char["name"],
                char["species"],
                char["template"],
                json.dumps(char["attributes"]),
                json.dumps(char["skills"]),
                char["wound_level"],
                char["character_points"],
                char["force_points"],
                char["dark_side_points"],
                start_room_id,
                char["description"],
                char["credits"],
                json.dumps(char["equipment"]),
                json.dumps(char["inventory"]),
                char["faction_id"],
            ),
        )
        await db.commit()

        # Confirm
        char_rows = await db.fetchall(
            "SELECT id, name FROM characters WHERE account_id = ?",
            (acct_id,),
        )
        if not char_rows:
            print(f"ERROR: character insert failed silently.")
            return 7

        print()
        print(f"  OK  — account '{acct['username']}' (id={acct_id}) "
              f"and character '{char['name']}' (id={char_rows[0]['id']}) "
              f"present in {db_path}.")
        print(f"       Login: {acct['username']} / {acct['password']}  "
              f"({'Admin+' if acct['is_admin'] else ''}"
              f"{'Builder' if acct['is_builder'] else ''})")
        print(f"       Spawn: {char['starting_room']} (room_id={start_room_id})")
        print(f"       Faction: {char['faction_id']}")
        print()
        return 0
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Seed the era's test character into an existing DB.")
    parser.add_argument("--db", default="sw_mush.db",
                        help="SQLite DB path (default: sw_mush.db)")
    parser.add_argument("--era", default=None,
                        help="Era code (default: read from active_era config)")
    args = parser.parse_args()

    era = args.era
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception:
            era = "clone_wars"

    rc = asyncio.run(seed(args.db, era))
    sys.exit(rc)


if __name__ == "__main__":
    main()
