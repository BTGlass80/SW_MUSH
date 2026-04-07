#!/usr/bin/env python3
"""
db/mission_db_patch.py
----------------------
Adds 7 async mission methods to db/database.py and ensures the
missions table is created in schema setup.

Run from the SW_MUSH project root:
    python3 db/mission_db_patch.py

Safe to re-run: skips if methods are already present.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("db/database.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Already patched? ───────────────────────────────────────────────────────────

if "get_available_missions" in source:
    print("✓ Mission DB methods already present — nothing to do.")
    sys.exit(0)

# ── 1. Ensure missions table is created in _create_tables ─────────────────────
#
# Find the CREATE TABLE npcs block (which exists in v3 schema) and append
# the missions table creation after it, if not already there.

MISSIONS_TABLE_DDL = """\
        await db.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS missions (
                id          TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'available',
                accepted_by TEXT,
                created_at  REAL NOT NULL,
                accepted_at REAL,
                expires_at  REAL,
                mission_type TEXT NOT NULL,
                reward      INTEGER NOT NULL,
                data        TEXT NOT NULL DEFAULT '{}'
            )
        \"\"\")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_missions_accepted_by ON missions(accepted_by)"
        )"""

# Look for existing missions table creation; add if missing.
if "CREATE TABLE IF NOT EXISTS missions" not in source:
    # Anchor: insert after npc_memory table creation block
    ANCHOR_TABLE = 'CREATE TABLE IF NOT EXISTS npc_memory'
    if ANCHOR_TABLE not in source:
        # Fallback: insert before the final `await db.commit()` in _create_tables
        ANCHOR_TABLE = "await db.commit()"
        idx = source.rfind(ANCHOR_TABLE)
        if idx == -1:
            print("WARNING: Could not locate schema anchor for missions table.")
            print("Please add the missions table manually. Continuing with method patch.")
        else:
            source = source[:idx] + MISSIONS_TABLE_DDL + "\n        " + source[idx:]
            print("  + missions table DDL inserted into _create_tables")
    else:
        # Insert after the npc_memory table block ends (next CREATE TABLE or commit)
        idx = source.find(ANCHOR_TABLE)
        end_of_block = source.find("CREATE TABLE IF NOT EXISTS", idx + 10)
        if end_of_block == -1:
            end_of_block = source.rfind("await db.commit()")
        source = source[:end_of_block] + MISSIONS_TABLE_DDL + "\n\n        " + source[end_of_block:]
        print("  + missions table DDL inserted into _create_tables")
else:
    print("  ✓ missions table DDL already present")

# ── 2. Append mission methods before the end of the Database class ─────────────

MISSION_METHODS = '''
    # ── Mission Board Methods ──────────────────────────────────────────────────

    async def get_available_missions(self) -> list[dict]:
        """Return all missions with status=available."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM missions WHERE status = 'available' ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_character_active_mission(self, character_id: str) -> dict | None:
        """Return the accepted mission for a character, or None."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM missions WHERE status = 'accepted' AND accepted_by = ?",
                (character_id,),
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

    async def save_mission(self, mission) -> None:
        """Insert a new mission (Mission dataclass or dict with to_dict())."""
        import json as _json
        import time as _time
        d = mission.to_dict() if hasattr(mission, "to_dict") else mission
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO missions
                   (id, status, accepted_by, created_at, accepted_at,
                    expires_at, mission_type, reward, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d["id"],
                    d["status"],
                    d.get("accepted_by"),
                    d.get("created_at", _time.time()),
                    d.get("accepted_at"),
                    d.get("expires_at"),
                    d["mission_type"],
                    d["reward"],
                    _json.dumps(d),
                ),
            )
            await db.commit()

    async def accept_mission(
        self,
        mission_id: str,
        character_id: str,
        expires_at: float,
        data: dict,
    ) -> None:
        """Mark a mission as accepted by a character."""
        import json as _json
        import time as _time
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE missions SET
                   status = 'accepted',
                   accepted_by = ?,
                   accepted_at = ?,
                   expires_at = ?,
                   data = ?
                   WHERE id = ?""",
                (character_id, _time.time(), expires_at, _json.dumps(data), mission_id),
            )
            await db.commit()

    async def complete_mission(self, mission_id: str, data: dict) -> None:
        """Mark a mission as complete."""
        import json as _json
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE missions SET status = 'complete', data = ? WHERE id = ?",
                (_json.dumps(data), mission_id),
            )
            await db.commit()

    async def abandon_mission(self, mission_id: str, data: dict) -> None:
        """Return a mission to available status."""
        import json as _json
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE missions SET
                   status = 'available',
                   accepted_by = NULL,
                   accepted_at = NULL,
                   data = ?
                   WHERE id = ?""",
                (_json.dumps(data), mission_id),
            )
            await db.commit()

    async def expire_mission(self, mission_id: str) -> None:
        """Mark a mission as expired."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE missions SET status = 'expired' WHERE id = ?",
                (mission_id,),
            )
            await db.commit()
'''

# Find the last method in the class to anchor the insertion.
# Strategy: find the last "    async def " before end of file, insert after its block.
# Simpler: find the closing of the class by locating "# -- end of Database --" or
# just appending before the final newlines, since Python classes end at EOF.

# Find a reliable tail anchor: the last "    async def" definition.
TAIL_ANCHOR = "    async def expire_mission"
if TAIL_ANCHOR in source:
    print("  ✓ mission methods already present (expire_mission found)")
else:
    # Append before EOF (works for module-level Database class)
    source = source.rstrip() + "\n" + MISSION_METHODS + "\n"
    print("  + Mission DB methods appended to database.py")

# ── 3. Syntax validation ───────────────────────────────────────────────────────

try:
    ast.parse(source)
except SyntaxError as e:
    print(f"\nERROR: Patched source failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

# ── 4. Write ───────────────────────────────────────────────────────────────────

backup = TARGET.with_suffix(".py.missions_bak")
backup.write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
print(f"  Backup written → {backup}")

TARGET.write_text(source, encoding="utf-8")
print(f"✓ Patched {TARGET}")
print()
print("DB methods added:")
print("  get_available_missions()")
print("  get_character_active_mission(character_id)")
print("  save_mission(mission)")
print("  accept_mission(mission_id, character_id, expires_at, data)")
print("  complete_mission(mission_id, data)")
print("  abandon_mission(mission_id, data)")
print("  expire_mission(mission_id)")
print()
print("missions table DDL added to _create_tables().")
print("Delete the DB and restart main.py to create the missions table.")
