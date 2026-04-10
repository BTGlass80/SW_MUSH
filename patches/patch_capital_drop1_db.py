#!/usr/bin/env python3
"""
Capital Ship Rules — Drop 1 DB Migration
Adds gunner_stations column to ships table.

The crew JSON already stores {"gunners": [id, ...]}.
This migration changes the crew JSON contract so that gunners are
stored as {"gunner_stations": {"0": char_id, "2": char_id}} mapping
weapon index to character ID.

Backward compat: if "gunners" list exists and "gunner_stations" doesn't,
the list is auto-migrated at read time by _get_crew() — first gunner
maps to weapon 0, second to weapon 1, etc.

No new SQL column needed — everything lives in the existing crew JSON.
This script migrates existing crew JSON in-place.
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


async def migrate():
    import aiosqlite
    db_path = os.path.join(ROOT, "sw_mush.db")
    if not os.path.exists(db_path):
        print("  No database found — migration will apply on first boot.")
        return

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT id, crew FROM ships")
        migrated = 0
        for row in rows:
            crew = json.loads(row["crew"] or "{}")
            if "gunners" in crew and "gunner_stations" not in crew:
                # Migrate: list → dict
                stations = {}
                for i, gid in enumerate(crew["gunners"]):
                    stations[str(i)] = gid
                crew["gunner_stations"] = stations
                del crew["gunners"]
                await db.execute(
                    "UPDATE ships SET crew = ? WHERE id = ?",
                    (json.dumps(crew), row["id"])
                )
                migrated += 1
        await db.commit()
        print(f"  Migrated {migrated} ship(s) from gunners list to gunner_stations dict.")


if __name__ == "__main__":
    asyncio.run(migrate())
