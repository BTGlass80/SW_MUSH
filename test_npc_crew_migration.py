"""
Tests for NPC crew DB migration (schema v1 → v2).
Verifies both fresh installs and upgrades from existing v1 databases.
"""
import asyncio
import os
import sys
import json
import tempfile

# Add project root to path
sys.path.insert(0, "/mnt/project")

from database import Database, SCHEMA_VERSION


async def test_fresh_install():
    """Fresh DB should have all crew columns on npcs table."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()
        await db.initialize()

        # Verify schema version
        rows = await db._db.execute_fetchall(
            "SELECT MAX(version) as v FROM schema_version"
        )
        assert rows[0]["v"] == 2, f"Expected schema v2, got {rows[0]['v']}"

        # Verify npcs table has new columns
        cols = await db._db.execute_fetchall("PRAGMA table_info(npcs)")
        col_names = {c["name"] for c in cols}
        for expected in ("hired_by", "hire_wage", "assigned_ship",
                         "assigned_station", "hired_at"):
            assert expected in col_names, f"Missing column: {expected}"

        # Create a test NPC and verify crew fields work
        npc_id = await db.create_npc("Test Pilot", room_id=1, species="Human")
        npc = await db.get_npc(npc_id)
        assert npc["hired_by"] is None
        assert npc["hire_wage"] == 0
        assert npc["assigned_ship"] is None
        assert npc["assigned_station"] == ""

        print("  PASS: fresh install — all columns present, defaults correct")
    finally:
        await db.close()
        os.unlink(db_path)


async def test_v1_upgrade():
    """Simulate an existing v1 database and verify migration adds columns."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()

        # Manually create a v1 schema (npcs without crew columns)
        await db._db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO schema_version (version) VALUES (1);

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                email TEXT,
                is_admin INTEGER DEFAULT 0,
                is_builder INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_login TEXT,
                login_failures INTEGER DEFAULT 0,
                locked_until TEXT
            );

            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                species TEXT DEFAULT 'Human',
                template TEXT,
                attributes TEXT DEFAULT '{}',
                skills TEXT DEFAULT '{}',
                wound_level INTEGER DEFAULT 0,
                character_points INTEGER DEFAULT 5,
                force_points INTEGER DEFAULT 1,
                dark_side_points INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 1000,
                resources TEXT DEFAULT '[]',
                room_id INTEGER DEFAULT 1,
                inventory TEXT DEFAULT '[]',
                equipment TEXT DEFAULT '{}',
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id INTEGER,
                name TEXT NOT NULL,
                desc_short TEXT DEFAULT '',
                desc_long TEXT DEFAULT '',
                properties TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_id INTEGER REFERENCES characters(id),
                bridge_room_id INTEGER REFERENCES rooms(id),
                docked_at INTEGER REFERENCES rooms(id),
                hull_damage INTEGER DEFAULT 0,
                shield_damage INTEGER DEFAULT 0,
                systems TEXT DEFAULT '{}',
                crew TEXT DEFAULT '{}',
                cargo TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- V1 npcs table — NO crew columns
            CREATE TABLE IF NOT EXISTS npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                room_id INTEGER REFERENCES rooms(id),
                species TEXT DEFAULT 'Human',
                description TEXT DEFAULT '',
                char_sheet_json TEXT DEFAULT '{}',
                ai_config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS npc_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                npc_id INTEGER NOT NULL REFERENCES npcs(id),
                character_id INTEGER NOT NULL REFERENCES characters(id),
                memory_json TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(npc_id, character_id)
            );

            INSERT OR IGNORE INTO rooms (id, name) VALUES (1, 'Test Room');
        """)
        await db._db.commit()

        # Insert a pre-existing NPC (v1 style)
        await db._db.execute(
            "INSERT INTO npcs (name, room_id) VALUES ('Old NPC', 1)"
        )
        await db._db.commit()

        # Now run initialize — should detect v1 and migrate to v2
        await db.initialize()

        # Verify schema version bumped
        rows = await db._db.execute_fetchall(
            "SELECT MAX(version) as v FROM schema_version"
        )
        assert rows[0]["v"] == 2, f"Expected schema v2 after migration, got {rows[0]['v']}"

        # Verify new columns exist
        cols = await db._db.execute_fetchall("PRAGMA table_info(npcs)")
        col_names = {c["name"] for c in cols}
        for expected in ("hired_by", "hire_wage", "assigned_ship",
                         "assigned_station", "hired_at"):
            assert expected in col_names, f"Missing column after migration: {expected}"

        # Verify pre-existing NPC still works and has default values
        rows = await db._db.execute_fetchall("SELECT * FROM npcs WHERE name = 'Old NPC'")
        old_npc = dict(rows[0])
        assert old_npc["hired_by"] is None
        assert old_npc["hire_wage"] == 0

        print("  PASS: v1→v2 migration — columns added, existing data preserved")
    finally:
        await db.close()
        os.unlink(db_path)


async def test_idempotent_migration():
    """Running initialize twice should not crash (duplicate column safety)."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()
        await db.initialize()
        await db.initialize()  # Second run — should be safe
        print("  PASS: idempotent — double initialize is safe")
    finally:
        await db.close()
        os.unlink(db_path)


async def test_crew_operations():
    """Test the full hire → assign → unassign → dismiss lifecycle."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()
        await db.initialize()

        # Create a character
        acct_id = await db.create_account("testuser", "password123")
        await db._db.execute(
            """INSERT INTO characters (account_id, name, credits, room_id)
               VALUES (?, 'Han Solo', 5000, 1)""",
            (acct_id,),
        )
        await db._db.commit()
        chars = await db.get_characters(acct_id)
        char = chars[0]

        # Create a ship
        ship_id = await db.create_ship("yt1300", "Millennium Falcon",
                                        char["id"], 1, 1)

        # Create an NPC
        npc_id = await db.create_npc("Kael Voss", room_id=1, species="Human")

        # Hire
        await db.hire_npc(npc_id, char["id"], 150)
        npc = await db.get_npc(npc_id)
        assert npc["hired_by"] == char["id"]
        assert npc["hire_wage"] == 150
        assert npc["hired_at"] != ""

        # Get hired NPCs
        hired = await db.get_npcs_hired_by(char["id"])
        assert len(hired) == 1
        assert hired[0]["name"] == "Kael Voss"

        # Assign to station
        await db.assign_npc_to_station(npc_id, ship_id, "pilot")
        npc = await db.get_npc(npc_id)
        assert npc["assigned_ship"] == ship_id
        assert npc["assigned_station"] == "pilot"

        # Query by ship
        crew = await db.get_npc_crew_on_ship(ship_id)
        assert len(crew) == 1

        # Query by station
        pilot = await db.get_npc_at_station(ship_id, "pilot")
        assert pilot is not None
        assert pilot["name"] == "Kael Voss"

        # Empty station returns None
        gunner = await db.get_npc_at_station(ship_id, "gunner")
        assert gunner is None

        # Unassign (stays hired)
        await db.unassign_npc(npc_id)
        npc = await db.get_npc(npc_id)
        assert npc["assigned_ship"] is None
        assert npc["assigned_station"] == ""
        assert npc["hired_by"] == char["id"]  # Still hired

        # Dismiss
        await db.dismiss_npc(npc_id)
        npc = await db.get_npc(npc_id)
        assert npc["hired_by"] is None
        assert npc["hire_wage"] == 0

        print("  PASS: crew lifecycle — hire/assign/unassign/dismiss all work")
    finally:
        await db.close()
        os.unlink(db_path)


async def test_wage_deduction():
    """Test wage deduction with sufficient and insufficient funds."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()
        await db.initialize()

        # Create character with 200 credits
        acct_id = await db.create_account("testuser2", "password123")
        await db._db.execute(
            """INSERT INTO characters (account_id, name, credits, room_id)
               VALUES (?, 'Broke Pilot', 200, 1)""",
            (acct_id,),
        )
        await db._db.commit()
        chars = await db.get_characters(acct_id)
        char = chars[0]

        # Hire two NPCs: one affordable (80), one not after first (150)
        npc1_id = await db.create_npc("Cheap Mech", room_id=1)
        npc2_id = await db.create_npc("Pricey Pilot", room_id=1)
        await db.hire_npc(npc1_id, char["id"], 80)
        await db.hire_npc(npc2_id, char["id"], 150)

        # Deduct wages: 200 credits, 80+150=230 needed
        total, departed = await db.deduct_crew_wages(char["id"])

        # First NPC (80) should be paid; second (150) should leave
        assert total == 80, f"Expected 80 deducted, got {total}"
        assert len(departed) == 1
        assert "Pricey Pilot" in departed

        # Verify credits updated
        char = await db.get_character(char["id"])
        assert char["credits"] == 120  # 200 - 80

        # Verify departed NPC is gone
        npc2 = await db.get_npc(npc2_id)
        assert npc2 is None  # Deleted

        print("  PASS: wage deduction — pays who it can, fires who it can't")
    finally:
        await db.close()
        os.unlink(db_path)


async def test_unhired_npcs_query():
    """get_unhired_npcs_in_room should only return NPCs not hired by anyone."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    try:
        await db.connect()
        await db.initialize()

        acct_id = await db.create_account("testuser3", "password123")
        await db._db.execute(
            """INSERT INTO characters (account_id, name, credits, room_id)
               VALUES (?, 'Recruiter', 9999, 1)""",
            (acct_id,),
        )
        await db._db.commit()
        chars = await db.get_characters(acct_id)
        char = chars[0]

        # Create 3 NPCs in room 1
        npc1 = await db.create_npc("Available One", room_id=1)
        npc2 = await db.create_npc("Available Two", room_id=1)
        npc3 = await db.create_npc("Hired Already", room_id=1)
        await db.hire_npc(npc3, char["id"], 100)

        unhired = await db.get_unhired_npcs_in_room(1)
        names = {n["name"] for n in unhired}
        assert "Available One" in names
        assert "Available Two" in names
        assert "Hired Already" not in names

        print("  PASS: unhired query — filters out hired NPCs correctly")
    finally:
        await db.close()
        os.unlink(db_path)


async def main():
    print(f"Testing NPC Crew Migration (target schema v{SCHEMA_VERSION})")
    print("=" * 55)
    await test_fresh_install()
    await test_v1_upgrade()
    await test_idempotent_migration()
    await test_crew_operations()
    await test_wage_deduction()
    await test_unhired_npcs_query()
    print("=" * 55)
    print("All tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
