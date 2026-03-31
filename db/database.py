# -*- coding: utf-8 -*-
"""
Database layer - SQLite with WAL mode, async via aiosqlite.
Handles schema creation, migrations, and core CRUD operations.
"""
import aiosqlite
import bcrypt
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# -- Schema version --
SCHEMA_VERSION = 3

SCHEMA_SQL = """
-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT DEFAULT (datetime('now'))
);

-- Player accounts (login credentials, not characters)
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    email           TEXT,
    is_admin        INTEGER DEFAULT 0,
    is_builder      INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    last_login      TEXT,
    login_failures  INTEGER DEFAULT 0,
    locked_until    TEXT
);

-- Characters (one account can own multiple characters)
CREATE TABLE IF NOT EXISTS characters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    name            TEXT UNIQUE NOT NULL COLLATE NOCASE,
    species         TEXT DEFAULT 'Human',
    template        TEXT,
    attributes      TEXT DEFAULT '{}',   -- JSON: {dex: "3D+1", ...}
    skills          TEXT DEFAULT '{}',   -- JSON: {blaster: "5D+2", ...}
    wound_level     INTEGER DEFAULT 0,
    character_points INTEGER DEFAULT 5,
    force_points    INTEGER DEFAULT 1,
    dark_side_points INTEGER DEFAULT 0,
    credits         INTEGER DEFAULT 1000,
    resources       TEXT DEFAULT '[]',    -- JSON: [{type, qty, quality}, ...]
    room_id         INTEGER DEFAULT 1,
    inventory       TEXT DEFAULT '[]',
    equipment       TEXT DEFAULT '{}',
    description     TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    is_active       INTEGER DEFAULT 1
);

-- Rooms
CREATE TABLE IF NOT EXISTS rooms (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id         INTEGER,
    name            TEXT NOT NULL,
    desc_short      TEXT DEFAULT '',
    desc_long       TEXT DEFAULT '',
    properties      TEXT DEFAULT '{}',   -- JSON: environment, gravity, etc.
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Exits between rooms
CREATE TABLE IF NOT EXISTS exits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_room_id    INTEGER NOT NULL REFERENCES rooms(id),
    to_room_id      INTEGER NOT NULL REFERENCES rooms(id),
    direction       TEXT NOT NULL,        -- north, south, east, west, up, down, or custom
    name            TEXT DEFAULT '',      -- display name if custom
    lock_data       TEXT DEFAULT '{}',
    is_hidden       INTEGER DEFAULT 0
);

-- Zones (hierarchical)
CREATE TABLE IF NOT EXISTS zones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id       INTEGER REFERENCES zones(id),
    name            TEXT NOT NULL,
    coords          TEXT DEFAULT '{}',    -- JSON: galactic coordinates
    properties      TEXT DEFAULT '{}'
);

-- Objects (items, weapons, armor, etc.)
CREATE TABLE IF NOT EXISTS objects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL DEFAULT 'item',
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    room_id         INTEGER REFERENCES rooms(id),
    owner_id        INTEGER REFERENCES characters(id),
    data            TEXT DEFAULT '{}',    -- JSON: type-specific data
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Missions (auto-generated jobs)
CREATE TABLE IF NOT EXISTS missions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_type    TEXT NOT NULL,         -- delivery, combat, bounty, smuggling, medical, technical, social, salvage, slicing
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    reward          INTEGER DEFAULT 500,
    difficulty      TEXT DEFAULT 'easy',   -- easy, moderate, difficult, heroic
    target_room_id  INTEGER REFERENCES rooms(id),
    source_room_id  INTEGER REFERENCES rooms(id),
    target_npc_name TEXT DEFAULT '',       -- For bounty: NPC to defeat
    cargo_type      TEXT DEFAULT '',       -- For smuggling: cargo description
    skill_required  TEXT DEFAULT '',       -- Primary skill needed
    accepted_by     INTEGER REFERENCES characters(id),
    status          TEXT DEFAULT 'available',  -- available, accepted, completed, expired
    expires_at      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Ships
CREATE TABLE IF NOT EXISTS ships (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template        TEXT NOT NULL,
    name            TEXT NOT NULL,
    owner_id        INTEGER REFERENCES characters(id),
    bridge_room_id  INTEGER REFERENCES rooms(id),   -- Interior bridge room
    docked_at       INTEGER REFERENCES rooms(id),   -- Docking bay room (NULL = in space)
    hull_damage     INTEGER DEFAULT 0,
    shield_damage   INTEGER DEFAULT 0,
    systems         TEXT DEFAULT '{}',    -- JSON: {"engines": true, "weapons": true, ...}
    crew            TEXT DEFAULT '{}',    -- JSON: {"pilot": char_id, "gunners": [id, ...]}
    cargo           TEXT DEFAULT '[]',
    created_at      TEXT DEFAULT (datetime('now'))
);

-- NPCs
CREATE TABLE IF NOT EXISTS npcs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    room_id         INTEGER REFERENCES rooms(id),
    species         TEXT DEFAULT 'Human',
    description     TEXT DEFAULT '',
    char_sheet_json TEXT DEFAULT '{}',
    ai_config_json  TEXT DEFAULT '{}',
    hired_by        INTEGER REFERENCES characters(id),  -- NULL = not hired
    hire_wage       INTEGER DEFAULT 0,                   -- credits/day
    assigned_ship   INTEGER REFERENCES ships(id),        -- NULL = unassigned
    assigned_station TEXT DEFAULT '',                     -- pilot/gunner/engineer/etc.
    hired_at        TEXT DEFAULT '',                      -- datetime when hired
    created_at      TEXT DEFAULT (datetime('now'))
);

-- NPC Memory of player interactions
CREATE TABLE IF NOT EXISTS npc_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id          INTEGER NOT NULL REFERENCES npcs(id),
    character_id    INTEGER NOT NULL REFERENCES characters(id),
    memory_json     TEXT DEFAULT '{}',
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(npc_id, character_id)
);

-- Seed data: starting room
INSERT OR IGNORE INTO rooms (id, name, desc_short, desc_long) VALUES (
    1,
    'Landing Pad - Mos Eisley Spaceport',
    'A dusty landing pad on the outskirts of Mos Eisley.',
    'Heat shimmers rise from the cracked duracrete of this well-worn landing pad. '
    || 'The twin suns of Tatooine beat down mercilessly, casting harsh shadows from '
    || 'the scattered freighters and transports that dot the sprawling spaceport. '
    || 'To the north, the low mud-brick buildings of Mos Eisley beckon with the '
    || 'promise of shade and cantina drinks. The hum of repulsorlifts and the chatter '
    || 'of alien languages fill the dry air.'
);

INSERT OR IGNORE INTO rooms (id, name, desc_short, desc_long) VALUES (
    2,
    'Mos Eisley Street',
    'A narrow street winding through Mos Eisley.',
    'Sand-scoured walls rise on either side of this narrow street, dotted with '
    || 'doorways leading to shops, residences, and establishments of questionable '
    || 'repute. Jawas hawk salvaged droid parts from a rusted speeder, while a '
    || 'pair of Stormtroopers patrol with practiced disinterest. The acrid smell '
    || 'of exhaust mingles with the spicy aroma of street food.'
);

INSERT OR IGNORE INTO rooms (id, name, desc_short, desc_long) VALUES (
    3,
    'Chalmun''s Cantina',
    'The infamous Mos Eisley Cantina.',
    'The cool darkness of the cantina is a welcome relief from the searing heat '
    || 'outside. A curved bar dominates the center of the room, tended by a surly '
    || 'Wookiee barkeep. Figrin D''an and the Modal Nodes play a jaunty tune from '
    || 'a small alcove. Booths line the walls, occupied by a menagerie of species '
    || 'conducting business both legitimate and otherwise. A sign near the door '
    || 'reads: NO DROIDS.'
);

-- Seed exits
INSERT OR IGNORE INTO exits (id, from_room_id, to_room_id, direction) VALUES (1, 1, 2, 'north');
INSERT OR IGNORE INTO exits (id, from_room_id, to_room_id, direction) VALUES (2, 2, 1, 'south');
INSERT OR IGNORE INTO exits (id, from_room_id, to_room_id, direction) VALUES (3, 2, 3, 'east');
INSERT OR IGNORE INTO exits (id, from_room_id, to_room_id, direction) VALUES (4, 3, 2, 'west');
"""

# -- Migrations --
# Each key is the target version; value is a list of SQL statements to apply.
# Migrations run in order for any version > current DB version.
MIGRATIONS = {
    2: [
        "ALTER TABLE npcs ADD COLUMN hired_by INTEGER REFERENCES characters(id)",
        "ALTER TABLE npcs ADD COLUMN hire_wage INTEGER DEFAULT 0",
        "ALTER TABLE npcs ADD COLUMN assigned_ship INTEGER REFERENCES ships(id)",
        "ALTER TABLE npcs ADD COLUMN assigned_station TEXT DEFAULT ''",
        "ALTER TABLE npcs ADD COLUMN hired_at TEXT DEFAULT ''",
    ],
    3: [
        "ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0",
    ],
}


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Open the database and enable WAL mode."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        log.info("Database connected: %s (WAL mode)", self.db_path)

    async def initialize(self):
        """Create tables if they don't exist, apply migrations, and seed data."""
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

        # Determine current DB schema version
        row = await self._db.execute_fetchall(
            "SELECT MAX(version) as v FROM schema_version"
        )
        current_version = row[0]["v"] if row and row[0]["v"] else 0

        # Apply any pending migrations
        if current_version < SCHEMA_VERSION:
            await self._run_migrations(current_version)

        # Record current schema version
        row = await self._db.execute_fetchall(
            "SELECT version FROM schema_version WHERE version = ?",
            (SCHEMA_VERSION,),
        )
        if not row:
            await self._db.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            await self._db.commit()

        log.info("Schema initialized (version %d)", SCHEMA_VERSION)

    async def _run_migrations(self, from_version: int):
        """Apply sequential migrations from from_version+1 to SCHEMA_VERSION."""
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            stmts = MIGRATIONS.get(target, [])
            if not stmts:
                continue
            log.info("Applying migration v%d -> v%d (%d statements)",
                     target - 1, target, len(stmts))
            for sql in stmts:
                try:
                    await self._db.execute(sql)
                except Exception as e:
                    # Column may already exist (re-run safety)
                    if "duplicate column" in str(e).lower():
                        log.debug("Migration skip (already applied): %s", sql[:60])
                    else:
                        raise
            await self._db.commit()
            log.info("Migration to v%d complete.", target)

    async def close(self):
        """Gracefully close the database."""
        if self._db:
            await self._db.close()
            log.info("Database closed.")

    # -- Account Operations --

    async def create_account(self, username: str, password: str) -> Optional[int]:
        """Create a new account. Returns account ID or None if username taken.
        The first account created is automatically admin+builder."""
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        try:
            # Check if this is the first account
            rows = await self._db.execute_fetchall(
                "SELECT COUNT(*) as cnt FROM accounts"
            )
            is_first = rows[0]["cnt"] == 0

            cursor = await self._db.execute(
                """INSERT INTO accounts
                   (username, password_hash, is_admin, is_builder)
                   VALUES (?, ?, ?, ?)""",
                (username, password_hash, 1 if is_first else 0, 1 if is_first else 0),
            )
            await self._db.commit()
            if is_first:
                log.info("Account created: %s (id=%d) [ADMIN+BUILDER - first account]",
                         username, cursor.lastrowid)
            else:
                log.info("Account created: %s (id=%d)", username, cursor.lastrowid)
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None

    async def authenticate(self, username: str, password: str) -> Optional[dict]:
        """
        Verify credentials. Returns account row dict on success, None on failure.
        Handles login lockout tracking.
        """
        row = await self._db.execute_fetchall(
            "SELECT * FROM accounts WHERE username = ?", (username,)
        )
        if not row:
            return None

        account = dict(row[0])

        # Check lockout
        if account.get("locked_until"):
            # SQLite stores datetimes as naive UTC strings; parse and compare
            # using timezone-aware datetimes (utcnow() is deprecated in 3.12+).
            locked = datetime.fromisoformat(account["locked_until"]).replace(
                tzinfo=timezone.utc
            )
            if datetime.now(timezone.utc) < locked:
                return None  # Still locked out

        # Verify password
        if bcrypt.checkpw(
            password.encode("utf-8"), account["password_hash"].encode("utf-8")
        ):
            # Reset failures and update last_login
            await self._db.execute(
                "UPDATE accounts SET login_failures = 0, last_login = datetime('now') WHERE id = ?",
                (account["id"],),
            )
            await self._db.commit()
            return account
        else:
            # Increment failures
            failures = account.get("login_failures", 0) + 1
            lock_clause = ""
            params = [failures, account["id"]]
            if failures >= 5:
                lock_clause = ", locked_until = datetime('now', '+5 minutes')"
            await self._db.execute(
                f"UPDATE accounts SET login_failures = ?{lock_clause} WHERE id = ?",
                params,
            )
            await self._db.commit()
            return None

    async def get_account(self, account_id: int) -> Optional[dict]:
        """Fetch an account by ID."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_characters(self, account_id: int) -> list:
        """Get all characters for an account."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE account_id = ? AND is_active = 1",
            (account_id,),
        )
        return [dict(r) for r in rows]

    async def get_character(self, character_id: int) -> Optional[dict]:
        """Get a single character by ID."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        )
        return dict(rows[0]) if rows else None

    async def create_character(self, account_id: int, fields: dict) -> int:
        """
        Insert a new character row. Returns the new character's ID.

        `fields` must be a dict from Character.to_db_dict(). Raises
        aiosqlite.IntegrityError on duplicate name (UNIQUE constraint).
        """
        cursor = await self._db.execute(
            """INSERT INTO characters
               (account_id, name, species, template, attributes, skills,
                wound_level, character_points, force_points,
                dark_side_points, room_id, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id,
                fields["name"],
                fields.get("species", "Human"),
                fields.get("template", ""),
                fields.get("attributes", "{}"),
                fields.get("skills", "{}"),
                fields.get("wound_level", 0),
                fields.get("character_points", 5),
                fields.get("force_points", 1),
                fields.get("dark_side_points", 0),
                fields.get("room_id", 1),
                fields.get("description", ""),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    # Allowlisted column names for save_character.
    # Only these fields may be updated via save_character(**kwargs) to prevent
    # f-string SQL injection if a caller ever passes attacker-controlled keys.
    _CHARACTER_WRITABLE_COLUMNS = frozenset({
        "name", "species", "template", "attributes", "skills",
        "wound_level", "character_points", "force_points", "dark_side_points",
        "credits", "resources", "room_id", "inventory", "equipment",
        "description", "is_active",
    })

    async def save_character(self, char_id: int, **fields):
        """Update arbitrary character fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._CHARACTER_WRITABLE_COLUMNS
        if bad:
            raise ValueError(f"save_character: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [char_id]
        await self._db.execute(
            f"UPDATE characters SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    # -- Room Operations --

    async def get_room(self, room_id: int) -> Optional[dict]:
        """Fetch a room by ID."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_exits(self, room_id: int) -> list:
        """Get all exits from a room."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM exits WHERE from_room_id = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    async def get_characters_in_room(self, room_id: int) -> list:
        """Get all active characters in a room."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE room_id = ? AND is_active = 1",
            (room_id,),
        )
        return [dict(r) for r in rows]

    # -- Room Building Operations --

    async def create_room(self, name: str, desc_short: str = "",
                          desc_long: str = "", zone_id: int = None,
                          properties: str = "{}") -> int:
        """Create a new room. Returns the room ID."""
        cursor = await self._db.execute(
            """INSERT INTO rooms (name, desc_short, desc_long, zone_id, properties)
               VALUES (?, ?, ?, ?, ?)""",
            (name, desc_short, desc_long, zone_id, properties),
        )
        await self._db.commit()
        return cursor.lastrowid

    _ROOM_WRITABLE_COLUMNS = frozenset({
        "name", "desc_short", "desc_long", "zone_id", "properties",
    })

    async def update_room(self, room_id: int, **fields):
        """Update room fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._ROOM_WRITABLE_COLUMNS
        if bad:
            raise ValueError(f"update_room: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [room_id]
        await self._db.execute(
            f"UPDATE rooms SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    async def delete_room(self, room_id: int) -> bool:
        """Delete a room and all its exits. Returns True if deleted."""
        room = await self.get_room(room_id)
        if not room:
            return False
        # Delete exits from and to this room
        await self._db.execute(
            "DELETE FROM exits WHERE from_room_id = ? OR to_room_id = ?",
            (room_id, room_id),
        )
        await self._db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        await self._db.commit()
        return True

    async def list_rooms(self, limit: int = 50, offset: int = 0) -> list:
        """List all rooms with optional pagination."""
        rows = await self._db.execute_fetchall(
            "SELECT id, name, zone_id FROM rooms ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in rows]

    async def find_rooms(self, search: str) -> list:
        """Search rooms by name (partial match)."""
        rows = await self._db.execute_fetchall(
            "SELECT id, name, zone_id FROM rooms WHERE name LIKE ?",
            (f"%{search}%",),
        )
        return [dict(r) for r in rows]

    async def count_rooms(self) -> int:
        """Get total room count."""
        rows = await self._db.execute_fetchall("SELECT COUNT(*) as cnt FROM rooms")
        return rows[0]["cnt"]

    # -- Zone Operations --

    async def get_zone(self, zone_id: int) -> Optional[dict]:
        """Fetch a zone by ID."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        return dict(rows[0]) if rows else None

    async def create_zone(self, name: str, parent_id: int = None,
                          properties: str = "{}") -> int:
        """Create a zone. Returns zone ID."""
        cursor = await self._db.execute(
            """INSERT INTO zones (name, parent_id, properties)
               VALUES (?, ?, ?)""",
            (name, parent_id, properties),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_room_property(self, room_id: int, prop_name: str, default=None):
        """
        Resolve a room property with zone inheritance (LambdaMOO pattern).

        Resolution order:
          1. room.properties[prop_name]  (if set and non-null)
          2. zone.properties[prop_name]  (room's zone)
          3. parent_zone.properties[prop_name]  (walk up zone hierarchy)
          4. default

        Max depth of 10 to prevent infinite loops.
        """
        import json as _json

        # Check room properties first
        room = await self.get_room(room_id)
        if not room:
            return default

        props = room.get("properties", "{}")
        if isinstance(props, str):
            try:
                props = _json.loads(props)
            except (ValueError, TypeError):
                props = {}
        if isinstance(props, dict) and prop_name in props:
            return props[prop_name]

        # Walk zone hierarchy
        zone_id = room.get("zone_id")
        depth = 0
        while zone_id and depth < 10:
            zone = await self.get_zone(zone_id)
            if not zone:
                break
            zprops = zone.get("properties", "{}")
            if isinstance(zprops, str):
                try:
                    zprops = _json.loads(zprops)
                except (ValueError, TypeError):
                    zprops = {}
            if isinstance(zprops, dict) and prop_name in zprops:
                return zprops[prop_name]
            zone_id = zone.get("parent_id")
            depth += 1

        return default

    async def get_all_room_properties(self, room_id: int) -> dict:
        """
        Get all resolved properties for a room (zone defaults merged
        with room overrides). Room values take precedence.
        """
        import json as _json
        merged = {}

        # Collect zone chain properties (deepest ancestor first)
        room = await self.get_room(room_id)
        if not room:
            return merged

        zone_chain = []
        zone_id = room.get("zone_id")
        depth = 0
        while zone_id and depth < 10:
            zone = await self.get_zone(zone_id)
            if not zone:
                break
            zone_chain.append(zone)
            zone_id = zone.get("parent_id")
            depth += 1

        # Apply from deepest ancestor to nearest parent
        for zone in reversed(zone_chain):
            zprops = zone.get("properties", "{}")
            if isinstance(zprops, str):
                try:
                    zprops = _json.loads(zprops)
                except (ValueError, TypeError):
                    zprops = {}
            if isinstance(zprops, dict):
                merged.update(zprops)

        # Room properties override everything
        rprops = room.get("properties", "{}")
        if isinstance(rprops, str):
            try:
                rprops = _json.loads(rprops)
            except (ValueError, TypeError):
                rprops = {}
        if isinstance(rprops, dict):
            merged.update(rprops)

        return merged

    # -- Exit Building Operations --

    async def create_exit(self, from_room: int, to_room: int,
                          direction: str, name: str = "") -> int:
        """Create an exit between two rooms. Returns exit ID."""
        cursor = await self._db.execute(
            """INSERT INTO exits (from_room_id, to_room_id, direction, name)
               VALUES (?, ?, ?, ?)""",
            (from_room, to_room, direction, name),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def delete_exit(self, exit_id: int) -> bool:
        """Delete an exit by ID."""
        cursor = await self._db.execute(
            "DELETE FROM exits WHERE id = ?", (exit_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_exit_by_dir(self, from_room: int, direction: str) -> bool:
        """Delete an exit by room and direction."""
        cursor = await self._db.execute(
            "DELETE FROM exits WHERE from_room_id = ? AND direction = ?",
            (from_room, direction),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    _EXIT_WRITABLE_COLUMNS = frozenset({
        "from_room_id", "to_room_id", "direction", "name", "lock_data", "is_hidden",
    })

    async def update_exit(self, exit_id: int, **fields):
        """Update exit fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._EXIT_WRITABLE_COLUMNS
        if bad:
            raise ValueError(f"update_exit: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [exit_id]
        await self._db.execute(
            f"UPDATE exits SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    async def get_exit(self, exit_id: int) -> Optional[dict]:
        """Get a single exit by ID."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM exits WHERE id = ?", (exit_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_entrances(self, room_id: int) -> list:
        """Get all exits leading TO a room."""
        rows = await self._db.execute_fetchall(
            """SELECT e.*, r.name as from_room_name
               FROM exits e JOIN rooms r ON e.from_room_id = r.id
               WHERE e.to_room_id = ?""",
            (room_id,),
        )
        return [dict(r) for r in rows]

    async def find_exit_by_dir(self, from_room: int, direction: str) -> Optional[dict]:
        """Find an exit from a room in a given direction."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM exits WHERE from_room_id = ? AND direction = ?",
            (from_room, direction),
        )
        return dict(rows[0]) if rows else None

    # -- Mission Operations --

    async def create_mission(self, **fields) -> int:
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        values = list(fields.values())
        cursor = await self._db.execute(
            f"INSERT INTO missions ({cols}) VALUES ({placeholders})", values
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_available_missions(self, limit: int = 8) -> list:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM missions WHERE status = 'available' ORDER BY reward DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in rows]

    async def get_mission(self, mission_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM missions WHERE id = ?", (mission_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_active_mission(self, char_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM missions WHERE accepted_by = ? AND status = 'accepted'",
            (char_id,)
        )
        return dict(rows[0]) if rows else None

    async def update_mission(self, mission_id: int, **fields):
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [mission_id]
        await self._db.execute(
            f"UPDATE missions SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    async def count_available_missions(self) -> int:
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM missions WHERE status = 'available'"
        )
        return rows[0]["cnt"]

    async def cleanup_expired_missions(self):
        """Remove expired missions."""
        await self._db.execute(
            "DELETE FROM missions WHERE status = 'available' AND expires_at < datetime('now')"
        )
        await self._db.commit()

    # -- Ship Operations --

    async def create_ship(self, template: str, name: str, owner_id: int,
                          bridge_room_id: int, docked_at: int) -> int:
        """Create a ship. Returns ship ID."""
        cursor = await self._db.execute(
            """INSERT INTO ships (template, name, owner_id, bridge_room_id, docked_at,
               systems, crew)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (template, name, owner_id, bridge_room_id, docked_at,
             '{"engines":true,"weapons":true,"shields":true,"hyperdrive":true,"sensors":true}',
             '{}'),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_ship(self, ship_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE id = ?", (ship_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_ship_by_bridge(self, bridge_room_id: int) -> Optional[dict]:
        """Find the ship whose bridge is this room."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE bridge_room_id = ?", (bridge_room_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_ships_docked_at(self, room_id: int) -> list:
        """Get all ships docked at a particular room."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE docked_at = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    async def get_ships_owned_by(self, owner_id: int) -> list:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE owner_id = ?", (owner_id,)
        )
        return [dict(r) for r in rows]

    async def get_ships_in_space(self) -> list:
        """Get all ships currently in space (not docked)."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE docked_at IS NULL"
        )
        return [dict(r) for r in rows]

    _SHIP_WRITABLE_COLUMNS = frozenset({
        "template", "name", "owner_id", "bridge_room_id", "docked_at",
        "hull_damage", "shield_damage", "systems", "crew", "cargo",
    })

    async def update_ship(self, ship_id: int, **fields):
        """Update ship fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._SHIP_WRITABLE_COLUMNS
        if bad:
            raise ValueError(f"update_ship: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [ship_id]
        await self._db.execute(
            f"UPDATE ships SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    # -- NPC Operations --

    async def create_npc(self, name: str, room_id: int, species: str = "Human",
                         description: str = "", char_sheet_json: str = "{}",
                         ai_config_json: str = "{}") -> int:
        """Create an NPC. Returns NPC ID."""
        cursor = await self._db.execute(
            """INSERT INTO npcs (name, room_id, species, description, char_sheet_json, ai_config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, room_id, species, description, char_sheet_json, ai_config_json),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_npc(self, npc_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE id = ?", (npc_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_npcs_in_room(self, room_id: int) -> list:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE room_id = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    _NPC_WRITABLE_COLUMNS = frozenset({
        "name", "room_id", "species", "description", "char_sheet_json",
        "ai_config_json", "hired_by", "hire_wage", "assigned_ship",
        "assigned_station", "hired_at",
    })

    async def update_npc(self, npc_id: int, **fields):
        """Update NPC fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._NPC_WRITABLE_COLUMNS
        if bad:
            raise ValueError(f"update_npc: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [npc_id]
        await self._db.execute(
            f"UPDATE npcs SET {set_clause} WHERE id = ?", values
        )
        await self._db.commit()

    async def delete_npc(self, npc_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
        await self._db.execute("DELETE FROM npc_memory WHERE npc_id = ?", (npc_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    # -- NPC Crew Operations --

    async def hire_npc(self, npc_id: int, char_id: int, wage: int):
        """Mark an NPC as hired by a character."""
        await self._db.execute(
            """UPDATE npcs SET hired_by = ?, hire_wage = ?, hired_at = datetime('now')
               WHERE id = ?""",
            (char_id, wage, npc_id),
        )
        await self._db.commit()

    async def dismiss_npc(self, npc_id: int):
        """Release an NPC from service (clears hire + assignment fields)."""
        await self._db.execute(
            """UPDATE npcs SET hired_by = NULL, hire_wage = 0,
               assigned_ship = NULL, assigned_station = '', hired_at = ''
               WHERE id = ?""",
            (npc_id,),
        )
        await self._db.commit()

    async def assign_npc_to_station(self, npc_id: int, ship_id: int, station: str):
        """Assign a hired NPC to a crew station on a ship."""
        await self._db.execute(
            "UPDATE npcs SET assigned_ship = ?, assigned_station = ? WHERE id = ?",
            (ship_id, station, npc_id),
        )
        await self._db.commit()

    async def unassign_npc(self, npc_id: int):
        """Remove an NPC from their crew station (stays hired)."""
        await self._db.execute(
            "UPDATE npcs SET assigned_ship = NULL, assigned_station = '' WHERE id = ?",
            (npc_id,),
        )
        await self._db.commit()

    async def get_npcs_hired_by(self, char_id: int) -> list:
        """Get all NPCs currently hired by a character."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE hired_by = ?", (char_id,)
        )
        return [dict(r) for r in rows]

    async def get_npc_crew_on_ship(self, ship_id: int) -> list:
        """Get all NPCs assigned to a specific ship."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE assigned_ship = ?", (ship_id,)
        )
        return [dict(r) for r in rows]

    async def get_npc_at_station(self, ship_id: int, station: str) -> Optional[dict]:
        """Get the NPC assigned to a specific station on a ship."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE assigned_ship = ? AND assigned_station = ?",
            (ship_id, station),
        )
        return dict(rows[0]) if rows else None

    async def get_unhired_npcs_in_room(self, room_id: int) -> list:
        """Get NPCs in a room that are available for hire (not currently hired)."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE room_id = ? AND hired_by IS NULL",
            (room_id,),
        )
        return [dict(r) for r in rows]

    async def deduct_crew_wages(self, char_id: int) -> tuple[int, list]:
        """
        Deduct one day's wages for all NPCs hired by a character.
        Returns (total_deducted, list of NPC names that left due to insufficient funds).
        """
        npcs = await self.get_npcs_hired_by(char_id)
        if not npcs:
            return 0, []

        char = await self.get_character(char_id)
        if not char:
            return 0, []

        credits = char.get("credits", 0)
        total_deducted = 0
        departed = []

        for npc in npcs:
            wage = npc.get("hire_wage", 0)
            if credits >= wage:
                credits -= wage
                total_deducted += wage
            else:
                # Can't pay -- NPC quits (but stays in the world)
                departed.append(npc["name"])
                await self.dismiss_npc(npc["id"])

        if total_deducted > 0:
            await self.save_character(char_id, credits=credits)

        return total_deducted, departed

    # -- Traffic Ship Methods --

    async def create_traffic_ship(self, name: str, template: str) -> int:
        import json as _j
        systems = _j.dumps({"traffic": {}})
        cursor = await self._db.execute(
            "INSERT INTO ships "
            "(name, template, hull_damage, shield_damage, systems, crew, owner_id, docked_at) "
            "VALUES (?, ?, 0, 0, ?, '{}', NULL, NULL)",
            (name, template, systems),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def create_traffic_npc(self, name: str, ship_id: int, skill: str) -> int:
        import json as _j
        char_sheet = _j.dumps({
            "attributes": {
                "DEX": skill, "MEC": skill, "STR": "2D",
                "KNO": "2D",  "PER": "2D",  "TEC": "2D",
            },
            "skills": {
                "starfighter_piloting": skill,
                "space_transports":     skill,
                "starship_gunnery":     skill,
            },
        })
        cursor = await self._db.execute(
            "INSERT INTO npcs "
            "(name, species, room_id, char_sheet_json, ai_config_json, assigned_ship) "
            "VALUES (?, 'Human', 1, ?, '{}', ?)",
            (name, char_sheet, ship_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_traffic_ship_state(self, ship_id: int, traffic_data: dict):
        import json as _j
        rows = await self._db.execute_fetchall(
            "SELECT systems FROM ships WHERE id = ?", (ship_id,)
        )
        if not rows:
            return
        systems = _j.loads(rows[0]["systems"] or "{}")
        systems["traffic"] = traffic_data
        await self._db.execute(
            "UPDATE ships SET systems = ? WHERE id = ?",
            (_j.dumps(systems), ship_id),
        )
        await self._db.commit()

    async def get_all_traffic_ships(self) -> list:
        needle = '"traffic"'
        rows = await self._db.execute_fetchall(
            "SELECT * FROM ships WHERE systems LIKE ?",
            (f"%{needle}%",),
        )
        return rows or []

    async def delete_traffic_ship(self, ship_id: int):
        await self._db.execute(
            "DELETE FROM npcs WHERE assigned_ship = ?", (ship_id,)
        )
        await self._db.execute("DELETE FROM ships WHERE id = ?", (ship_id,))
        await self._db.commit()

    async def set_character_bounty(self, char_id: int, amount: int):
        await self._db.execute(
            "UPDATE characters SET bounty = ? WHERE id = ?",
            (max(0, amount), char_id),
        )
        await self._db.commit()

    async def get_character_bounty(self, char_id: int) -> int:
        rows = await self._db.execute_fetchall(
            "SELECT bounty FROM characters WHERE id = ?", (char_id,)
        )
        return rows[0]["bounty"] if rows else 0
