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
SCHEMA_VERSION = 26

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
    sender_id       INTEGER NOT NULL REFERENCES characters(id),
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
        if self._db:
            await self._db.close()
            log.info("Database closed.")

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
        """Mark a mission accepted by a character."""
        import json as _json
        await self._db.execute(
            "UPDATE missions SET status='accepted', accepted_by=?, expires_at=?, data=? WHERE id=?",
            (character_id, expires_at, _json.dumps(data), mission_id),
        )
        await self._db.commit()

    async def complete_mission(self, mission_id, data: dict):
        """Mark a mission complete."""
        import json as _json
        await self._db.execute(
            "UPDATE missions SET status='completed', data=? WHERE id=?",
            (_json.dumps(data), mission_id),
        )
        await self._db.commit()

    async def abandon_mission(self, mission_id, data: dict):
        """Return an accepted mission to available status."""
        import json as _json
        await self._db.execute(
            "UPDATE missions SET status='available', accepted_by=NULL, data=? WHERE id=?",
            (_json.dumps(data), mission_id),
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

    async def add_to_inventory(self, char_id: int, item: dict):
        """Append an item dict to character inventory and persist."""
        import json as _j
        inv = await self._get_inventory_raw(char_id)
        inv["items"].append(item)
        await self._db.execute(
            "UPDATE characters SET inventory = ? WHERE id = ?",
            (_j.dumps(inv), char_id),
        )
        await self._db.commit()

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
