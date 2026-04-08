#!/usr/bin/env python3
"""
fix_duplicate_exits.py
----------------------
Finds and removes duplicate exits (same from_room + direction) in the DB.
When duplicates exist for the same destination, keeps the first and deletes the rest.
When duplicates go to different destinations, renames them to be distinct.

Also patches db/database.py to add a duplicate guard to create_exit().

Run from the SW_MUSH project root:
    python3 patches/fix_duplicate_exits.py

Uses stdlib sqlite3 — no venv needed.
"""

import ast
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = "sw_mush.db"
DB_MODULE = Path("db/database.py")


# ══════════════════════════════════════════════════════════════
#  PHASE 1: Database cleanup
# ══════════════════════════════════════════════════════════════

def cleanup_db():
    if not os.path.exists(DB_PATH):
        print(f"  DB not found ({DB_PATH}) — skipping cleanup.")
        print(f"  Run after the server has created the DB.")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Find all duplicate (from_room_id, direction) groups
    rows = db.execute("""
        SELECT from_room_id, direction, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
        FROM exits
        GROUP BY from_room_id, direction
        HAVING cnt > 1
        ORDER BY from_room_id
    """).fetchall()

    if not rows:
        print("  No duplicate exits found in database.")
        db.close()
        return

    total_deleted = 0
    total_renamed = 0

    for row in rows:
        room_id = row["from_room_id"]
        direction = row["direction"]
        count = row["cnt"]
        exit_ids = [int(x) for x in row["ids"].split(",")]

        # Fetch destination info for each duplicate
        dupes = []
        for eid in exit_ids:
            erow = db.execute(
                "SELECT e.*, r.name as dest_name FROM exits e "
                "LEFT JOIN rooms r ON e.to_room_id = r.id "
                "WHERE e.id = ?", (eid,)
            ).fetchone()
            if erow:
                dupes.append(dict(erow))

        # Check if all duplicates go to the SAME destination
        destinations = set(d["to_room_id"] for d in dupes)

        if len(destinations) == 1:
            # True duplicates — same direction, same destination. Delete extras.
            keep = exit_ids[0]
            delete_ids = exit_ids[1:]
            src_row = db.execute("SELECT name FROM rooms WHERE id = ?", (room_id,)).fetchone()
            src_name = src_row["name"] if src_row else f"Room #{room_id}"
            print(f"  [{src_name}] '{direction}' x{count}: keeping #{keep}, deleting {delete_ids}")
            for eid in delete_ids:
                db.execute("DELETE FROM exits WHERE id = ?", (eid,))
                total_deleted += 1
        else:
            # Different destinations sharing the same direction label. Rename.
            src_row = db.execute("SELECT name FROM rooms WHERE id = ?", (room_id,)).fetchone()
            src_name = src_row["name"] if src_row else f"Room #{room_id}"
            print(f"  [{src_name}] '{direction}' x{count} to {len(destinations)} different rooms:")
            for d in dupes:
                dest_name = d.get("dest_name", f"Room #{d['to_room_id']}")
                short = dest_name.split(" - ")[0]
                for prefix in ["Mos Eisley ", "The "]:
                    if short.startswith(prefix):
                        short = short[len(prefix):]
                new_dir = f"{direction} to {short}"
                print(f"    #{d['id']}: '{direction}' -> '{new_dir}' (to {dest_name})")
                db.execute(
                    "UPDATE exits SET direction = ? WHERE id = ?",
                    (new_dir, d["id"])
                )
                total_renamed += 1

    db.commit()
    db.close()
    print(f"\n  Done: {total_deleted} duplicates deleted, {total_renamed} exits renamed.")


# ══════════════════════════════════════════════════════════════
#  PHASE 2: Patch create_exit() to guard against future dupes
# ══════════════════════════════════════════════════════════════

def patch_create_exit():
    if not DB_MODULE.exists():
        print(f"  {DB_MODULE} not found — skipping code patch.")
        return

    src = DB_MODULE.read_text(encoding="utf-8")

    if "Duplicate exit skipped" in src:
        print("  ✓ create_exit() already has duplicate guard — skipping.")
        return

    OLD = '''    async def create_exit(self, from_room: int, to_room: int,
                          direction: str, name: str = "") -> int:
        """Create an exit between two rooms. Returns exit ID."""
        cursor = await self._db.execute(
            """INSERT INTO exits (from_room_id, to_room_id, direction, name)
               VALUES (?, ?, ?, ?)""",
            (from_room, to_room, direction, name),
        )
        await self._db.commit()
        return cursor.lastrowid'''

    NEW = '''    async def create_exit(self, from_room: int, to_room: int,
                          direction: str, name: str = "") -> int:
        """Create an exit between two rooms. Returns exit ID.
        Skips silently if an exit in that direction already exists."""
        existing = await self.find_exit_by_dir(from_room, direction)
        if existing:
            log.debug("Duplicate exit skipped: room %d %s already exists (exit #%d)",
                      from_room, direction, existing["id"])
            return existing["id"]
        cursor = await self._db.execute(
            """INSERT INTO exits (from_room_id, to_room_id, direction, name)
               VALUES (?, ?, ?, ?)""",
            (from_room, to_room, direction, name),
        )
        await self._db.commit()
        return cursor.lastrowid'''

    if OLD not in src:
        print("  WARNING: Could not find exact create_exit anchor in database.py.")
        print("  Add a duplicate guard manually.")
        return

    src = src.replace(OLD, NEW, 1)

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  ERROR: Patched database.py failed syntax check: {e}")
        return

    DB_MODULE.write_text(src, encoding="utf-8")
    print("  ✓ database.py patched: create_exit() now skips duplicates.")


# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Phase 1: Database cleanup")
    cleanup_db()
    print()
    print("Phase 2: Code patch (create_exit guard)")
    patch_create_exit()
    print()
    print("Done. Restart the server to pick up changes.")
