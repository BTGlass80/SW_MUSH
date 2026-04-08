#!/usr/bin/env python3
"""
bounty_wire_patch.py
--------------------
1. Adds bounty DB methods to db/database.py
2. Wires register_bounty_commands() into server/game_server.py

Run from the SW_MUSH project root:
    python3 bounty_wire_patch.py

Safe to re-run.
"""

import ast
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════
# PART 1 — db/database.py
# ══════════════════════════════════════════════════════════

DB_TARGET = Path("db/database.py")

if not DB_TARGET.exists():
    print(f"ERROR: {DB_TARGET} not found.")
    sys.exit(1)

db_source = DB_TARGET.read_text(encoding="utf-8")

DB_METHODS = '''
    # ── Bounty Board Methods ───────────────────────────────────────────────────

    async def get_posted_bounties(self) -> list[dict]:
        """Return all bounty contracts with status posted or claimed."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bounties WHERE status IN ('posted','claimed') "
                "ORDER BY posted_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def save_bounty(self, contract) -> None:
        """Insert a new bounty contract."""
        import json as _json
        import time as _time
        d = contract.to_dict() if hasattr(contract, "to_dict") else contract
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO bounties
                   (id, status, tier, target_npc_id, claimed_by,
                    posted_at, expires_at, reward, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d["id"], d["status"], d["tier"],
                    d.get("target_npc_id"), d.get("claimed_by"),
                    d.get("posted_at", _time.time()),
                    d.get("expires_at"),
                    d["reward"],
                    _json.dumps(d),
                ),
            )
            await db.commit()

    async def update_bounty(self, contract_id: str, data: dict) -> None:
        """Update a bounty contract's data and status fields."""
        import json as _json
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE bounties SET
                   status = ?, claimed_by = ?, expires_at = ?, data = ?
                   WHERE id = ?""",
                (
                    data.get("status", "posted"),
                    data.get("claimed_by"),
                    data.get("expires_at"),
                    _json.dumps(data),
                    contract_id,
                ),
            )
            await db.commit()

    async def delete_npc(self, npc_id: int) -> None:
        """Delete an NPC record by ID (used for bounty target cleanup)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
            await db.commit()
'''

BOUNTIES_TABLE_DDL = """\
        await db.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS bounties (
                id           TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'posted',
                tier         TEXT NOT NULL,
                target_npc_id INTEGER,
                claimed_by   TEXT,
                posted_at    REAL NOT NULL,
                expires_at   REAL,
                reward       INTEGER NOT NULL,
                data         TEXT NOT NULL DEFAULT '{}'
            )
        \"\"\")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_bounties_status ON bounties(status)"
        )"""

if "get_posted_bounties" in db_source:
    print("✓ Bounty DB methods already present — skipping.")
else:
    # Add table DDL
    if "CREATE TABLE IF NOT EXISTS bounties" not in db_source:
        anchor = "await db.commit()"
        idx = db_source.rfind(anchor)
        if idx != -1:
            db_source = db_source[:idx] + BOUNTIES_TABLE_DDL + "\n        " + db_source[idx:]
            print("  + bounties table DDL inserted")
        else:
            print("  WARNING: Could not insert bounties table DDL automatically.")
            print("  Add it manually to _create_tables() in database.py.")
    else:
        print("  ✓ bounties table DDL already present")

    # Add methods
    db_source = db_source.rstrip() + "\n" + DB_METHODS + "\n"
    print("  + Bounty DB methods appended")

    try:
        ast.parse(db_source)
    except SyntaxError as e:
        print(f"ERROR: db/database.py syntax check failed: {e}")
        sys.exit(1)

    bak = DB_TARGET.with_suffix(".py.bounty_bak")
    bak.write_text(DB_TARGET.read_text(encoding="utf-8"), encoding="utf-8")
    DB_TARGET.write_text(db_source, encoding="utf-8")
    print(f"✓ db/database.py patched (backup → {bak.name})")


# ══════════════════════════════════════════════════════════
# PART 2 — server/game_server.py
# ══════════════════════════════════════════════════════════

GS_TARGET = Path("server/game_server.py")

if not GS_TARGET.exists():
    print(f"ERROR: {GS_TARGET} not found.")
    sys.exit(1)

gs_source = GS_TARGET.read_text(encoding="utf-8")

if "register_bounty_commands" in gs_source:
    print("✓ register_bounty_commands already present — skipping.")
else:
    IMPORT_LINE = "from parser.bounty_commands import register_bounty_commands"
    CALL_LINE   = "        register_bounty_commands(self.registry)"

    # Import anchor
    for anchor in [
        "from parser.mission_commands import register_mission_commands",
        "from parser.crew_commands import register_crew_commands",
        "from parser.force_commands import register_force_commands",
    ]:
        if anchor in gs_source:
            gs_source = gs_source.replace(anchor, anchor + "\n" + IMPORT_LINE, 1)
            print(f"  + Import inserted after: {anchor}")
            break
    else:
        print(f"  WARNING: Could not find import anchor. Add manually:\n    {IMPORT_LINE}")

    # Call anchor
    for anchor in [
        "        register_mission_commands(self.registry)",
        "        register_crew_commands(self.registry)",
        "        register_force_commands(self.registry)",
    ]:
        if anchor in gs_source:
            gs_source = gs_source.replace(anchor, anchor + "\n" + CALL_LINE, 1)
            print(f"  + Call inserted after: {anchor.strip()}")
            break
    else:
        print(f"  WARNING: Could not find call anchor. Add manually:\n    {CALL_LINE.strip()}")

    try:
        ast.parse(gs_source)
    except SyntaxError as e:
        print(f"ERROR: game_server.py syntax check failed: {e}")
        sys.exit(1)

    bak = GS_TARGET.with_suffix(".py.bounty_bak")
    bak.write_text(GS_TARGET.read_text(encoding="utf-8"), encoding="utf-8")
    GS_TARGET.write_text(gs_source, encoding="utf-8")
    print(f"✓ server/game_server.py patched (backup → {bak.name})")

print()
print("Bounty board installation complete.")
print("Commands: bounties, bountyclaim, mybounty, bountytrack, bountycollect")
print("Delete SW_MUSH.db and restart main.py to create the bounties table.")
