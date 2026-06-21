# -*- coding: utf-8 -*-
"""
engine/territory.py — Territory Control system.  [Security Drop 6A+6B+6C]

Influence-based territory claiming for player organizations.

Storage: New `territory_influence` and `territory_claims` tables with
integer zone IDs and org codes.  This is SEPARATE from the Director's
`zone_influence` table (which uses string environment keys and faction
axis names for narrative purposes).  Both systems coexist:

  zone_influence        → Director narrative (string keys, axis names)
  territory_influence   → Gameplay mechanic (int zone IDs, org codes)
  territory_claims      → Room-level claims by organizations

The Director reads territory_influence in its digest to narrate territory
shifts.  The security engine reads territory_claims for claim-based
security upgrades.  Neither system writes to the other's table.

Drop 6A: Influence earning, decay, invest/influence commands, look line
Drop 6B: Room claiming, unclaiming, claimed room security upgrade, look tag
Drop 6C: Guard NPC spawning, resource node tick, faction armory storage

Architecture invariants:
- All influence changes go through adjust_territory_influence(). No direct
  DB writes elsewhere.
- All guard spawns go through spawn_guard_npc(). No direct NPC creation
  for territory guards elsewhere.
- All org storage changes go through adjust_org_storage(). No direct writes
  to properties["org_storage"] elsewhere.
"""

from __future__ import annotations
import json
import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Influence thresholds (from design doc) ───────────────────────────────────
THRESHOLD_PRESENCE  = 25    # Org name appears in look output
THRESHOLD_FOOTHOLD  = 50    # Can claim rooms (Drop 6B)
THRESHOLD_DOMINANCE = 75    # Security upgrade + passive income (Drop 6B)
THRESHOLD_CONTROL   = 100   # Full zone branding (Drop 6B)

INFLUENCE_CAP = 150         # Max influence per org per zone

# ── Influence earn rates ─────────────────────────────────────────────────────
INFLUENCE_PRESENCE_HOURLY = 1    # Per member present in zone per hour
INFLUENCE_NPC_KILL        = 2    # Per NPC kill in zone
INFLUENCE_MISSION         = 5    # Per mission/bounty/smuggling completed in zone
INFLUENCE_PVP_WIN         = 15   # PvP kill in contested/lawless zone
INFLUENCE_INVEST_PER_1K   = 10   # Per 1,000cr invested from treasury
INFLUENCE_INVEST_MIN      = 1000 # Minimum investment amount
INFLUENCE_INVEST_MAX      = 10000 # Maximum per investment

# ── Influence decay ──────────────────────────────────────────────────────────
DECAY_NO_PRESENCE_HOURS   = 48   # Hours without members before decay starts
DECAY_RATE_PER_DAY        = 5    # Influence lost per day when decaying

# ── Claim constants (Drop 6B) ───────────────────────────────────────────────
# DEPRECATED 2026-05-24 — CLAIM_MAX_PER_ZONE and CLAIM_MAX_TOTAL retire in
# SYN.1 per contestable_wilderness_design_v2.md §6. Region ownership is
# 1-owner-per-region with no per-org cap — orgs CAN hold every wilderness
# region simultaneously if they can defend them. (NOTE: the design doc
# +TODO.json listed these as MAX_CLAIMS_PER_ZONE / MAX_CLAIMS_PER_ORG;
# the actual symbol names are CLAIM_MAX_PER_ZONE / CLAIM_MAX_TOTAL —
# SYN.0 pre-flight correction.)
CLAIM_COST            = 5000   # Credits from org treasury per room claim
CLAIM_WEEKLY_MAINT    = 200    # Credits per week per claimed room
# CLAIM_MAX_PER_ZONE and CLAIM_MAX_TOTAL retired in SYN.1.b
# (2026-05-24). Per design §1.2 region ownership has no per-org
# cap. Keeping breadcrumb so future greps find this.
CLAIM_MIN_RANK        = 3      # Minimum org rank to claim/unclaim

# ── Guard constants (Drop 6C) ────────────────────────────────────────────────
GUARD_COST            = 500    # One-time cost to station a guard
GUARD_WEEKLY_UPKEEP   = 100    # Added to room maintenance cost when guard active
GUARD_MIN_RANK        = 3      # Minimum org rank to manage guards

# Guard NPC stat templates by org flavor
_GUARD_TEMPLATES = {
    "empire": {
        "name_prefix": "Imperial Garrison Guard",
        "species": "Human",
        "description": (
            "A stormtrooper in scuffed white armor stands watch, blaster rifle "
            "held at a businesslike angle. An Imperial crest is stenciled on the "
            "shoulder plate."
        ),
        "dex": "3D+1", "blaster": "5D", "dodge": "4D",
        "brawling": "3D+1", "str": "3D+1", "per": "3D",
        "weapon": "Blaster Rifle (5D)",
        "faction": "Imperial",
    },
    "rebel": {
        "name_prefix": "Alliance Sentry",
        "species": "Human",
        "description": (
            "A lean figure in mismatched rebel gear keeps a cautious watch. "
            "A battered A280 rifle is slung across their back, ready for trouble."
        ),
        "dex": "3D+1", "blaster": "4D+2", "dodge": "4D",
        "brawling": "3D", "str": "3D", "per": "3D+1",
        "weapon": "Blaster Rifle (5D)",
        "faction": "Rebel Alliance",
    },
    "hutt": {
        "name_prefix": "Cartel Enforcer",
        "species": "Gamorrean",
        "description": (
            "A hulking Gamorrean enforcer in mismatched armor stands at the "
            "entrance, meaty hands resting on a vibroaxe haft. It eyes you "
            "with dim suspicion."
        ),
        "dex": "2D+2", "blaster": "3D+1", "dodge": "3D",
        "brawling": "5D", "str": "4D", "per": "2D+1",
        "weapon": "Vibroaxe (STR+3D)",
        "faction": "Hutt Cartel",
    },
    "bh_guild": {
        "name_prefix": "Guild Watchman",
        "species": "Human",
        "description": (
            "A sharp-eyed hunter in practical armor leans against the wall, "
            "arms crossed. A Mandalorian-pattern holster sits low on one hip. "
            "The Guild insignia is etched into their chest plate."
        ),
        "dex": "3D+2", "blaster": "5D+1", "dodge": "4D+1",
        "brawling": "4D", "str": "3D+1", "per": "4D",
        "weapon": "Heavy Blaster Pistol (5D)",
        "faction": "Bounty Hunters' Guild",
    },
    # ── B.1.c (Apr 29 2026) — CW guard templates ─────────────────────
    # Mirrors the GCW four-faction shape with era-appropriate species,
    # gear, and flavor. A CW PC's claimed room gets a thematically
    # correct guard instead of falling through to the generic
    # "_default" template.
    "republic": {
        "name_prefix": "Republic Garrison Guard",
        "species": "Clone Trooper",
        "description": (
            "A clone trooper in standard Phase II armor stands watch with "
            "a DC-15A blaster rifle held at the ready. The Republic crest "
            "is stenciled in faded blue across the shoulder plate."
        ),
        "dex": "3D+1", "blaster": "5D", "dodge": "4D",
        "brawling": "3D+2", "str": "3D+2", "per": "3D",
        "weapon": "DC-15A Blaster Rifle (5D)",
        "faction": "Galactic Republic",
    },
    "cis": {
        "name_prefix": "CIS Battle Droid",
        "species": "B1 Battle Droid",
        "description": (
            "A B1 battle droid stands at attention with an E-5 blaster rifle. "
            "Its movements are slightly jerky, but its programming will not "
            "hesitate. A Separatist hex is painted on its chest plate."
        ),
        "dex": "3D", "blaster": "4D+1", "dodge": "3D",
        "brawling": "3D", "str": "3D+1", "per": "2D+2",
        "weapon": "E-5 Blaster Rifle (4D+1)",
        "faction": "Confederacy",
    },
    "jedi_order": {
        "name_prefix": "Temple Sentinel",
        "species": "Human",
        "description": (
            "A Jedi sentinel in tan robes stands quietly, hands folded into "
            "their sleeves. A lightsaber hangs at their belt. They watch "
            "without speaking — and they see everything."
        ),
        "dex": "4D", "blaster": "3D", "dodge": "5D",
        "brawling": "4D", "str": "3D", "per": "4D+1",
        "weapon": "Lightsaber (5D)",
        "faction": "Jedi Order",
    },
    "hutt_cartel": {
        "name_prefix": "Cartel Enforcer",
        "species": "Gamorrean",
        "description": (
            "A hulking Gamorrean enforcer in mismatched armor stands at the "
            "entrance, meaty hands resting on a vibroaxe haft. It eyes you "
            "with dim suspicion."
        ),
        "dex": "2D+2", "blaster": "3D+1", "dodge": "3D",
        "brawling": "5D", "str": "4D", "per": "2D+1",
        "weapon": "Vibroaxe (STR+3D)",
        "faction": "Hutt Cartel",
    },
    "bounty_hunters_guild": {
        "name_prefix": "Guild Hunter",
        "species": "Human",
        "description": (
            "A scarred hunter in well-worn armor leans against the wall, arms "
            "crossed. A heavy holster sits low on one hip and a tracking fob "
            "winks from a chest pocket."
        ),
        "dex": "3D+2", "blaster": "5D+1", "dodge": "4D+1",
        "brawling": "4D", "str": "3D+1", "per": "4D",
        "weapon": "Heavy Blaster Pistol (5D)",
        "faction": "Bounty Hunters' Guild",
    },
    "_default": {
        "name_prefix": "Territory Guard",
        "species": "Human",
        "description": (
            "A rough-looking guard stands watch, hand resting on a holstered "
            "blaster. They scan every entrant with professional wariness."
        ),
        "dex": "3D", "blaster": "4D", "dodge": "3D+2",
        "brawling": "3D+1", "str": "3D", "per": "3D",
        "weapon": "Blaster Pistol (4D)",
        "faction": "Independent",
    },
}

# ── Resource node constants (Drop 6C) ────────────────────────────────────────
# Daily tick yields per claimed room by zone security level + influence tier.
# Format: (resource_type, min_qty, max_qty, credit_bonus)
_RESOURCE_YIELDS = {
    # (security, influence_tier) → list of possible yields
    ("contested", "foothold"):   [("credits", 50,  150,  0)],
    ("contested", "dominant"):   [("credits", 100, 300,  0),
                                   ("metal",   1,   2,   0)],
    ("contested", "control"):    [("credits", 150, 400,  0),
                                   ("metal",   1,   3,   0),
                                   ("chemical", 1,  2,   0)],
    ("lawless",   "foothold"):   [("credits", 75,  200,  0),
                                   ("metal",   1,   2,   0)],
    ("lawless",   "dominant"):   [("credits", 150, 400,  0),
                                   ("metal",   2,   4,   0),
                                   ("chemical", 1,  3,   0)],
    ("lawless",   "control"):    [("credits", 200, 600,  0),
                                   ("metal",   2,   5,   0),
                                   ("chemical", 2,  4,   0),
                                   ("rare",     1,  2,   0)],
}

# Org storage limits
ORG_STORAGE_MAX_ITEMS    = 50    # Max items in org shared storage
ORG_STORAGE_MAX_RESOURCES = 200  # Max total resource units in org storage

# ── Org code → Director axis mapping ────────────────────────────────────────
# Maps an organization-axis code (what's stored in `char.faction_id`) to
# the director-axis code (what's used by zone-influence aggregation +
# Director AI narration). The director axis is always one of:
# imperial / rebel / criminal / independent (era-stable; the rewicker
# in director_config.yaml handles era display for these labels).
#
# Mapping rationale (mirrors data/worlds/clone_wars/organizations.yaml's
# legacy_rewicker reverse direction):
#   GCW: empire→imperial, rebel→rebel, hutt→criminal, bh_guild→independent
#   CW:  republic→imperial, cis→rebel, jedi_order→imperial,
#        hutt_cartel→criminal, bounty_hunters_guild→independent
#
# Unmapped codes fall through to "independent" via the .get() default
# at every call site.
ORG_TO_AXIS = {
    # ── GCW ──
    "empire":                "imperial",
    "rebel":                 "rebel",
    "hutt":                  "criminal",
    "bh_guild":              "independent",
    # ── CW (B.1.c, Apr 29 2026) ──
    "republic":              "imperial",   # lawful state authority
    "cis":                   "rebel",      # insurgent challenger
    "jedi_order":            "imperial",   # Jedi serve the Republic
    "hutt_cartel":           "criminal",
    "bounty_hunters_guild":  "independent",
}


# ── Schema (auto-created on startup) ────────────────────────────────────────

TERRITORY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS territory_influence (
    zone_id       INTEGER NOT NULL,
    org_code      TEXT    NOT NULL,
    score         INTEGER NOT NULL DEFAULT 0,
    last_activity REAL    NOT NULL DEFAULT 0,
    last_presence REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, org_code)
);
CREATE TABLE IF NOT EXISTS territory_claims (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_code      TEXT    NOT NULL,
    room_id       INTEGER NOT NULL UNIQUE,
    zone_id       INTEGER NOT NULL,
    claimed_by    INTEGER NOT NULL,
    claimed_at    REAL    NOT NULL,
    maintenance   INTEGER NOT NULL DEFAULT 200,
    guard_npc_id  INTEGER DEFAULT NULL
);
"""


async def ensure_territory_schema(db) -> None:
    """Create territory tables if they don't exist. Idempotent."""
    try:
        for stmt in TERRITORY_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception as e:
        log.warning("[territory] schema create error: %s", e)
    # SYN.1.a (May 24 2026): region ownership tables (Contestable
    # Wilderness pivot). Per contestable_wilderness_design_v2.md §3.1.
    await ensure_region_ownership_schema(db)
    # SYN.3 (2026-05-25): region-keyed contest tables
    # (region_contests + region_contest_cooldowns) per
    # contestable_wilderness_design_v2.md §2.4 + §3.3. The legacy
    # Drop 6D ``ensure_contest_schema(db)`` call was deleted in the
    # same drop — Drop 6D block physically retired.
    try:
        from engine.contest import ensure_region_contest_schema
        await ensure_region_contest_schema(db)
    except Exception as e:
        log.warning("[territory] SYN.3 contest schema wire-up failed: %s", e)
    # SYN.1.b (May 24 2026): one-shot cold-start wipe of
    # territory_claims per design §1.4. Idempotent via the
    # syn_migration_state row.
    await _syn1b_wipe_territory_claims_once(db)


# ── Core influence adjustment ────────────────────────────────────────────────

async def adjust_territory_influence(db, org_code: str, zone_id: int,
                                      delta: int, reason: str = "",
                                      *,
                                      region_slug: Optional[str] = None) -> int:
    """
    Adjust territory influence for an org in a zone.
    All influence changes MUST go through this function.
    Returns the new influence score.

    SYN.3 (2026-05-25): optional ``region_slug`` kwarg. When passed
    and an active region contest exists for that region with this
    org as a contestant, applies the contest influence multipliers
    (2× doubling for both sides + 1.5× outnumbered-defender bonus
    on top, defender-side only) via
    ``engine.contest.apply_contest_influence_multipliers``. Callers
    that don't pass ``region_slug`` are unaffected (backward
    compatible). Domain hooks (missions, bounties, harvests) wire
    the region context when they land in SYN.5 / SYN.6.

    Also: positive deltas trigger the region-contest auto-trigger
    check via ``engine.contest.check_and_declare_region_contests``
    when ``region_slug`` is provided. (The legacy zone-keyed
    auto-trigger ``check_and_declare_contests`` was removed in SYN.3
    along with the rest of the Drop 6D contest block.)
    """
    now = time.time()

    # SYN.3: apply contest multipliers to positive deltas when the
    # caller knows the region context.
    if region_slug and delta > 0:
        try:
            from engine.contest import apply_contest_influence_multipliers
            multiplied = await apply_contest_influence_multipliers(
                db, org_code, region_slug, delta)
            if multiplied != delta:
                log.info(
                    "[territory] contest multiplier: %s in %s "
                    "%d -> %d (reason=%s)",
                    org_code, region_slug, delta, multiplied, reason)
            delta = multiplied
        except Exception:
            log.warning(
                "[territory] contest multiplier failed (passthrough)",
                exc_info=True)

    rows = await db.fetchall(
        "SELECT score FROM territory_influence WHERE zone_id = ? AND org_code = ?",
        (zone_id, org_code),
    )
    current = rows[0]["score"] if rows else 0
    new_score = max(0, min(INFLUENCE_CAP, current + delta))

    await db.execute(
        """INSERT INTO territory_influence (zone_id, org_code, score, last_activity, last_presence)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(zone_id, org_code) DO UPDATE SET
             score = excluded.score,
             last_activity = excluded.last_activity""",
        (zone_id, org_code, new_score, now, now),
    )
    await db.commit()

    if delta != 0:
        log.info("[territory] %s influence in zone %d: %d -> %d (%s%d) %s",
                 org_code, zone_id, current, new_score,
                 "+" if delta > 0 else "", delta, reason)

        # T3.19 telemetry: adjust_territory_influence is the SINGLE funnel for
        # ALL territory-control movement (the influence analog of credit_flow
        # riding log_credit), so one emit here captures every influence change
        # by org / zone / source — the post-launch "who is contesting or holding
        # which zones, and what drives it" balance signal. Fail-open +
        # buffer-only: it can NEVER block or disturb the influence path it
        # observes. ``clamped`` flags a delta that hit the floor (0) or the
        # INFLUENCE_CAP ceiling, so a zone pinned at cap is visible offline.
        # Keep-rate is a use-site tunable per the T3.19 contract (1.0 at
        # launch's small population; dial down later).
        try:
            from engine.telemetry import emit as _tele_emit
            from engine.tunables import get_tunable
            _tele_emit("influence", {
                "org": org_code,
                "zone_id": zone_id,
                "delta": int(delta),
                "score": int(new_score),
                "prev": int(current),
                "clamped": (current + delta) != new_score,
                "reason": reason or "",
                "region": region_slug or "",
            }, sample=float(get_tunable("telemetry.influence_sample", 1.0)))
        except Exception as _e:
            log.debug("influence telemetry emit failed: %s", _e)

    # SYN.3: region-contest auto-trigger on positive deltas, when the
    # caller supplied a region slug. The legacy zone-keyed
    # check_and_declare_contests was removed in SYN.3 along with the
    # rest of Drop 6D contests.
    if delta > 0 and region_slug:
        try:
            from engine.contest import check_and_declare_region_contests
            await check_and_declare_region_contests(
                db, org_code, region_slug)
        except Exception as _e:
            log.warning("[territory] region contest check error: %s", _e)

    return new_score


async def get_territory_influence(db, org_code: str, zone_id: int) -> int:
    """Get current influence score for an org in a zone."""
    rows = await db.fetchall(
        "SELECT score FROM territory_influence WHERE zone_id = ? AND org_code = ?",
        (zone_id, org_code),
    )
    return rows[0]["score"] if rows else 0


async def get_zone_territory_all(db, zone_id: int) -> dict[str, int]:
    """Get all org influence scores for a zone. Returns {org_code: score}."""
    rows = await db.fetchall(
        "SELECT org_code, score FROM territory_influence WHERE zone_id = ? AND score > 0",
        (zone_id,),
    )
    return {r["org_code"]: r["score"] for r in rows}


async def get_org_territory_all(db, org_code: str) -> dict[int, int]:
    """Get all zone influence scores for an org. Returns {zone_id: score}."""
    rows = await db.fetchall(
        "SELECT zone_id, score FROM territory_influence WHERE org_code = ? AND score > 0",
        (org_code,),
    )
    return {r["zone_id"]: r["score"] for r in rows}


# ── Room / Zone helpers ──────────────────────────────────────────────────────

async def get_room_zone_id(db, room_id: int) -> Optional[int]:
    """Resolve a room's integer zone ID. Returns None if no zone."""
    room = await db.get_room(room_id)
    if room and room.get("zone_id"):
        return room["zone_id"]
    return None


async def get_zone_name(db, zone_id: int) -> str:
    """Get human-readable zone name."""
    zone = await db.get_zone(zone_id)
    if zone:
        return zone.get("name", f"Zone #{zone_id}")
    return f"Zone #{zone_id}"


async def get_zone_security(db, zone_id: int) -> str:
    """Get the base security level of a zone from its properties."""
    zone = await db.get_zone(zone_id)
    if not zone:
        return "contested"
    props = zone.get("properties", "{}")
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except Exception:
            props = {}
    return props.get("security", "contested")


# ── Influence earning hooks ──────────────────────────────────────────────────
#
# SYN.5 (2026-05-25): two-tier reward rule per design v2 §2.7.
#   * City-map activity (room has no wilderness_region_id):
#         rep + credits + CP only. NO influence delta.
#   * Wilderness activity (room has wilderness_region_id set):
#         rep + credits + CP + influence delta. The delta is routed
#         through ``adjust_territory_influence(..., region_slug=...)``
#         so SYN.3's contest multipliers (2× during active contest;
#         1.5× outnumbered-defender on top, defender-side only) apply
#         automatically.
#
# All three hooks share the same shape: resolve the room's
# wilderness_region_id; if it's NULL the hook becomes a no-op for
# influence purposes (the rep/credit/CP award lives in the caller,
# not here). If it's set, look up the parent zone for the influence
# row and pass region_slug down so contest multipliers fire.
#
# The rep/credits/CP awards live in their respective subsystems
# (engine.missions, engine.bounty_board, engine.organizations.adjust_rep,
# etc.) and are unaffected by this gate — those keep firing on every
# completion regardless of room location.

async def _resolve_room_region(db, room_id: int) -> tuple[Optional[str], Optional[int]]:
    """Return (wilderness_region_id, zone_id) for a room.

    Either tuple element may be None: ``wilderness_region_id`` is NULL
    for city-map rooms; ``zone_id`` is NULL for orphan rooms (no zone
    declared). Both NULLs are valid runtime states.
    """
    try:
        room = await db.get_room(room_id)
    except Exception:
        room = None
    if not room:
        return (None, None)
    return (room.get("wilderness_region_id"), room.get("zone_id"))


async def on_npc_kill(db, char: dict, room_id: int) -> None:
    """Called when a player kills an NPC.

    SYN.5: grants influence ONLY in wilderness rooms (rooms with a
    ``wilderness_region_id``). City-map kills are zero-influence per
    design §2.7. The 2-influence NPC-kill delta applies via the
    region-keyed code path so SYN.3 contest multipliers fire.
    """
    org_code = char.get("faction_id", "independent")
    if not org_code or org_code == "independent":
        return
    region_slug, zone_id = await _resolve_room_region(db, room_id)
    if region_slug is None:
        # City-map NPC kill: no influence delta. The killer's rep +
        # combat XP awards live in the caller and still fire.
        return
    if zone_id is None:
        # Region has no resolvable parent zone — defensive skip.
        return
    await adjust_territory_influence(
        db, org_code, zone_id, INFLUENCE_NPC_KILL,
        reason=f"NPC kill by {char.get('name', '?')} in {region_slug}",
        region_slug=region_slug)


async def on_mission_complete(db, char: dict, room_id: int) -> None:
    """Called on mission/bounty/smuggling completion.

    SYN.5: grants influence ONLY in wilderness rooms per design §2.7.
    The MISSION constant (5) covers all three completion types —
    missions, bounties, and smuggling — per the design table's
    matching values.
    """
    org_code = char.get("faction_id", "independent")
    if not org_code or org_code == "independent":
        return
    region_slug, zone_id = await _resolve_room_region(db, room_id)
    if region_slug is None:
        return
    if zone_id is None:
        return
    await adjust_territory_influence(
        db, org_code, zone_id, INFLUENCE_MISSION,
        reason=f"mission complete by {char.get('name', '?')} in {region_slug}",
        region_slug=region_slug)


async def on_pvp_kill(db, winner: dict, loser: dict, room_id: int) -> None:
    """Called on PvP kill.

    SYN.5: winner's org gains influence, loser's loses — both ONLY in
    wilderness rooms per design §2.7. The 15-influence PvP-win delta
    matches the design table; the -5 loser penalty stays as a
    flat number (penalties don't get contest-multiplied in
    apply_contest_influence_multipliers — negatives short-circuit).

    Per design §2.7 row "PvP kill": city-map PvP requires consent
    (which is enforced upstream in combat_commands.py's PvP gate)
    and yields zero influence either way. Wilderness PvP yields
    +15 to the winner, -5 to the loser.
    """
    winner_org = winner.get("faction_id", "independent")
    loser_org = loser.get("faction_id", "independent")
    region_slug, zone_id = await _resolve_room_region(db, room_id)
    if region_slug is None:
        # City-map PvP: consent-gated, no influence delta either way.
        return
    if zone_id is None:
        return
    if winner_org and winner_org != "independent":
        await adjust_territory_influence(
            db, winner_org, zone_id, INFLUENCE_PVP_WIN,
            reason=f"PvP victory by {winner.get('name', '?')} in {region_slug}",
            region_slug=region_slug)
    if loser_org and loser_org != "independent":
        await adjust_territory_influence(
            db, loser_org, zone_id, -5,
            reason=f"PvP defeat of {loser.get('name', '?')} in {region_slug}",
            region_slug=region_slug)


async def invest_influence(db, char: dict, org_code: str,
                            amount: int) -> dict:
    """
    Invest credits from org treasury into zone influence.
    Returns {"ok": bool, "msg": str}.
    """
    if amount < INFLUENCE_INVEST_MIN:
        return {"ok": False,
                "msg": f"Minimum investment: {INFLUENCE_INVEST_MIN:,}cr."}
    if amount > INFLUENCE_INVEST_MAX:
        return {"ok": False,
                "msg": f"Maximum investment per action: {INFLUENCE_INVEST_MAX:,}cr."}

    room_id = char.get("room_id")
    zone_id = await get_room_zone_id(db, room_id)
    if zone_id is None:
        return {"ok": False, "msg": "You're not in a zone that can receive investment."}

    sec = await get_zone_security(db, zone_id)
    if sec == "secured":
        return {"ok": False,
                "msg": "This zone is under Imperial control. You can't establish a territorial foothold here."}

    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Unknown organization: {org_code}"}
    if org.get("treasury", 0) < amount:
        return {"ok": False,
                "msg": f"Insufficient treasury. Balance: {org.get('treasury', 0):,}cr."}

    mem = await db.get_membership(char["id"], org["id"])
    if not mem or mem.get("rank_level", 0) < 3:
        return {"ok": False,
                "msg": "You need rank 3 or higher to invest in territory."}

    new_balance = await db.adjust_org_treasury(org["id"], -amount)

    influence_gain = (amount // 1000) * INFLUENCE_INVEST_PER_1K
    zone_name = await get_zone_name(db, zone_id)
    new_score = await adjust_territory_influence(
        db, org_code, zone_id, influence_gain,
        reason=f"investment by {char.get('name', '?')}")

    return {
        "ok": True,
        "msg": (f"Invested {amount:,}cr in {zone_name}. "
                f"Influence: +{influence_gain} (now {new_score}). "
                f"Treasury: {new_balance:,}cr."),
    }


# ── Presence tick ────────────────────────────────────────────────────────────

async def tick_territory_presence(db, session_mgr) -> None:
    """
    Hourly tick: grant +1 influence per org member present in a zone.
    Also updates last_presence timestamps for decay tracking.
    """
    try:
        zone_orgs: dict[int, dict[str, int]] = {}

        for sess in session_mgr.all:
            if not sess.is_in_game or not sess.character:
                continue
            char = sess.character
            org_code = char.get("faction_id", "independent")
            if not org_code or org_code == "independent":
                continue
            room_id = char.get("room_id")
            if not room_id:
                continue
            zone_id = await get_room_zone_id(db, room_id)
            if zone_id is None:
                continue

            if zone_id not in zone_orgs:
                zone_orgs[zone_id] = {}
            zone_orgs[zone_id][org_code] = zone_orgs[zone_id].get(org_code, 0) + 1

        now = time.time()
        for zone_id, orgs in zone_orgs.items():
            for org_code, count in orgs.items():
                gain = INFLUENCE_PRESENCE_HOURLY * count
                await adjust_territory_influence(
                    db, org_code, zone_id, gain,
                    reason=f"presence ({count} members)")
                await db.execute(
                    """UPDATE territory_influence SET last_presence = ?
                       WHERE zone_id = ? AND org_code = ?""",
                    (now, zone_id, org_code),
                )

        await db.commit()
    except Exception as e:
        log.warning("[territory] presence tick error: %s", e)


# ── Decay tick ───────────────────────────────────────────────────────────────

async def tick_territory_decay(db) -> None:
    """
    Daily tick: decay influence for orgs with no recent presence.
    Run once per day (86400 ticks).
    """
    try:
        now = time.time()
        cutoff = now - (DECAY_NO_PRESENCE_HOURS * 3600)

        rows = await db.fetchall(
            """SELECT zone_id, org_code, score, last_presence
               FROM territory_influence
               WHERE score > 0 AND last_presence < ?""",
            (cutoff,),
        )

        for r in rows:
            await adjust_territory_influence(
                db, r["org_code"], r["zone_id"], -DECAY_RATE_PER_DAY,
                reason="no presence decay")

    except Exception as e:
        log.warning("[territory] decay tick error: %s", e)


# ── Display helpers ──────────────────────────────────────────────────────────

def _threshold_label(score: int) -> str:
    """Return ANSI-colored threshold label for a score."""
    if score >= THRESHOLD_CONTROL:
        return "\033[1;32m[CONTROL]\033[0m"
    elif score >= THRESHOLD_DOMINANCE:
        return "\033[1;36m[DOMINANT]\033[0m"
    elif score >= THRESHOLD_FOOTHOLD:
        return "\033[1;33m[FOOTHOLD]\033[0m"
    elif score >= THRESHOLD_PRESENCE:
        return "\033[2m[PRESENCE]\033[0m"
    return ""


def _influence_bar(score: int, width: int = 20) -> str:
    """Return a simple ASCII bar for influence score."""
    filled = min(width, int((score / INFLUENCE_CAP) * width))
    return "\033[1;36m" + "█" * filled + "\033[2m" + "░" * (width - filled) + "\033[0m"


async def get_influence_status_lines(db, org_code: str) -> list[str]:
    """Return formatted influence status across all zones for an org."""
    all_inf = await get_org_territory_all(db, org_code)
    if not all_inf:
        return [
            "\033[1;37m── Territory Influence ──\033[0m",
            f"  {org_code.title()} has no territorial influence.",
            "",
            "  Earn influence by:",
            "    - Having members present in contested/lawless zones",
            "    - Killing NPCs, completing missions",
            "    - Investing from faction treasury: \033[1;37mfaction invest <amount>\033[0m",
        ]

    lines = ["\033[1;37m── Territory Influence ──\033[0m"]
    for zone_id, score in sorted(all_inf.items(), key=lambda x: -x[1]):
        zone_name = await get_zone_name(db, zone_id)
        tier = _threshold_label(score)
        lines.append(
            f"  {zone_name:<35} {_influence_bar(score)} {score:>3}/{INFLUENCE_CAP} {tier}"
        )

    lines.append("")
    lines.append(f"  Thresholds: 25 Presence · 50 Foothold · 75 Dominant · 100 Control")
    return lines


async def get_zone_influence_line(db, zone_id: int) -> Optional[str]:
    """
    Return a single-line influence presence message for look output.
    Returns None if no org has 25+ influence in this zone.
    """
    all_inf = await get_zone_territory_all(db, zone_id)
    if not all_inf:
        return None

    dominant_org = None
    dominant_score = 0
    for org_code, score in all_inf.items():
        if score >= THRESHOLD_PRESENCE and score > dominant_score:
            dominant_org = org_code
            dominant_score = score

    if not dominant_org:
        return None

    flavor = {
        # ── GCW ──
        "empire":               "The Empire's presence is felt here — patrols and informants.",
        "rebel":                "Rebel Alliance influence stirs quietly in the shadows.",
        "hutt":                 "The Hutt Cartel's grip extends to these streets.",
        "bh_guild":             "Bounty Hunters' Guild operatives watch from the corners.",
        # ── CW (B.1.c) ──
        "republic":             "Republic patrols and clone trooper presence are felt here.",
        "cis":                  "Separatist sympathizers and droid scouts move quietly here.",
        "jedi_order":           "Jedi presence pervades this place — quiet, watchful, alert.",
        "hutt_cartel":          "The Hutt Cartel's grip extends to these streets.",
        "bounty_hunters_guild": "Guild hunters watch from the corners, ledgers in hand.",
    }
    msg = flavor.get(dominant_org, f"{dominant_org.title()} influence is felt here.")
    return f"  \033[2m{msg}\033[0m"


# ── Director digest integration ──────────────────────────────────────────────

async def get_territory_digest(db) -> dict:
    """
    Compile territory data for the Director AI's digest.
    Returns {zone_name: {org_code: score}} for zones with any influence.
    """
    try:
        rows = await db.fetchall(
            "SELECT zone_id, org_code, score FROM territory_influence WHERE score > 0"
        )
        if not rows:
            return {}

        result = {}
        for r in rows:
            zone_name = await get_zone_name(db, r["zone_id"])
            if zone_name not in result:
                result[zone_name] = {}
            result[zone_name][r["org_code"]] = r["score"]
        return result
    except Exception as e:
        log.warning("[territory] digest compile error: %s", e)
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6B: Room Claiming
# ══════════════════════════════════════════════════════════════════════════════

async def get_claim(db, room_id: int) -> Optional[dict]:
    """Get the territory claim for a room, or None."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM territory_claims WHERE room_id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_claim: unhandled exception", exc_info=True)
        return None


async def get_org_claims(db, org_code: str) -> list[dict]:
    """Get all claims for an organization."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM territory_claims WHERE org_code = ? ORDER BY claimed_at",
            (org_code,),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_org_claims: unhandled exception", exc_info=True)
        return []


async def get_org_claims_in_zone(db, org_code: str, zone_id: int) -> list[dict]:
    """Get claims for an org in a specific zone."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM territory_claims WHERE org_code = ? AND zone_id = ?",
            (org_code, zone_id),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_org_claims_in_zone: unhandled exception", exc_info=True)
        return []


async def claim_room(db, char: dict, org_code: str, room_id: int) -> dict:
    """RETIRED in SYN.1.b (2026-05-24) per
    ``contestable_wilderness_design_v2.md`` §6. Per-room claim
    semantics retired in favor of region ownership; use
    ``claim_region(db, char, org_code, wilderness_region_slug)``.

    Returns a constant rejection. The function remains callable so
    legacy import sites compile without modification, but no claim
    ever lands.
    """
    return {
        "ok": False,
        "msg": ("Per-room territory claims have been retired. Use "
                "'faction claim' on a wilderness region instead — "
                "see help faction territory for details."),
    }


async def unclaim_room(db, char: dict, org_code: str, room_id: int) -> dict:
    """RETIRED in SYN.1.b (2026-05-24). Use ``unclaim_region``."""
    return {
        "ok": False,
        "msg": ("Per-room territory claims have been retired. Use "
                "'faction unclaim' on the region instead."),
    }


async def get_claim_display_tag(db, room_id: int) -> Optional[str]:
    """
    Return an ANSI-formatted claim tag for look output, or None.
    E.g. " [CLAIMED — Hutt Cartel]"
    """
    claim = await get_claim(db, room_id)
    if not claim:
        return None
    org_colors = {
        # ── GCW ──
        "empire":               "\033[1;34m",
        "rebel":                "\033[1;31m",
        "hutt":                 "\033[1;33m",
        "bh_guild":             "\033[1;35m",
        # ── CW (B.1.c) ──
        # Colors mirror data/worlds/clone_wars/organizations.yaml properties.color
        # so claim tags display in the same color as the faction's flagged hue.
        "republic":             "\033[1;34m",   # bold blue
        "cis":                  "\033[1;31m",   # bold red
        "jedi_order":           "\033[1;36m",   # bold cyan
        "hutt_cartel":          "\033[1;33m",   # bold yellow
        "bounty_hunters_guild": "\033[1;35m",   # bold magenta
    }
    color = org_colors.get(claim["org_code"], "\033[1;37m")
    org_name = claim["org_code"].replace("_", " ").title()
    return f" {color}[CLAIMED \u2014 {org_name}]\033[0m"


async def is_room_claimed_by(db, room_id: int, org_code: str) -> bool:
    """RETIRED in SYN.1.b (2026-05-24). Per-room claims no longer
    exist; this stub always returns False so any remaining consumers
    behave as if the room is un-claimed (the truth, post-wipe).
    Region-scope callers should use ``is_region_owned_by`` instead.
    """
    return False


# ── Claim maintenance tick ───────────────────────────────────────────────────

async def tick_claim_maintenance(db, session_mgr) -> None:
    """RETIRED in SYN.1.b (2026-05-24). Use ``tick_region_maintenance``.

    No-op stub. The scheduler in server/tick_handlers_economy.py was
    retargeted to call ``tick_region_maintenance`` instead. If any
    other caller imports this by name, the call is a safe no-op.
    """
    return None


async def get_claims_status_lines(db, org_code: str) -> list[str]:
    """Return formatted list of owned regions for an org.

    SYN.1.b (2026-05-24): retargeted from per-room claim display to
    region ownership display. Function name preserved for caller
    compatibility (parser/faction_commands.py imports this by name);
    body iterates ``region_ownership`` instead of ``territory_claims``.
    """
    regions = await get_org_regions(db, org_code)
    if not regions:
        return [
            "  No territory owned.",
            f"  Build influence to {THRESHOLD_FOOTHOLD}+ in a wilderness "
            f"region, then use \033[1;37mfaction claim\033[0m to claim it.",
        ]
    lines = ["\033[1;37m── Owned Regions ──\033[0m"]
    for r in regions:
        slug = r.get("region_slug", "?")
        upkeep = int(r.get("maintenance") or
                     (REGION_WEEKLY_MAINT + REGION_GARRISON_WEEKLY))
        lines.append(f"  {slug:<30}  {upkeep}cr/wk")
    lines.append(f"  ({len(regions)} region{'s' if len(regions) != 1 else ''} owned)")
    # Append active region-contest info (SYN.3: region-keyed).
    try:
        from engine.contest import get_region_contest_status_lines
        contest_lines = await get_region_contest_status_lines(db, org_code)
    except Exception:
        contest_lines = []
    if contest_lines:
        lines.append("")
        lines.extend(contest_lines)
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6C: Guard NPC Spawning
# ══════════════════════════════════════════════════════════════════════════════

def _build_guard_sheet(tmpl: dict) -> dict:
    """Build a char_sheet dict for a guard NPC from a template."""
    return {
        "attributes": {
            "dexterity":  tmpl["dex"],
            "knowledge":  "2D",
            "mechanical": "2D",
            "perception": tmpl["per"],
            "strength":   tmpl["str"],
            "technical":  "2D",
        },
        "skills": {
            "blaster":         tmpl["blaster"],
            "dodge":           tmpl["dodge"],
            "brawling":        tmpl["brawling"],
            "intimidation":    "3D",
            "search":          "3D",
        },
        "weapon":            tmpl["weapon"],
        "species":           tmpl["species"],
        "wound_level":       0,
        "move":              10,
        "force_points":      0,
        "character_points":  0,
        "dark_side_points":  0,
    }


def _build_guard_ai(tmpl: dict, org_code: str) -> dict:
    """Build an ai_config dict for a guard NPC."""
    guard_name = tmpl["name_prefix"]
    return {
        "personality": (
            f"A loyal {tmpl['faction']} guard stationed here by order of "
            f"their organization. Challenges non-members and fights anyone "
            f"who threatens the territory. Terse, alert, professional."
        ),
        "knowledge": [
            f"Guards territory claimed by {org_code}",
            "Challenges anyone without proper affiliation",
            "Reports intruders to faction leadership",
        ],
        "faction":          tmpl["faction"],
        "dialogue_style":   "terse",
        "fallback_lines": [
            f"{guard_name} eyes you coldly. \"Move along.\"",
            f"{guard_name} shifts their weapon grip meaningfully.",
            f"{guard_name} says, \"This area is under {tmpl['faction']} control.\"",
        ],
        "hostile":          False,   # challenges but does not auto-attack
        "combat_behavior":  "aggressive",
        "guard_for_org":    org_code,  # custom flag for NPC AI to check membership
        "model_tier":       1,
        "temperature":      0.5,
        "max_tokens":       80,
    }


async def spawn_guard_npc(db, org_code: str, room_id: int,
                           char_id: int) -> dict:
    """RETIRED in SYN.1.b (2026-05-24). Region garrison spawning is
    automatic on ``claim_region`` — there is no per-room guard
    stationing under the region model.
    """
    return {
        "ok": False,
        "msg": ("Per-room guard stationing has been retired. Region "
                "garrisons are deployed automatically when you claim "
                "a wilderness region."),
        "npc_id": None,
    }


async def remove_guard_npc(db, org_code: str, room_id: int,
                            char_id: int = 0, **kwargs) -> dict:
    """RETIRED in SYN.1.b (2026-05-24). No-op stub (per-room guards
    no longer exist). Accepts ``**kwargs`` because at least one HQ-
    cleanup caller in engine/housing.py used ``force=True``; that
    kwarg never matched the old signature either, so the call was
    silently failing — preserving the kwarg-tolerance keeps the
    behavior identical.
    """
    return {"ok": True, "msg": ""}


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6C: Resource Node Tick
# ══════════════════════════════════════════════════════════════════════════════

def _get_influence_tier(score: int) -> str:
    """Return the tier string for resource yield lookup."""
    if score >= THRESHOLD_CONTROL:
        return "control"
    elif score >= THRESHOLD_DOMINANCE:
        return "dominant"
    elif score >= THRESHOLD_FOOTHOLD:
        return "foothold"
    return "none"


async def tick_resource_nodes(db, session_mgr) -> None:
    """RETIRED in SYN.1.b (2026-05-24). Use ``tick_region_passive_yield``.

    No-op stub. Active harvest ships in SYN.6.
    """
    return None


def _random_resource_quality(sec: str, influence: int) -> int:
    """Generate a resource quality value (1-100) based on zone and influence."""
    base = 30 if sec == "contested" else 45
    bonus = min(30, (influence - THRESHOLD_FOOTHOLD) // 2)
    variance = random.randint(-10, 10)
    return max(10, min(90, base + bonus + variance))


async def _notify_org_members(session_mgr, org_code: str, msg: str) -> None:
    """Send a message to all online members of an org."""
    try:
        for sess in session_mgr.all:
            if not sess.is_in_game or not sess.character:
                continue
            if sess.character.get("faction_id") == org_code:
                await sess.send_line(msg)
    except Exception as e:
        log.warning("[territory] notify org error: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6C: Org Shared Storage (Armory)
# ══════════════════════════════════════════════════════════════════════════════

async def _get_org_storage(db, org_code: str) -> dict:
    """
    Get org shared storage dict from properties JSON.
    Returns {"items": [...], "resources": [...]}.
    """
    org = await db.get_organization(org_code)
    if not org:
        return {"items": [], "resources": []}
    props_raw = org.get("properties", "{}")
    try:
        props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
    except Exception:
        props = {}
    storage = props.get("org_storage", {"items": [], "resources": []})
    if "items" not in storage:
        storage["items"] = []
    if "resources" not in storage:
        storage["resources"] = []
    return storage


async def _save_org_storage(db, org_code: str, storage: dict) -> bool:
    """
    Save org shared storage back to properties JSON.
    Returns True on success.
    """
    org = await db.get_organization(org_code)
    if not org:
        return False
    props_raw = org.get("properties", "{}")
    try:
        props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
    except Exception:
        props = {}
    props["org_storage"] = storage
    try:
        await db.execute(
            "UPDATE organizations SET properties = ? WHERE code = ?",
            (json.dumps(props), org_code),
        )
        await db.commit()
        return True
    except Exception as e:
        log.warning("[territory] save org storage error: %s", e)
        return False


async def adjust_org_storage(db, org_code: str, *,
                               resource_type: str, quantity: int,
                               quality: int = 50) -> dict:
    """
    Add crafting resources to org shared storage.
    All org storage additions MUST go through this function (for resource nodes).
    Returns {"ok": bool, "msg": str, "quality": int}.
    """
    storage = await _get_org_storage(db, org_code)
    resources = storage.get("resources", [])

    # Count total units
    total_units = sum(r.get("quantity", 0) for r in resources)
    if total_units + quantity > ORG_STORAGE_MAX_RESOURCES:
        return {"ok": False,
                "msg": f"Org armory resource storage full ({total_units}/{ORG_STORAGE_MAX_RESOURCES} units)."}

    # Try to stack with existing entry of same type and similar quality (±10)
    stacked = False
    for entry in resources:
        if entry.get("type") == resource_type and abs(entry.get("quality", 50) - quality) <= 10:
            # Merge quality as weighted average
            old_qty = entry.get("quantity", 0)
            new_qty = old_qty + quantity
            merged_quality = round((entry.get("quality", 50) * old_qty + quality * quantity) / new_qty)
            entry["quantity"] = new_qty
            entry["quality"] = merged_quality
            quality = merged_quality
            stacked = True
            break

    if not stacked:
        resources.append({"type": resource_type, "quantity": quantity, "quality": quality})

    storage["resources"] = resources
    ok = await _save_org_storage(db, org_code, storage)
    return {"ok": ok, "msg": "" if ok else "Storage save failed.", "quality": quality}


async def get_armory_lines(db, org_code: str) -> list[str]:
    """Return formatted armory contents for display."""
    storage = await _get_org_storage(db, org_code)
    items = storage.get("items", [])
    resources = storage.get("resources", [])
    total_res = sum(r.get("quantity", 0) for r in resources)

    lines = ["\033[1;37m── Faction Armory ──\033[0m"]

    if not items and not resources:
        lines.append("  The armory is empty.")
        lines.append("")
        lines.append(f"  Resources will accumulate here from territory resource nodes.")
        lines.append(f"  Members can deposit items with: \033[1;37mfaction armory deposit <item>\033[0m")
        return lines

    if resources:
        lines.append("  \033[1;36mCrafting Resources:\033[0m")
        for r in sorted(resources, key=lambda x: x.get("type", "")):
            lines.append(
                f"    {r.get('type', '?'):<15} {r.get('quantity', 0):>4}x  "
                f"quality {r.get('quality', 0):>3}"
            )
        lines.append(f"  ({total_res}/{ORG_STORAGE_MAX_RESOURCES} resource units used)")

    if items:
        lines.append("")
        lines.append("  \033[1;36mStored Items:\033[0m")
        for it in items:
            lines.append(f"    {it.get('name', '?')}")
        lines.append(f"  ({len(items)}/{ORG_STORAGE_MAX_ITEMS} item slots used)")

    return lines


async def armory_deposit_item(db, char: dict, org_code: str,
                               item_key: str) -> dict:
    """
    Deposit an item from character inventory into the org armory.
    Returns {"ok": bool, "msg": str}.
    """
    # Check character is in a claimed room for this org
    room_id = char.get("room_id")
    if not room_id:
        return {"ok": False, "msg": "You're not in a room."}
    # SYN.1.b (2026-05-24): retargeted from per-room
    # is_room_claimed_by to region-scope is_region_owned_by. Armory
    # access now requires standing in a room within a wilderness
    # region owned by the org.
    _room = await db.get_room(room_id)
    _region_slug = (_room or {}).get("wilderness_region_id")
    if not _region_slug or not await is_region_owned_by(db, _region_slug, org_code):
        return {"ok": False,
                "msg": ("You must be in one of your organization's owned "
                        "wilderness regions to access the armory.")}

    # Find item in character inventory
    inv_raw = char.get("inventory", "{}")
    try:
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
    except Exception:
        inv = {}
    items_list = inv.get("items", [])
    target = None
    target_idx = -1
    for i, it in enumerate(items_list):
        if item_key.lower() in it.get("key", "").lower() or item_key.lower() in it.get("name", "").lower():
            target = it
            target_idx = i
            break

    if target is None:
        return {"ok": False, "msg": f"You don't have '{item_key}' in your inventory."}

    # Check armory item limit
    storage = await _get_org_storage(db, org_code)
    if len(storage.get("items", [])) >= ORG_STORAGE_MAX_ITEMS:
        return {"ok": False, "msg": f"The armory is full ({ORG_STORAGE_MAX_ITEMS} items max)."}

    # Remove from character inventory
    items_list.pop(target_idx)
    inv["items"] = items_list
    await db.update_character(char["id"], inventory=json.dumps(inv))

    # Add to armory
    storage.setdefault("items", []).append(target)
    await _save_org_storage(db, org_code, storage)

    return {"ok": True, "msg": f"Deposited {target.get('name', item_key)} into the faction armory."}


async def armory_withdraw_item(db, char: dict, org_code: str,
                                item_key: str) -> dict:
    """
    Withdraw an item from the org armory into character inventory.
    Returns {"ok": bool, "msg": str}.
    """
    room_id = char.get("room_id")
    if not room_id:
        return {"ok": False, "msg": "You're not in a room."}
    # SYN.1.b (2026-05-24): retargeted from per-room
    # is_room_claimed_by to region-scope is_region_owned_by. Armory
    # access now requires standing in a room within a wilderness
    # region owned by the org.
    _room = await db.get_room(room_id)
    _region_slug = (_room or {}).get("wilderness_region_id")
    if not _region_slug or not await is_region_owned_by(db, _region_slug, org_code):
        return {"ok": False,
                "msg": ("You must be in one of your organization's owned "
                        "wilderness regions to access the armory.")}

    storage = await _get_org_storage(db, org_code)
    armory_items = storage.get("items", [])
    target = None
    target_idx = -1
    for i, it in enumerate(armory_items):
        if item_key.lower() in it.get("key", "").lower() or item_key.lower() in it.get("name", "").lower():
            target = it
            target_idx = i
            break

    if target is None:
        return {"ok": False, "msg": f"The armory doesn't have '{item_key}'."}

    # Add to character inventory
    inv_raw = char.get("inventory", "{}")
    try:
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
    except Exception:
        inv = {}
    inv.setdefault("items", []).append(target)
    await db.update_character(char["id"], inventory=json.dumps(inv))

    # Remove from armory
    armory_items.pop(target_idx)
    storage["items"] = armory_items
    await _save_org_storage(db, org_code, storage)

    return {"ok": True, "msg": f"Withdrew {target.get('name', item_key)} from the faction armory."}


async def armory_withdraw_resources(db, char: dict, org_code: str,
                                     resource_type: str, quantity: int) -> dict:
    """
    Withdraw crafting resources from the org armory into character inventory.
    Returns {"ok": bool, "msg": str}.
    """
    room_id = char.get("room_id")
    if not room_id:
        return {"ok": False, "msg": "You're not in a room."}
    # SYN.1.b (2026-05-24): retargeted from per-room
    # is_room_claimed_by to region-scope is_region_owned_by. Armory
    # access now requires standing in a room within a wilderness
    # region owned by the org.
    _room = await db.get_room(room_id)
    _region_slug = (_room or {}).get("wilderness_region_id")
    if not _region_slug or not await is_region_owned_by(db, _region_slug, org_code):
        return {"ok": False,
                "msg": ("You must be in one of your organization's owned "
                        "wilderness regions to access the armory.")}

    storage = await _get_org_storage(db, org_code)
    resources = storage.get("resources", [])

    # Find matching resource
    target = None
    target_idx = -1
    for i, r in enumerate(resources):
        if r.get("type", "").lower() == resource_type.lower():
            target = r
            target_idx = i
            break

    if target is None:
        return {"ok": False, "msg": f"The armory has no {resource_type}."}
    if target.get("quantity", 0) < quantity:
        return {"ok": False,
                "msg": f"The armory only has {target['quantity']}x {resource_type} "
                       f"(requested {quantity})."}

    # Deduct from armory
    target["quantity"] -= quantity
    if target["quantity"] <= 0:
        resources.pop(target_idx)
    storage["resources"] = resources
    await _save_org_storage(db, org_code, storage)

    # Add to character inventory
    inv_raw = char.get("inventory", "{}")
    try:
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
    except Exception:
        inv = {}
    inv_resources = inv.get("resources", [])

    # Stack with existing if same type and close quality
    stacked = False
    q = target.get("quality", 50)
    for existing in inv_resources:
        if existing.get("type") == resource_type and abs(existing.get("quality", 50) - q) <= 10:
            old_q = existing.get("quantity", 0)
            new_q = old_q + quantity
            existing["quality"] = round((existing.get("quality", 50) * old_q + q * quantity) / new_q)
            existing["quantity"] = new_q
            stacked = True
            break
    if not stacked:
        inv_resources.append({"type": resource_type, "quantity": quantity, "quality": q})

    inv["resources"] = inv_resources
    await db.update_character(char["id"], inventory=json.dumps(inv))

    return {"ok": True,
            "msg": f"Withdrew {quantity}x {resource_type} (quality {q}) from the faction armory."}


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6D (Contest State Machine) — RETIRED in SYN.3 (2026-05-25)
# ══════════════════════════════════════════════════════════════════════════════
#
# Per ``contestable_wilderness_design_v2.md`` §2.4: contest state moved
# to ``engine/contest.py`` (region-keyed, not zone-keyed). The 12 surfaces
# previously in this block — ``territory_contests`` schema,
# ``ensure_contest_schema``, ``get_active_contest``,
# ``get_contests_for_org``, ``is_in_active_contest``, ``_declare_contest``,
# ``check_and_declare_contests``, ``tick_contest_resolution``,
# ``_transfer_zone_claims``, ``hostile_takeover_claim``,
# ``get_contest_status_lines``, and the ``CONTEST_*`` constants —
# are physically deleted. See engine/contest.py for the replacements.
#
# Caller retargets shipped in the same drop:
#   * server/session.py::_hud_territory       — region_ownership + region contest
#   * parser/combat_commands.py PvP gate      — is_region_in_active_contest
#   * parser/combat_commands.py NPC death     — on_npc_killed_in_combat (Anchor)
#   * parser/faction_commands.py::_cmd_seize  — DELETED
#   * server/tick_handlers_economy.py         — tick_region_contest_resolution
#
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# SYN.1.a (May 24 2026): Region Ownership — Contestable Wilderness pivot
# ══════════════════════════════════════════════════════════════════════════════
#
# Per ``contestable_wilderness_design_v2.md`` §2.2 and §3.1.
#
# This block ships the *new* surfaces for wilderness-region ownership. The
# legacy per-room ``claim_room``/``unclaim_room``/``is_room_claimed_by``
# block above remains operational through SYN.1.a (parallel ship). SYN.1.b
# will:
#   * retarget the six known consumers of ``is_room_claimed_by`` (see
#     SYN.0 Finding 2 in TODO.json),
#   * retarget ``parser/faction_commands.py::_cmd_claim``/``_cmd_unclaim``,
#   * invoke ``tools/syn_migration.py::wipe_territory_claims`` and delete
#     the eight tagged surfaces.
#
# Surfaces shipped here (additive — no deletions in SYN.1.a):
#   * ``REGION_*`` constants (cost, upkeep, garrison count, thresholds)
#   * ``region_ownership`` table — one row per owned region
#   * ``region_garrison`` table — region_slug → npc_id mapping
#   * ``ensure_region_ownership_schema(db)`` — idempotent table create
#   * ``get_region_owner(db, slug)`` / ``get_org_regions(db, org_code)``
#   * ``is_region_owned_by(db, slug, org_code)``  (NEW name; old per-room
#     ``is_room_claimed_by`` still lives above and is the deprecated one)
#   * ``claim_region(db, char, org_code, slug)``
#   * ``unclaim_region(db, char, org_code, slug)``
#   * ``spawn_region_garrison(db, org_code, slug)``
#   * ``dismiss_region_garrison(db, slug)``
#   * ``tick_region_maintenance(db, session_mgr)`` — weekly
#   * ``tick_region_passive_yield(db, session_mgr)`` — daily
#
# Design invariants (one-owner-per-region):
#   * ``region_ownership`` uses ``region_slug`` as PRIMARY KEY — at most
#     one owner per region. Re-claiming a region while owned by another
#     org is the contest path (SYN.3); claim_region rejects it here.
#   * NO per-org cap. An org can own every wilderness region simultaneously
#     if it can defend them (per design §1.2 and §6, the legacy
#     ``CLAIM_MAX_*`` caps retire in SYN.1.b).
#
# ──────────────────────────────────────────────────────────────────────────────

# ── Region constants ────────────────────────────────────────────────────────
REGION_CLAIM_COST            = 5000   # Treasury cost to claim a region
REGION_CLAIM_MIN_RANK        = 3      # Org rank to claim/unclaim
REGION_WEEKLY_MAINT          = 2000   # Per design §2.5.4 — base region upkeep
REGION_GARRISON_WEEKLY       = 1000   # Per design §2.5.4 — garrison upkeep
REGION_GARRISON_COUNT        = 5      # Per design §3.1 — NPCs per garrison
REGION_PASSIVE_LAWLESS_MIN   = 100    # Per design §2.5.1 — lawless daily passive (min)
REGION_PASSIVE_LAWLESS_MAX   = 250    # Per design §2.5.1 — lawless daily passive (max)
REGION_PASSIVE_CONTESTED_MIN = 50     # Per design §2.5.1 — contested daily passive (min)
REGION_PASSIVE_CONTESTED_MAX = 150    # Per design §2.5.1 — contested daily passive (max)


# ── Schema ──────────────────────────────────────────────────────────────────

REGION_OWNERSHIP_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS region_ownership (
    region_slug   TEXT    NOT NULL PRIMARY KEY,
    org_code      TEXT    NOT NULL,
    zone_id       INTEGER,
    claimed_by    INTEGER NOT NULL,
    claimed_at    REAL    NOT NULL,
    maintenance   INTEGER NOT NULL DEFAULT 3000
);
CREATE INDEX IF NOT EXISTS idx_region_ownership_org
    ON region_ownership(org_code);
CREATE TABLE IF NOT EXISTS region_garrison (
    region_slug TEXT    NOT NULL,
    npc_id      INTEGER NOT NULL,
    PRIMARY KEY (region_slug, npc_id)
);
CREATE INDEX IF NOT EXISTS idx_region_garrison_slug
    ON region_garrison(region_slug);
"""


async def ensure_region_ownership_schema(db) -> None:
    """Create region_ownership + region_garrison tables. Idempotent."""
    try:
        for stmt in REGION_OWNERSHIP_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception as e:
        log.warning("[territory/region] schema create error: %s", e)


# ── Region introspection helpers ────────────────────────────────────────────

async def _get_region_landmarks(db, region_slug: str) -> list[int]:
    """Return room_ids of all landmarks in a wilderness region.

    A "landmark" here is any row in ``rooms`` whose
    ``wilderness_region_id`` matches the slug. The wilderness writer
    (engine/wilderness_writer.py) populates this column on the rooms
    it materialises from a region YAML.
    """
    try:
        rows = await db.fetchall(
            "SELECT id FROM rooms WHERE wilderness_region_id = ? ORDER BY id",
            (region_slug,),
        )
        return [int(r["id"]) for r in rows]
    except Exception:
        log.warning("_get_region_landmarks: unhandled exception", exc_info=True)
        return []


async def _get_region_zone(db, region_slug: str) -> Optional[int]:
    """Derive a region's zone_id from any one of its landmark rooms.

    Wilderness regions inherit their security tier from their parent
    zone (per ``data/worlds/clone_wars/wilderness/*.yaml::region.zone``).
    Rather than introduce a separate region→zone mapping table in
    SYN.1.a, we read it back off any landmark room. Wilderness loaders
    guarantee every landmark in a region shares the same parent zone.
    """
    try:
        rows = await db.fetchall(
            "SELECT zone_id FROM rooms "
            "WHERE wilderness_region_id = ? AND zone_id IS NOT NULL "
            "LIMIT 1",
            (region_slug,),
        )
        if not rows:
            return None
        return int(rows[0]["zone_id"]) if rows[0]["zone_id"] is not None else None
    except Exception:
        log.warning("_get_region_zone: unhandled exception", exc_info=True)
        return None


# ── Region ownership queries ────────────────────────────────────────────────

async def get_region_owner(db, region_slug: str) -> Optional[dict]:
    """Return ownership row for a region, or None if unowned."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_ownership WHERE region_slug = ?",
            (region_slug,),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_region_owner: unhandled exception", exc_info=True)
        return None


async def get_org_regions(db, org_code: str) -> list[dict]:
    """Return all regions owned by an org."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_ownership WHERE org_code = ? "
            "ORDER BY claimed_at",
            (org_code,),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_org_regions: unhandled exception", exc_info=True)
        return []


async def is_region_owned_by(db, region_slug: str, org_code: str) -> bool:
    """True if region is currently owned by org_code, False otherwise.

    Replaces the per-room ``is_room_claimed_by`` for region-scope
    callers. SYN.1.b retargets the six legacy ``is_room_claimed_by``
    consumers to this function (or inlines the equivalent logic for
    consumers that don't fit the region model).
    """
    row = await get_region_owner(db, region_slug)
    return row is not None and row["org_code"] == org_code


# ── Region garrison spawning ────────────────────────────────────────────────

async def spawn_region_garrison(
    db, org_code: str, region_slug: str,
) -> dict:
    """Spawn the garrison for an owned region.

    Per ``contestable_wilderness_design_v2.md`` §3.1: 5 NPCs scattered
    among the region's landmarks. Uses the existing ``_GUARD_TEMPLATES``
    for org-flavored NPCs; falls back to ``_default`` for unknown orgs.

    Idempotent: if a garrison already exists for the region, returns
    the existing npc_ids without spawning new ones.

    Returns ``{"ok": bool, "msg": str, "npc_ids": list[int]}``.
    """
    # Idempotency check — already garrisoned?
    try:
        existing_rows = await db.fetchall(
            "SELECT npc_id FROM region_garrison WHERE region_slug = ?",
            (region_slug,),
        )
    except Exception:
        log.warning("spawn_region_garrison: unhandled exception", exc_info=True)
        existing_rows = []
    if existing_rows:
        npc_ids = [int(r["npc_id"]) for r in existing_rows]
        return {
            "ok": True,
            "msg": f"Garrison already present in {region_slug} ({len(npc_ids)} NPCs).",
            "npc_ids": npc_ids,
        }

    landmarks = await _get_region_landmarks(db, region_slug)
    if not landmarks:
        return {
            "ok": False,
            "msg": (f"Region '{region_slug}' has no landmark rooms; "
                    f"cannot place a garrison."),
            "npc_ids": [],
        }

    # Pick up to REGION_GARRISON_COUNT random landmarks. If the region
    # has fewer landmarks than the garrison size, multiple NPCs can
    # share a room.
    tmpl = _GUARD_TEMPLATES.get(org_code, _GUARD_TEMPLATES["_default"])
    npc_ids = []
    for i in range(REGION_GARRISON_COUNT):
        room_id = random.choice(landmarks)
        # Name suffix disambiguates multiple NPCs in the same room.
        guard_name = f"{tmpl['name_prefix']} #{i + 1}"
        char_sheet = _build_guard_sheet(tmpl)
        ai_config = _build_guard_ai(tmpl, org_code)
        try:
            npc_id = await db.create_npc(
                name=guard_name,
                room_id=room_id,
                species=tmpl["species"],
                description=tmpl["description"],
                char_sheet_json=json.dumps(char_sheet),
                ai_config_json=json.dumps(ai_config),
            )
            npc_ids.append(int(npc_id))
            await db.execute(
                "INSERT OR IGNORE INTO region_garrison (region_slug, npc_id) "
                "VALUES (?, ?)",
                (region_slug, int(npc_id)),
            )
        except Exception as e:
            log.warning("spawn_region_garrison: create_npc failed (%s)", e)
            continue
    try:
        await db.commit()
    except Exception:
        log.warning("spawn_region_garrison: commit failed", exc_info=True)

    log.info("[territory/region] spawned garrison of %d for %s in %s",
             len(npc_ids), org_code, region_slug)
    return {
        "ok": True,
        "msg": (f"Garrison of {len(npc_ids)} {org_code} NPCs deployed "
                f"to {region_slug}."),
        "npc_ids": npc_ids,
    }


async def dismiss_region_garrison(db, region_slug: str) -> dict:
    """Remove all garrison NPCs for a region.

    Deletes both the underlying NPC rows and the ``region_garrison``
    mapping rows. Called by ``unclaim_region`` and by
    ``tick_region_maintenance`` when treasury can't cover upkeep.

    Returns ``{"ok": bool, "msg": str, "removed": int}``.
    """
    try:
        rows = await db.fetchall(
            "SELECT npc_id FROM region_garrison WHERE region_slug = ?",
            (region_slug,),
        )
    except Exception:
        log.warning("dismiss_region_garrison: unhandled exception", exc_info=True)
        return {"ok": False, "msg": "Garrison lookup failed.", "removed": 0}

    if not rows:
        return {"ok": True, "msg": "No garrison present.", "removed": 0}

    removed = 0
    for r in rows:
        npc_id = int(r["npc_id"])
        try:
            await db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
            removed += 1
        except Exception:
            log.warning("dismiss_region_garrison: NPC delete failed (id=%d)", npc_id)
            continue
    try:
        await db.execute(
            "DELETE FROM region_garrison WHERE region_slug = ?",
            (region_slug,),
        )
        await db.commit()
    except Exception:
        log.warning("dismiss_region_garrison: cleanup failed", exc_info=True)

    log.info("[territory/region] dismissed garrison of %d in %s", removed, region_slug)
    return {
        "ok": True,
        "msg": f"Dismissed {removed} garrison NPCs from {region_slug}.",
        "removed": removed,
    }


# ── Claim / unclaim region ──────────────────────────────────────────────────

async def claim_region(
    db, char: dict, org_code: str, region_slug: str,
) -> dict:
    """Claim a wilderness region for an organization.

    Per ``contestable_wilderness_design_v2.md`` §2.2:
      * Region must be a valid wilderness region (has landmark rooms).
      * Region must not already be owned (contest path is SYN.3, not
        an immediate re-claim).
      * Acting character must be a member of ``org_code`` with rank
        ≥ ``REGION_CLAIM_MIN_RANK``.
      * Org must have at least ``THRESHOLD_FOOTHOLD`` influence in the
        region's parent zone (transitional rule for SYN.1; SYN.3 will
        make this strictly per-region once influence is region-keyed).
      * Org treasury must cover ``REGION_CLAIM_COST``.

    On success:
      * Inserts a row into ``region_ownership``.
      * Deducts ``REGION_CLAIM_COST`` from treasury.
      * Spawns the region garrison (5 NPCs).
      * Bumps influence +20 in the parent zone (parity with the legacy
        per-room claim bump in ``claim_room``).

    Returns ``{"ok": bool, "msg": str}``.
    """
    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Unknown organization: {org_code}"}

    mem = await db.get_membership(char["id"], org["id"])
    if not mem or mem.get("rank_level", 0) < REGION_CLAIM_MIN_RANK:
        return {"ok": False,
                "msg": f"You need rank {REGION_CLAIM_MIN_RANK}+ to claim a region."}

    landmarks = await _get_region_landmarks(db, region_slug)
    if not landmarks:
        return {"ok": False,
                "msg": f"'{region_slug}' is not a known wilderness region."}

    existing = await get_region_owner(db, region_slug)
    if existing:
        if existing["org_code"] == org_code:
            return {"ok": False,
                    "msg": "Your organization already owns this region."}
        owner_display = existing["org_code"].replace("_", " ").title()
        return {"ok": False,
                "msg": (f"This region is owned by {owner_display}. "
                        f"Contest their ownership through sustained "
                        f"influence (SYN.3).")}

    zone_id = await _get_region_zone(db, region_slug)
    if zone_id is not None:
        sec = await get_zone_security(db, zone_id)
        if sec == "secured":
            return {"ok": False,
                    "msg": ("Imperial-controlled zones cannot be claimed "
                            "as wilderness regions.")}

        influence = await get_territory_influence(db, org_code, zone_id)
        if influence < THRESHOLD_FOOTHOLD:
            return {"ok": False,
                    "msg": (f"Insufficient influence "
                            f"({influence}/{THRESHOLD_FOOTHOLD}). "
                            f"Build presence with combat, missions, and "
                            f"investment first.")}

    if org.get("treasury", 0) < REGION_CLAIM_COST:
        return {"ok": False,
                "msg": (f"Insufficient treasury. Need "
                        f"{REGION_CLAIM_COST:,}cr, have "
                        f"{org.get('treasury', 0):,}cr.")}

    new_balance = await db.adjust_org_treasury(org["id"], -REGION_CLAIM_COST)

    now = time.time()
    upkeep = REGION_WEEKLY_MAINT + REGION_GARRISON_WEEKLY
    try:
        await db.execute(
            """INSERT INTO region_ownership
               (region_slug, org_code, zone_id, claimed_by, claimed_at, maintenance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (region_slug, org_code, zone_id, int(char["id"]), now, upkeep),
        )
        await db.commit()
    except Exception as e:
        log.warning("claim_region: insert failed (%s)", e, exc_info=True)
        # Best-effort refund on failure
        try:
            await db.adjust_org_treasury(org["id"], REGION_CLAIM_COST)
        except Exception:
            log.debug(
                "claim_region: refund after insert failure also "
                "failed; org %s lost %s credits",
                org.get("id"), REGION_CLAIM_COST, exc_info=True,
            )
        return {"ok": False, "msg": "Claim failed (database error)."}

    # Bump influence for narrative parity with claim_room
    if zone_id is not None:
        try:
            await adjust_territory_influence(
                db, org_code, zone_id, 20,
                reason=f"region claim by {char.get('name', '?')}")
        except Exception:
            log.warning("claim_region: influence bump failed", exc_info=True)

    # Spawn garrison
    garrison_result = await spawn_region_garrison(db, org_code, region_slug)
    garrison_count = len(garrison_result.get("npc_ids", []))

    log.info("[territory/region] %s claimed region '%s' (zone %s) "
             "by char %d. Garrison: %d NPCs.",
             org_code, region_slug, str(zone_id), char["id"], garrison_count)

    # SYN.10 (May 25 2026): news-digest broadcast per design §2.6.
    # Best-effort; never blocks the claim path.
    try:
        from engine.territory_display import format_ownership_change_news
        rows = await db.fetchall(
            "SELECT name FROM organizations WHERE code = ?",
            (org_code,),
        )
        org_name = dict(rows[0]).get("name") if rows else org_code
        news = format_ownership_change_news(
            region_slug, org_name=org_name, action="claimed",
        )
        # session_mgr is not in scope here; the broadcast is done by
        # the caller (parser command) if a session_mgr is available.
        # We surface the news text in the result dict instead.
        return {
            "ok": True,
            "msg": (f"Region claimed: {region_slug}. "
                    f"Cost: {REGION_CLAIM_COST:,}cr. "
                    f"Upkeep: {upkeep:,}cr/week. "
                    f"Garrison: {garrison_count} NPCs deployed. "
                    f"Treasury: {new_balance:,}cr."),
            "news": news,
        }
    except Exception:
        log.warning("[territory/region] news format failed",
                    exc_info=True)
        return {
            "ok": True,
            "msg": (f"Region claimed: {region_slug}. "
                    f"Cost: {REGION_CLAIM_COST:,}cr. "
                    f"Upkeep: {upkeep:,}cr/week. "
                    f"Garrison: {garrison_count} NPCs deployed. "
                    f"Treasury: {new_balance:,}cr."),
        }


async def unclaim_region(
    db, char: dict, org_code: str, region_slug: str,
) -> dict:
    """Release ownership of a region.

    Per ``contestable_wilderness_design_v2.md`` §2.5.4 (region upkeep
    lapse path) and §2.2 (voluntary release):
      * Region must currently be owned by ``org_code``.
      * Acting character must be a member with rank
        ≥ ``REGION_CLAIM_MIN_RANK``.
      * Garrison NPCs are dismissed.
      * No partial refund of claim cost (this is a release, not a
        contest defeat — the lapse path is in ``tick_region_maintenance``).

    Returns ``{"ok": bool, "msg": str}``.
    """
    owner = await get_region_owner(db, region_slug)
    if not owner or owner["org_code"] != org_code:
        return {"ok": False,
                "msg": "Your organization doesn't own this region."}

    org = await db.get_organization(org_code)
    if org:
        mem = await db.get_membership(char["id"], org["id"])
        if not mem or mem.get("rank_level", 0) < REGION_CLAIM_MIN_RANK:
            return {"ok": False,
                    "msg": (f"You need rank {REGION_CLAIM_MIN_RANK}+ "
                            f"to release a region.")}

    # Dismiss garrison first (avoids orphan NPC rows on cleanup failure)
    await dismiss_region_garrison(db, region_slug)

    try:
        await db.execute(
            "DELETE FROM region_ownership WHERE region_slug = ?",
            (region_slug,),
        )
        await db.commit()
    except Exception:
        log.warning("unclaim_region: delete failed", exc_info=True)
        return {"ok": False, "msg": "Release failed (database error)."}

    log.info("[territory/region] %s released region '%s'", org_code, region_slug)

    # SYN.10 (May 25 2026): news broadcast per design §2.6.
    try:
        from engine.territory_display import format_ownership_change_news
        rows = await db.fetchall(
            "SELECT name FROM organizations WHERE code = ?",
            (org_code,),
        )
        org_name = dict(rows[0]).get("name") if rows else org_code
        news = format_ownership_change_news(
            region_slug, org_name=org_name, action="unclaimed",
        )
        return {
            "ok": True,
            "msg": f"Region released: {region_slug}.",
            "news": news,
        }
    except Exception:
        log.warning("[territory/region] news format failed",
                    exc_info=True)
        return {"ok": True, "msg": f"Region released: {region_slug}."}


# ── Region maintenance + passive yield ticks ────────────────────────────────

async def tick_region_maintenance(db, session_mgr) -> None:
    """Weekly tick: deduct region upkeep from owning orgs.

    Per ``contestable_wilderness_design_v2.md`` §2.5.4:
      * Base region maintenance: 2,000 cr/wk.
      * Garrison upkeep: 1,000 cr/wk.
      * If treasury can't cover full upkeep, garrison dismisses first
        (saves 1,000 cr).
      * If treasury still can't pay (after garrison dismissed): region
        lapses — ownership row deleted; org notified.

    Replaces ``tick_claim_maintenance`` for the new region-scope model.
    The old per-room tick continues running through SYN.1.a; SYN.1.b
    retires it.
    """
    try:
        rows = await db.fetchall("SELECT * FROM region_ownership")
    except Exception:
        log.warning("tick_region_maintenance: read failed", exc_info=True)
        return

    for r in rows:
        ownership = dict(r)
        org_code = ownership["org_code"]
        region_slug = ownership["region_slug"]
        upkeep_full = int(ownership.get("maintenance") or
                          (REGION_WEEKLY_MAINT + REGION_GARRISON_WEEKLY))

        org = await db.get_organization(org_code)
        if not org:
            continue

        treasury = int(org.get("treasury", 0) or 0)

        if treasury >= upkeep_full:
            await db.adjust_org_treasury(org["id"], -upkeep_full)
            log.info("[territory/region] %s paid %dcr maint for %s",
                     org_code, upkeep_full, region_slug)
            continue

        # Step 1: dismiss garrison to save REGION_GARRISON_WEEKLY
        dismiss_result = await dismiss_region_garrison(db, region_slug)
        if dismiss_result.get("removed", 0) > 0:
            await _notify_org_members(
                session_mgr,
                org_code,
                (f"  \033[1;33m[Territory] Treasury short — garrison "
                 f"dismissed from {region_slug}.\033[0m"),
            )
            # Update maintenance row to base-only going forward
            try:
                await db.execute(
                    "UPDATE region_ownership SET maintenance = ? "
                    "WHERE region_slug = ?",
                    (REGION_WEEKLY_MAINT, region_slug),
                )
                await db.commit()
            except Exception:
                log.warning("tick_region_maintenance: upkeep update failed",
                            exc_info=True)

        # Step 2: check if base upkeep is still unaffordable
        if treasury >= REGION_WEEKLY_MAINT:
            # Pay base after garrison saved us
            await db.adjust_org_treasury(org["id"], -REGION_WEEKLY_MAINT)
            log.info("[territory/region] %s paid base %dcr maint for %s "
                     "(garrison dismissed)",
                     org_code, REGION_WEEKLY_MAINT, region_slug)
            continue

        # Step 3: lapse — region returns to un-owned
        try:
            await db.execute(
                "DELETE FROM region_ownership WHERE region_slug = ?",
                (region_slug,),
            )
            await db.commit()
        except Exception:
            log.warning("tick_region_maintenance: lapse delete failed",
                        exc_info=True)
            continue

        await _notify_org_members(
            session_mgr,
            org_code,
            (f"  \033[1;31m[Territory] {region_slug} has lapsed — "
             f"unable to cover upkeep. Region is now un-owned.\033[0m"),
        )
        log.warning("[territory/region] %s lapsed region %s (treasury %d < %d)",
                    org_code, region_slug, treasury, REGION_WEEKLY_MAINT)


async def tick_region_passive_yield(db, session_mgr) -> None:
    """Daily tick: pay passive credit yield to owners of wilderness regions.

    Per ``contestable_wilderness_design_v2.md`` §2.5.1:
      * Lawless: 100–250 cr/day.
      * Contested: 50–150 cr/day.
      * Secured: no yield (Imperial commons, not contestable).

    Replaces ``tick_resource_nodes`` for the region-scope model. Active
    harvest (the larger income lever) ships in SYN.6. The old per-room
    tick continues running through SYN.1.a; SYN.1.b retires it.
    """
    try:
        rows = await db.fetchall("SELECT * FROM region_ownership")
    except Exception:
        log.warning("tick_region_passive_yield: read failed", exc_info=True)
        return

    for r in rows:
        ownership = dict(r)
        org_code = ownership["org_code"]
        region_slug = ownership["region_slug"]
        zone_id = ownership.get("zone_id")

        org = await db.get_organization(org_code)
        if not org:
            continue

        if zone_id is None:
            zone_id = await _get_region_zone(db, region_slug)
        sec = await get_zone_security(db, zone_id) if zone_id else "lawless"

        if sec == "secured":
            continue

        if sec == "contested":
            yield_cr = random.randint(
                REGION_PASSIVE_CONTESTED_MIN, REGION_PASSIVE_CONTESTED_MAX,
            )
        else:
            # Default to lawless yield band (covers "lawless" and any
            # legacy/unrecognised tier).
            yield_cr = random.randint(
                REGION_PASSIVE_LAWLESS_MIN, REGION_PASSIVE_LAWLESS_MAX,
            )

        try:
            await db.adjust_org_treasury(org["id"], yield_cr)
        except Exception:
            log.warning("tick_region_passive_yield: treasury adjust failed",
                        exc_info=True)
            continue

        log.info("[territory/region] passive yield: %s +%dcr from %s",
                 org_code, yield_cr, region_slug)
        await _notify_org_members(
            session_mgr,
            org_code,
            (f"  \033[2m[Territory] Passive yield from {region_slug}: "
             f"{yield_cr:,}cr to treasury.\033[0m"),
        )



# ── SYN.1.b one-shot cold-start wipe helper ─────────────────────────────────

async def _syn1b_wipe_territory_claims_once(db) -> None:
    """Idempotent wipe of ``territory_claims`` per
    ``contestable_wilderness_design_v2.md`` §1.4 (cold start with zero
    seeded influence). Runs once at first boot post-SYN.1.b apply, then
    leaves a marker row so re-boots don't wipe again.

    The marker uses ``syn_migration_state``, a tiny table this helper
    creates on first call. Reuses the same module-level table the
    rest of the SYN sequence will write to as it transitions surfaces.
    """
    try:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS syn_migration_state ("
            "  step_id TEXT PRIMARY KEY, applied_at REAL NOT NULL"
            ")"
        )
        await db.commit()
        rows = await db.fetchall(
            "SELECT step_id FROM syn_migration_state WHERE step_id = ?",
            ("SYN.1.b.wipe_territory_claims",),
        )
        if rows:
            return  # Already wiped
        # Wipe
        try:
            await db.execute("DELETE FROM territory_claims")
        except Exception:
            log.warning("[territory/SYN.1.b] wipe failed (table absent?)",
                        exc_info=True)
        # Mark applied
        await db.execute(
            "INSERT OR IGNORE INTO syn_migration_state (step_id, applied_at) "
            "VALUES (?, ?)",
            ("SYN.1.b.wipe_territory_claims", time.time()),
        )
        await db.commit()
        log.info("[territory/SYN.1.b] territory_claims wiped (cold-start)")
    except Exception:
        log.warning("[territory/SYN.1.b] migration helper failed", exc_info=True)

