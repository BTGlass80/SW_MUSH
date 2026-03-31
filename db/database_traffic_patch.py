"""
db/database_traffic_patch.py

Schema v3 migration and DB helper methods for NPC Space Traffic.
These methods must be merged into db/database.py.

MERGE INSTRUCTIONS:
  1. In the initialize() method, increment SCHEMA_VERSION to 3 and add
     the migration block shown below.
  2. Copy all methods from the "Traffic Ship DB Methods" section into
     the Database class body (alongside the existing ship/NPC methods).

─────────────────────────────────────────────────────────────────────────────
PART 1 — Schema v3 migration block
─────────────────────────────────────────────────────────────────────────────

Change SCHEMA_VERSION at top of database.py:
    SCHEMA_VERSION = 3

Add to the _run_migrations() method (or equivalent migration block):

    if current_version < 3:
        # v3: bounty field on characters; current_zone on ships via systems_json
        # The current_zone for ships is stored in systems_json (no column needed).
        # The bounty field IS a new column.
        await self._db.execute(
            "ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0"
        )
        await self._db.execute(
            "INSERT INTO schema_version (version) VALUES (3)"
        )
        await self._db.commit()
        log.info("DB migrated to schema v3 (bounty column)")
        current_version = 3

─────────────────────────────────────────────────────────────────────────────
PART 2 — Traffic Ship DB Methods (merge into Database class)
─────────────────────────────────────────────────────────────────────────────
"""

import json
import logging

log = logging.getLogger(__name__)

# ── The methods below belong inside the Database class ────────────────────────

# Paste these into database.py inside the Database class, near the ship methods:

"""
    # ── Traffic Ship Methods ──────────────────────────────────────────────────

    async def create_traffic_ship(self, name: str, template: str) -> int:
        \"\"\"Create a minimal ship record for a traffic NPC. Returns ship_id.\"\"\"
        # Build a minimal systems_json with traffic placeholder
        systems = json.dumps({"traffic": {}})
        cursor = await self._db.execute(
            \"\"\"
            INSERT INTO ships (name, template, hull_damage, shield_damage,
                               systems_json, crew_json, owner_char_id, docked_at)
            VALUES (?, ?, 0, 0, ?, '{}', NULL, NULL)
            \"\"\",
            (name, template, systems),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def create_traffic_npc(self, name: str, ship_id: int, skill: str) -> int:
        \"\"\"Create a minimal NPC record for a traffic ship captain. Returns npc_id.\"\"\"
        # Build a minimal char_sheet_json with the given skill level
        char_sheet = json.dumps({
            "attributes": {"DEX": skill, "MEC": skill, "STR": "2D",
                           "KNO": "2D", "PER": "2D", "TEC": "2D"},
            "skills": {
                "starfighter_piloting": skill,
                "space_transports": skill,
                "starship_gunnery": skill,
            },
        })
        cursor = await self._db.execute(
            \"\"\"
            INSERT INTO npcs (name, species, room_id, char_sheet_json,
                              ai_config_json, hostile, assigned_ship)
            VALUES (?, 'Human', 1, ?, '{}', 0, ?)
            \"\"\",
            (name, char_sheet, ship_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_traffic_ship_state(self, ship_id: int, traffic_data: dict):
        \"\"\"Write the traffic state dict into systems_json['traffic'].\"\"\"
        row = await self._db.execute_fetchone(
            "SELECT systems_json FROM ships WHERE id = ?", (ship_id,)
        )
        if not row:
            return
        systems = json.loads(row["systems_json"] or "{}")
        systems["traffic"] = traffic_data
        await self._db.execute(
            "UPDATE ships SET systems_json = ? WHERE id = ?",
            (json.dumps(systems), ship_id),
        )
        await self._db.commit()

    async def get_all_traffic_ships(self) -> list:
        \"\"\"Return all ship rows that have a 'traffic' key in systems_json.\"\"\"
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE systems_json LIKE '%\"traffic\"%'"
        )
        return rows or []

    async def get_ships_in_space(self) -> list:
        \"\"\"Return all ships not currently docked (docked_at IS NULL).\"\"\"
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE docked_at IS NULL"
        )
        return rows or []

    async def delete_traffic_ship(self, ship_id: int):
        \"\"\"Remove a traffic ship and its NPC crew from the DB.\"\"\"
        # Delete associated NPCs first
        await self._db.execute(
            "DELETE FROM npcs WHERE assigned_ship = ?", (ship_id,)
        )
        await self._db.execute(
            "DELETE FROM ships WHERE id = ?", (ship_id,)
        )
        await self._db.commit()

    async def set_character_bounty(self, char_id: int, amount: int):
        \"\"\"Set the bounty on a character (0 = no bounty).\"\"\"
        await self._db.execute(
            "UPDATE characters SET bounty = ? WHERE id = ?",
            (max(0, amount), char_id),
        )
        await self._db.commit()

    async def get_character_bounty(self, char_id: int) -> int:
        \"\"\"Return the current bounty amount for a character.\"\"\"
        row = await self._db.execute_fetchone(
            "SELECT bounty FROM characters WHERE id = ?", (char_id,)
        )
        return row["bounty"] if row else 0
"""

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Merge checklist
# ─────────────────────────────────────────────────────────────────────────────
MERGE_CHECKLIST = """
db/database.py changes required for Drop 1:

[ ] 1. Set SCHEMA_VERSION = 3 (was 2)
[ ] 2. Add v3 migration block in _run_migrations() (ALTER TABLE characters ADD COLUMN bounty)
[ ] 3. Add create_traffic_ship() method
[ ] 4. Add create_traffic_npc() method
[ ] 5. Add update_traffic_ship_state() method
[ ] 6. Add get_all_traffic_ships() method
[ ] 7. Add get_ships_in_space() method
[ ] 8. Add delete_traffic_ship() method
[ ] 9. Add set_character_bounty() method
[  ] 10. Add get_character_bounty() method
"""
