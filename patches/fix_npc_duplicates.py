# -*- coding: utf-8 -*-
"""
fix_npc_duplicates.py — Remove duplicate NPCs from the database.

Keeps the OLDEST copy (lowest id) of each name+room_id pair and
deletes the rest. Also adds a UNIQUE constraint to prevent future
duplicates (if SQLite allows it on the existing table).

Usage:
    python patches/fix_npc_duplicates.py

Safe to run multiple times — no-ops if no duplicates exist.
"""
import asyncio
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT)


async def main():
    import aiosqlite

    db_path = os.path.join(ROOT, "sw_mush.db")
    if not os.path.isfile(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        return

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Find duplicates
        rows = await db.execute_fetchall(
            "SELECT name, room_id, COUNT(*) as cnt, MIN(id) as keep_id "
            "FROM npcs GROUP BY name, room_id HAVING cnt > 1"
        )
        dupes = [dict(r) for r in rows]

        if not dupes:
            print("[OK] No duplicate NPCs found. Database is clean.")
            return

        print(f"Found {len(dupes)} duplicate NPC group(s):\n")

        total_removed = 0
        for d in dupes:
            name = d["name"]
            room = d["room_id"]
            keep = d["keep_id"]
            cnt = d["cnt"]

            # Get all IDs for this name+room
            id_rows = await db.execute_fetchall(
                "SELECT id FROM npcs WHERE name = ? AND room_id = ? ORDER BY id",
                (name, room),
            )
            all_ids = [r["id"] for r in id_rows]
            remove_ids = [i for i in all_ids if i != keep]

            print(f"  {name} in room {room}: {cnt} copies, keeping #{keep}, removing {remove_ids}")

            for rid in remove_ids:
                await db.execute("DELETE FROM npcs WHERE id = ?", (rid,))
                total_removed += 1

        await db.commit()
        print(f"\n[OK] Removed {total_removed} duplicate NPC(s).")

        # Verify
        remaining = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM npcs")
        print(f"     {remaining[0]['cnt']} NPCs remain in database.")


if __name__ == "__main__":
    asyncio.run(main())
