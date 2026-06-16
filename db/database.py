# -*- coding: utf-8 -*-
"""
Database layer - SQLite with WAL mode, async via aiosqlite.
Handles schema creation, migrations, and core CRUD operations.
"""
import aiosqlite
import asyncio
import bcrypt
import contextlib
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# -- Schema version --
# v44 (T3.22 Phase 0, 2026-06-13): ambient NPC life scaffolding —
# npc_ambient_state + npc_ambient_relationship. INERT pre-launch (read by
# nothing until the post-launch sim ships); landed now so the post-launch
# build never migrates a live, populated DB. See
# docs/design/ambient_npc_life_design_v1.md §5-6.
#
# v45 (T3.21 Blocker 3): admin_audit table — durable trail of every
# elevated (BUILDER/ADMIN) command dispatch, written at the parser seam.
SCHEMA_VERSION = 46

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

-- Admin/builder audit trail (T3.21 Blocker 3): one row per elevated
-- command dispatch, written at the parser seam. Secret-bearing args
-- (e.g. @newpassword) are redacted before insert. Append-only.
CREATE TABLE IF NOT EXISTS admin_audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER,
    username      TEXT,
    char_id       INTEGER,
    char_name     TEXT,
    access_level  INTEGER NOT NULL,
    command       TEXT NOT NULL,
    detail        TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_account ON admin_audit(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit(created_at);

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

-- v46 (T3.21 opt): the account->characters lookup (login, char-select, and the
-- accounts<->characters JOINs in builder/mux tooling) keyed on account_id and
-- previously did a full characters scan. Composite (account_id, is_active)
-- fully covers get_characters' WHERE account_id=? AND is_active=1 and serves
-- the account_id-prefix JOINs.
CREATE INDEX IF NOT EXISTS idx_characters_account
ON characters(account_id, is_active);

-- Rooms
CREATE TABLE IF NOT EXISTS rooms (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id         INTEGER,
    name            TEXT NOT NULL,
    desc_short      TEXT DEFAULT '',
    desc_long       TEXT DEFAULT '',
    properties      TEXT DEFAULT '{}',   -- JSON: environment, gravity, etc.
    wilderness_region_id  TEXT,          -- v19 (May 3 2026): NULL for hand-built rooms;
                                         -- set on wilderness landmark rows. Foundation for
                                         -- the Village's Dune Sea substrate; full coordinate-
                                         -- movement engine ships in a future drop per
                                         -- wilderness_system_design_v1.md.
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rooms_wilderness_region
ON rooms(wilderness_region_id)
WHERE wilderness_region_id IS NOT NULL;

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

-- Bounty contracts (live NPC targets)
CREATE TABLE IF NOT EXISTS bounties (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'posted',
    tier            TEXT NOT NULL,
    target_npc_id   INTEGER,
    claimed_by      TEXT,
    posted_at       REAL NOT NULL,
    expires_at      REAL,
    reward          INTEGER NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bounties_status ON bounties(status);

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

-- Mail subsystem (smoke drop 4 carry-over, May 2026)
-- The mail subsystem (parser/mail_commands.py) had been shipping
-- against missing tables — every @mail subcommand 500'd with
-- "no such table: mail". Schema inferred from queries in
-- mail_commands.py (_list_inbox, _read, _quick, _do_send, _delete,
-- _purge, _unread, _sent, _forward, _reply, _compose_*).
--
-- sent_at is stored as ISO format text (datetime.utcnow().isoformat()
-- in _do_send) — it goes through datetime.fromisoformat() on read.
-- Keeping TEXT (not REAL) to match the existing format and avoid
-- a downstream parser change.
--
-- ON DELETE CASCADE on mail_recipients.mail_id matches the manual
-- orphan-cleanup _purge already does:
--   DELETE FROM mail WHERE id NOT IN (SELECT DISTINCT mail_id
--   FROM mail_recipients)
-- The cascade makes that defensive cleanup redundant but harmless.
--
-- This block + the v23 migration below were carried into F.7.c.1
-- because Brian's apply chain (smoke drop 4 → F.7.b → W.2 phase 2)
-- caused the later W.2 phase 2 db/database.py overwrite to drop the
-- mail tables. F.7.c.1's database.py is the chain's new HEAD.
CREATE TABLE IF NOT EXISTS mail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id       INTEGER NOT NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    sent_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_recipients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id         INTEGER NOT NULL REFERENCES mail(id) ON DELETE CASCADE,
    char_id         INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    is_read         INTEGER NOT NULL DEFAULT 0,
    is_deleted      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mail_recipients_char_id
    ON mail_recipients(char_id);
CREATE INDEX IF NOT EXISTS idx_mail_recipients_mail_id
    ON mail_recipients(mail_id);
CREATE INDEX IF NOT EXISTS idx_mail_sender_id
    ON mail(sender_id);

-- v28 (May 19 2026): Padawan-Master bond table (P-M.1 foundation).
-- Per padawan_master_system_design_v1.md §4.3. The bond is the
-- mechanical substrate for the Padawan-Master relationship system;
-- commands, training events, and the Trials build on top of this
-- table. P-M.1 ships the table + DB methods only — commands and
-- gameplay surfaces are P-M.2 and beyond.
--
-- bond_status values:
--   'active'    — bond is current; the two PCs are paired
--   'dissolved' — bond ended without knighting (mutual release,
--                 staff intervention, master abandonment, etc.)
--   'knighted'  — Padawan completed Trials and was knighted;
--                 the bond closes naturally
--   'fallen'    — Padawan fell to the Dark Side (see design §7)
--
-- A Padawan can have at most one bond_status='active' bond at any
-- time. A Master can have at most one at launch (Council
-- authorization can raise the cap post-launch via staff
-- adjudication; the schema does not enforce this — the DB layer's
-- create_bond method does).
--
-- trials_passed_json: JSON array of passed Trial names (Skill,
-- Courage, Flesh, Spirit, Insight per design doc §6.2). NULL or
-- '[]' for new bonds.
CREATE TABLE IF NOT EXISTS master_padawan_bond (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    master_char_id        INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    padawan_char_id       INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    bond_established_at   TEXT NOT NULL DEFAULT (datetime('now')),
    bond_status           TEXT NOT NULL DEFAULT 'active'
        CHECK(bond_status IN ('active', 'dissolved', 'knighted', 'fallen')),
    dissolved_at          TEXT,
    dissolved_reason      TEXT,
    knight_promotion_at   TEXT,
    trials_passed_json    TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_bond_master
    ON master_padawan_bond(master_char_id, bond_status);
CREATE INDEX IF NOT EXISTS idx_bond_padawan
    ON master_padawan_bond(padawan_char_id, bond_status);

-- Ambient NPC life (T3.22 Phase 0 — INERT scaffolding, read by nothing
-- until the post-launch sim ships). Per-NPC runtime goal/movement state;
-- ambient config rides the existing npcs.ai_config_json (no schema change).
-- Both tables carry a JSON `extra` future-proof blank (the SQLite-idiomatic
-- "blank space" — new fields go into JSON with zero migration, like
-- characters.attributes). See docs/design/ambient_npc_life_design_v1.md §5.2.
CREATE TABLE IF NOT EXISTS npc_ambient_state (
    npc_id          INTEGER PRIMARY KEY REFERENCES npcs(id),
    current_goal    TEXT DEFAULT '',
    current_room_id INTEGER REFERENCES rooms(id),
    dest_room_id    INTEGER REFERENCES rooms(id),
    move_started_at REAL,
    move_duration   REAL,
    last_tick_at    REAL,
    activity        TEXT DEFAULT '',
    extra           TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_npc_ambient_room
    ON npc_ambient_state(current_room_id);

CREATE TABLE IF NOT EXISTS npc_ambient_relationship (
    npc_id_a   INTEGER NOT NULL REFERENCES npcs(id),
    npc_id_b   INTEGER NOT NULL REFERENCES npcs(id),
    affinity   INTEGER DEFAULT 0,
    extra      TEXT DEFAULT '{}',
    PRIMARY KEY (npc_id_a, npc_id_b)
);
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
    4: [
        "ALTER TABLE characters ADD COLUMN tutorial_step INTEGER DEFAULT 0",
    ],
    5: [
        """CREATE TABLE IF NOT EXISTS zone_influence (
            zone_id TEXT NOT NULL,
            faction TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (zone_id, faction)
        )""",
        """CREATE TABLE IF NOT EXISTS director_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            event_type TEXT NOT NULL,
            summary TEXT,
            details_json TEXT,
            token_cost_input INTEGER DEFAULT 0,
            token_cost_output INTEGER DEFAULT 0
        )""",
    ],
    6: [
        """CREATE TABLE IF NOT EXISTS smuggling_jobs (
            id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'available',
            accepted_by INTEGER,
            data TEXT NOT NULL
        )""",
    ],

    7: [
        """CREATE TABLE IF NOT EXISTS cp_ticks (
            char_id         INTEGER PRIMARY KEY REFERENCES characters(id),
            ticks_total     INTEGER DEFAULT 0,
            ticks_this_week INTEGER DEFAULT 0,
            week_start_ts   REAL    DEFAULT 0,
            cap_hit_streak  INTEGER DEFAULT 0,
            last_passive_ts REAL    DEFAULT 0,
            last_scene_ts   REAL    DEFAULT 0,
            last_award_ts   REAL    DEFAULT 0,
            last_source     TEXT    DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS kudos_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            giver_id    INTEGER NOT NULL REFERENCES characters(id),
            target_id   INTEGER NOT NULL REFERENCES characters(id),
            ticks       INTEGER DEFAULT 0,
            awarded_at  REAL    NOT NULL
        )""",
    ],

    8: [],  # placeholder (was already applied)

    9: [
        # Faction column on characters
        "ALTER TABLE characters ADD COLUMN faction_id TEXT DEFAULT 'independent'",

        # Organizations master table (factions + guilds)
        """CREATE TABLE IF NOT EXISTS organizations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT UNIQUE NOT NULL,
            name            TEXT NOT NULL,
            org_type        TEXT NOT NULL DEFAULT 'faction',
            director_managed INTEGER DEFAULT 1,
            leader_id       INTEGER REFERENCES characters(id),
            hq_room_id      INTEGER REFERENCES rooms(id),
            treasury        INTEGER DEFAULT 0,
            properties      TEXT DEFAULT '{}'
        )""",

        # Rank definitions per organization
        """CREATE TABLE IF NOT EXISTS org_ranks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id          INTEGER NOT NULL REFERENCES organizations(id),
            rank_level      INTEGER NOT NULL,
            title           TEXT NOT NULL,
            min_rep         INTEGER DEFAULT 0,
            permissions     TEXT DEFAULT '[]',
            equipment       TEXT DEFAULT '[]',
            UNIQUE(org_id, rank_level)
        )""",

        # PC membership in organizations
        """CREATE TABLE IF NOT EXISTS org_memberships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            org_id          INTEGER NOT NULL REFERENCES organizations(id),
            rank_level      INTEGER DEFAULT 0,
            standing        TEXT DEFAULT 'good',
            rep_score       INTEGER DEFAULT 0,
            specialization  TEXT DEFAULT '',
            joined_at       TEXT DEFAULT (datetime('now')),
            UNIQUE(char_id, org_id)
        )""",

        # Faction-issued equipment tracking
        """CREATE TABLE IF NOT EXISTS issued_equipment (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            org_id          INTEGER NOT NULL REFERENCES organizations(id),
            item_key        TEXT NOT NULL,
            item_name       TEXT NOT NULL,
            issued_at       TEXT DEFAULT (datetime('now')),
            reclaimed       INTEGER DEFAULT 0
        )""",

        # Faction-issued ships
        """CREATE TABLE IF NOT EXISTS issued_ships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            org_id          INTEGER NOT NULL REFERENCES organizations(id),
            ship_id         INTEGER REFERENCES ships(id),
            issued_at       TEXT DEFAULT (datetime('now')),
            returned        INTEGER DEFAULT 0
        )""",

        # Guild dues log
        """CREATE TABLE IF NOT EXISTS guild_dues (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            org_id          INTEGER NOT NULL REFERENCES organizations(id),
            amount          INTEGER DEFAULT 0,
            paid_at         TEXT DEFAULT (datetime('now'))
        )""",

        # Faction event / action log
        """CREATE TABLE IF NOT EXISTS faction_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER REFERENCES characters(id),
            org_id          INTEGER REFERENCES organizations(id),
            action_type     TEXT NOT NULL,
            details         TEXT DEFAULT '',
            logged_at       TEXT DEFAULT (datetime('now'))
        )""",

        # PC narrative memory (two-tier: short for NPC brain, long for Director)
        """CREATE TABLE IF NOT EXISTS pc_narrative (
            char_id         INTEGER PRIMARY KEY REFERENCES characters(id),
            background      TEXT DEFAULT '',
            short_record    TEXT DEFAULT '',
            long_record     TEXT DEFAULT '',
            last_summarized TEXT DEFAULT ''
        )""",

        # PC action log (raw events, summarized nightly into pc_narrative)
        """CREATE TABLE IF NOT EXISTS pc_action_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            action_type     TEXT NOT NULL,
            summary         TEXT NOT NULL,
            details         TEXT DEFAULT '{}',
            logged_at       TEXT DEFAULT (datetime('now'))
        )""",

        # Personal quests (Director-generated, player-tracked)
        """CREATE TABLE IF NOT EXISTS personal_quests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            title           TEXT NOT NULL,
            description     TEXT DEFAULT '',
            status          TEXT DEFAULT 'active',
            created_at      TEXT DEFAULT (datetime('now')),
            completed_at    TEXT DEFAULT ''
        )""",
    ],

    10: [
        # Tag missions to a specific faction (NULL = public mission board)
        "ALTER TABLE missions ADD COLUMN faction_id TEXT DEFAULT NULL",

        # Mission type-specific payload (required by engine/missions.py)
        "ALTER TABLE missions ADD COLUMN data TEXT DEFAULT '{}'",

        # Shop transaction log for vendor droids
        """CREATE TABLE IF NOT EXISTS shop_transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            droid_id    INTEGER NOT NULL REFERENCES objects(id),
            seller_id   INTEGER NOT NULL REFERENCES characters(id),
            buyer_id    INTEGER NOT NULL REFERENCES characters(id),
            item_key    TEXT    NOT NULL,
            item_name   TEXT    NOT NULL,
            quality     INTEGER DEFAULT 0,
            quantity    INTEGER DEFAULT 1,
            unit_price  INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            listing_fee INTEGER DEFAULT 0,
            txn_type    TEXT    DEFAULT 'sale',
            created_at  REAL    NOT NULL
        )""",
    ],

    11: [
        # Hand-tuned map coordinates for area map display
        "ALTER TABLE rooms ADD COLUMN map_x REAL DEFAULT NULL",
        "ALTER TABLE rooms ADD COLUMN map_y REAL DEFAULT NULL",
    ],

    12: [
        # Economy hardening: credit transaction log for velocity tracking
        """CREATE TABLE IF NOT EXISTS credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id     INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            source      TEXT NOT NULL,
            balance     INTEGER NOT NULL,
            created_at  REAL NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_credit_log_time ON credit_log(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_credit_log_source ON credit_log(source, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_credit_log_char ON credit_log(char_id, created_at)",
    ],

    13: [
        # Scene logging & archive (Priority D Phase 1)
        """CREATE TABLE IF NOT EXISTS scenes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    DEFAULT '',
            summary         TEXT    DEFAULT '',
            scene_type      TEXT    DEFAULT 'Social',
            location        TEXT    DEFAULT '',
            room_id         INTEGER,
            creator_id      INTEGER NOT NULL REFERENCES characters(id),
            status          TEXT    DEFAULT 'active',
            started_at      REAL    NOT NULL,
            completed_at    REAL,
            shared_at       REAL
        )""",
        """CREATE TABLE IF NOT EXISTS scene_poses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id        INTEGER NOT NULL REFERENCES scenes(id),
            char_id         INTEGER,
            char_name       TEXT    NOT NULL,
            pose_text       TEXT    NOT NULL,
            pose_type       TEXT    DEFAULT 'pose',
            is_ooc          INTEGER DEFAULT 0,
            created_at      REAL    NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS scene_participants (
            scene_id        INTEGER NOT NULL REFERENCES scenes(id),
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            PRIMARY KEY (scene_id, char_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_scene_poses_scene ON scene_poses(scene_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_scenes_status ON scenes(status, started_at)",
        "CREATE INDEX IF NOT EXISTS idx_scene_participants ON scene_participants(char_id)",
        "CREATE INDEX IF NOT EXISTS idx_scenes_room ON scenes(room_id, status)",
    ],

    14: [
        # Achievement tracking system
        """CREATE TABLE IF NOT EXISTS character_achievements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL,
            achievement_key TEXT NOT NULL,
            progress        INTEGER DEFAULT 0,
            completed       INTEGER DEFAULT 0,
            completed_at    REAL,
            UNIQUE(char_id, achievement_key)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_achievements_char ON character_achievements(char_id)",
        "CREATE INDEX IF NOT EXISTS idx_achievements_key ON character_achievements(achievement_key)",
    ],

    15: [
        # Event calendar system (Priority D Phase 4)
        """CREATE TABLE IF NOT EXISTS game_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            description     TEXT    DEFAULT '',
            location        TEXT    DEFAULT '',
            creator_id      INTEGER NOT NULL REFERENCES characters(id),
            creator_name    TEXT    NOT NULL,
            status          TEXT    DEFAULT 'upcoming',
            scheduled_at    REAL    NOT NULL,
            created_at      REAL    NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS game_event_signups (
            event_id        INTEGER NOT NULL REFERENCES game_events(id),
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            char_name       TEXT    NOT NULL,
            signed_up_at    REAL    NOT NULL,
            PRIMARY KEY (event_id, char_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_events_status ON game_events(status, scheduled_at)",
        "CREATE INDEX IF NOT EXISTS idx_events_creator ON game_events(creator_id)",
    ],

    16: [
        # Plot / Story Arc Tracker (Priority D Phase 4, Drop 3)
        """CREATE TABLE IF NOT EXISTS plots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            summary         TEXT    DEFAULT '',
            creator_id      INTEGER NOT NULL REFERENCES characters(id),
            creator_name    TEXT    NOT NULL,
            status          TEXT    DEFAULT 'open',
            created_at      REAL    NOT NULL,
            updated_at      REAL    NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS plot_scenes (
            plot_id         INTEGER NOT NULL REFERENCES plots(id),
            scene_id        INTEGER NOT NULL REFERENCES scenes(id),
            linked_at       REAL    NOT NULL,
            PRIMARY KEY (plot_id, scene_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_plots_status ON plots(status, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_plots_creator ON plots(creator_id)",
        "CREATE INDEX IF NOT EXISTS idx_plot_scenes_scene ON plot_scenes(scene_id)",
    ],

    17: [
        # Sheet redesign — chargen_notes captures the player's
        # "why I built this character this way" rationale during
        # creation. Defaults to '' for existing characters; surfaces
        # in the GUI sheet's right-rail and is editable from the
        # panel via +chargen_notes <text>. Distinct from `description`
        # (in-character look-at text) and `pc_narrative.background`
        # (in-character biography).
        "ALTER TABLE characters ADD COLUMN chargen_notes TEXT DEFAULT ''",
    ],

    18: [
        # ── Progression Gates & Consequences — Phase 1 schema ────────────
        # Per progression_gates_and_consequences_design_v1.md and
        # architecture v39 §3.3 (CW.GATES sub-decomposition: PG.1.schema).
        #
        # This migration adds the persistent state for three coupled
        # systems: Jedi gating (50-hour playtime + Village trial chain),
        # death penalty (respawn-Wounded + corpse retrieval), and the
        # PC bounty / BH insurance loop. No data backfill required —
        # all columns default to safe pre-feature values, and at the
        # time this lands there are no live players whose state would
        # need migrating.
        #
        # The legacy `characters.bounty` column from migration 3 is
        # untouched and remains independent of the new PC-posted bounty
        # system below (`pc_bounties` table). The legacy column tracked
        # NPC-bounty placeholder state and is not used by the design.
        # The legacy `characters.wound_level` column (set in base
        # SCHEMA_SQL) tracks combat-active wound levels via the WEG
        # ladder; the new `wound_state` / `wound_clear_at` columns track
        # the post-respawn Wounded debuff that persists across
        # logout/login until cleared by time or bacta. Distinct concerns.

        # ── Jedi gating: per-character playtime, predisposition, Village state ─
        "ALTER TABLE characters ADD COLUMN play_time_seconds INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN force_predisposition REAL DEFAULT 0.0",
        "ALTER TABLE characters ADD COLUMN force_signs_accumulated INTEGER DEFAULT 0",
        # village_act: 0=pre-invitation, 1=invited (post-Hermit),
        #              2=in-trials, 3=passed (Padawan)
        "ALTER TABLE characters ADD COLUMN village_act INTEGER DEFAULT 0",
        # Wall-clock timestamp of last act transition; drives 7-day
        # Act-1→Act-2 cooldown.
        "ALTER TABLE characters ADD COLUMN village_act_unlocked_at REAL DEFAULT 0",
        # Per-trial completion flags. 0=not done, 1=done.
        "ALTER TABLE characters ADD COLUMN village_trial_courage_done INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_insight_done INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_flesh_done INTEGER DEFAULT 0",
        # Wall-clock of last trial attempt; drives 14-day inter-trial cooldown.
        "ALTER TABLE characters ADD COLUMN village_trial_last_attempt REAL DEFAULT 0",

        # ── Death penalty: respawn-Wounded persistence ──────────────────────
        # wound_state: 'healthy' | 'wounded'
        # wound_clear_at: unix epoch seconds when wound_state returns to
        #                 'healthy' via passive recovery; 0 means no
        #                 active recovery clock (already healthy).
        "ALTER TABLE characters ADD COLUMN wound_state TEXT DEFAULT 'healthy'",
        "ALTER TABLE characters ADD COLUMN wound_clear_at REAL DEFAULT 0",

        # ── Death penalty: corpses ──────────────────────────────────────────
        # On PC death the body persists at the death location for a
        # bounded window (2h contested / 4h lawless / no-corpse for
        # secured). Decay either auto-mails `bound` items to the owner
        # or destroys the rest.
        """CREATE TABLE IF NOT EXISTS corpses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL REFERENCES characters(id),
            room_id         INTEGER NOT NULL REFERENCES rooms(id),
            died_at         REAL    NOT NULL,
            decay_at        REAL    NOT NULL,
            inventory       TEXT    NOT NULL DEFAULT '[]',
            credits         INTEGER DEFAULT 0,
            killer_id       INTEGER REFERENCES characters(id),
            killer_is_bh    INTEGER DEFAULT 0,
            bounty_resolved INTEGER DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_corpses_room ON corpses(room_id, decay_at)",
        "CREATE INDEX IF NOT EXISTS idx_corpses_char ON corpses(char_id)",

        # ── PC bounty system ────────────────────────────────────────────────
        # state: 'active' | 'claimed' | 'fulfilled' | 'expired' | 'canceled'
        """CREATE TABLE IF NOT EXISTS pc_bounties (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            poster_id       INTEGER NOT NULL REFERENCES characters(id),
            target_id       INTEGER NOT NULL REFERENCES characters(id),
            amount          INTEGER NOT NULL,
            reason          TEXT    NOT NULL,
            state           TEXT    NOT NULL DEFAULT 'active',
            claimed_by      INTEGER REFERENCES characters(id),
            claimed_at      REAL    DEFAULT 0,
            posted_at       REAL    NOT NULL,
            expires_at      REAL    NOT NULL,
            resolved_at     REAL    DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_bounties_target ON pc_bounties(target_id, state)",
        "CREATE INDEX IF NOT EXISTS idx_bounties_poster ON pc_bounties(poster_id, state)",
        "CREATE INDEX IF NOT EXISTS idx_bounties_state_expiry ON pc_bounties(state, expires_at)",

        # 30-day per-(poster, target) cooldown after expiry/cancel.
        # Prevents harassment loops.
        """CREATE TABLE IF NOT EXISTS bounty_cooldowns (
            poster_id   INTEGER NOT NULL REFERENCES characters(id),
            target_id   INTEGER NOT NULL REFERENCES characters(id),
            until       REAL    NOT NULL,
            PRIMARY KEY (poster_id, target_id)
        )""",

        # BH insurance debt — accrues when target lacks credits at
        # respawn to cover the 10%-of-bounty insurance hit. Blocks
        # Guild services, intercepts faction stipends, refused at
        # some BH-tier vendors until paid off.
        """CREATE TABLE IF NOT EXISTS bh_insurance_debt (
            char_id     INTEGER PRIMARY KEY REFERENCES characters(id),
            amount      INTEGER NOT NULL,
            incurred_at REAL    NOT NULL
        )""",
    ],

    # ─── v19 (May 3 2026) — Wilderness substrate (Dune Sea minimal) ──────
    #
    # Per wilderness_system_design_v1.md and the v40 §3.5 Village build
    # prerequisite stack: the Village quest needs a wilderness region
    # that hosts its landmarks (Anchor Stones, Outer Watch, Common
    # Square, Hermit's Hut, etc.). The full coordinate-grid wilderness
    # system is a future multi-drop track; this migration adds the
    # MINIMUM column needed for the Dune Sea substrate to land:
    #
    #   - rooms.wilderness_region_id    NULL for hand-built rooms;
    #                                   set on rows that belong to a
    #                                   wilderness region's landmark
    #                                   roster. Used by the wilderness
    #                                   loader/writer (engine/wilderness_*)
    #                                   and (eventually) by the future
    #                                   coordinate-movement engine to
    #                                   distinguish "this is a wilderness
    #                                   landmark room" from "this is a
    #                                   hand-built city room."
    #
    # Coordinates themselves live in properties JSON (already a flexible
    # dict on rooms); we don't need a hard column for them right now.
    # If/when coordinate queries become hot enough to justify indexed
    # access, a future migration adds (region_id, x, y) columns.
    #
    # The full wilderness buildout (per wilderness_system_design_v1.md
    # Drops 2-7) is the post-Village roadmap item; see the May 3 handoff
    # doc.
    19: [
        "ALTER TABLE rooms ADD COLUMN wilderness_region_id TEXT NULL",
        "CREATE INDEX IF NOT EXISTS idx_rooms_wilderness_region "
        "ON rooms(wilderness_region_id) "
        "WHERE wilderness_region_id IS NOT NULL",
    ],

    # ── v20 (May 3 2026): Wilderness movement core (Drop 2) ──────────────────
    #
    # Per wilderness_system_design_v1.md §3.2 §3.3 and Drop 2 plan:
    # adds the per-character wilderness coordinate state + the regions
    # registry table. The virtual sentinel room is written by the
    # build script, not by migration (it's content, not schema).
    #
    # `characters.wilderness_region_slug` is the slug TEXT (matches the
    # F.5 / v19 pattern of slug-based wilderness_region_id on rooms,
    # rather than INTEGER FK that the design doc originally specified —
    # consistent with how landmark rooms reference the region).
    #
    # `wilderness_x` / `wilderness_y` are NULL when the character is in
    # a normal room, set to (col, row) when in wilderness. The pair
    # (slug, x, y) is the authoritative wilderness location.
    #
    # `wilderness_regions` is a registry table written at world-build
    # time from each loaded region YAML. This gives the engine a fast
    # path for "look up bounds / default terrain by slug" without
    # re-reading the YAML at every move.
    #
    # `wilderness_discoveries` is deferred to Drop 4 (search/landmark
    # discovery) — not part of Drop 2.
    20: [
        "ALTER TABLE characters ADD COLUMN wilderness_region_slug TEXT NULL",
        "ALTER TABLE characters ADD COLUMN wilderness_x INTEGER NULL",
        "ALTER TABLE characters ADD COLUMN wilderness_y INTEGER NULL",
        "CREATE TABLE IF NOT EXISTS wilderness_regions ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " slug TEXT NOT NULL UNIQUE,"
        " name TEXT NOT NULL,"
        " planet TEXT NOT NULL,"
        " zone_slug TEXT NOT NULL,"
        " width INTEGER NOT NULL,"
        " height INTEGER NOT NULL,"
        " tile_scale_km INTEGER NOT NULL DEFAULT 1,"
        " default_terrain TEXT NOT NULL,"
        " default_security TEXT NOT NULL,"
        " sentinel_room_id INTEGER,"
        " config_json TEXT NOT NULL DEFAULT '{}',"
        " created_at REAL NOT NULL"
        ")",
        # Index for the common query "is this character in a region?"
        "CREATE INDEX IF NOT EXISTS idx_characters_wilderness_region "
        "ON characters(wilderness_region_slug) "
        "WHERE wilderness_region_slug IS NOT NULL",
    ],

    # ── v21 (May 4 2026): Village quest Step 3 gate state (F.7.b) ────────────
    #
    # Per jedi_village_quest_design_v1.md §4.2: Sister Vitha's Gate
    # accepts answers [1] and [3] (advance), and rejects answer [2]
    # with a 24-hour cooldown. We need to track:
    #
    #   - village_gate_passed:        bool — True iff Vitha admitted
    #     the player. Set to 1 when answer [1] or [3] chosen.
    #     Idempotent (a passed gate stays passed).
    #
    #   - village_gate_lockout_until: REAL — Unix timestamp when the
    #     24-hour cooldown expires. 0 if no lockout active. Set when
    #     answer [2] is chosen.
    #
    #   - village_gate_attempts:      INTEGER — total times the gate
    #     dialogue has been initiated. Used for telemetry/balance —
    #     no in-game effect.
    21: [
        "ALTER TABLE characters ADD COLUMN village_gate_passed INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_gate_lockout_until REAL DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_gate_attempts INTEGER DEFAULT 0",
    ],

    # ── v22 (May 4 2026): Village quest Trials runtime state (F.7.c.1) ───────
    #
    # Per jedi_village_quest_design_v1.md §5: five trials, each with
    # its own completion type and state. F.7.c.1 ships Trial 1 (Skill)
    # and Trial 5 (Insight) end-to-end.
    #
    # NOTE: v18 (PG.1.schema) already declared the four "headline"
    # done-flag columns: village_trial_courage_done,
    # village_trial_insight_done, village_trial_flesh_done, and
    # village_trial_last_attempt. v22 adds the remaining state columns
    # specific to each trial's mechanic — and intentionally does NOT
    # redeclare the v18 columns (the migration runner is duplicate-
    # tolerant, but cleaner not to repeat).
    #
    # F.7.c.1 RUNTIME-LIVE columns (Skill + Insight):
    #
    #   Trial 1 (Skill — 3-step craft_lightsaber check, 1h cooldown):
    #     - village_trial_skill_done               INTEGER  bool
    #     - village_trial_skill_step               INTEGER  0..3
    #     - village_trial_skill_attempts           INTEGER  total attempts
    #     - village_trial_skill_last_at            REAL     last-attempt ts
    #     - village_trial_skill_crystal_granted    INTEGER  one-shot reward
    #
    #   Trial 5 (Insight — accuse fragment_N, hint+retry on wrong):
    #     - village_trial_insight_attempts         INTEGER  total accusations
    #     - village_trial_insight_correct_fragment INTEGER  1..3, persisted
    #         on first encounter so retries don't shuffle
    #     - village_trial_insight_pendant_granted  INTEGER  one-shot reward
    #
    # Reserved-for-future columns (F.7.c.2/3):
    #
    #   Trial 2 (Courage):
    #     - village_trial_courage_lockout_until    REAL    (24h fail cooldown)
    #
    #   Trial 3 (Flesh):
    #     - village_trial_flesh_started_at         REAL    0 if not started
    #     - village_trial_flesh_session_seconds    REAL    accumulated time
    #
    #   Trial 4 (Spirit):
    #     - village_trial_spirit_done              INTEGER  bool
    #     - village_trial_spirit_dark_pull         INTEGER  0..3 (Path C lock at 3)
    #     - village_trial_spirit_rejections        INTEGER  toward pass-threshold (4)
    #
    # All forward columns ship in v22 even though F.7.c.1 only writes
    # to Skill + Insight; cheaper than two more schema bumps.
    22: [
        # Trial 1: Skill (Smith Daro)
        "ALTER TABLE characters ADD COLUMN village_trial_skill_done INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_skill_step INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_skill_attempts INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_skill_last_at REAL DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_skill_crystal_granted INTEGER DEFAULT 0",
        # Trial 2: Courage (Elder Mira Delen) — F.7.c.2 will use
        "ALTER TABLE characters ADD COLUMN village_trial_courage_lockout_until REAL DEFAULT 0",
        # Trial 3: Flesh (Elder Korvas) — F.7.c.3 will use
        "ALTER TABLE characters ADD COLUMN village_trial_flesh_started_at REAL DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_flesh_session_seconds REAL DEFAULT 0",
        # Trial 4: Spirit (Master Yarael in Sealed Sanctum) — F.7.c.2 will use
        "ALTER TABLE characters ADD COLUMN village_trial_spirit_done INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_spirit_dark_pull INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_spirit_rejections INTEGER DEFAULT 0",
        # Trial 5: Insight (Elder Saro Veck)
        "ALTER TABLE characters ADD COLUMN village_trial_insight_attempts INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_insight_correct_fragment INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_insight_pendant_granted INTEGER DEFAULT 0",
    ],

    # ── v23 (May 4 2026): Mail subsystem tables (smoke-drop-4 carry-over) ────
    #
    # Brian's apply chain on his Windows dev box was:
    #     smoke drop3 → smoke drop4 → smoke drop5 → W.2 phase 2 → F.7.b
    # W.2 phase 2 and F.7.b each shipped a `db/database.py`. Neither
    # included the mail tables that smoke drop 4 had introduced (smoke
    # drop 4 forked from a v19 baseline before W.2's wilderness
    # migration existed). The result: F.7.b's database.py overwrote
    # smoke drop 4's, and the mail subsystem tables vanished from HEAD.
    #
    # The runtime parser/mail_commands.py file survived (neither W.2p2
    # nor F.7.b touched it), so re-introducing the schema here is the
    # full fix. CREATE TABLE IF NOT EXISTS is idempotent: existing DBs
    # that somehow already have the tables won't error.
    #
    # Schema is identical to what smoke drop 4 declared:
    #   - mail (id, sender_id FK characters, subject TEXT, body TEXT,
    #     sent_at TEXT in ISO format)
    #   - mail_recipients (id, mail_id FK mail ON DELETE CASCADE,
    #     char_id FK characters ON DELETE CASCADE, is_read,
    #     is_deleted)
    #   - 3 indexes on the high-cardinality access columns
    #
    # See SCHEMA_SQL above for the full create statements; this
    # migration runs the same DDL against existing DBs (the IF NOT
    # EXISTS clauses make the two paths converge).
    23: [
        "CREATE TABLE IF NOT EXISTS mail ("
        "  id        INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  sender_id INTEGER NOT NULL REFERENCES characters(id),"
        "  subject   TEXT NOT NULL,"
        "  body      TEXT NOT NULL,"
        "  sent_at   TEXT NOT NULL"
        ")",
        "CREATE TABLE IF NOT EXISTS mail_recipients ("
        "  id         INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  mail_id    INTEGER NOT NULL REFERENCES mail(id) "
        "             ON DELETE CASCADE,"
        "  char_id    INTEGER NOT NULL REFERENCES characters(id) "
        "             ON DELETE CASCADE,"
        "  is_read    INTEGER NOT NULL DEFAULT 0,"
        "  is_deleted INTEGER NOT NULL DEFAULT 0"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_mail_recipients_char_id "
        "ON mail_recipients(char_id)",
        "CREATE INDEX IF NOT EXISTS idx_mail_recipients_mail_id "
        "ON mail_recipients(mail_id)",
        "CREATE INDEX IF NOT EXISTS idx_mail_sender_id "
        "ON mail(sender_id)",
    ],

    # ── v24 (May 4 2026): Trial 4 (Spirit) — turn counter + Path C ──────────
    #
    # F.7.c.4 (Spirit runtime) needs two more pieces of state beyond
    # what v22 reserved:
    #
    #   - village_trial_spirit_turn      INTEGER  current turn 1..7
    #     (the trial caps at 7 turns; without this column we'd have to
    #      derive it as `dark_pull + rejections + ambivalent`, but
    #      ambivalent is otherwise unused — the explicit column is
    #      cleaner than adding a fourth counter just to derive turn).
    #
    #   - village_trial_spirit_path_c_locked INTEGER  bool, 1 once
    #      dark_pull >= 3. Per design §7.3 this is a one-way irreversible
    #      lock that re-shapes Yarael's Act 3 dialogue (Path A/B suppressed,
    #      only Path C offered). Stored explicitly rather than derived from
    #      dark_pull because (a) future drops may dial back the dark_pull
    #      threshold without changing the lock semantic, and (b) it makes
    #      the gate check cheap and obvious.
    #
    # Both columns are additive and default 0. No existing column or
    # table semantics change.
    24: [
        "ALTER TABLE characters ADD COLUMN village_trial_spirit_turn INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_trial_spirit_path_c_locked INTEGER DEFAULT 0",
    ],

    # ── v25 (May 4 2026): Village quest Step 10 — Path A/B/C choice ─────────
    #
    # F.7.d (the Path choice) needs two columns to record which path
    # the character committed to:
    #
    #   - village_choice_completed   INTEGER  bool, 1 once a path is
    #     committed. Once true, the choice is irreversible — see
    #     design §7.0 ("the choice is the end of the chain; the
    #     character does not return to it").
    #
    #   - village_chosen_path        TEXT     'a' | 'b' | 'c' | ''.
    #     Empty string until choice is committed, then one of the
    #     three single-letter codes. Matches the user-facing
    #     `path a` / `path b` / `path c` command vocabulary, and is
    #     explicit enough that downstream code never has to guess
    #     what an enum value meant.
    #
    # Path-specific consequence flags (jedi_path_unlocked,
    # dark_path_unlocked, village_chosen_path_a, etc.) live in
    # chargen_notes JSON alongside village_first_audience_done; that
    # pattern works for the engine consumers (tutorial_chains.py
    # reads them out of a dict, not a column).
    #
    # Both columns are additive. No existing column or table
    # semantics change.
    25: [
        "ALTER TABLE characters ADD COLUMN village_choice_completed INTEGER DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN village_chosen_path TEXT DEFAULT ''",
    ],

    # ── v26 (May 4 2026): Village quest — village_standing attribute ────────
    #
    # Per ``jedi_village_quest_design_v1.md`` §6.2: a per-character
    # integer attribute that increments on positive Village quest
    # outcomes. Local to the Village; not a faction code.
    #
    # Deltas come from ``data/worlds/clone_wars/quests/jedi_village.yaml``
    # (the existing world-data field ``village_standing_delta``):
    #
    #   gate pass (Sister Vitha test) ........... +1
    #   First Audience (Master Yarael) .......... +1
    #   Trial of Skill (Forge / Daro) ........... +1
    #   Trial of Courage (Mira) ................. +2
    #   Trial of Flesh (Korvas) ................. +2
    #   Trial of Spirit (Yarael, Sanctum) ....... +3
    #   Trial of Insight (Saro, Council Hut) .... +2
    #
    # Total possible: 12. Path C lock-in completes the Spirit trial
    # per design §7.3, so it also grants +3 — the Village's *welcome*
    # diverges at Step 10 (the Path commit) but the trial-completion
    # standing is earned regardless of dark/light alignment during
    # the trial.
    #
    # Forward-additive: future drops may grant standing for non-trial
    # actions (helping NPCs, returning artifacts, etc.). The column
    # is unbounded but in practice will sit in the 0–20 range for the
    # foreseeable future.
    26: [
        "ALTER TABLE characters ADD COLUMN village_standing INTEGER DEFAULT 0",
    ],

    # ── v27 (May 18 2026): +pvp opt-in flag ─────────────────────────────────
    # Per the userMemory note "+pvp on/off opt-in flag (WoW-Outland-style)".
    # Per-character standing flag (vs the per-pair _pvp_active dict used by
    # challenge/accept). When set, the character is open to PvP without
    # going through challenge/accept in CONTESTED zones. SECURED zones
    # remain absolute (the flag does NOT override SECURED — design call
    # recorded in HANDOFF_MAY18_ROLLUP §"Future improvements").
    #
    # The flag is stored as INTEGER 0/1 (SQLite has no native BOOL). The
    # gate logic in parser/combat_commands.py::_check_pvp_consent reads
    # this column via char.get("pvp_flagged"). Default 0 means existing
    # characters keep their pre-drop behavior (must use challenge/accept).
    27: [
        "ALTER TABLE characters ADD COLUMN pvp_flagged INTEGER DEFAULT 0",
    ],

    # ── v28 (May 19 2026): Padawan-Master bond table (P-M.1) ───────────────
    # Per padawan_master_system_design_v1.md §4.3. Foundation layer for
    # the Padawan-Master relationship system. Commands, training events,
    # Trials, and the rest of the system layer on top of this table in
    # P-M.2 and beyond.
    #
    # The fresh-DB path applies this via the CREATE TABLE in SCHEMA_SQL.
    # The migration path (existing DBs at v27) applies the same CREATE
    # TABLE here. Both paths are idempotent (CREATE TABLE IF NOT EXISTS).
    28: [
        """CREATE TABLE IF NOT EXISTS master_padawan_bond (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            master_char_id        INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            padawan_char_id       INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            bond_established_at   TEXT NOT NULL DEFAULT (datetime('now')),
            bond_status           TEXT NOT NULL DEFAULT 'active'
                CHECK(bond_status IN ('active', 'dissolved', 'knighted', 'fallen')),
            dissolved_at          TEXT,
            dissolved_reason      TEXT,
            knight_promotion_at   TEXT,
            trials_passed_json    TEXT DEFAULT '[]'
        )""",
        """CREATE INDEX IF NOT EXISTS idx_bond_master
            ON master_padawan_bond(master_char_id, bond_status)""",
        """CREATE INDEX IF NOT EXISTS idx_bond_padawan
            ON master_padawan_bond(padawan_char_id, bond_status)""",
    ],

    # ── v29 (May 20 2026): Padawan-Master command layer (P-M.2) ────────────
    # Per padawan_master_system_design_v1.md §4.3, design call §8.12 #3:
    # the launch Master-cap of 1 is held in a per-character DB column so
    # staff/Council can raise an individual Master's cap (e.g. for a
    # senior teacher) without a code/config push. The DB-API layer
    # (P-M.1) remains permissive on the Master side; the command layer
    # (P-M.2) consults this column to gate +bond.
    #
    # Default 1 matches the launch design. Existing characters get 1
    # via the DEFAULT clause on ALTER. Staff can edit the column for
    # specific Masters as needed.
    29: [
        "ALTER TABLE characters ADD COLUMN master_cap INTEGER DEFAULT 1",
    ],

    # ── v30 (May 20 2026): PG.2.bounty session 1 — contributors sidecar ─
    # Per progression_gates_and_consequences_design_v1.md §4.2 +
    # the May 20 PG.2 design call: when a bounty is stacked (a
    # second poster contributes credits to an existing bounty on
    # the same target), we need to track each contributor's gross
    # stake + posting fee separately. This lets the cancel path
    # (§4.3) refund each contributor proportionally on primary
    # cancel.
    #
    # Shape: JSON list of {"poster_id": int, "amount": int,
    # "fee": int, "added_at": float} dicts. The "primary"
    # contributor is the first entry (matches pc_bounties.poster_id);
    # subsequent entries are stack-add contributions.
    #
    # Existing rows get the default '[]' empty list. Migration is
    # idempotent (`pc_bounties` already exists from v18).
    30: [
        "ALTER TABLE pc_bounties ADD COLUMN contributors_json TEXT "
        "DEFAULT '[]'",
    ],

    # ── v31 (May 22 2026): SECMOD.1 — room-level faction override ─────────
    # Per security_zones_design_v1.md §3.2 + §4.1: rooms inside a
    # SECURED zone can carry a faction restriction. A non-aligned PC
    # walking into an Imperial Garrison interior is trespassing, even
    # though the surrounding zone is secured. The room stamps
    # `faction_override = "<faction_code>"`; when an outsider with
    # Hostile/Unfriendly standing toward that faction enters, the
    # `engine.security.get_effective_security` resolver downgrades
    # the effective security tier (SECURED → LAWLESS for outsiders).
    #
    # NULL on every existing row = inherit zone security (no override).
    # Builder-set via the `@security override <room> = <faction>`
    # admin command (SECMOD.1 ships the command + the resolver branch).
    #
    # Schema only — no data backfill. Existing rooms keep NULL and
    # behave exactly as before. The override is opt-in per room.
    31: [
        "ALTER TABLE rooms ADD COLUMN faction_override TEXT DEFAULT NULL",
    ],

    # ── SRB.2 (Support Role Buffs session 2, May 22 2026) ─────────────
    #
    # Entertainer morale aura per support_role_buffs_design_v1.md §2.
    #
    # `morale_auras`: per-room aura row. One row per room max
    # (room_id is PRIMARY KEY). Lookup is cheap — a single PK
    # SELECT on every morale-flavored skill check.
    #
    # Performance fatigue columns on characters: track repeated
    # performances per real-day so a single entertainer can't camp
    # a cantina indefinitely. -1D penalty after the first perform;
    # resets after 8 hours of no performance.
    32: [
        """CREATE TABLE IF NOT EXISTS morale_auras (
            room_id         INTEGER PRIMARY KEY,
            performer_id    INTEGER NOT NULL,
            magnitude       INTEGER NOT NULL,
            started_at      REAL    NOT NULL,
            expires_at      REAL    NOT NULL
        )""",
        "ALTER TABLE characters ADD COLUMN perform_fatigue_resets_at REAL DEFAULT 0",
        "ALTER TABLE characters ADD COLUMN perform_fatigue_count INTEGER DEFAULT 0",
    ],

    # ── PG2.PL (May 22 2026) ──────────────────────────────────────────
    #
    # Relax the mail.sender_id FK so that engine-layer code can send
    # system mail (stipend interceptor, BH bounty payout notification,
    # stale-claim warning). Original schema had:
    #   sender_id INTEGER NOT NULL REFERENCES characters(id)
    # Per engine/mail_utils.py, system mail uses sender_id=0 with the
    # subject line carrying source attribution ("From BH Guild —
    # bounty fulfilled"). SQLite doesn't support ALTER TABLE DROP
    # CONSTRAINT, so we rebuild the table: create a new table without
    # the FK, copy data, drop the old, rename.
    33: [
        """CREATE TABLE IF NOT EXISTS mail_v33 (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id       INTEGER NOT NULL,
            subject         TEXT NOT NULL,
            body            TEXT NOT NULL,
            sent_at         TEXT NOT NULL
        )""",
        "INSERT INTO mail_v33 (id, sender_id, subject, body, sent_at) "
        "SELECT id, sender_id, subject, body, sent_at FROM mail",
        "DROP TABLE mail",
        "ALTER TABLE mail_v33 RENAME TO mail",
        "CREATE INDEX IF NOT EXISTS idx_mail_sender_id ON mail(sender_id)",
    ],

    # ── P-M.3 (Padawan-Master training events, May 22 2026) ───────────
    #
    # `training_log` — append-only record of Master-Padawan training
    # events per padawan_master_system_design_v1.md §5.2. Two event
    # types stored: 'teach' (Master taught Padawan a Force power) and
    # 'spar' (training duel between bonded pair).
    #
    # Used by:
    #   - The Knight ceremony (§6.4) to verify the Master has actually
    #     trained the Padawan, not just nominally bonded.
    #   - Spar cooldown enforcement (§5.2: 1 CP-granting spar per
    #     in-game day per pair).
    #   - Master Approval Weight (§5.3) for audit purposes.
    #
    # Append-only: no UPDATE/DELETE in normal flow. Indexed on
    # (bond_id, event_type, created_at) for the cooldown query.
    34: [
        """CREATE TABLE IF NOT EXISTS training_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bond_id         INTEGER NOT NULL,
            master_id       INTEGER NOT NULL,
            padawan_id      INTEGER NOT NULL,
            event_type      TEXT    NOT NULL,
            payload_json    TEXT    NOT NULL DEFAULT '{}',
            created_at      REAL    NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_training_log_bond "
        "ON training_log(bond_id, event_type, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_training_log_padawan "
        "ON training_log(padawan_id, created_at)",
    ],

    # ── Weight of War substrate (May 23 2026) ─────────────────────────
    #
    # Per weight_of_war_design_v1.md §8 (database schema). This is
    # Drop 1 of the Weight of War rollout — substrate only. No
    # combat hooks, no tick handler, no commands. Subsequent drops
    # (Drop 2 = commands + look self; Drop 3 = combat hooks +
    # tick handler + DSP/FP modifiers) wire consumers against
    # the helpers in `engine/weight_of_war.py`.
    #
    # Columns on `characters`:
    #   - weight_of_war            INTEGER, default 0, range [0, 200].
    #     The cumulative war-strain metric per design §4–§5.
    #   - weight_last_decay_at     REAL, NULL until first decay event.
    #     Wall-clock timestamp; used by the future tick handler to
    #     compute elapsed in-game days for passive decay (§5.1).
    #   - weight_last_accrual_at   REAL, NULL until first accrual.
    #     Wall-clock timestamp; used to enforce the weekly accrual
    #     cap (§4.4) without re-scanning the event log.
    #
    # `weight_of_war_events` table — append-only event log:
    #   - char_id        FK to characters.char_id.
    #   - event_at       REAL wall-clock when the event was logged.
    #   - delta          signed int; positive = accrual, negative =
    #                    decay.
    #   - trigger_type   short text key (e.g. 'mission_clone_loss',
    #                    'meditate', 'temple_passive', 'admin_adjust').
    #   - description    optional human-readable context for staff
    #                    audit and the future `+history weight`
    #                    command (§10 post-launch).
    #
    # Indexed on (char_id, event_at DESC) per design §8 — the
    # primary query is "show me this character's recent events
    # for Director AI prompt context."
    #
    # Migration is additive. Default weight_of_war = 0 for all
    # existing characters (per design §8: "grandfather in beta
    # activity").
    35: [
        "ALTER TABLE characters "
        "ADD COLUMN weight_of_war INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE characters "
        "ADD COLUMN weight_last_decay_at REAL",
        "ALTER TABLE characters "
        "ADD COLUMN weight_last_accrual_at REAL",
        """CREATE TABLE IF NOT EXISTS weight_of_war_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id         INTEGER NOT NULL,
            event_at        REAL    NOT NULL,
            delta           INTEGER NOT NULL,
            trigger_type    TEXT    NOT NULL,
            description     TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_wow_char "
        "ON weight_of_war_events(char_id, event_at DESC)",
    ],

    36: [
        # Drop 1.c: persistent economy config (key/value). First key is
        # 'faucet_throttle_pct' (0-100), the @economy throttle lever — a
        # global multiplier applied to player credit faucets inside
        # adjust_credits so an admin can dampen inflation without a code
        # change. Persisted so the lever survives a restart.
        """CREATE TABLE IF NOT EXISTS economy_config (
            key         TEXT PRIMARY KEY,
            value       REAL NOT NULL,
            updated_at  REAL NOT NULL
        )""",
    ],

    37: [
        # Drop 2: anti-grief PvP-death ledger. Tracks recent PvP kills so
        # repeated kills of the same victim by the same killer diminish the
        # corpse loot the killer can take, and so a freshly-killed victim
        # gets a short respawn-grace window the combat layer honors. Rows
        # are short-lived (only the last GRIEF_WINDOW_SECONDS matter); a
        # periodic prune or a decay job can trim old rows, but staleness is
        # harmless because lookbacks are time-bounded.
        """CREATE TABLE IF NOT EXISTS recent_pvp_deaths (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            victim_id   INTEGER NOT NULL,
            killer_id   INTEGER NOT NULL,
            died_at     REAL NOT NULL,
            grace_until REAL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rpd_pair "
        "ON recent_pvp_deaths(victim_id, killer_id, died_at)",
        "CREATE INDEX IF NOT EXISTS idx_rpd_victim "
        "ON recent_pvp_deaths(victim_id, died_at)",
    ],

    38: [
        # Economy audit v2 §1.5: persist the trade supply/demand pools so a
        # server restart no longer re-seeds every market to full (a windfall
        # for the first trader after a bounce) or clears demand depression (a
        # windfall for the first seller). One KV row per pool, JSON-encoded;
        # updated_at lets `@economy zones` show which markets ran hot recently.
        """CREATE TABLE IF NOT EXISTS market_state (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  REAL DEFAULT 0
        )""",
    ],

    39: [
        # Drop 3 B4: gear-insurance flag. A one-shot policyholder flag set by
        # `+insure buy` (after debiting the flat premium through the ledger as
        # `gear_insurance_premium`, a sink) and consumed on the holder's next
        # lawless/contested death - engine/death.py then keeps their loose
        # loadout on them instead of dropping it to a lootable corpse. There is
        # no credit payout (a payout would be a suicide-faucet, since this death
        # model sends gear to a re-lootable corpse rather than destroying it);
        # the premium is the only credit movement. Additive; default 0
        # (uninsured) for all existing characters.
        "ALTER TABLE characters "
        "ADD COLUMN gear_insured INTEGER NOT NULL DEFAULT 0",
    ],

    40: [
        # Drop 3 A5: sabacc dens. A Hutt-cartel org "operates" a den in a
        # cantina room (established via `+den establish` by a sufficiently-ranked
        # member, who pays a setup-cost sink). While a room is a den, the sabacc
        # house rake (after the city's slice) routes to that org's treasury as a
        # TRANSFER: the winning player is debited the full rake on the ledger as
        # `sabacc_rake`, so the org's receipt is NOT net-new credit creation.
        # One den per room.
        "CREATE TABLE IF NOT EXISTS sabacc_dens ("
        " room_id INTEGER PRIMARY KEY,"
        " org_id INTEGER NOT NULL,"
        " org_code TEXT NOT NULL,"
        " established_by INTEGER,"
        " established_at REAL NOT NULL DEFAULT 0)",
    ],

    41: [
        # Drop 4b (hunter.1): the roaming Dark-Side bounty hunter. Once a
        # character's dark_side_points cross the wanted threshold (DSP 4 — the
        # same band the BH board flags), a named non-canon hunter picks up the
        # trail and closes in over time. This table is the ONLY persistent state
        # for that pursuit; the "wanted" status itself stays derived from
        # dark_side_points (no bounty rows, no credits — prestige-domain, exactly
        # like the existing DSP-notoriety surface). One pursuit per character;
        # cleared when the character atones (drops back under the threshold).
        # See engine/dsp_hunter.py + server/tick_handlers_progression.py.
        "CREATE TABLE IF NOT EXISTS dsp_hunter_pursuit ("
        " char_id INTEGER PRIMARY KEY,"
        " hunter_name TEXT NOT NULL,"
        " progress INTEGER NOT NULL DEFAULT 0,"
        " stage TEXT NOT NULL DEFAULT 'tracking',"
        " last_notified_stage TEXT DEFAULT '',"
        " updated_at REAL NOT NULL DEFAULT 0)",
    ],

    # hunter.2 (2026-06-05): the live-spawn climax records which NPC was spawned
    # for a quarry so it can be reconciled/despawned (atonement, escape) without
    # scanning every room. NULL = no live hunter currently spawned.
    42: [
        "ALTER TABLE dsp_hunter_pursuit ADD COLUMN spawned_npc_id INTEGER DEFAULT NULL",
    ],

    # Drop 4b (the communal-rally villain): the dark-side cult communal objective
    # (design III.3). One row per uprising the Director posts; the active one is
    # the latest row with state='active'. `menace` (0..100) RISES over time and
    # players push it DOWN via `rally strike`; routed at <=0 (won), ascendant/
    # deadline-passed = lost. `contributions_json` is {char_id: {points,
    # last_strike_at}} so per-contributor reward shares + the per-character strike
    # cooldown need no extra table. Prestige-domain: rewards are Republic rep +
    # a III.2 status flag, never credits.
    43: [
        "CREATE TABLE IF NOT EXISTS communal_objective ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " cult_key TEXT NOT NULL,"
        " zone_key TEXT NOT NULL DEFAULT '',"
        " zone_label TEXT NOT NULL DEFAULT '',"
        " menace REAL NOT NULL DEFAULT 0,"
        " state TEXT NOT NULL DEFAULT 'active',"
        " contributions_json TEXT NOT NULL DEFAULT '{}',"
        " rotation INTEGER NOT NULL DEFAULT 0,"
        " started_at REAL NOT NULL DEFAULT 0,"
        " deadline_at REAL NOT NULL DEFAULT 0,"
        " advanced_at REAL NOT NULL DEFAULT 0,"
        " resolved_at REAL NOT NULL DEFAULT 0)",
        "CREATE INDEX IF NOT EXISTS idx_communal_objective_state "
        "ON communal_objective(state)",
    ],

    # T3.22 Phase 0 — ambient NPC life scaffolding (INERT pre-launch; read by
    # nothing until the post-launch sim ships). Mirrors the SCHEMA_SQL block;
    # CREATE TABLE IF NOT EXISTS so a fresh DB (already created by SCHEMA_SQL)
    # and an upgrading DB both land idempotently. Lowest-risk migration class:
    # NEW empty tables, no ALTER on a hot table. See
    # docs/design/ambient_npc_life_design_v1.md §5.2.
    44: [
        "CREATE TABLE IF NOT EXISTS npc_ambient_state ("
        " npc_id INTEGER PRIMARY KEY REFERENCES npcs(id),"
        " current_goal TEXT DEFAULT '',"
        " current_room_id INTEGER REFERENCES rooms(id),"
        " dest_room_id INTEGER REFERENCES rooms(id),"
        " move_started_at REAL,"
        " move_duration REAL,"
        " last_tick_at REAL,"
        " activity TEXT DEFAULT '',"
        " extra TEXT DEFAULT '{}')",
        "CREATE INDEX IF NOT EXISTS idx_npc_ambient_room "
        "ON npc_ambient_state(current_room_id)",
        "CREATE TABLE IF NOT EXISTS npc_ambient_relationship ("
        " npc_id_a INTEGER NOT NULL REFERENCES npcs(id),"
        " npc_id_b INTEGER NOT NULL REFERENCES npcs(id),"
        " affinity INTEGER DEFAULT 0,"
        " extra TEXT DEFAULT '{}',"
        " PRIMARY KEY (npc_id_a, npc_id_b))",
    ],

    # ── v45 (T3.21 Blocker 3): admin/builder command audit trail ────────────
    # A durable, append-only record of who exercised elevated authority and
    # when — written at the parser dispatch seam for every BUILDER/ADMIN
    # command that passes the (now DB-revalidated) access gate. Secret-bearing
    # arguments (@newpassword etc.) are redacted before the row is written.
    45: [
        "CREATE TABLE IF NOT EXISTS admin_audit ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " account_id INTEGER,"
        " username TEXT,"
        " char_id INTEGER,"
        " char_name TEXT,"
        " access_level INTEGER NOT NULL,"
        " command TEXT NOT NULL,"
        " detail TEXT,"
        " created_at TEXT DEFAULT (datetime('now')))",
        "CREATE INDEX IF NOT EXISTS idx_admin_audit_account "
        "ON admin_audit(account_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_audit_created "
        "ON admin_audit(created_at)",
    ],

    # ── v46 (T3.21 opt): index the account -> characters lookup ──────────────
    # get_characters(account_id) (login + character selection hot path) and the
    # accounts<->characters JOINs (parser/building_tier2, parser/mux_commands)
    # filtered characters by account_id with no supporting index -> full table
    # scan that grows with every character in the game. Composite
    # (account_id, is_active) fully covers the WHERE account_id=? AND
    # is_active=1 query and serves the account_id-prefix JOINs. Pure
    # performance; no behavior change.
    46: [
        "CREATE INDEX IF NOT EXISTS idx_characters_account "
        "ON characters(account_id, is_active)",
    ],

}


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        # Drop 1.c: cached @economy throttle (percent, 0-100; 100 = no-op).
        # Lazily loaded from economy_config on first adjust_credits faucet,
        # refreshed in-process by set_faucet_throttle_pct. None = not yet
        # loaded.
        self._faucet_throttle_pct: Optional[int] = None
        # T3.21: lazy read-only connection pool for SELECT-heavy read endpoints.
        # WAL lets these read a consistent snapshot CONCURRENTLY while the single
        # writer connection (self._db) handles writes — relieving the
        # serialize-everything-through-one-connection scale ceiling (the dominant
        # perf item in the T3.21 audit). Each pool connection is opened mode=ro
        # + PRAGMA query_only=ON, so it is PHYSICALLY incapable of writing — no
        # corruption risk from this path. Built lazily on first read; pool size
        # via SWMUSH_DB_READ_POOL (default 4), read at build time so it is
        # boot-order-safe (load_tunables runs after connect()).
        self._read_pool: Optional[asyncio.Queue] = None
        self._read_conns: list = []
        self._read_pool_lock = asyncio.Lock()
        self._closed = False

    async def connect(self):
        """Open the database and enable WAL mode."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        self._closed = False  # (re)opened — allow the read pool to (re)build
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        # Review fix: prevent SQLITE_BUSY under write contention from the
        # 1 Hz tick loop racing interactive command writes.
        await self._db.execute("PRAGMA busy_timeout=5000")
        # v22 audit S13: synchronous=NORMAL is the recommended setting for WAL.
        # Near-FULL durability (only crash-during-checkpoint can lose data).
        # 2–10× write throughput improvement over default FULL.
        await self._db.execute("PRAGMA synchronous=NORMAL")
        log.info("Database connected: %s (WAL mode, busy_timeout=5000ms, synchronous=NORMAL)", self.db_path)

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

        # Warm up scene active-room cache
        try:
            from engine.scenes import warm_cache as _scene_warm
            await _scene_warm(self)
        except Exception as _e:
            log.warning("Scene cache warm-up failed: %s", _e)

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
        # Flag closed FIRST so an in-flight _reader/_ensure_read_pool doesn't
        # rebuild or hand out a connection we're about to tear down.
        self._closed = True
        if self._db:
            await self._db.close()
            self._db = None  # idempotent: a second close() is a no-op
            log.info("Database closed.")
        # Tear down the read-only pool, if it was ever built.
        for c in self._read_conns:
            try:
                await c.close()
            except Exception:
                log.warning("read-pool connection close failed", exc_info=True)
        self._read_conns = []
        self._read_pool = None

    # -- Read-only connection pool (T3.21) --
    # SELECT-heavy read endpoints (web portal directory / profiles / scenes)
    # call read_fetchall / read_fetchone, drawing a read-only connection from a
    # small pool instead of serializing behind the single writer connection.
    # The pool connections are opened mode=ro + query_only=ON: they cannot
    # write, so they can never corrupt the DB; WAL gives them consistent-snapshot
    # concurrent reads.

    async def _ensure_read_pool(self) -> None:
        if self._read_pool is not None:
            return
        async with self._read_pool_lock:
            if self._read_pool is not None:  # built while we awaited the lock
                return
            if self._closed:
                raise RuntimeError("Database is closed; cannot build read pool")
            size = max(1, int(os.environ.get("SWMUSH_DB_READ_POOL", "4")))
            pool: asyncio.Queue = asyncio.Queue()
            conns: list = []
            uri = f"file:{Path(self.db_path).as_posix()}?mode=ro"
            try:
                for _ in range(size):
                    conn = await aiosqlite.connect(uri, uri=True)
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA query_only=ON")
                    await conn.execute("PRAGMA busy_timeout=5000")
                    conns.append(conn)
                    pool.put_nowait(conn)
            except Exception:
                # Partial build (e.g. fd exhaustion mid-loop): close what we
                # opened so nothing leaks, then re-raise (a later call retries).
                for c in conns:
                    try:
                        await c.close()
                    except Exception:
                        pass
                raise
            self._read_conns = conns
            self._read_pool = pool
            log.info("DB read pool ready: %d read-only connection(s)", size)

    @contextlib.asynccontextmanager
    async def _reader(self):
        """Hold a read-only pool connection for the block, then return it.

        In-memory databases are per-connection (a 2nd connection is a DIFFERENT
        empty DB), so for ``:memory:`` we fall back to the writer connection —
        correctness over concurrency, which matters only for the file-backed
        production DB anyway.
        """
        if ":memory:" in self.db_path:
            yield self._db
            return
        await self._ensure_read_pool()
        pool = self._read_pool
        if pool is None:  # closed between _ensure and here (shutdown race)
            raise RuntimeError("Database is closed")
        conn = await pool.get()
        try:
            yield conn
        finally:
            # Only return the connection if the pool is still the live one —
            # if close() swapped/nulled it mid-read, drop the (now-closed) conn.
            if self._read_pool is pool:
                pool.put_nowait(conn)

    async def read_fetchall(self, sql: str, params: tuple = ()) -> list:
        """Like fetchall(), but served by the read-only pool (SELECT-heavy read
        endpoints). Reads a consistent WAL snapshot; physically cannot write."""
        async with self._reader() as conn:
            return await conn.execute_fetchall(sql, params)

    async def read_fetchone(self, sql: str, params: tuple = ()):
        """Like fetchone(), but served by the read-only pool."""
        rows = await self.read_fetchall(sql, params)
        return rows[0] if rows else None

    # -- Query Proxy Methods --
    # These proxy methods provide a stable public API for raw SQL queries.
    # External callers should use these instead of reaching through to
    # self._db (the raw aiosqlite Connection). This enables future
    # backend swaps, auto-commit options, and transaction management
    # without touching every call site.

    async def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute SQL and return all rows as a list of Row objects."""
        return await self._db.execute_fetchall(sql, params)

    async def fetchone(self, sql: str, params: tuple = ()):
        """Execute SQL and return the first row, or None if no results."""
        rows = await self._db.execute_fetchall(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple = ()):
        """Execute a write statement (INSERT/UPDATE/DELETE).

        Does NOT auto-commit. Call db.commit() after your last write in a
        logical batch. For single-write convenience, use execute_commit().
        """
        return await self._db.execute(sql, params)

    async def execute_commit(self, sql: str, params: tuple = ()):
        """Execute a write statement and immediately commit.

        Convenience method for single-statement writes. For multi-statement
        batches, use execute() + commit() separately.
        """
        result = await self._db.execute(sql, params)
        await self._db.commit()
        return result

    async def commit(self):
        """Commit the current transaction."""
        await self._db.commit()

    async def executescript(self, sql: str):
        """Execute a multi-statement SQL script."""
        await self._db.executescript(sql)

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

        # Verify password. Guard bcrypt.checkpw, which RAISES (ValueError
        # "Invalid salt" / TypeError) on a stored hash that isn't a valid
        # bcrypt string — e.g. a legacy SHA-256 hex digest written by the
        # pre-fix @newpassword bug. Fail CLOSED (treat as a bad password)
        # instead of letting the exception escape the login path.
        try:
            _password_ok = bcrypt.checkpw(
                password.encode("utf-8"),
                account["password_hash"].encode("utf-8"),
            )
        except (ValueError, TypeError):
            _password_ok = False
        if _password_ok:
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

    async def get_account_privileges(self, account_id: int) -> tuple[bool, bool]:
        """Return live ``(is_admin, is_builder)`` for an account.

        Returns ``(False, False)`` if the account no longer exists. Used by
        the parser to re-validate elevated access on each BUILDER/ADMIN
        command dispatch rather than trusting the cached login snapshot, so a
        revoked privilege takes effect immediately (T3.21 Blocker 3).
        """
        rows = await self._db.execute_fetchall(
            "SELECT is_admin, is_builder FROM accounts WHERE id = ?",
            (account_id,),
        )
        if not rows:
            return (False, False)
        row = rows[0]
        return (bool(row["is_admin"]), bool(row["is_builder"]))

    async def record_admin_action(
        self,
        *,
        account_id: Optional[int],
        username: Optional[str],
        char_id: Optional[int],
        char_name: Optional[str],
        access_level: int,
        command: str,
        detail: Optional[str],
    ) -> None:
        """Append a row to the admin_audit trail (T3.21 Blocker 3).

        Best-effort: callers wrap this in try/except so an audit-write failure
        never blocks the privileged command. ``detail`` MUST be pre-redacted
        by the caller — secret-bearing args (e.g. @newpassword) are not
        sanitized here.
        """
        await self._db.execute(
            "INSERT INTO admin_audit "
            "(account_id, username, char_id, char_name, access_level, command, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, username, char_id, char_name, access_level, command, detail),
        )
        await self._db.commit()

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

    async def get_character_by_name(self, name: str) -> Optional[dict]:
        """Get a single active character by name (case-insensitive)."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE name = ? AND is_active = 1",
            (name,)
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
                dark_side_points, room_id, description, chargen_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                fields.get("chargen_notes", ""),
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
        "description", "is_active", "faction_id", "bounty",
        "chargen_notes",
        # ── PG.1.schema columns (v18 migration) ──────────────────────────
        # Per F.7.a (May 3 2026): these columns landed in schema v18
        # but were never added to the writable set. The Village quest
        # engine and the playtime heartbeat need to write to them.
        # Adding them here is the missing wiring, not a new feature.
        "play_time_seconds",
        "force_predisposition",
        "force_signs_accumulated",
        "village_act",
        "village_act_unlocked_at",
        "village_trial_courage_done",
        "village_trial_insight_done",
        "village_trial_flesh_done",
        "village_trial_last_attempt",
        "wound_state",
        "wound_clear_at",
        # ── Wilderness Drop 2 columns (v20 migration) ────────────────────
        # Per wilderness_system_design_v1.md §3.2: per-character
        # wilderness coordinate state. NULL when in a normal room;
        # set to (slug, x, y) when in a wilderness region.
        "wilderness_region_slug",
        "wilderness_x",
        "wilderness_y",
        # ── Village quest Step 3 gate state (v21 migration) ──────────────
        # Per F.7.b (May 4 2026): Sister Vitha's gate dialogue records
        # outcome here. Idempotent on retry; lockout_until is a
        # wall-clock timestamp.
        "village_gate_passed",
        "village_gate_lockout_until",
        "village_gate_attempts",
        # ── Village quest Trials runtime state (v22 migration) ───────────
        # Per F.7.c.1 (May 4 2026): Trial 1 (Skill) + Trial 5 (Insight)
        # runtime columns + reserved columns for Trials 2-4 (F.7.c.2/3).
        "village_trial_skill_done",
        "village_trial_skill_step",
        "village_trial_skill_attempts",
        "village_trial_skill_last_at",
        "village_trial_skill_crystal_granted",
        "village_trial_courage_done",
        "village_trial_courage_lockout_until",
        "village_trial_flesh_done",
        "village_trial_flesh_started_at",
        "village_trial_flesh_session_seconds",
        "village_trial_spirit_done",
        "village_trial_spirit_dark_pull",
        "village_trial_spirit_rejections",
        "village_trial_spirit_turn",
        "village_trial_spirit_path_c_locked",
        "village_choice_completed",
        "village_chosen_path",
        "village_standing",
        "village_trial_insight_done",
        "village_trial_insight_attempts",
        "village_trial_insight_correct_fragment",
        "village_trial_insight_pendant_granted",
        # ── v27 columns (May 18 2026): +pvp opt-in flag ──────────────────
        "pvp_flagged",
        # ── v29 columns (May 20 2026): P-M.2 Master-cap (per-char) ──────
        # Per design §8.12 #3: per-character cap on simultaneous active
        # Padawan bonds. Default 1 at launch; staff can raise. P-M.2's
        # +bond command consults this column before calling create_bond.
        "master_cap",
        # ── v35 columns (May 23 2026): Weight of War substrate ──────────
        # Per weight_of_war_design_v1.md §8. The metric itself plus two
        # bookkeeping timestamps. Range invariant [0, 200] is enforced
        # in engine/weight_of_war.py rather than at the DB layer, so
        # callers can save_character(char_id, weight_of_war=N) safely;
        # the engine's set_weight() helper clamps before writing.
        "weight_of_war",
        "weight_last_decay_at",
        "weight_last_accrual_at",
        # ── Drop 3 B3 (Jun 3 2026): vanity titles (cosmetic credit sink) ──
        # Added to characters via engine/titles.py's own idempotent
        # ensure_schema column-loop (NOT the main SCHEMA_MIGRATIONS dict, so
        # no SCHEMA_VERSION bump). purchase_title / set_worn_title write them
        # through this allowlisted proxy. vanity_titles is a JSON list of owned
        # title keys; display_title is the literal worn label.
        "vanity_titles",
        "display_title",
        # ── Drop 3 B4 (Jun 4 2026): gear-insurance flag (loadout protection) ──
        # Added to characters via main schema migration v39. purchase/cancel in
        # engine/gear_insurance.py write it through this allowlisted proxy;
        # engine/death.py consumes it (flips 1->0) on a lawless/contested death.
        "gear_insured",
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

    async def get_all_rooms(self) -> list:
        """Fetch all rooms (id and name only) for mission destination selection."""
        rows = await self._db.execute_fetchall(
            "SELECT id, name FROM rooms ORDER BY id"
        )
        return [dict(r) for r in rows]

    async def get_room_by_slug(self, slug: str) -> Optional[dict]:
        """Fetch a room by its ``properties.slug`` value.

        F.8.c.2.c (May 4 2026): primary consumer is the chain
        graduation teleport, which resolves
        ``graduation.drop_room`` (a slug) to a real room id. Also
        consumed by ``engine/village_choice.py`` (already using
        ``getattr`` fallback).

        Slugs are stamped onto rooms by ``engine/world_writer.py``
        per F.8.c.1 (Apr 30 2026). Pre-F.8.c.1 rooms need a DB
        rebuild migration; see migration ``v18_to_v19_backfill``
        in this file.

        SQLite's JSON1 ``json_extract`` is the right tool — it's
        an indexable, nullable extraction. The candidate row is
        small (always a single match if any) so we don't bother
        with a generated column index.
        """
        if not slug:
            return None
        clean = slug.strip()
        if not clean:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms "
            "WHERE json_extract(properties, '$.slug') = ? "
            "LIMIT 1",
            (clean,),
        )
        return dict(rows[0]) if rows else None

    async def set_room_map_coords(self, room_id: int,
                                   map_x: float, map_y: float):
        """Set hand-tuned map coordinates for a room."""
        await self._db.execute(
            "UPDATE rooms SET map_x = ?, map_y = ? WHERE id = ?",
            (map_x, map_y, room_id),
        )
        await self._db.commit()

    async def get_exits(self, room_id: int) -> list:
        """Get all exits from a room."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM exits WHERE from_room_id = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    async def get_characters_in_room(self, room_id: int, *, source_char=None) -> list:
        """Get all active characters in a room.

        Args:
            source_char: optional character dict. When set AND source is
                in wilderness, results are filtered to characters at
                the same wilderness tile. Path B (W.2 phase 2): every
                ground-interaction surface that calls this with
                source_char=char respects co-location automatically.
        """
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE room_id = ? AND is_active = 1",
            (room_id,),
        )
        chars = [dict(r) for r in rows]
        if source_char is None:
            return chars
        try:
            from engine.wilderness_movement import filter_by_source_location
            return filter_by_source_location(chars, source_char)
        except Exception:
            return chars

    async def get_characters_in_room_summary(self, room_id: int, *, source_char=None) -> list:
        """Get active characters in a room — lightweight (id, name, account_id only).

        Use this when you only need to know WHO is present, not their full
        stats/inventory/attributes. Avoids deserializing large JSON blobs.

        Args:
            source_char: optional. Same Path B semantics as get_characters_in_room.
                Note: if source_char is in wilderness we still need the
                wilderness coord columns, so the SELECT widens to include
                them when filtering.
        """
        if source_char is None:
            rows = await self._db.execute_fetchall(
                "SELECT id, name, account_id FROM characters "
                "WHERE room_id = ? AND is_active = 1",
                (room_id,),
            )
            return [dict(r) for r in rows]

        # Source-char-aware path: include wilderness coord columns so
        # the filter helper has what it needs.
        rows = await self._db.execute_fetchall(
            "SELECT id, name, account_id, room_id, "
            "wilderness_region_slug, wilderness_x, wilderness_y "
            "FROM characters WHERE room_id = ? AND is_active = 1",
            (room_id,),
        )
        chars = [dict(r) for r in rows]
        try:
            from engine.wilderness_movement import filter_by_source_location
            return filter_by_source_location(chars, source_char)
        except Exception:
            return chars

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
        "map_x", "map_y",
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

    async def get_all_zones(self) -> list[dict]:
        """Return all zones."""
        rows = await self._db.execute_fetchall("SELECT * FROM zones")
        return [dict(r) for r in rows]

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

    # ── SECMOD.1 (May 22 2026): zone & room admin mutations ────────────────
    # The `@security` admin command needs to:
    #   - Look up a zone by its name (so staff can type
    #     `@security tatooine_market = lawless` instead of an int id).
    #   - Mutate `zones.properties` JSON to set/update the
    #     `security` key (the resolver reads from properties).
    #   - Mutate `rooms.faction_override` column to set/clear the
    #     v31 room-level override.
    # These three methods are small, deliberate seams. Builder
    # tooling consumes them; nothing else mutates zone properties
    # at runtime (the loader writes properties only on initial
    # world-build).

    async def get_zone_by_name(self, name: str) -> Optional[dict]:
        """Fetch a zone by its exact `name` column value.

        SECMOD.1: the `@security <zone>` admin command takes a
        zone name (which matches the YAML zone slug, e.g.
        `tatooine_market`), not an integer id. This is the
        case-insensitive exact-match lookup.

        Returns the zone row dict or None if no match.
        """
        if not name:
            return None
        clean = name.strip()
        if not clean:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE LOWER(name) = LOWER(?) LIMIT 1",
            (clean,),
        )
        return dict(rows[0]) if rows else None

    async def set_zone_property(self, zone_id: int, key: str,
                                 value) -> bool:
        """Set a single key inside a zone's `properties` JSON blob.

        SECMOD.1: the `@security <zone> = <level>` admin command
        writes `properties.security = <level>` via this method.
        Generic enough to support future zone-property mutations
        without adding more single-purpose methods.

        - If `value` is None, the key is removed from properties.
        - If `properties` is currently NULL or malformed, it is
          rebuilt as an empty dict before write.
        - Returns True on success, False if the zone doesn't exist.

        The write is committed immediately. Effective security
        reads from properties on every check, so changes apply
        without a restart (per security_zones_design_v1.md §9).
        """
        import json as _json
        zone = await self.get_zone(zone_id)
        if not zone:
            return False
        props_raw = zone.get("properties") or "{}"
        if isinstance(props_raw, str):
            try:
                props = _json.loads(props_raw)
            except (ValueError, TypeError):
                props = {}
        elif isinstance(props_raw, dict):
            props = dict(props_raw)
        else:
            props = {}
        if value is None:
            props.pop(key, None)
        else:
            props[key] = value
        await self._db.execute(
            "UPDATE zones SET properties = ? WHERE id = ?",
            (_json.dumps(props), zone_id),
        )
        await self._db.commit()
        return True

    async def set_room_faction_override(self, room_id: int,
                                         faction: Optional[str]) -> bool:
        """Set or clear a room's faction_override (v31 column).

        SECMOD.1: backs the `@security override <room> = <faction>`
        and `@security override <room> = none` admin commands per
        security_zones_design_v1.md §3.2 + §9.

        - `faction=None` clears the override (SQL NULL).
        - `faction="empire"` (or any non-empty string) sets it.
        - Returns True on success, False if the room doesn't exist.

        The resolver reads this column on every effective-security
        check, so changes apply immediately without a restart.
        Note: this method does NOT validate that `faction` is a
        known faction code — that's the parser command's job.
        Stored value is taken verbatim (lowercased by the parser).
        """
        room = await self.get_room(room_id)
        if not room:
            return False
        await self._db.execute(
            "UPDATE rooms SET faction_override = ? WHERE id = ?",
            (faction, room_id),
        )
        await self._db.commit()
        return True

    # ── SRB.2 (May 22 2026) — Entertainer morale aura helpers ────────────
    #
    # Per support_role_buffs_design_v1.md §2.7:
    #   morale_auras: per-room aura row (room_id PK, performer_id,
    #                 magnitude in {1,2,3,5}, started_at, expires_at).
    #   characters.perform_fatigue_resets_at, perform_fatigue_count.
    #
    # The aura is read on every morale-flavored skill check via
    # engine.skill_checks.perform_morale_aware_check. It's set/refreshed
    # by parser/entertainer_commands.PerformCommand on a successful
    # `perform` roll. It's cleared when the performer leaves the room
    # (MoveCommand hook), expires by tick, or is overwritten by a
    # higher-magnitude performance from another entertainer.

    async def get_morale_aura(self, room_id: int) -> Optional[dict]:
        """Return the active morale_auras row for a room, or None.

        Caller is responsible for checking `expires_at` against the
        current time — this helper does NOT filter expired rows
        (the periodic tick handler reaps; the look-side renderer
        does the time check inline).
        """
        rows = await self._db.execute_fetchall(
            "SELECT * FROM morale_auras WHERE room_id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None

    async def set_morale_aura(self, *, room_id: int, performer_id: int,
                               magnitude: int, started_at: float,
                               expires_at: float) -> None:
        """Insert or replace the morale aura for a room.

        UPSERT semantics: room_id is PRIMARY KEY. A second performer
        in the same room overwrites the prior aura row outright.
        The "higher aura wins" rule per design §2.4 is enforced at
        the parser layer (it reads the existing aura first and skips
        the write if its magnitude would be smaller).
        """
        await self._db.execute(
            """INSERT OR REPLACE INTO morale_auras
               (room_id, performer_id, magnitude, started_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (room_id, performer_id, int(magnitude),
             float(started_at), float(expires_at)),
        )
        await self._db.commit()

    async def clear_morale_aura(self, room_id: int) -> bool:
        """Delete the morale aura for a room. Returns True if removed."""
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM morale_auras WHERE room_id = ?", (room_id,)
        )
        if not rows:
            return False
        await self._db.execute(
            "DELETE FROM morale_auras WHERE room_id = ?", (room_id,)
        )
        await self._db.commit()
        return True

    async def clear_morale_auras_for_performer(self, performer_id: int) -> int:
        """Delete all morale auras created by a given performer.

        Used by the MoveCommand hook: if a performer leaves any room
        where they're the active performer, that aura is cleared.
        (A performer can only be performing in one room at a time at
        the command layer, but this helper is robust to the multi-row
        case.) Returns count of rows removed.
        """
        rows = await self._db.execute_fetchall(
            "SELECT room_id FROM morale_auras WHERE performer_id = ?",
            (performer_id,),
        )
        if not rows:
            return 0
        await self._db.execute(
            "DELETE FROM morale_auras WHERE performer_id = ?",
            (performer_id,),
        )
        await self._db.commit()
        return len(rows)

    async def list_expired_morale_auras(self, now: float) -> list[dict]:
        """Return all aura rows with `expires_at <= now`. Used by tick."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM morale_auras WHERE expires_at <= ?", (float(now),)
        )
        return [dict(r) for r in rows]

    async def reap_expired_morale_auras(self, now: float) -> int:
        """Delete all expired aura rows. Returns count removed."""
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM morale_auras WHERE expires_at <= ?",
            (float(now),),
        )
        count = int(rows[0]["c"]) if rows else 0
        if count == 0:
            return 0
        await self._db.execute(
            "DELETE FROM morale_auras WHERE expires_at <= ?", (float(now),)
        )
        await self._db.commit()
        return count

    async def get_perform_fatigue(self, char_id: int) -> tuple[float, int]:
        """Return (resets_at, count) for a character's perform fatigue.

        Both columns default to 0 for unset rows. If the resets_at
        timestamp has passed, the caller should treat the count as
        zero — but the column isn't auto-zeroed on read. The
        PerformCommand resets both columns on the first perform
        after the window expires.
        """
        rows = await self._db.execute_fetchall(
            "SELECT perform_fatigue_resets_at, perform_fatigue_count "
            "FROM characters WHERE id = ?",
            (char_id,),
        )
        if not rows:
            return (0.0, 0)
        row = rows[0]
        return (
            float(row["perform_fatigue_resets_at"] or 0.0),
            int(row["perform_fatigue_count"] or 0),
        )

    async def set_perform_fatigue(self, *, char_id: int,
                                   resets_at: float, count: int) -> None:
        """Persist a character's perform fatigue state."""
        await self._db.execute(
            "UPDATE characters "
            "SET perform_fatigue_resets_at = ?, perform_fatigue_count = ? "
            "WHERE id = ?",
            (float(resets_at), int(count), char_id),
        )
        await self._db.commit()

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

    async def accept_mission(self, mission_id, character_id, expires_at, data: dict):
        """Mark a mission accepted by a character.

        Board mission ids are strings ("m-..."); the missions table PK is an
        INTEGER autoincrement, so the old ``WHERE id=?`` matched 0 rows and the
        accept was never persisted (mission silently lost on restart). Match by
        the string id stored in the JSON ``data`` column — save_mission's proven
        idiom — and upsert if the available mission was never written, so the
        row carries the correct ``accepted_by`` for get_active_mission().
        """
        import json as _json
        cur = await self._db.execute(
            "UPDATE missions SET status='accepted', accepted_by=?, expires_at=?, "
            "data=? WHERE data LIKE ?",
            (character_id, expires_at, _json.dumps(data),
             f'%"id": "{mission_id}"%'),
        )
        if cur.rowcount == 0:
            await self._db.execute(
                "INSERT INTO missions (mission_type, title, description, reward, "
                "skill_required, accepted_by, status, expires_at, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    data.get("mission_type"), data.get("title"),
                    data.get("objective", ""), data.get("reward"),
                    data.get("required_skill", ""), character_id,
                    "accepted", expires_at, _json.dumps(data),
                ),
            )
        await self._db.commit()

    async def complete_mission(self, mission_id, data: dict):
        """Mark a mission complete (match by the string id in the data column)."""
        import json as _json
        await self._db.execute(
            "UPDATE missions SET status='completed', data=? WHERE data LIKE ?",
            (_json.dumps(data), f'%"id": "{mission_id}"%'),
        )
        await self._db.commit()

    async def abandon_mission(self, mission_id, data: dict):
        """Return an accepted mission to available status (match by string id)."""
        import json as _json
        await self._db.execute(
            "UPDATE missions SET status='available', accepted_by=NULL, data=? "
            "WHERE data LIKE ?",
            (_json.dumps(data), f'%"id": "{mission_id}"%'),
        )
        await self._db.commit()

    async def save_mission(self, mission) -> None:
        """Upsert a Mission object into the DB (insert or replace by string id)."""
        import json as _json
        d = mission.to_dict()
        # missions table uses INTEGER PK autoincrement, but mission IDs are strings.
        # We store by matching on the JSON id field inside the data column,
        # OR use the string id as a lookup in the data column.
        # Simplest: try UPDATE first, INSERT if no rows affected.
        cur = await self._db.execute(
            "UPDATE missions SET status=?, accepted_by=?, expires_at=?, "
            "mission_type=?, title=?, reward=?, skill_required=?, data=? "
            "WHERE data LIKE ?",
            (
                d["status"], d["accepted_by"], d["expires_at"],
                d["mission_type"], d["title"], d["reward"],
                d.get("required_skill", ""),
                _json.dumps(d),
                f'%"id": "{mission.id}"%',
            ),
        )
        if cur.rowcount == 0:
            await self._db.execute(
                "INSERT INTO missions (mission_type, title, description, reward, "
                "skill_required, accepted_by, status, expires_at, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    d["mission_type"], d["title"], d.get("objective", ""),
                    d["reward"], d.get("required_skill", ""),
                    d["accepted_by"], d["status"], d["expires_at"],
                    _json.dumps(d),
                ),
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

    # -- Credit Log (Economy Hardening v23) --

    async def log_credit(self, char_id: int, delta: int, source: str,
                         balance: int) -> None:
        """Record a credit mutation. char_id=0 for system sinks."""
        try:
            await self._db.execute(
                "INSERT INTO credit_log (char_id, delta, source, balance, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (char_id, delta, source, balance, time.time()),
            )
            await self._db.commit()
        except Exception:
            # credit_log table may not exist yet (pre-v12 DB)
            log.debug("log_credit: table may not exist yet", exc_info=True)

    async def adjust_credits(self, char_id: int, delta: int, source: str,
                             *, allow_negative: bool = True) -> Optional[int]:
        """Single sanctioned chokepoint for moving credits.

        Atomically applies ``delta`` to a character's balance AND records
        the movement in ``credit_log``, returning the new balance. This is
        the only function that should mutate the ``characters.credits``
        column going forward: routing every faucet and sink through here is
        what makes the economy measurable (the ``@economy`` dashboard,
        velocity, and the whale/farming/inflation alerts all read
        ``credit_log``). Writing credits via ``save_character(credits=...)``
        bypasses the ledger and is the thing the economy audit (F1) flagged
        — those sites are being migrated to call this instead.

        Args:
            char_id: Character whose balance moves. Pass ``0`` for a
                *system* faucet/sink — credits entering or leaving the
                player economy with no player on the other side (a treasury
                sink, a tax). For ``char_id == 0`` no character row is
                touched; the movement is logged with ``balance=0`` and
                ``0`` is returned.
            delta: Signed amount. Positive = faucet (award); negative =
                sink (charge).
            source: Short, stable tag for the movement (e.g. ``"mission"``,
                ``"bounty"``, ``"trade_goods"``, ``"docking_fee"``). Used to
                group faucets/sinks in the dashboard — reuse an existing tag
                rather than inventing a near-duplicate.
            allow_negative: When ``False``, a sink that would overdraw the
                balance is refused: nothing is applied or logged and
                ``None`` is returned, so the caller can report "insufficient
                funds". Defaults ``True`` (behaviour-preserving for callers
                that pre-check affordability themselves).

        Returns:
            The new balance (``int``) after applying ``delta``, or ``None``
            if the movement was refused (``allow_negative=False`` and
            insufficient funds).

        Notes:
            - The balance change uses an atomic ``credits = credits + ?``
              SQL increment rather than a read-then-set, so concurrent
              movements on the same character cannot clobber each other —
              an improvement over the legacy ``save_character`` pattern.
            - Logging is best-effort: a ``credit_log`` failure is swallowed
              inside ``log_credit`` so a transient ledger problem never
              blocks a gameplay transaction; the balance change still
              commits.
        """
        # System faucet/sink — no character row to touch, ledger entry only.
        if char_id == 0:
            await self.log_credit(0, delta, source, 0)
            return 0

        # Affordability guard (opt-in). Best-effort read-check; the current
        # migration leaves this off (callers pre-check), so the small
        # read-then-write window here is not exercised by live call sites.
        # Drop 3 can tighten individual sink paths to use it.
        if delta < 0 and not allow_negative:
            rows = await self._db.execute_fetchall(
                "SELECT credits FROM characters WHERE id = ?", (char_id,)
            )
            if not rows:
                return None
            if int(rows[0]["credits"] or 0) + delta < 0:
                return None

        # Drop 1.c — faucet throttle. A player *faucet* (delta > 0,
        # char_id > 0) is scaled by the global @economy throttle so an
        # admin can dampen inflation without a code change. Sinks
        # (delta < 0) and system entries (char_id == 0, handled above) are
        # never throttled. Player-to-player transfers and refunds are NOT
        # faucets either — a transfer just moves existing credits (zero-sum)
        # and a refund reverses a prior charge — so they are excluded; only
        # genuine new-money faucets are cooled. At the default 100% this is
        # an exact integer no-op — (delta * 100) // 100 == delta — so it is
        # behaviourally invisible until an admin sets a non-default value.
        if delta > 0 and not any(
            tok in source for tok in ("p2p_transfer", "refund")
        ):
            pct = await self.get_faucet_throttle_pct()
            if pct != 100:
                delta = (delta * pct) // 100
                if delta == 0:
                    # Throttled to nothing: no balance change, but log the
                    # zero faucet so the suppression is visible on @economy.
                    await self.log_credit(char_id, 0, source, 0)
                    rows = await self._db.execute_fetchall(
                        "SELECT credits FROM characters WHERE id = ?",
                        (char_id,),
                    )
                    return int(rows[0]["credits"]) if rows else 0

        # Atomic balance change.
        await self._db.execute(
            "UPDATE characters SET credits = credits + ? WHERE id = ?",
            (delta, char_id),
        )
        await self._db.commit()

        # Read the authoritative post-update balance.
        rows = await self._db.execute_fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,)
        )
        new_balance = int(rows[0]["credits"]) if rows else 0

        # Ledger entry (best-effort — see Notes).
        await self.log_credit(char_id, delta, source, new_balance)
        return new_balance

    # -- Faucet throttle (@economy throttle, Drop 1.c) --

    async def get_faucet_throttle_pct(self) -> int:
        """Return the global player-faucet throttle as a percent (0-100).

        100 means faucets pay in full (the default and the behaviourally
        invisible no-op); 50 means every player award is halved; 0 means
        faucets are fully suppressed. Cached in-process after the first
        read so the adjust_credits hot path does not hit the DB per call.
        Fails open to 100 on any error (a throttle problem must never block
        a transaction or silently zero a faucet).
        """
        if self._faucet_throttle_pct is not None:
            return self._faucet_throttle_pct
        pct = 100
        try:
            rows = await self._db.execute_fetchall(
                "SELECT value FROM economy_config WHERE key = ?",
                ("faucet_throttle_pct",),
            )
            if rows:
                pct = int(rows[0]["value"])
        except Exception:
            # Table may not exist on a pre-v36 DB, or transient error.
            log.debug("get_faucet_throttle_pct: defaulting to 100",
                      exc_info=True)
            pct = 100
        pct = max(0, min(100, pct))
        self._faucet_throttle_pct = pct
        return pct

    async def set_faucet_throttle_pct(self, pct: int) -> int:
        """Persist the player-faucet throttle (clamped to 0-100) and refresh
        the in-process cache. Returns the clamped value actually stored."""
        pct = max(0, min(100, int(pct)))
        try:
            await self._db.execute(
                "INSERT INTO economy_config (key, value, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                ("faucet_throttle_pct", float(pct), time.time()),
            )
            await self._db.commit()
        except Exception:
            log.warning("set_faucet_throttle_pct: persist failed",
                        exc_info=True)
        self._faucet_throttle_pct = pct
        return pct

    async def get_market_state(self, key: str) -> str | None:
        """Return the stored JSON blob for a market-state key, or None.

        Backs the trade supply/demand pool persistence (economy audit v2 §1.5).
        Fails open to None on a pre-v38 DB or transient error.
        """
        try:
            rows = await self._db.execute_fetchall(
                "SELECT value FROM market_state WHERE key = ?", (key,),
            )
            if rows:
                return rows[0]["value"]
        except Exception:
            log.debug("get_market_state(%s): defaulting to None", key, exc_info=True)
        return None

    async def set_market_state(self, key: str, value: str) -> None:
        """Upsert a market-state JSON blob with a fresh updated_at."""
        try:
            await self._db.execute(
                "INSERT INTO market_state (key, value, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, time.time()),
            )
            await self._db.commit()
        except Exception:
            log.warning("set_market_state(%s): persist failed", key, exc_info=True)

    async def get_char_credit_breakdown(self, char_id: int,
                                        seconds: int = 86400) -> dict:
        """Per-character credit_log breakdown over the last ``seconds``.

        Powers the player-facing ``+finances`` command — the player's own
        faucet/sink totals grouped by source. Mirrors ``get_credit_velocity``
        but scoped to one character. Fails open to an empty summary on DB
        error so ``+finances`` never errors out.

        Returns: {
            'faucet_total': int, 'sink_total': int, 'net': int,
            'txn_count': int,
            'faucets': [(source, total), ...],   # descending by magnitude
            'sinks':   [(source, total), ...],   # descending by magnitude
        }
        """
        empty = {"faucet_total": 0, "sink_total": 0, "net": 0,
                 "txn_count": 0, "faucets": [], "sinks": []}
        try:
            cutoff = time.time() - seconds
            rows = await self._db.execute_fetchall(
                "SELECT source, "
                "SUM(CASE WHEN delta > 0 THEN delta ELSE 0 END) AS faucet, "
                "SUM(CASE WHEN delta < 0 THEN delta ELSE 0 END) AS sink, "
                "COUNT(*) AS cnt "
                "FROM credit_log "
                "WHERE char_id = ? AND created_at > ? "
                "GROUP BY source",
                (char_id, cutoff),
            )
        except Exception:
            log.debug("get_char_credit_breakdown: failing open", exc_info=True)
            return empty

        faucets, sinks = [], []
        faucet_total = sink_total = txn_count = 0
        for r in rows or []:
            src = r["source"]
            f = int(r["faucet"] or 0)
            s = int(r["sink"] or 0)
            txn_count += int(r["cnt"] or 0)
            if f:
                faucets.append((src, f))
                faucet_total += f
            if s:
                sinks.append((src, s))
                sink_total += s
        faucets.sort(key=lambda t: t[1], reverse=True)
        sinks.sort(key=lambda t: t[1])  # most-negative first
        return {
            "faucet_total": faucet_total,
            "sink_total": sink_total,
            "net": faucet_total + sink_total,
            "txn_count": txn_count,
            "faucets": faucets,
            "sinks": sinks,
        }

    async def get_credit_velocity(self, seconds: int = 86400) -> dict:
        """Return credit flow summary over the last `seconds`.

        Returns: {
            'faucet_total': int, 'sink_total': int, 'net': int,
            'txn_count': int,
            'top_faucets': [(source, total), ...],
            'top_sinks': [(source, total), ...],
            'top_earners': [(char_id, total), ...],
        }
        """
        cutoff = time.time() - seconds
        try:
            # Faucets (positive delta, excluding system char_id=0)
            faucet_rows = await self._db.execute_fetchall(
                "SELECT source, SUM(delta) as total, COUNT(*) as cnt "
                "FROM credit_log WHERE delta > 0 AND char_id > 0 "
                "AND created_at > ? GROUP BY source ORDER BY total DESC",
                (cutoff,),
            )
            # Sinks (negative delta, excluding system)
            sink_rows = await self._db.execute_fetchall(
                "SELECT source, SUM(delta) as total, COUNT(*) as cnt "
                "FROM credit_log WHERE delta < 0 AND char_id > 0 "
                "AND created_at > ? GROUP BY source ORDER BY total ASC",
                (cutoff,),
            )
            # Top earners
            earner_rows = await self._db.execute_fetchall(
                "SELECT char_id, SUM(delta) as total "
                "FROM credit_log WHERE char_id > 0 AND created_at > ? "
                "GROUP BY char_id ORDER BY total DESC LIMIT 10",
                (cutoff,),
            )
            # Totals
            total_row = await self._db.execute_fetchall(
                "SELECT SUM(CASE WHEN delta > 0 AND char_id > 0 THEN delta ELSE 0 END) as faucet, "
                "SUM(CASE WHEN delta < 0 AND char_id > 0 THEN delta ELSE 0 END) as sink, "
                "COUNT(*) as cnt "
                "FROM credit_log WHERE created_at > ?",
                (cutoff,),
            )
            ft = int(total_row[0]["faucet"] or 0)
            st = int(total_row[0]["sink"] or 0)
            return {
                "faucet_total": ft,
                "sink_total": st,
                "net": ft + st,
                "txn_count": int(total_row[0]["cnt"] or 0),
                "top_faucets": [(r["source"], int(r["total"])) for r in (faucet_rows or [])[:5]],
                "top_sinks": [(r["source"], int(r["total"])) for r in (sink_rows or [])[:5]],
                "top_earners": [(int(r["char_id"]), int(r["total"])) for r in (earner_rows or [])],
            }
        except Exception:
            log.warning("get_credit_velocity: failed", exc_info=True)
            return {
                "faucet_total": 0, "sink_total": 0, "net": 0,
                "txn_count": 0, "top_faucets": [], "top_sinks": [],
                "top_earners": [],
            }

    # ── S51 economy hardening helpers ──────────────────────────────────────
    # All four read directly from credit_log. The aiosqlite connection is
    # stored as ``self._db`` so these mirror the patterns used by
    # ``get_credit_velocity`` above. Each method fails open (returns the
    # neutral "no data" result) on any DB error so they can be safely
    # called from tick handlers that must not crash the loop.

    async def get_daily_p2p_outgoing(self, char_id: int,
                                       seconds: int = 86400) -> int:
        """Sum of credits the character has *sent* via p2p_transfer in the
        last ``seconds`` seconds.

        Only negative-delta rows count (positive deltas are receipts).
        Returns the absolute value so callers can compare directly against
        ``P2P_DAILY_CAP``.

        Used by the trade command to enforce the daily transfer cap.
        Fails open (returns 0) on DB error so a transient credit_log
        outage never permanently locks every account out of trading.
        """
        try:
            cutoff = time.time() - seconds
            rows = await self._db.execute_fetchall(
                "SELECT SUM(delta) AS total FROM credit_log "
                "WHERE char_id = ? AND source = 'p2p_transfer' "
                "AND delta < 0 AND created_at > ?",
                (char_id, cutoff),
            )
            if not rows or rows[0]["total"] is None:
                return 0
            return abs(int(rows[0]["total"]))
        except Exception:
            log.warning("get_daily_p2p_outgoing: failed", exc_info=True)
            return 0

    async def get_whale_transactions(self, threshold: int = 50000,
                                       seconds: int = 86400,
                                       limit: int = 50) -> list[dict]:
        """Return individual credit_log rows whose ``|delta| >= threshold``
        within the last ``seconds`` seconds.

        Excludes ``char_id = 0`` (system sinks) — those represent credits
        leaving the player economy and would dwarf real player movement.
        Ordered by ``|delta| DESC`` so the biggest single moves are first.
        Each row is a plain dict with ``id, char_id, delta, source,
        created_at`` keys.
        """
        try:
            cutoff = time.time() - seconds
            rows = await self._db.execute_fetchall(
                "SELECT id, char_id, delta, source, created_at "
                "FROM credit_log "
                "WHERE char_id > 0 AND ABS(delta) >= ? AND created_at > ? "
                "ORDER BY ABS(delta) DESC LIMIT ?",
                (threshold, cutoff, limit),
            )
            return [
                {
                    "id":         int(r["id"]),
                    "char_id":    int(r["char_id"]),
                    "delta":      int(r["delta"]),
                    "source":     r["source"],
                    "created_at": float(r["created_at"]),
                }
                for r in (rows or [])
            ]
        except Exception:
            log.warning("get_whale_transactions: failed", exc_info=True)
            return []

    async def get_farming_alerts(self,
                                   hourly_threshold: int = 5000,
                                   sustained_hours: int = 2,
                                   lookback_seconds: int = 86400) -> list[dict]:
        """Identify characters whose hourly *positive* income has stayed
        above ``hourly_threshold`` for at least ``sustained_hours`` distinct
        hour-buckets inside the lookback window.

        Bucketing uses ``CAST(created_at/3600 AS INTEGER)`` — Unix-epoch
        hour index, so two timestamps fall in the same bucket if they
        share the same hour offset from epoch (NOT the same hour-of-day).
        Negative deltas (sinks) never contribute — spending money does
        not make someone a farmer.

        Returns a list of dicts:
            {
              "char_id":               int,
              "hours_over_threshold":  int,
              "total_in_window":       int,  (sum of positive deltas)
              "peak_hour_total":       int,  (max single-hour total)
            }

        Sorted by ``hours_over_threshold DESC`` then ``peak_hour_total DESC``
        so the most concerning offenders surface first.
        """
        try:
            cutoff = time.time() - lookback_seconds
            # Two-stage aggregation: first per (char_id, hour_bucket), then
            # filter buckets ≥ threshold and roll up per char.
            rows = await self._db.execute_fetchall(
                "SELECT char_id, "
                "       CAST(created_at / 3600 AS INTEGER) AS hour_bucket, "
                "       SUM(delta) AS hour_total "
                "FROM credit_log "
                "WHERE char_id > 0 AND delta > 0 AND created_at > ? "
                "GROUP BY char_id, hour_bucket "
                "HAVING hour_total >= ?",
                (cutoff, hourly_threshold),
            )
            # Aggregate hot-hours per char in Python — easier than nested SQL
            # and perfectly fine for the modest volume we expect here.
            by_char: dict[int, dict] = {}
            for r in (rows or []):
                cid = int(r["char_id"])
                ht  = int(r["hour_total"] or 0)
                bucket = by_char.setdefault(cid, {
                    "char_id":              cid,
                    "hours_over_threshold": 0,
                    "total_in_window":      0,
                    "peak_hour_total":      0,
                })
                bucket["hours_over_threshold"] += 1
                bucket["total_in_window"]      += ht
                if ht > bucket["peak_hour_total"]:
                    bucket["peak_hour_total"] = ht
            alerts = [
                b for b in by_char.values()
                if b["hours_over_threshold"] >= sustained_hours
            ]
            alerts.sort(
                key=lambda a: (
                    -a["hours_over_threshold"],
                    -a["peak_hour_total"],
                ),
            )
            return alerts
        except Exception:
            log.warning("get_farming_alerts: failed", exc_info=True)
            return []

    async def get_inflation_metrics(self, seconds: int = 86400) -> dict:
        """Net player-economy flow over the last ``seconds`` seconds vs
        the current circulation total.

        Returns ``{net_flow, circulation, flow_pct}`` where:
          - net_flow    : SUM(delta) for char_id > 0 in the window. Excludes
                          char_id=0 (system) so a tax destroying credits
                          isn't double-counted alongside the absence of
                          those credits in circulation.
          - circulation : SUM(credits) over the characters table — what
                          players are currently holding.
          - flow_pct    : net_flow / circulation, as a float in [-inf, +inf].
                          Returns 0.0 (not NaN) when circulation is zero.
        """
        try:
            cutoff = time.time() - seconds
            flow_rows = await self._db.execute_fetchall(
                "SELECT SUM(delta) AS total FROM credit_log "
                "WHERE char_id > 0 AND created_at > ?",
                (cutoff,),
            )
            net_flow = int((flow_rows[0]["total"] or 0)) if flow_rows else 0

            circ_rows = await self._db.execute_fetchall(
                "SELECT SUM(credits) AS total FROM characters",
            )
            circulation = int((circ_rows[0]["total"] or 0)) if circ_rows else 0

            if circulation > 0:
                flow_pct = float(net_flow) / float(circulation)
            else:
                flow_pct = 0.0
            return {
                "net_flow":    net_flow,
                "circulation": circulation,
                "flow_pct":    flow_pct,
            }
        except Exception:
            log.warning("get_inflation_metrics: failed", exc_info=True)
            return {"net_flow": 0, "circulation": 0, "flow_pct": 0.0}

    async def get_docked_player_ships(self) -> list:
        """Return all player-owned ships that are currently docked.

        Used by the docking fee tick. Returns list of dicts with
        id, name, owner_id, docked_at.
        """
        rows = await self._db.execute_fetchall(
            "SELECT id, name, owner_id, docked_at FROM ships "
            "WHERE docked_at IS NOT NULL AND owner_id IS NOT NULL"
        )
        return [dict(r) for r in rows] if rows else []

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
        """Create an NPC. Returns NPC ID. Skips creation if NPC with same name
        already exists in the room (duplicate guard for idempotent build scripts)."""
        existing = await self._db.execute_fetchall(
            "SELECT id FROM npcs WHERE name = ? AND room_id = ?",
            (name, room_id),
        )
        if existing:
            return existing[0]["id"]
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
        # Deduplicate: if a traffic ship with this name already exists in DB
        # (from a previous server run that was not cleaned up), reuse it.
        existing = await self._db.execute_fetchall(
            "SELECT id FROM ships WHERE name = ? AND owner_id IS NULL",
            (name,),
        )
        if existing:
            return existing[0]["id"]
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

    # ── Bounty Board Methods ───────────────────────────────────────────────────

    async def get_posted_bounties(self) -> list[dict]:
        """Return all bounty contracts with status posted or claimed."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM bounties WHERE status IN ('posted','claimed') "
            "ORDER BY posted_at DESC"
        )
        return [dict(r) for r in rows]

    async def save_bounty(self, contract) -> None:
        """Insert a new bounty contract."""
        import json as _json
        import time as _time
        d = contract.to_dict() if hasattr(contract, "to_dict") else contract
        await self._db.execute(
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
        await self._db.commit()

    async def update_bounty(self, contract_id: str, data: dict) -> None:
        """Update a bounty contract's data and status fields."""
        import json as _json
        await self._db.execute(
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
        await self._db.commit()

    async def delete_npc(self, npc_id: int) -> None:
        """Delete an NPC record by ID (used for bounty target cleanup)."""
        await self._db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
        await self._db.commit()

    # ── CP Progression DB methods ─────────────────────────────────────────────

    async def cp_get_row(self, char_id: int):
        """Return the cp_ticks row for a character, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM cp_ticks WHERE char_id = ?", (char_id,)
        )
        return dict(rows[0]) if rows else None

    async def cp_ensure_row(self, char_id: int) -> None:
        """Insert a default cp_ticks row if one does not exist."""
        await self._db.execute(
            "INSERT OR IGNORE INTO cp_ticks (char_id) VALUES (?)", (char_id,)
        )
        await self._db.commit()

    async def cp_update_row(self, char_id: int, **fields) -> None:
        """Update arbitrary fields on a cp_ticks row."""
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [char_id]
        await self._db.execute(
            f"UPDATE cp_ticks SET {set_clause} WHERE char_id = ?", values
        )
        await self._db.commit()

    # ── Ambient NPC life (T3.22 Phase 0 — INERT accessor stubs) ──────────
    # These read/write the npc_ambient_state table the schema scaffolds. They
    # have NO callers yet — the post-launch ambient-life sim (Phases 1-4) will
    # use them. Shipped now with the schema so Phase 1 is pure feature code
    # against a present table + present accessors (no DB-layer change races a
    # live player). Mirror the cp_ticks trio. See
    # docs/design/ambient_npc_life_design_v1.md §6 Phase 0.

    _NPC_AMBIENT_STATE_WRITABLE = frozenset({
        "current_goal", "current_room_id", "dest_room_id", "move_started_at",
        "move_duration", "last_tick_at", "activity", "extra",
    })

    async def ambient_state_get(self, npc_id: int) -> Optional[dict]:
        """Return the npc_ambient_state row for an NPC, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npc_ambient_state WHERE npc_id = ?", (npc_id,)
        )
        return dict(rows[0]) if rows else None

    async def ambient_state_ensure_row(self, npc_id: int) -> None:
        """Insert a default npc_ambient_state row if one does not exist."""
        await self._db.execute(
            "INSERT OR IGNORE INTO npc_ambient_state (npc_id) VALUES (?)",
            (npc_id,),
        )
        await self._db.commit()

    async def ambient_state_update(self, npc_id: int, **fields) -> None:
        """Update npc_ambient_state fields (allowlisted columns only)."""
        if not fields:
            return
        bad = set(fields) - self._NPC_AMBIENT_STATE_WRITABLE
        if bad:
            raise ValueError(
                f"ambient_state_update: unknown/disallowed columns: {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [npc_id]
        await self._db.execute(
            f"UPDATE npc_ambient_state SET {set_clause} WHERE npc_id = ?",
            values,
        )
        await self._db.commit()

    async def ambient_state_in_room(self, room_id: int) -> list:
        """Return all npc_ambient_state rows currently in a room (uses the
        idx_npc_ambient_room index). The sim's co-location query."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npc_ambient_state WHERE current_room_id = ?",
            (room_id,),
        )
        return [dict(r) for r in rows]

    async def cp_add_character_points(self, char_id: int, amount: int) -> None:
        """Add CP to characters.character_points (floor at 0)."""
        await self._db.execute(
            "UPDATE characters SET character_points = MAX(0, character_points + ?) WHERE id = ?",
            (amount, char_id),
        )
        await self._db.commit()

    async def kudos_log(self, giver_id: int, target_id: int, ticks: int, ts: float) -> None:
        """Record a kudos event."""
        await self._db.execute(
            "INSERT INTO kudos_log (giver_id, target_id, ticks, awarded_at) VALUES (?, ?, ?, ?)",
            (giver_id, target_id, ticks, ts),
        )
        await self._db.commit()

    async def kudos_last_given(self, giver_id: int, target_id: int):
        """Return timestamp of last kudos given from giver to target, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT MAX(awarded_at) as ts FROM kudos_log WHERE giver_id = ? AND target_id = ?",
            (giver_id, target_id),
        )
        if rows:
            return rows[0]["ts"]
        return None

    async def kudos_count_received_this_week(self, target_id: int) -> int:
        """Count kudos received by target in the rolling 7-day window."""
        import time as _time
        cutoff = _time.time() - (7 * 24 * 3600)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM kudos_log WHERE target_id = ? AND awarded_at >= ?",
            (target_id, cutoff),
        )
        return rows[0]["cnt"] if rows else 0

    # -- Organization Operations --

    async def get_organization(self, code: str) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (code,)
        )
        return dict(rows[0]) if rows else None

    async def get_all_organizations(self) -> list:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations ORDER BY org_type, name"
        )
        return [dict(r) for r in rows]

    async def create_organization(self, code: str, name: str, org_type: str = "faction",
                                   director_managed: bool = True, hq_room_id: int = None,
                                   properties: str = "{}") -> int:
        existing = await self._db.execute_fetchall(
            "SELECT id FROM organizations WHERE code = ?", (code,)
        )
        if existing:
            return existing[0]["id"]
        cursor = await self._db.execute(
            """INSERT INTO organizations (code, name, org_type, director_managed,
               hq_room_id, properties)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, name, org_type, 1 if director_managed else 0, hq_room_id, properties),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def create_org_rank(self, org_id: int, rank_level: int, title: str,
                               min_rep: int = 0, permissions: str = "[]",
                               equipment: str = "[]"):
        await self._db.execute(
            """INSERT OR IGNORE INTO org_ranks
               (org_id, rank_level, title, min_rep, permissions, equipment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (org_id, rank_level, title, min_rep, permissions, equipment),
        )
        await self._db.commit()

    async def get_org_ranks(self, org_id: int) -> list:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM org_ranks WHERE org_id = ? ORDER BY rank_level",
            (org_id,)
        )
        return [dict(r) for r in rows]

    async def get_membership(self, char_id: int, org_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM org_memberships WHERE char_id = ? AND org_id = ?",
            (char_id, org_id)
        )
        return dict(rows[0]) if rows else None

    async def get_memberships_for_char(self, char_id: int) -> list:
        rows = await self._db.execute_fetchall(
            """SELECT m.*, o.code, o.name, o.org_type,
                      r.title, r.permissions, r.equipment
               FROM org_memberships m
               JOIN organizations o ON o.id = m.org_id
               LEFT JOIN org_ranks r ON r.org_id = m.org_id AND r.rank_level = m.rank_level
               WHERE m.char_id = ?""",
            (char_id,)
        )
        return [dict(r) for r in rows]

    async def join_organization(self, char_id: int, org_id: int,
                                 specialization: str = "") -> bool:
        existing = await self.get_membership(char_id, org_id)
        if existing:
            return False
        await self._db.execute(
            """INSERT INTO org_memberships (char_id, org_id, specialization)
               VALUES (?, ?, ?)""",
            (char_id, org_id, specialization),
        )
        await self._db.commit()
        return True

    async def leave_organization(self, char_id: int, org_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM org_memberships WHERE char_id = ? AND org_id = ?",
            (char_id, org_id)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def update_membership(self, char_id: int, org_id: int, **fields):
        allowed = {"rank_level", "standing", "rep_score", "specialization"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"update_membership: unknown fields {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [char_id, org_id]
        await self._db.execute(
            f"UPDATE org_memberships SET {set_clause} WHERE char_id = ? AND org_id = ?",
            vals
        )
        await self._db.commit()

    async def adjust_rep(self, char_id: int, org_code: str, delta: int):
        org = await self.get_organization(org_code)
        if not org:
            return
        mem = await self.get_membership(char_id, org["id"])
        if not mem:
            return
        new_rep = max(0, min(100, mem["rep_score"] + delta))
        await self.update_membership(char_id, org["id"], rep_score=new_rep)

    async def log_faction_action(self, char_id: int, org_id: int,
                                  action_type: str, details: str = ""):
        await self._db.execute(
            """INSERT INTO faction_log (char_id, org_id, action_type, details)
               VALUES (?, ?, ?, ?)""",
            (char_id, org_id, action_type, details)
        )
        await self._db.commit()

    # -- Issued Equipment Operations --

    async def issue_equipment(self, char_id: int, org_id: int,
                               item_key: str, item_name: str) -> int:
        """Record a faction-issued item. Returns row id."""
        cursor = await self._db.execute(
            """INSERT INTO issued_equipment (char_id, org_id, item_key, item_name)
               VALUES (?, ?, ?, ?)""",
            (char_id, org_id, item_key, item_name),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_issued_equipment(self, char_id: int,
                                    org_id: int = None) -> list:
        """Return all un-reclaimed issued equipment for a character."""
        if org_id:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM issued_equipment
                   WHERE char_id = ? AND org_id = ? AND reclaimed = 0""",
                (char_id, org_id),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM issued_equipment WHERE char_id = ? AND reclaimed = 0",
                (char_id,),
            )
        return [dict(r) for r in rows]

    async def reclaim_equipment(self, char_id: int, org_id: int) -> int:
        """Mark all un-reclaimed issued equipment for an org as reclaimed.
        Returns count of rows updated."""
        cursor = await self._db.execute(
            """UPDATE issued_equipment SET reclaimed = 1
               WHERE char_id = ? AND org_id = ? AND reclaimed = 0""",
            (char_id, org_id),
        )
        await self._db.commit()
        return cursor.rowcount

    # -- Master-Padawan Bond Operations (P-M.1, v28) --
    #
    # Per padawan_master_system_design_v1.md §4.3. P-M.1 ships the
    # foundation layer: CRUD on the master_padawan_bond table. Higher-
    # level surfaces (+master / +padawan commands, training events,
    # Trials, dark-side fall handling) are P-M.2 and beyond and call
    # into these methods.

    async def create_bond(
        self, master_char_id: int, padawan_char_id: int,
    ) -> int:
        """Create a new active Master-Padawan bond. Returns the bond id.

        Enforces the design rule that a Padawan can have at most one
        bond_status='active' bond at a time. If the padawan already
        has an active bond, raises ValueError without creating a
        duplicate.

        The master-side cap (1 active bond at launch) is NOT enforced
        here — the design doc §4.3 says Council authorization can raise
        the cap post-launch via staff adjudication. The command-level
        layer (P-M.2) will check Master eligibility and current Padawan
        count before calling create_bond; create_bond itself is
        deliberately permissive on the Master side so staff overrides
        work without going through the Database API.
        """
        existing = await self.get_active_bond_for_padawan(padawan_char_id)
        if existing:
            raise ValueError(
                f"Padawan {padawan_char_id} already has an active bond "
                f"(bond id {existing['id']} with master "
                f"{existing['master_char_id']})"
            )
        cursor = await self._db.execute(
            """INSERT INTO master_padawan_bond
               (master_char_id, padawan_char_id, bond_status,
                trials_passed_json)
               VALUES (?, ?, 'active', '[]')""",
            (master_char_id, padawan_char_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_bond(self, bond_id: int) -> Optional[dict]:
        """Return a bond row by id, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM master_padawan_bond WHERE id = ?",
            (bond_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_active_bond_for_padawan(
        self, padawan_char_id: int,
    ) -> Optional[dict]:
        """Return the Padawan's currently-active bond, or None.

        A Padawan has at most one active bond by the create_bond
        invariant. Returns the bond row as a dict.
        """
        rows = await self._db.execute_fetchall(
            """SELECT * FROM master_padawan_bond
               WHERE padawan_char_id = ? AND bond_status = 'active'
               LIMIT 1""",
            (padawan_char_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_active_bonds_for_master(
        self, master_char_id: int,
    ) -> list:
        """Return all of the Master's currently-active bonds as a list
        of dicts.

        Note plural: a Master CAN have more than one active bond
        (Council-authorized post-launch per design §4.3). At launch
        the gameplay cap is 1, but the schema and this query support
        multiple.
        """
        rows = await self._db.execute_fetchall(
            """SELECT * FROM master_padawan_bond
               WHERE master_char_id = ? AND bond_status = 'active'""",
            (master_char_id,),
        )
        return [dict(r) for r in rows]

    async def dissolve_bond(
        self, bond_id: int, reason: str = "",
    ) -> bool:
        """Mark a bond as dissolved with optional reason.

        Returns True if the bond was active and is now dissolved;
        False if the bond was not in 'active' status (already
        dissolved, knighted, or fallen — dissolve is a no-op).

        Failure-tolerant: a dissolve on a non-existent bond_id
        returns False without raising.
        """
        cursor = await self._db.execute(
            """UPDATE master_padawan_bond
               SET bond_status = 'dissolved',
                   dissolved_at = datetime('now'),
                   dissolved_reason = ?
               WHERE id = ? AND bond_status = 'active'""",
            (reason, bond_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def knight_bond(
        self, bond_id: int, trials_passed: Optional[list] = None,
    ) -> bool:
        """Mark a Padawan-Master bond as completed via Knighting.

        The Padawan completed the Trials and was knighted. Records
        the timestamp and the list of Trials passed (Skill, Courage,
        Flesh, Spirit, Insight per design §6.2). Returns True if the
        bond was active and is now knighted; False otherwise.

        trials_passed: list of trial names. If None, the existing
        trials_passed_json on the row is preserved (the caller may
        have been recording trial completions piecemeal via
        record_trial_passed and now just wants to close the bond).
        """
        import json as _json
        if trials_passed is not None:
            cursor = await self._db.execute(
                """UPDATE master_padawan_bond
                   SET bond_status = 'knighted',
                       knight_promotion_at = datetime('now'),
                       trials_passed_json = ?
                   WHERE id = ? AND bond_status = 'active'""",
                (_json.dumps(trials_passed), bond_id),
            )
        else:
            cursor = await self._db.execute(
                """UPDATE master_padawan_bond
                   SET bond_status = 'knighted',
                       knight_promotion_at = datetime('now')
                   WHERE id = ? AND bond_status = 'active'""",
                (bond_id,),
            )
        await self._db.commit()
        return cursor.rowcount > 0

    async def fall_bond(self, bond_id: int, reason: str = "") -> bool:
        """Mark a bond as 'fallen' (Padawan turned to the Dark Side).

        Per design §7. Returns True if the bond was active and is now
        fallen; False otherwise. The reason field is reused as a
        dissolution reason on the dissolved_reason column for
        narrative continuity (a fall IS a kind of dissolution, just a
        more dramatic one).
        """
        cursor = await self._db.execute(
            """UPDATE master_padawan_bond
               SET bond_status = 'fallen',
                   dissolved_at = datetime('now'),
                   dissolved_reason = ?
               WHERE id = ? AND bond_status = 'active'""",
            (reason, bond_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def record_trial_passed(
        self, bond_id: int, trial_name: str,
    ) -> bool:
        """Append a passed Trial name to the bond's trials_passed_json.

        Idempotent: if the trial is already in the list, returns False
        without modifying. Returns True if the trial was newly
        appended.

        Designed to be called as each Trial is completed, so the bond
        can be knighted with the full list at the end. The
        record_trial_passed + knight_bond(trials_passed=None)
        pattern is the intended flow.
        """
        import json as _json
        bond = await self.get_bond(bond_id)
        if not bond:
            return False
        raw = bond.get("trials_passed_json") or "[]"
        try:
            passed = _json.loads(raw)
            if not isinstance(passed, list):
                passed = []
        except (ValueError, TypeError):
            log.warning(
                "[bond] malformed trials_passed_json on bond %s: %r",
                bond_id, raw,
            )
            passed = []
        if trial_name in passed:
            return False
        passed.append(trial_name)
        await self._db.execute(
            """UPDATE master_padawan_bond
               SET trials_passed_json = ?
               WHERE id = ?""",
            (_json.dumps(passed), bond_id),
        )
        await self._db.commit()
        return True

    async def get_bond_roles_for_chars(
        self, char_ids: list,
    ) -> dict:
        """Return a {char_id: role} dict for the given character ids.

        role ∈ {'master', 'padawan', 'both', None}. None means the
        char has no active bond as either master or padawan. 'both'
        means the char is a Master in one active bond AND a Padawan
        in another (unusual but possible: a Knight who took a
        Padawan but whose own Master-bond has not yet been
        marked knighted — schema permits it).

        Batched for use by LookCommand: one SELECT regardless of
        room population. P-M.2 §8.12 #4 design call.

        Returns {} on empty input (no SQL fired).
        """
        if not char_ids:
            return {}
        # SQLite IN-clause: build a parameterized list.
        placeholders = ",".join("?" * len(char_ids))
        rows = await self._db.execute_fetchall(
            f"""SELECT master_char_id, padawan_char_id
                FROM master_padawan_bond
                WHERE bond_status = 'active'
                  AND (master_char_id IN ({placeholders})
                       OR padawan_char_id IN ({placeholders}))""",
            tuple(char_ids) + tuple(char_ids),
        )
        masters = set()
        padawans = set()
        wanted = set(char_ids)
        for r in rows:
            m_id = r["master_char_id"]
            p_id = r["padawan_char_id"]
            if m_id in wanted:
                masters.add(m_id)
            if p_id in wanted:
                padawans.add(p_id)
        out: dict = {}
        for cid in char_ids:
            is_m = cid in masters
            is_p = cid in padawans
            if is_m and is_p:
                out[cid] = "both"
            elif is_m:
                out[cid] = "master"
            elif is_p:
                out[cid] = "padawan"
            else:
                out[cid] = None
        return out

    # -- P-M.3 training_log helpers (May 22 2026) ----------------------
    #
    # Per padawan_master_system_design_v1.md §5.2:
    #   - `+teach <power>` logs an event_type='teach' row with the
    #     power key and any CP-spend detail in payload_json.
    #   - `+spar` logs an event_type='spar' row; design caps "one
    #     CP-granting spar per in-game day per pair." We enforce that
    #     by querying last_spar_for_bond.
    # The table is append-only — no UPDATE/DELETE in normal flow.

    async def insert_training_log(
        self,
        *,
        bond_id: int,
        master_id: int,
        padawan_id: int,
        event_type: str,
        payload: Optional[dict] = None,
        created_at: Optional[float] = None,
    ) -> int:
        """Append a training-log row. Returns the new row's id."""
        import time as _time
        import json as _json
        if created_at is None:
            created_at = _time.time()
        if payload is None:
            payload = {}
        cursor = await self._db.execute(
            """INSERT INTO training_log
               (bond_id, master_id, padawan_id, event_type,
                payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                int(bond_id), int(master_id), int(padawan_id),
                str(event_type), _json.dumps(payload),
                float(created_at),
            ),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def get_last_spar_for_bond(
        self, bond_id: int,
    ) -> Optional[dict]:
        """Return the most recent 'spar' training_log row for this
        bond, or None. Used by +spar cooldown check."""
        rows = await self._db.execute_fetchall(
            """SELECT * FROM training_log
               WHERE bond_id = ? AND event_type = 'spar'
               ORDER BY created_at DESC LIMIT 1""",
            (int(bond_id),),
        )
        return dict(rows[0]) if rows else None

    async def get_training_log_for_bond(
        self, bond_id: int, *, limit: int = 100,
    ) -> list:
        """Return training_log rows for a bond (newest first). Used
        by the Knight ceremony / Master Approval Weight surfaces."""
        rows = await self._db.execute_fetchall(
            """SELECT * FROM training_log
               WHERE bond_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (int(bond_id), int(limit)),
        )
        return [dict(r) for r in rows]

    async def count_teach_events_for_bond(
        self, bond_id: int, *, power_key: Optional[str] = None,
    ) -> int:
        """Count 'teach' events for this bond. If `power_key` is
        given, restricts to that power (used to gate "Padawan
        already taught this power" idempotency)."""
        if power_key is None:
            rows = await self._db.execute_fetchall(
                """SELECT COUNT(*) AS c FROM training_log
                   WHERE bond_id = ? AND event_type = 'teach'""",
                (int(bond_id),),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT COUNT(*) AS c FROM training_log
                   WHERE bond_id = ? AND event_type = 'teach'
                     AND payload_json LIKE ?""",
                (int(bond_id), f'%"power_key": "{power_key}"%'),
            )
        return int(rows[0]["c"]) if rows else 0

    # -- PC Bounty Operations (PG.2 session 1, May 20 2026) --
    #
    # Per progression_gates_and_consequences_design_v1.md §4.
    # Schema is v18 baseline + v30 contributors_json sidecar.
    # Session 1 ships: post, stack, cancel, get, list, cooldown.
    # Session 2 ships: claim, release, fulfill, insurance, tick.

    async def get_pc_bounty(self, bounty_id: int) -> Optional[dict]:
        """Return a bounty row by id, or None if not found."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM pc_bounties WHERE id = ?", (bounty_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_active_outgoing_for_poster(
        self, poster_id: int,
    ) -> Optional[dict]:
        """Return the poster's currently-active outgoing bounty
        (they are the primary `poster_id`), or None.

        Per design §4.2: ONE active outgoing bounty per primary
        poster. Stacking as a secondary contributor does NOT count
        as outgoing — the secondary is contributing to someone
        else's primary post.
        """
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE poster_id = ? AND state = 'active'
               ORDER BY id DESC LIMIT 1""",
            (poster_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_active_incoming_for_target(
        self, target_id: int,
    ) -> Optional[dict]:
        """Return the target's currently-active incoming bounty,
        or None. Per design §4.2: ONE active incoming bounty per
        target. Used to drive stacking behavior."""
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE target_id = ? AND state = 'active'
               ORDER BY id DESC LIMIT 1""",
            (target_id,),
        )
        return dict(rows[0]) if rows else None

    async def list_active_pc_bounties(
        self, limit: int = 100,
    ) -> list:
        """Return all active bounties for the BH Guild board.

        Most-recently-posted first. Capped at `limit` to avoid
        unbounded scans. Session 1: read-only listing for
        `+bounty board` display; session 2 will add claim.
        """
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE state = 'active'
               ORDER BY posted_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def get_dsp_wanted_characters(
        self, threshold: int, limit: int = 50,
    ) -> list:
        """Drop 4b: return active characters whose Dark Side Points are at
        or above `threshold`, highest first.

        Powers the Dark-Side Notoriety section of the BH board. This is a
        derived, read-only view (no bounty rows are written) — the "wanted"
        state lives entirely in dark_side_points, like force_sensitive.
        """
        rows = await self._db.execute_fetchall(
            """SELECT id, name, dark_side_points
               FROM characters
               WHERE dark_side_points >= ? AND is_active = 1
               ORDER BY dark_side_points DESC
               LIMIT ?""",
            (int(threshold), int(limit)),
        )
        return [dict(r) for r in rows]

    # ── Drop 4b (hunter.1): roaming Dark-Side hunter pursuit state ──────────
    # One row per hunted character; the only persistent state for the pursuit
    # (the "wanted" flag itself stays derived from dark_side_points). See
    # engine/dsp_hunter.py and the dsp_hunter_tick driver.

    async def get_dsp_pursuit(self, char_id: int) -> Optional[dict]:
        """Return the pursuit row for a character, or None if no hunter is
        currently on their trail."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM dsp_hunter_pursuit WHERE char_id = ?", (int(char_id),)
        )
        return dict(rows[0]) if rows else None

    async def get_all_dsp_pursuits(self) -> list:
        """Return every active pursuit row (powers the BH-board pursuit suffix
        and lets the tick clear pursuits whose quarry has atoned)."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM dsp_hunter_pursuit"
        )
        return [dict(r) for r in rows]

    async def upsert_dsp_pursuit(
        self, char_id: int, hunter_name: str, progress: int, stage: str,
        last_notified_stage: Optional[str] = None,
    ) -> None:
        """Insert or update a character's pursuit. ``last_notified_stage`` is
        only written when provided (the tick sets it once it has actually
        delivered the stage-change warning), so a None leaves the existing
        value intact on update."""
        import time as _t
        now = _t.time()
        if last_notified_stage is None:
            await self._db.execute(
                """INSERT INTO dsp_hunter_pursuit
                       (char_id, hunter_name, progress, stage, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(char_id) DO UPDATE SET
                       hunter_name = excluded.hunter_name,
                       progress    = excluded.progress,
                       stage       = excluded.stage,
                       updated_at  = excluded.updated_at""",
                (int(char_id), hunter_name, int(progress), stage, now),
            )
        else:
            await self._db.execute(
                """INSERT INTO dsp_hunter_pursuit
                       (char_id, hunter_name, progress, stage,
                        last_notified_stage, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(char_id) DO UPDATE SET
                       hunter_name         = excluded.hunter_name,
                       progress            = excluded.progress,
                       stage               = excluded.stage,
                       last_notified_stage = excluded.last_notified_stage,
                       updated_at          = excluded.updated_at""",
                (int(char_id), hunter_name, int(progress), stage,
                 last_notified_stage, now),
            )
        await self._db.commit()

    async def clear_dsp_pursuit(self, char_id: int) -> bool:
        """End a pursuit (the quarry atoned / the trail went cold). Returns
        True if a row was removed."""
        cur = await self._db.execute(
            "DELETE FROM dsp_hunter_pursuit WHERE char_id = ?", (int(char_id),)
        )
        await self._db.commit()
        return bool(getattr(cur, "rowcount", 0))

    async def set_dsp_pursuit_spawn(self, char_id: int,
                                    spawned_npc_id: Optional[int]) -> None:
        """Record (or clear, with None) the live hunter NPC spawned for a
        quarry at the at-heels climax (hunter.2). No-op if the pursuit row
        doesn't exist."""
        await self._db.execute(
            "UPDATE dsp_hunter_pursuit SET spawned_npc_id = ? WHERE char_id = ?",
            (int(spawned_npc_id) if spawned_npc_id is not None else None,
             int(char_id)),
        )
        await self._db.commit()


    async def post_pc_bounty(
        self, *, poster_id: int, target_id: int, amount: int,
        reason: str, fee: int, duration_seconds: float,
    ) -> int:
        """Create a new PC bounty row. Returns the new bounty id.

        Caller is responsible for:
          - Validating amount range, debiting poster credits,
            checking outgoing/incoming preconditions, cooldowns.
          - Logging the credit movements (this method only writes
            the bounty row).

        The contributors_json sidecar is initialized with the
        primary poster's stake + fee. Stacking (subsequent
        contributors) is handled by `stack_pc_bounty`.
        """
        import json as _json
        import time as _time
        now = _time.time()
        contributors = [{
            "poster_id": poster_id,
            "amount": amount,
            "fee": fee,
            "added_at": now,
        }]
        cur = await self._db.execute(
            """INSERT INTO pc_bounties
               (poster_id, target_id, amount, reason, state,
                posted_at, expires_at, contributors_json)
               VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
            (poster_id, target_id, amount, reason, now,
             now + duration_seconds,
             _json.dumps(contributors)),
        )
        await self._db.commit()
        return cur.lastrowid

    async def stack_pc_bounty(
        self, *, bounty_id: int, poster_id: int, amount: int,
        fee: int,
    ) -> bool:
        """Add a secondary contribution to an existing active
        bounty. Increments amount and appends to contributors_json.

        Returns True iff the bounty was active and the contribution
        was recorded. False on any precondition failure (bounty
        not found, not active).

        Caller validates that the secondary poster is NOT the
        primary, that they're not on cooldown, and debits their
        credits.
        """
        import json as _json
        import time as _time
        bounty = await self.get_pc_bounty(bounty_id)
        if not bounty or bounty["state"] != "active":
            return False
        try:
            contributors = _json.loads(
                bounty.get("contributors_json") or "[]"
            )
            if not isinstance(contributors, list):
                contributors = []
        except (ValueError, TypeError):
            contributors = []
        now = _time.time()
        contributors.append({
            "poster_id": poster_id,
            "amount": amount,
            "fee": fee,
            "added_at": now,
        })
        new_total = bounty["amount"] + amount
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET amount = ?, contributors_json = ?
               WHERE id = ? AND state = 'active'""",
            (new_total, _json.dumps(contributors), bounty_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def cancel_pc_bounty(self, bounty_id: int) -> Optional[dict]:
        """Cancel an active bounty. Returns the bounty row as it
        was at cancel time (so the caller can read contributors_json
        for proportional refunds), or None on failure.

        Caller is responsible for the refund arithmetic + credit
        movements (the DB layer only flips state).
        """
        import time as _time
        bounty = await self.get_pc_bounty(bounty_id)
        if not bounty or bounty["state"] != "active":
            return None
        now = _time.time()
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'canceled', resolved_at = ?
               WHERE id = ? AND state = 'active'""",
            (now, bounty_id),
        )
        await self._db.commit()
        if cur.rowcount == 0:
            return None
        return bounty  # return the pre-cancel snapshot for refund math

    async def get_bounty_cooldown(
        self, poster_id: int, target_id: int,
    ) -> float:
        """Return the unix-ts until which `poster_id` is cooled
        down from posting against `target_id`. Returns 0.0 if no
        cooldown is recorded (or it's expired and pruned).
        """
        rows = await self._db.execute_fetchall(
            """SELECT until FROM bounty_cooldowns
               WHERE poster_id = ? AND target_id = ?""",
            (poster_id, target_id),
        )
        if not rows:
            return 0.0
        return float(rows[0]["until"])

    async def set_bounty_cooldown(
        self, poster_id: int, target_id: int, until_ts: float,
    ) -> None:
        """Upsert a cooldown row. `until_ts` is unix epoch
        seconds when the cooldown lapses. Idempotent."""
        await self._db.execute(
            """INSERT OR REPLACE INTO bounty_cooldowns
               (poster_id, target_id, until)
               VALUES (?, ?, ?)""",
            (poster_id, target_id, until_ts),
        )
        await self._db.commit()

    # -- PC Bounty Session 2 — BH workflow + insurance + tick (May 21 2026) --

    async def claim_pc_bounty(
        self, *, bounty_id: int, bh_char_id: int,
        timer_seconds: float,
    ) -> bool:
        """BH Guild member claims an active bounty. Flips state
        to 'claimed', records claimed_by + claimed_at, and stamps
        a 7-day claim timer. Returns True on success, False if
        the bounty isn't active.

        Caller validates BH Guild membership.
        """
        import time as _time
        now = _time.time()
        # Use claimed_at to encode the timer expiry: claimed_at +
        # timer_seconds is the deadline. (Schema already has
        # claimed_at REAL; no new column needed.)
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'claimed', claimed_by = ?, claimed_at = ?
               WHERE id = ? AND state = 'active'""",
            (bh_char_id, now, bounty_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def release_pc_bounty(self, bounty_id: int) -> bool:
        """BH releases a claimed bounty back to active. Returns
        True if the bounty was claimed and is now active again."""
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'active', claimed_by = NULL, claimed_at = 0
               WHERE id = ? AND state = 'claimed'""",
            (bounty_id,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def fulfill_pc_bounty(
        self, *, bounty_id: int, bh_char_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Mark a bounty as fulfilled. Used after a BH kills the
        target. Returns the pre-fulfill snapshot (so the caller
        can read amount + contributors for the payout) or None if
        the bounty isn't in a fulfillable state.

        Acceptable from-states: 'active' (a BH killed an unclaimed
        target — uncommon but possible) and 'claimed'. The
        bh_char_id stamps `claimed_by` if it was previously
        unclaimed.
        """
        import time as _time
        bounty = await self.get_pc_bounty(bounty_id)
        if not bounty or bounty["state"] not in ("active", "claimed"):
            return None
        now = _time.time()
        # If the bounty was active (no claim) and we have a BH id,
        # stamp claimed_by + claimed_at so the payout knows who.
        new_claimed_by = bounty.get("claimed_by") or bh_char_id
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'fulfilled',
                   resolved_at = ?,
                   claimed_by = ?,
                   claimed_at = COALESCE(NULLIF(claimed_at, 0), ?)
               WHERE id = ? AND state IN ('active', 'claimed')""",
            (now, new_claimed_by, now, bounty_id),
        )
        await self._db.commit()
        if cur.rowcount == 0:
            return None
        # Return the pre-fulfill snapshot for payout math.
        return bounty

    async def void_pc_bounty(
        self, *, bounty_id: int, reason: str = "",
    ) -> Optional[dict]:
        """Admin-only: void a bounty. Returns the pre-void
        snapshot so the caller can refund all contributors in
        full (no fees, no cancel cut). Equivalent to admin-
        commanded cancel without the fee."""
        import time as _time
        bounty = await self.get_pc_bounty(bounty_id)
        if not bounty or bounty["state"] not in (
            "active", "claimed"
        ):
            return None
        now = _time.time()
        # Stash the void reason into resolved_at-adjacent storage:
        # we tack it onto the existing reason field as " | VOIDED:
        # <reason>" for audit trail. Mild abuse of the column but
        # cleaner than adding a column for one feature.
        existing_reason = bounty.get("reason") or ""
        new_reason = (
            existing_reason + " | VOIDED: " + reason
            if reason else existing_reason + " | VOIDED"
        )
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'canceled', resolved_at = ?, reason = ?
               WHERE id = ? AND state IN ('active', 'claimed')""",
            (now, new_reason, bounty_id),
        )
        await self._db.commit()
        if cur.rowcount == 0:
            return None
        return bounty

    async def expire_pc_bounty(self, bounty_id: int) -> Optional[dict]:
        """Mark an active bounty as expired. Returns the pre-
        expire snapshot for refund math, or None if not active.

        Called by run_pc_bounty_expiry_tick when expires_at has
        passed. Caller refunds escrow minus posting fee (per
        design §4.3 expired path).
        """
        import time as _time
        bounty = await self.get_pc_bounty(bounty_id)
        if not bounty or bounty["state"] != "active":
            return None
        now = _time.time()
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'expired', resolved_at = ?
               WHERE id = ? AND state = 'active'""",
            (now, bounty_id),
        )
        await self._db.commit()
        if cur.rowcount == 0:
            return None
        return bounty

    async def revert_expired_claim(self, bounty_id: int) -> bool:
        """If a claim timer has elapsed without fulfillment, revert
        the bounty from 'claimed' back to 'active' so another BH
        can take it. Returns True on success.

        Per design §4.3 'Active → Claimed: 7 days to fulfill or
        contract reverts to Active.'
        """
        cur = await self._db.execute(
            """UPDATE pc_bounties
               SET state = 'active', claimed_by = NULL, claimed_at = 0
               WHERE id = ? AND state = 'claimed'""",
            (bounty_id,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def list_expired_active_bounties(self) -> list:
        """Return active bounties whose expires_at has passed.
        Used by the expiry tick."""
        import time as _time
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE state = 'active' AND expires_at <= ?
               ORDER BY id""",
            (_time.time(),),
        )
        return [dict(r) for r in rows]

    async def list_expired_claims(
        self, claim_window_seconds: float,
    ) -> list:
        """Return claimed bounties whose claim timer has elapsed
        (claimed_at + claim_window_seconds <= now). Used by the
        expiry tick to revert stale claims."""
        import time as _time
        cutoff = _time.time() - claim_window_seconds
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE state = 'claimed' AND claimed_at <= ?
               ORDER BY id""",
            (cutoff,),
        )
        return [dict(r) for r in rows]

    async def list_claims_in_warning_window(
        self,
        *,
        warning_lower_seconds: float,
        warning_upper_seconds: float,
    ) -> list:
        """PG2.PL.C — claims with `warning_lower_seconds` <= elapsed <
        `warning_upper_seconds`.

        Used by the hourly bounty tick to surface "claim nearing
        expiry" mail to BHs. Typical call:

            list_claims_in_warning_window(
                warning_lower_seconds=6*86400,   # 6 days elapsed
                warning_upper_seconds=7*86400,   # not yet 7d (which expires)
            )

        Returns claimed-state rows with `claimed_at` falling in the
        elapsed-time window. Note this is "claimed at most upper
        seconds ago AND at least lower seconds ago" — the natural
        date math reverses the bounds.
        """
        import time as _time
        now = _time.time()
        upper_cutoff = now - float(warning_lower_seconds)  # claimed <= 1d ago (no warn yet)
        lower_cutoff = now - float(warning_upper_seconds)  # claimed >= 7d ago (already expired)
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_bounties
               WHERE state = 'claimed'
                 AND claimed_at <= ?
                 AND claimed_at > ?
               ORDER BY id""",
            (upper_cutoff, lower_cutoff),
        )
        return [dict(r) for r in rows]

    # -- BH Insurance Debt (PG.2 session 2) --

    async def get_insurance_debt(self, char_id: int) -> int:
        """Return the current insurance debt for char_id, or 0
        if none. Per design §4.4, debt accrues when a bountied
        PC is killed by a BH and lacks the credits to cover the
        10% insurance hit."""
        rows = await self._db.execute_fetchall(
            "SELECT amount FROM bh_insurance_debt WHERE char_id = ?",
            (char_id,),
        )
        return int(rows[0]["amount"]) if rows else 0

    async def add_insurance_debt(
        self, char_id: int, amount: int,
    ) -> int:
        """Add `amount` to char_id's insurance debt. Creates the
        row if it doesn't exist; otherwise sums. Returns the new
        total debt.

        Per design §4.4: debt persists until paid; while non-zero,
        Guild services / faction stipends / some BH-tier vendors
        are affected. Consumer surface lands in session 3+ or in
        the parser layer of this drop.
        """
        import time as _time
        current = await self.get_insurance_debt(char_id)
        new_total = current + amount
        await self._db.execute(
            """INSERT OR REPLACE INTO bh_insurance_debt
               (char_id, amount, incurred_at)
               VALUES (?, ?, ?)""",
            (char_id, new_total, _time.time()),
        )
        await self._db.commit()
        return new_total

    async def pay_insurance_debt(
        self, char_id: int, amount: int,
    ) -> int:
        """Pay down `amount` of insurance debt. Returns the
        remaining balance. If amount >= current debt, the row is
        deleted (clean state).
        """
        current = await self.get_insurance_debt(char_id)
        if current <= 0:
            return 0
        if amount >= current:
            await self._db.execute(
                "DELETE FROM bh_insurance_debt WHERE char_id = ?",
                (char_id,),
            )
            await self._db.commit()
            return 0
        remaining = current - amount
        await self._db.execute(
            """UPDATE bh_insurance_debt SET amount = ?
               WHERE char_id = ?""",
            (remaining, char_id),
        )
        await self._db.commit()
        return remaining

    # -- Inventory Operations --

    async def get_inventory(self, char_id: int) -> list:
        """Return character inventory as a list of item dicts.

        Handles both legacy list format and current dict format
        where items are stored under an 'items' key alongside
        a 'resources' key used by the crafting system.
        """
        import json as _j
        rows = await self._db.execute_fetchall(
            "SELECT inventory FROM characters WHERE id = ?", (char_id,)
        )
        if not rows:
            return []
        raw = rows[0]["inventory"] or "[]"
        try:
            parsed = _j.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            log.warning("get_inventory: JSON parse failed for char %s", char_id, exc_info=True)
            return []
        # Dict format: {"items": [...], "resources": [...]}
        if isinstance(parsed, dict):
            return parsed.get("items", [])
        # List format (legacy): [item, item, ...]
        if isinstance(parsed, list):
            return parsed
        return []

    async def _get_inventory_raw(self, char_id: int) -> dict:
        """Return the full inventory structure as a dict.

        Always returns {"items": [...], "resources": [...]}.
        Handles legacy list format, dict format, and NULL/empty.
        """
        import json as _j
        rows = await self._db.execute_fetchall(
            "SELECT inventory FROM characters WHERE id = ?", (char_id,)
        )
        if not rows:
            return {"items": [], "resources": []}
        raw = rows[0]["inventory"] or "{}"
        try:
            parsed = _j.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return {"items": [], "resources": []}
        if isinstance(parsed, dict):
            parsed.setdefault("items", [])
            parsed.setdefault("resources", [])
            return parsed
        if isinstance(parsed, list):
            # Legacy: bare list → migrate to dict format
            return {"items": parsed, "resources": []}
        return {"items": [], "resources": []}

    async def add_to_inventory(self, char_id: int, item: dict,
                               *, fire_chain_hook: bool = True):
        """Append an item dict to character inventory and persist.

        ``fire_chain_hook`` (default True) controls whether the
        ``item_acquired`` chain-event hook fires. Pass ``False`` when
        the add is a COMPENSATING action rather than a genuine
        acquisition — e.g. the ``give`` command's rollback re-add to
        the giver after a failed transfer (F.8.c.2.e). Firing the hook
        there would let a rolled-back give falsely advance a giver who
        happened to be on an ``item_acquired`` chain step.
        """
        import json as _j
        inv = await self._get_inventory_raw(char_id)
        inv["items"].append(item)
        await self._db.execute(
            "UPDATE characters SET inventory = ? WHERE id = ?",
            (_j.dumps(inv), char_id),
        )
        await self._db.commit()
        # F.8.c.2.b₂: CW tutorial chain — item_acquired completion.
        # The char-id variant fetches the row and dispatches; the
        # whole hook is failure-tolerant (errors are swallowed) so
        # inventory updates always succeed even if chain advancement
        # is broken. No-ops silently for items without a "key" field.
        if not fire_chain_hook:
            return
        try:
            from engine.chain_events import on_item_acquired_by_char_id
            _key = (item or {}).get("key", "") if isinstance(item, dict) else ""
            if _key:
                await on_item_acquired_by_char_id(self, char_id, _key)
        except Exception:
            log.debug("add_to_inventory: chain_events hook failed",
                      exc_info=True)

    async def remove_from_inventory(self, char_id: int,
                                     item_key: str) -> bool:
        """Remove the first inventory item matching item_key.
        Returns True if removed."""
        import json as _j
        inv = await self._get_inventory_raw(char_id)
        new_items = []
        removed = False
        for item in inv["items"]:
            if not removed and isinstance(item, dict) and item.get("key") == item_key:
                removed = True
            else:
                new_items.append(item)
        if removed:
            inv["items"] = new_items
            await self._db.execute(
                "UPDATE characters SET inventory = ? WHERE id = ?",
                (_j.dumps(inv), char_id),
            )
            await self._db.commit()
        return removed


    # ── PG.1.death (May 19 2026) ────────────────────────────────────────
    #
    # Corpse object lifecycle + wound_state mutation. Schema columns
    # (corpses table, characters.wound_state, characters.wound_clear_at)
    # landed in schema v18; this drop adds the engine-side consumers.
    #
    # Design: progression_gates_and_consequences_design_v1.md §3.
    #
    # Corpse persists at death location for a bounded window. Decay
    # window is per the design doc's §3.4/§3.5:
    #   - secured zones: no corpse created (instant respawn-with-gear)
    #   - contested:    2 hours
    #   - lawless:      4 hours
    # Anyone can `loot <corpse>` while it persists (PG.1.death.b
    # delivers the parser command). At decay time, bound items
    # auto-mail to the owner; the rest is destroyed.

    async def create_corpse(self, *, char_id: int, room_id: int,
                            inventory: list, credits: int = 0,
                            killer_id: int = None,
                            killer_is_bh: bool = False,
                            decay_seconds: float = 7200.0) -> int:
        """Insert a corpse row. inventory is the items list snapshot
        (already serialized to a Python list of dicts); credits is the
        cash on the body at time of death.

        Returns the new corpse id.
        """
        import json as _j
        import time as _t
        now = _t.time()
        await self._db.execute(
            "INSERT INTO corpses (char_id, room_id, died_at, decay_at, "
            "inventory, credits, killer_id, killer_is_bh, "
            "bounty_resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (char_id, room_id, now, now + float(decay_seconds),
             _j.dumps(list(inventory or [])), int(credits or 0),
             killer_id, 1 if killer_is_bh else 0),
        )
        # Return the new id. aiosqlite's lastrowid is on the cursor;
        # we use a follow-up SELECT for portability with the existing
        # Database wrapper.
        rows = await self._db.execute_fetchall(
            "SELECT last_insert_rowid() AS id"
        )
        new_id = int(rows[0]["id"]) if rows else 0
        await self._db.commit()
        return new_id

    async def get_corpse(self, corpse_id: int):
        """Fetch a single corpse row by id, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM corpses WHERE id = ?", (corpse_id,),
        )
        return rows[0] if rows else None

    async def get_corpses_in_room(self, room_id: int) -> list:
        """All non-decayed corpses currently in the given room.
        Ordered by died_at descending (most recent first)."""
        import time as _t
        return await self._db.execute_fetchall(
            "SELECT * FROM corpses WHERE room_id = ? AND decay_at > ? "
            "ORDER BY died_at DESC",
            (room_id, _t.time()),
        )

    async def get_corpses_by_char(self, char_id: int) -> list:
        """All non-decayed corpses belonging to a given character
        (the dead PC's id). Used by the LootCommand's owner-route
        and by tests. PG.1.death.b (Drop 2d)."""
        import time as _t
        return await self._db.execute_fetchall(
            "SELECT * FROM corpses WHERE char_id = ? AND decay_at > ? "
            "ORDER BY died_at DESC",
            (char_id, _t.time()),
        )

    async def get_decayed_corpses(self) -> list:
        """All corpse rows whose decay_at has passed.
        Caller is expected to process + delete them (PG.1.death.b
        wires this into a periodic tick)."""
        import time as _t
        return await self._db.execute_fetchall(
            "SELECT * FROM corpses WHERE decay_at <= ?",
            (_t.time(),),
        )

    async def delete_corpse(self, corpse_id: int) -> None:
        """Remove a corpse row (used after full loot or decay
        processing)."""
        await self._db.execute(
            "DELETE FROM corpses WHERE id = ?", (corpse_id,),
        )
        await self._db.commit()

    async def update_corpse_inventory(self, corpse_id: int,
                                       inventory: list,
                                       credits: int = None) -> None:
        """Replace the corpse's inventory snapshot (used by `loot`
        when items are taken — PG.1.death.b will call this). If
        credits is given, also overwrite the credit count."""
        import json as _j
        if credits is None:
            await self._db.execute(
                "UPDATE corpses SET inventory = ? WHERE id = ?",
                (_j.dumps(list(inventory or [])), corpse_id),
            )
        else:
            await self._db.execute(
                "UPDATE corpses SET inventory = ?, credits = ? "
                "WHERE id = ?",
                (_j.dumps(list(inventory or [])), int(credits),
                 corpse_id),
            )
        await self._db.commit()

    async def set_wound_state(self, char_id: int, *, state: str,
                              clear_at: float = 0.0) -> None:
        """Set the new-schema wound_state ('healthy'|'wounded') and
        wound_clear_at (unix-epoch seconds; 0 means no active
        recovery clock).

        This is the PG.1.death respawn-Wounded debuff, NOT the WEG
        wound_level ladder. The two coexist:
          - wound_level: WEG R&E in-combat ladder (Stunned/Wounded/
            Incap/MW/Dead). Reset on respawn.
          - wound_state: post-respawn debuff per design §3.3. −1D
            to all rolls until clear_at OR until bacta clears it.
        """
        if state not in ("healthy", "wounded"):
            raise ValueError(
                f"wound_state must be 'healthy' or 'wounded'; got {state!r}"
            )
        await self.save_character(
            char_id, wound_state=state,
            wound_clear_at=float(clear_at),
        )

    async def get_wound_state(self, char_id: int) -> tuple:
        """Read wound_state and wound_clear_at. Returns a
        ('healthy'|'wounded', float) tuple. Defaults to ('healthy', 0)
        for rows that predate the v18 migration's defaults."""
        rows = await self._db.execute_fetchall(
            "SELECT wound_state, wound_clear_at FROM characters "
            "WHERE id = ?", (char_id,),
        )
        if not rows:
            return ("healthy", 0.0)
        row = rows[0]
        return (row.get("wound_state") or "healthy",
                float(row.get("wound_clear_at") or 0.0))


    # -- Narrative Memory Operations --

    async def get_narrative(self, char_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM pc_narrative WHERE char_id = ?", (char_id,)
        )
        return dict(rows[0]) if rows else None

    async def upsert_narrative(self, char_id: int, **fields):
        allowed = {"background", "short_record", "long_record", "last_summarized"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"upsert_narrative: unknown fields {bad}")
        existing = await self.get_narrative(char_id)
        if existing:
            if fields:
                set_clause = ", ".join(f"{k} = ?" for k in fields)
                vals = list(fields.values()) + [char_id]
                await self._db.execute(
                    f"UPDATE pc_narrative SET {set_clause} WHERE char_id = ?", vals
                )
        else:
            await self._db.execute(
                "INSERT INTO pc_narrative (char_id) VALUES (?)", (char_id,)
            )
            if fields:
                set_clause = ", ".join(f"{k} = ?" for k in fields)
                vals = list(fields.values()) + [char_id]
                await self._db.execute(
                    f"UPDATE pc_narrative SET {set_clause} WHERE char_id = ?", vals
                )
        await self._db.commit()

    async def log_action(self, char_id: int, action_type: str,
                          summary: str, details: str = "{}"):
        await self._db.execute(
            """INSERT INTO pc_action_log (char_id, action_type, summary, details)
               VALUES (?, ?, ?, ?)""",
            (char_id, action_type, summary, details)
        )
        await self._db.commit()

    async def get_recent_actions(self, char_id: int, limit: int = 20) -> list:
        rows = await self._db.execute_fetchall(
            """SELECT * FROM pc_action_log WHERE char_id = ?
               ORDER BY logged_at DESC LIMIT ?""",
            (char_id, limit)
        )
        return [dict(r) for r in rows]

    async def get_personal_quests(self, char_id: int,
                                   status: str = "active") -> list:
        rows = await self._db.execute_fetchall(
            """SELECT * FROM personal_quests WHERE char_id = ? AND status = ?
               ORDER BY created_at DESC""",
            (char_id, status)
        )
        return [dict(r) for r in rows]

    async def create_personal_quest(self, char_id: int, title: str,
                                     description: str = "") -> int:
        cursor = await self._db.execute(
            """INSERT INTO personal_quests (char_id, title, description)
               VALUES (?, ?, ?)""",
            (char_id, title, description)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def complete_personal_quest(self, quest_id: int):
        import time as _t
        await self._db.execute(
            """UPDATE personal_quests SET status = 'complete',
               completed_at = ? WHERE id = ?""",
            (_t.strftime("%Y-%m-%d %H:%M:%S"), quest_id)
        )
        await self._db.commit()

    # ── Narrative summarization helpers ──────────────────────────────────────

    async def get_chars_with_new_actions(self) -> list[dict]:
        """Return character rows that have action log entries newer than their
        last_summarized timestamp (or any entries if never summarized)."""
        rows = await self._db.execute_fetchall(
            """SELECT c.id, c.name, c.room_id, c.credits,
                      COALESCE(n.last_summarized, '') AS last_summarized,
                      COALESCE(n.background, '')      AS background,
                      COALESCE(n.long_record, '')     AS long_record,
                      COALESCE(n.short_record, '')    AS short_record
               FROM characters c
               LEFT JOIN pc_narrative n ON n.char_id = c.id
               WHERE EXISTS (
                   SELECT 1 FROM pc_action_log a
                   WHERE a.char_id = c.id
                     AND (n.last_summarized IS NULL
                          OR n.last_summarized = ''
                          OR a.logged_at > n.last_summarized)
               )""",
        )
        return [dict(r) for r in rows]

    async def get_actions_since(self, char_id: int, since_ts: str,
                                 limit: int = 50) -> list[dict]:
        """Return action log entries newer than since_ts (empty = all)."""
        if since_ts:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM pc_action_log
                   WHERE char_id = ? AND logged_at > ?
                   ORDER BY logged_at ASC LIMIT ?""",
                (char_id, since_ts, limit),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM pc_action_log
                   WHERE char_id = ?
                   ORDER BY logged_at ASC LIMIT ?""",
                (char_id, limit),
            )
        return [dict(r) for r in rows]

    async def get_quest_by_id(self, quest_id: int) -> Optional[dict]:
        """Fetch a single personal quest by id."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM personal_quests WHERE id = ?", (quest_id,)
        )
        return dict(rows[0]) if rows else None

    async def update_quest_status(self, quest_id: int, status: str) -> None:
        """Update personal quest status (active / abandoned / complete)."""
        import time as _t
        ts = _t.strftime("%Y-%m-%d %H:%M:%S")
        if status == "complete":
            await self._db.execute(
                "UPDATE personal_quests SET status = ?, completed_at = ? WHERE id = ?",
                (status, ts, quest_id),
            )
        else:
            await self._db.execute(
                "UPDATE personal_quests SET status = ? WHERE id = ?",
                (status, quest_id),
            )
        await self._db.commit()

    # ── Faction missions ──────────────────────────────────────────────────────

    async def get_faction_missions(self, faction_id: str,
                                    limit: int = 10) -> list:
        """Return available missions tagged to a specific faction code."""
        rows = await self._db.execute_fetchall(
            """SELECT * FROM missions
               WHERE status = 'available' AND faction_id = ?
               ORDER BY reward DESC LIMIT ?""",
            (faction_id, limit),
        )
        return [dict(r) for r in rows]

    async def post_faction_mission(self, faction_id: str, **fields) -> int:
        """Create a faction-tagged mission. Returns mission id."""
        allowed = {
            "mission_type", "title", "description", "reward",
            "difficulty", "skill_required", "expires_at",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}
        fields["faction_id"] = faction_id
        fields["status"] = "available"
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        cursor = await self._db.execute(
            f"INSERT INTO missions ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )
        await self._db.commit()
        return cursor.lastrowid

    # ── Org roster + treasury ─────────────────────────────────────────────────

    async def get_org_members(self, org_id: int) -> list:
        """Return all active members of an organization with their rank."""
        rows = await self._db.execute_fetchall(
            """SELECT m.char_id, m.rank_level, m.standing, m.rep_score,
                      m.specialization, m.joined_at,
                      c.name AS char_name
               FROM org_memberships m
               JOIN characters c ON c.id = m.char_id
               WHERE m.org_id = ?
               ORDER BY m.rank_level DESC, c.name ASC""",
            (org_id,),
        )
        return [dict(r) for r in rows]

    async def adjust_org_treasury(self, org_id: int, delta: int) -> int:
        """Add delta credits to an org's treasury. Returns new balance."""
        await self._db.execute(
            "UPDATE organizations SET treasury = MAX(0, treasury + ?) WHERE id = ?",
            (delta, org_id),
        )
        await self._db.commit()
        rows = await self._db.execute_fetchall(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
        )
        return rows[0]["treasury"] if rows else 0

    async def update_member_standing(self, char_id: int, org_id: int,
                                      standing: str) -> None:
        """Set a member's standing (good / probation / expelled)."""
        await self._db.execute(
            "UPDATE org_memberships SET standing = ? WHERE char_id = ? AND org_id = ?",
            (standing, char_id, org_id),
        )
        await self._db.commit()

    # ── Objects (vendor droids, placed items) ─────────────────────────────────

    async def create_object(self, type: str, name: str, owner_id: int,
                             room_id: int = None, description: str = "",
                             data: str = "{}") -> int:
        """Create an object row. Returns new id."""
        cursor = await self._db.execute(
            """INSERT INTO objects (type, name, owner_id, room_id, description, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (type, name, owner_id, room_id, description, data),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_object(self, object_id: int) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM objects WHERE id = ?", (object_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_objects_in_room(self, room_id: int,
                                   obj_type: str = None) -> list:
        if obj_type:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM objects WHERE room_id = ? AND type = ? ORDER BY id",
                (room_id, obj_type),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM objects WHERE room_id = ? ORDER BY id", (room_id,)
            )
        return [dict(r) for r in rows]

    async def get_objects_owned_by(self, owner_id: int,
                                    obj_type: str = None) -> list:
        if obj_type:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM objects WHERE owner_id = ? AND type = ? ORDER BY id",
                (owner_id, obj_type),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM objects WHERE owner_id = ? ORDER BY id", (owner_id,)
            )
        return [dict(r) for r in rows]

    async def update_object(self, object_id: int, **fields) -> None:
        allowed = {"name", "description", "room_id", "owner_id", "data", "type"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"update_object: unknown fields {bad}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [object_id]
        await self._db.execute(
            f"UPDATE objects SET {set_clause} WHERE id = ?", vals
        )
        await self._db.commit()

    async def delete_object(self, object_id: int) -> None:
        await self._db.execute("DELETE FROM objects WHERE id = ?", (object_id,))
        await self._db.commit()

    # ── Shop transactions ─────────────────────────────────────────────────────

    async def log_shop_transaction(
        self, droid_id: int, seller_id: int, buyer_id: int,
        item_key: str, item_name: str, quality: int, quantity: int,
        unit_price: int, listing_fee: int, txn_type: str = "sale",
    ) -> int:
        import time as _t
        total_price = unit_price * quantity
        cursor = await self._db.execute(
            """INSERT INTO shop_transactions
               (droid_id, seller_id, buyer_id, item_key, item_name, quality,
                quantity, unit_price, total_price, listing_fee, txn_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (droid_id, seller_id, buyer_id, item_key, item_name, quality,
             quantity, unit_price, total_price, listing_fee, txn_type, _t.time()),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_shop_transactions(self, seller_id: int,
                                     droid_id: int = None,
                                     limit: int = 20) -> list:
        if droid_id:
            rows = await self._db.execute_fetchall(
                """SELECT st.*, c.name AS buyer_name
                   FROM shop_transactions st
                   JOIN characters c ON c.id = st.buyer_id
                   WHERE st.seller_id = ? AND st.droid_id = ?
                   ORDER BY st.id DESC LIMIT ?""",
                (seller_id, droid_id, limit),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT st.*, c.name AS buyer_name
                   FROM shop_transactions st
                   JOIN characters c ON c.id = st.buyer_id
                   WHERE st.seller_id = ?
                   ORDER BY st.id DESC LIMIT ?""",
                (seller_id, limit),
            )
        return [dict(r) for r in rows]
