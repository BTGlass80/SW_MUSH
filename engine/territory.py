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
CLAIM_COST            = 5000   # Credits from org treasury per room claim
CLAIM_WEEKLY_MAINT    = 200    # Credits per week per claimed room
CLAIM_MAX_PER_ZONE    = 3      # Max claimed rooms per org per zone
CLAIM_MAX_TOTAL       = 10     # Max total claimed rooms per org
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
ORG_TO_AXIS = {
    "empire":   "imperial",
    "rebel":    "rebel",
    "hutt":     "criminal",
    "bh_guild": "independent",
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
                await db._db.execute(stmt)
        await db._db.commit()
    except Exception as e:
        log.warning("[territory] schema create error: %s", e)
    # Drop 6D: contests table
    await ensure_contest_schema(db)


# ── Core influence adjustment ────────────────────────────────────────────────

async def adjust_territory_influence(db, org_code: str, zone_id: int,
                                      delta: int, reason: str = "") -> int:
    """
    Adjust territory influence for an org in a zone.
    All influence changes MUST go through this function.
    Returns the new influence score.
    """
    now = time.time()

    rows = await db._db.execute_fetchall(
        "SELECT score FROM territory_influence WHERE zone_id = ? AND org_code = ?",
        (zone_id, org_code),
    )
    current = rows[0]["score"] if rows else 0
    new_score = max(0, min(INFLUENCE_CAP, current + delta))

    await db._db.execute(
        """INSERT INTO territory_influence (zone_id, org_code, score, last_activity, last_presence)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(zone_id, org_code) DO UPDATE SET
             score = excluded.score,
             last_activity = excluded.last_activity""",
        (zone_id, org_code, new_score, now, now),
    )
    await db._db.commit()

    if delta != 0:
        log.info("[territory] %s influence in zone %d: %d -> %d (%s%d) %s",
                 org_code, zone_id, current, new_score,
                 "+" if delta > 0 else "", delta, reason)

    # After a positive influence change, check if a new contest should be declared.
    # Pass session_mgr=None here — callers that have it should call
    # check_and_declare_contests() directly after this if they need notifications.
    if delta > 0:
        try:
            await check_and_declare_contests(db, org_code, zone_id)
        except Exception as _e:
            log.warning("[territory] contest check error in adjust: %s", _e)

    return new_score


async def get_territory_influence(db, org_code: str, zone_id: int) -> int:
    """Get current influence score for an org in a zone."""
    rows = await db._db.execute_fetchall(
        "SELECT score FROM territory_influence WHERE zone_id = ? AND org_code = ?",
        (zone_id, org_code),
    )
    return rows[0]["score"] if rows else 0


async def get_zone_territory_all(db, zone_id: int) -> dict[str, int]:
    """Get all org influence scores for a zone. Returns {org_code: score}."""
    rows = await db._db.execute_fetchall(
        "SELECT org_code, score FROM territory_influence WHERE zone_id = ? AND score > 0",
        (zone_id,),
    )
    return {r["org_code"]: r["score"] for r in rows}


async def get_org_territory_all(db, org_code: str) -> dict[int, int]:
    """Get all zone influence scores for an org. Returns {zone_id: score}."""
    rows = await db._db.execute_fetchall(
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

async def on_npc_kill(db, char: dict, room_id: int) -> None:
    """Called when a player kills an NPC. Grants influence to their org."""
    org_code = char.get("faction_id", "independent")
    if not org_code or org_code == "independent":
        return
    zone_id = await get_room_zone_id(db, room_id)
    if zone_id is None:
        return
    await adjust_territory_influence(
        db, org_code, zone_id, INFLUENCE_NPC_KILL,
        reason=f"NPC kill by {char.get('name', '?')}")


async def on_mission_complete(db, char: dict, room_id: int) -> None:
    """Called on mission/bounty/smuggling completion. Grants influence."""
    org_code = char.get("faction_id", "independent")
    if not org_code or org_code == "independent":
        return
    zone_id = await get_room_zone_id(db, room_id)
    if zone_id is None:
        return
    await adjust_territory_influence(
        db, org_code, zone_id, INFLUENCE_MISSION,
        reason=f"mission complete by {char.get('name', '?')}")


async def on_pvp_kill(db, winner: dict, loser: dict, room_id: int) -> None:
    """Called on PvP kill. Winner's org gains influence, loser's loses."""
    winner_org = winner.get("faction_id", "independent")
    loser_org = loser.get("faction_id", "independent")
    zone_id = await get_room_zone_id(db, room_id)
    if zone_id is None:
        return
    if winner_org and winner_org != "independent":
        await adjust_territory_influence(
            db, winner_org, zone_id, INFLUENCE_PVP_WIN,
            reason=f"PvP victory by {winner.get('name', '?')}")
    if loser_org and loser_org != "independent":
        await adjust_territory_influence(
            db, loser_org, zone_id, -5,
            reason=f"PvP defeat of {loser.get('name', '?')}")


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
                await db._db.execute(
                    """UPDATE territory_influence SET last_presence = ?
                       WHERE zone_id = ? AND org_code = ?""",
                    (now, zone_id, org_code),
                )

        await db._db.commit()
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

        rows = await db._db.execute_fetchall(
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
        "empire":    "The Empire's presence is felt here — patrols and informants.",
        "rebel":     "Rebel Alliance influence stirs quietly in the shadows.",
        "hutt":      "The Hutt Cartel's grip extends to these streets.",
        "bh_guild":  "Bounty Hunters' Guild operatives watch from the corners.",
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
        rows = await db._db.execute_fetchall(
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
        rows = await db._db.execute_fetchall(
            "SELECT * FROM territory_claims WHERE room_id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_claim: unhandled exception", exc_info=True)
        return None


async def get_org_claims(db, org_code: str) -> list[dict]:
    """Get all claims for an organization."""
    try:
        rows = await db._db.execute_fetchall(
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
        rows = await db._db.execute_fetchall(
            "SELECT * FROM territory_claims WHERE org_code = ? AND zone_id = ?",
            (org_code, zone_id),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_org_claims_in_zone: unhandled exception", exc_info=True)
        return []


async def claim_room(db, char: dict, org_code: str, room_id: int) -> dict:
    """
    Claim a room for an organization.
    Returns {"ok": bool, "msg": str}.
    """
    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Unknown organization: {org_code}"}
    mem = await db.get_membership(char["id"], org["id"])
    if not mem or mem.get("rank_level", 0) < CLAIM_MIN_RANK:
        return {"ok": False,
                "msg": f"You need rank {CLAIM_MIN_RANK}+ to claim territory."}

    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}
    zone_id = room.get("zone_id")
    if not zone_id:
        return {"ok": False, "msg": "This room is not in a zone."}

    if char.get("room_id") != room_id:
        return {"ok": False, "msg": "You must be standing in the room you want to claim."}

    sec = await get_zone_security(db, zone_id)
    if sec == "secured":
        return {"ok": False,
                "msg": "Imperial-controlled territory cannot be claimed by private organizations."}

    influence = await get_territory_influence(db, org_code, zone_id)
    if influence < THRESHOLD_FOOTHOLD:
        return {"ok": False,
                "msg": f"Insufficient influence ({influence}/{THRESHOLD_FOOTHOLD}). "
                       f"Build presence with combat, missions, and investment first."}

    existing = await get_claim(db, room_id)
    if existing:
        if existing["org_code"] == org_code:
            return {"ok": False, "msg": "Your organization already claims this room."}
        return {"ok": False,
                "msg": f"This room is claimed by {existing['org_code'].title()}. "
                       f"Contest their claim through sustained influence (Drop 6D)."}

    zone_claims = await get_org_claims_in_zone(db, org_code, zone_id)
    if len(zone_claims) >= CLAIM_MAX_PER_ZONE:
        return {"ok": False,
                "msg": f"Maximum {CLAIM_MAX_PER_ZONE} claims per zone reached."}

    all_claims = await get_org_claims(db, org_code)
    if len(all_claims) >= CLAIM_MAX_TOTAL:
        return {"ok": False,
                "msg": f"Maximum {CLAIM_MAX_TOTAL} total claims reached."}

    try:
        from engine.housing import get_housing_for_room
        h = await get_housing_for_room(db, room_id)
        if h:
            return {"ok": False, "msg": "Player-owned housing cannot be claimed as territory."}
    except Exception:
        log.warning("claim_room: unhandled exception", exc_info=True)
        pass

    if org.get("treasury", 0) < CLAIM_COST:
        return {"ok": False,
                "msg": f"Insufficient treasury. Need {CLAIM_COST:,}cr, "
                       f"have {org.get('treasury', 0):,}cr."}

    new_balance = await db.adjust_org_treasury(org["id"], -CLAIM_COST)

    now = time.time()
    await db._db.execute(
        """INSERT INTO territory_claims
           (org_code, room_id, zone_id, claimed_by, claimed_at, maintenance)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (org_code, room_id, zone_id, char["id"], now, CLAIM_WEEKLY_MAINT),
    )
    await db._db.commit()

    await adjust_territory_influence(
        db, org_code, zone_id, 20,
        reason=f"room claim by {char.get('name', '?')}")

    zone_name = await get_zone_name(db, zone_id)
    room_name = room.get("name", f"Room #{room_id}")
    log.info("[territory] %s claimed room %d (%s) in zone %d (%s) by char %d",
             org_code, room_id, room_name, zone_id, zone_name, char["id"])

    return {
        "ok": True,
        "msg": (f"Territory claimed: {room_name} in {zone_name}. "
                f"Cost: {CLAIM_COST:,}cr. "
                f"Maintenance: {CLAIM_WEEKLY_MAINT:,}cr/week. "
                f"Treasury: {new_balance:,}cr."),
    }


async def unclaim_room(db, char: dict, org_code: str, room_id: int) -> dict:
    """
    Release a territory claim.
    Returns {"ok": bool, "msg": str}.
    """
    claim = await get_claim(db, room_id)
    if not claim or claim["org_code"] != org_code:
        return {"ok": False, "msg": "Your organization doesn't claim this room."}

    org = await db.get_organization(org_code)
    if org:
        mem = await db.get_membership(char["id"], org["id"])
        if not mem or mem.get("rank_level", 0) < CLAIM_MIN_RANK:
            return {"ok": False,
                    "msg": f"You need rank {CLAIM_MIN_RANK}+ to release territory."}

    # Remove guard NPC if present
    if claim.get("guard_npc_id"):
        try:
            await db._db.execute(
                "DELETE FROM npcs WHERE id = ?", (claim["guard_npc_id"],)
            )
        except Exception:
            log.warning("unclaim_room: unhandled exception", exc_info=True)
            pass

    await db._db.execute(
        "DELETE FROM territory_claims WHERE room_id = ?", (room_id,)
    )
    await db._db.commit()

    room = await db.get_room(room_id)
    room_name = room.get("name", f"Room #{room_id}") if room else f"Room #{room_id}"
    log.info("[territory] %s unclaimed room %d (%s)", org_code, room_id, room_name)

    return {"ok": True, "msg": f"Territory released: {room_name}."}


async def get_claim_display_tag(db, room_id: int) -> Optional[str]:
    """
    Return an ANSI-formatted claim tag for look output, or None.
    E.g. " [CLAIMED — Hutt Cartel]"
    """
    claim = await get_claim(db, room_id)
    if not claim:
        return None
    org_colors = {
        "empire":   "\033[1;34m",
        "rebel":    "\033[1;31m",
        "hutt":     "\033[1;33m",
        "bh_guild": "\033[1;35m",
    }
    color = org_colors.get(claim["org_code"], "\033[1;37m")
    org_name = claim["org_code"].replace("_", " ").title()
    return f" {color}[CLAIMED \u2014 {org_name}]\033[0m"


async def is_room_claimed_by(db, room_id: int, org_code: str) -> bool:
    """Check if a room is claimed by a specific org."""
    claim = await get_claim(db, room_id)
    return claim is not None and claim["org_code"] == org_code


# ── Claim maintenance tick ───────────────────────────────────────────────────

async def tick_claim_maintenance(db, session_mgr) -> None:
    """
    Weekly tick: deduct maintenance from org treasuries for claimed rooms.
    If treasury is empty, the claim decays (influence penalty).
    Guard upkeep is included in room maintenance cost if guard is stationed.
    """
    try:
        rows = await db._db.execute_fetchall(
            "SELECT * FROM territory_claims"
        )
        for r in rows:
            claim = dict(r)
            org = await db.get_organization(claim["org_code"])
            if not org:
                continue

            # Base maintenance + guard upkeep if guard is stationed
            maint = claim.get("maintenance", CLAIM_WEEKLY_MAINT)
            if claim.get("guard_npc_id"):
                maint += GUARD_WEEKLY_UPKEEP

            if org.get("treasury", 0) >= maint:
                await db.adjust_org_treasury(org["id"], -maint)
                log.info("[territory] maintenance collected: %s paid %dcr for room %d",
                         claim["org_code"], maint, claim["room_id"])
            else:
                await adjust_territory_influence(
                    db, claim["org_code"], claim["zone_id"], -10,
                    reason="unpaid claim maintenance")
                log.warning("[territory] %s can't pay maintenance for room %d",
                            claim["org_code"], claim["room_id"])

                # If influence drops below foothold, auto-release
                inf = await get_territory_influence(
                    db, claim["org_code"], claim["zone_id"])
                if inf < THRESHOLD_FOOTHOLD:
                    # Remove guard if present
                    if claim.get("guard_npc_id"):
                        try:
                            await db._db.execute(
                                "DELETE FROM npcs WHERE id = ?",
                                (claim["guard_npc_id"],),
                            )
                        except Exception:
                            log.warning("tick_claim_maintenance: unhandled exception", exc_info=True)
                            pass
                    await db._db.execute(
                        "DELETE FROM territory_claims WHERE id = ?",
                        (claim["id"],),
                    )
                    await db._db.commit()
                    log.info("[territory] auto-released claim on room %d (influence too low)",
                             claim["room_id"])

    except Exception as e:
        log.warning("[territory] claim maintenance tick error: %s", e)


async def get_claims_status_lines(db, org_code: str) -> list[str]:
    """Return formatted list of all claimed rooms for an org."""
    claims = await get_org_claims(db, org_code)
    if not claims:
        return [
            "  No territory claimed.",
            f"  Build influence to {THRESHOLD_FOOTHOLD}+ in a zone, then "
            f"use \033[1;37mfaction claim\033[0m while standing in the room.",
        ]

    lines = ["\033[1;37m── Claimed Territory ──\033[0m"]
    for c in claims:
        room = await db.get_room(c["room_id"])
        room_name = room.get("name", f"Room #{c['room_id']}") if room else f"#{c['room_id']}"
        zone_name = await get_zone_name(db, c["zone_id"])
        guard_str = "\033[1;32mGuard: Yes\033[0m" if c.get("guard_npc_id") else "\033[2mGuard: No\033[0m"
        maint = c.get("maintenance", CLAIM_WEEKLY_MAINT)
        if c.get("guard_npc_id"):
            maint += GUARD_WEEKLY_UPKEEP
        lines.append(
            f"  {room_name:<30} {zone_name:<20} {maint}cr/wk  {guard_str}"
        )
    lines.append(f"  ({len(claims)}/{CLAIM_MAX_TOTAL} total claims)")

    # Append active contest info if any
    contest_lines = await get_contest_status_lines(db, org_code)
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
    """
    Spawn a guard NPC in a claimed room.
    All guard NPC creation MUST go through this function.
    Returns {"ok": bool, "msg": str, "npc_id": int|None}.
    """
    # Validate claim exists and belongs to org
    claim = await get_claim(db, room_id)
    if not claim:
        return {"ok": False, "msg": "Your organization doesn't claim this room.", "npc_id": None}
    if claim["org_code"] != org_code:
        return {"ok": False, "msg": "Your organization doesn't claim this room.", "npc_id": None}

    # Check rank
    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Unknown organization: {org_code}", "npc_id": None}
    mem = await db.get_membership(char_id, org["id"])
    if not mem or mem.get("rank_level", 0) < GUARD_MIN_RANK:
        return {"ok": False,
                "msg": f"You need rank {GUARD_MIN_RANK}+ to station a guard.",
                "npc_id": None}

    # Already has a guard
    if claim.get("guard_npc_id"):
        existing_npc = await db.get_npc(claim["guard_npc_id"])
        if existing_npc:
            return {"ok": False,
                    "msg": "A guard is already stationed here. Use 'faction guard remove' first.",
                    "npc_id": claim["guard_npc_id"]}
        # Stale reference — clear it
        await db._db.execute(
            "UPDATE territory_claims SET guard_npc_id = NULL WHERE room_id = ?",
            (room_id,),
        )
        await db._db.commit()

    # Check treasury for one-time cost
    if org.get("treasury", 0) < GUARD_COST:
        return {"ok": False,
                "msg": f"Insufficient treasury. Stationing a guard costs {GUARD_COST:,}cr. "
                       f"Current balance: {org.get('treasury', 0):,}cr.",
                "npc_id": None}
    new_balance = await db.adjust_org_treasury(org["id"], -GUARD_COST)

    # Get template for org
    tmpl = _GUARD_TEMPLATES.get(org_code, _GUARD_TEMPLATES["_default"])

    # Build NPC
    room = await db.get_room(room_id)
    room_name = room.get("name", f"Room #{room_id}") if room else f"Room #{room_id}"
    guard_name = tmpl["name_prefix"]

    char_sheet = _build_guard_sheet(tmpl)
    ai_config = _build_guard_ai(tmpl, org_code)

    npc_id = await db.create_npc(
        name=guard_name,
        room_id=room_id,
        species=tmpl["species"],
        description=tmpl["description"],
        char_sheet_json=json.dumps(char_sheet),
        ai_config_json=json.dumps(ai_config),
    )

    # Link guard to claim
    await db._db.execute(
        "UPDATE territory_claims SET guard_npc_id = ? WHERE room_id = ?",
        (npc_id, room_id),
    )
    await db._db.commit()

    log.info("[territory] %s stationed guard NPC %d in room %d (%s). Cost: %dcr",
             org_code, npc_id, room_id, room_name, GUARD_COST)

    return {
        "ok": True,
        "msg": (f"Guard stationed in {room_name}. "
                f"Cost: {GUARD_COST:,}cr. Weekly upkeep: +{GUARD_WEEKLY_UPKEEP}cr/wk. "
                f"Treasury: {new_balance:,}cr."),
        "npc_id": npc_id,
    }


async def remove_guard_npc(db, org_code: str, room_id: int,
                            char_id: int) -> dict:
    """
    Remove a guard NPC from a claimed room.
    Returns {"ok": bool, "msg": str}.
    """
    claim = await get_claim(db, room_id)
    if not claim or claim["org_code"] != org_code:
        return {"ok": False, "msg": "Your organization doesn't claim this room."}

    org = await db.get_organization(org_code)
    if org:
        mem = await db.get_membership(char_id, org["id"])
        if not mem or mem.get("rank_level", 0) < GUARD_MIN_RANK:
            return {"ok": False,
                    "msg": f"You need rank {GUARD_MIN_RANK}+ to manage guards."}

    if not claim.get("guard_npc_id"):
        return {"ok": False, "msg": "No guard is stationed here."}

    npc_id = claim["guard_npc_id"]
    try:
        await db._db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
    except Exception as e:
        log.warning("[territory] error deleting guard NPC %d: %s", npc_id, e)

    await db._db.execute(
        "UPDATE territory_claims SET guard_npc_id = NULL WHERE room_id = ?",
        (room_id,),
    )
    await db._db.commit()

    room = await db.get_room(room_id)
    room_name = room.get("name", f"Room #{room_id}") if room else f"Room #{room_id}"
    log.info("[territory] %s removed guard NPC %d from room %d (%s)",
             org_code, npc_id, room_id, room_name)

    return {"ok": True, "msg": f"Guard dismissed from {room_name}."}


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
    """
    Daily tick: generate passive resources/credits for each claimed room.
    Yield depends on zone security level and org influence tier.
    Credits go directly to org treasury.
    Crafting resources go into org shared storage (properties["org_storage"]).
    """
    try:
        claims = await db._db.execute_fetchall(
            "SELECT * FROM territory_claims"
        )
        if not claims:
            return

        for r in claims:
            claim = dict(r)
            org_code = claim["org_code"]
            zone_id = claim["zone_id"]
            room_id = claim["room_id"]

            org = await db.get_organization(org_code)
            if not org:
                continue

            sec = await get_zone_security(db, zone_id)
            if sec == "secured":
                continue  # No yield from secured zones

            influence = await get_territory_influence(db, org_code, zone_id)
            tier = _get_influence_tier(influence)
            if tier == "none":
                continue

            yield_key = (sec, tier)
            yield_table = _RESOURCE_YIELDS.get(yield_key)
            if not yield_table:
                continue

            # Pick one yield entry at random from the table for this tick
            entry = random.choice(yield_table)
            resource_type, min_qty, max_qty, _bonus = entry
            qty = random.randint(min_qty, max_qty)

            room = await db.get_room(room_id)
            room_name = room.get("name", f"Room #{room_id}") if room else f"Room #{room_id}"

            if resource_type == "credits":
                await db.adjust_org_treasury(org["id"], qty)
                log.info("[territory] resource node: %s room %d yielded %dcr",
                         org_code, room_id, qty)
                # Notify any online members of this org
                await _notify_org_members(
                    session_mgr,
                    org_code,
                    f"  \033[2m[Territory] Resource node in {room_name} generated {qty:,}cr "
                    f"for the treasury.\033[0m",
                )
            else:
                # Crafting resource → org storage
                result = await adjust_org_storage(
                    db, org_code,
                    resource_type=resource_type,
                    quantity=qty,
                    quality=_random_resource_quality(sec, influence),
                )
                if result["ok"]:
                    log.info("[territory] resource node: %s room %d yielded %d %s (q%d)",
                             org_code, room_id, qty, resource_type, result.get("quality", 0))
                    await _notify_org_members(
                        session_mgr,
                        org_code,
                        f"  \033[2m[Territory] Resource node in {room_name} added "
                        f"{qty}x {resource_type} (quality {result.get('quality', 0)}) "
                        f"to the faction armory.\033[0m",
                    )
                else:
                    log.warning("[territory] resource node drop failed for %s room %d: %s",
                                org_code, room_id, result.get("msg", "unknown"))

    except Exception as e:
        log.warning("[territory] resource node tick error: %s", e)


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
        await db._db.execute(
            "UPDATE organizations SET properties = ? WHERE code = ?",
            (json.dumps(props), org_code),
        )
        await db._db.commit()
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
    if not await is_room_claimed_by(db, room_id, org_code):
        return {"ok": False,
                "msg": "You must be in one of your organization's claimed rooms to access the armory."}

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
    if not await is_room_claimed_by(db, room_id, org_code):
        return {"ok": False,
                "msg": "You must be in one of your organization's claimed rooms to access the armory."}

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
    if not await is_room_claimed_by(db, room_id, org_code):
        return {"ok": False,
                "msg": "You must be in one of your organization's claimed rooms to access the armory."}

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
# DROP 6D: Contesting Territory
# ══════════════════════════════════════════════════════════════════════════════
"""
Contest mechanic (design doc §6):

1. Rival org influence reaches 75% of holding org's influence in a zone.
2. Contest auto-declared. Director notified. 7-day timer starts.
3. During contest: both orgs' influence decays at 2× normal rate unless
   maintained by active presence.  Members of both orgs can attack each
   other without consent in that zone (PvP no-consent override).
4. After 7 days: if challenger influence > holder influence, all claimed
   rooms in zone transfer to challenger.  If holder still higher, contest
   ends, challenger loses 25 influence (failed assault cost).
5. Lawless-only shortcut: kill the guard NPC in a claimed room AND have
   50+ influence → immediate hostile takeover of that specific room.

Architecture invariant: all contest state lives in territory_contests table.
No in-memory caching of contest status — always read from DB.
"""

CONTEST_DURATION_SECS   = 7 * 24 * 3600   # 7 real days
CONTEST_TRIGGER_RATIO   = 0.75             # challenger / holder ratio that triggers
CONTEST_DECAY_MULTIPLIER = 2               # influence decay rate during contest
CONTEST_FAILURE_PENALTY = 25              # influence lost by challenger on failed contest

TERRITORY_CONTESTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS territory_contests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id             INTEGER NOT NULL,
    holder_org_code     TEXT    NOT NULL,
    challenger_org_code TEXT    NOT NULL,
    started_at          REAL    NOT NULL,
    ends_at             REAL    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'active',
    UNIQUE(zone_id, status)
);
"""


async def ensure_contest_schema(db) -> None:
    """Create territory_contests table if absent. Idempotent."""
    try:
        await db._db.execute(TERRITORY_CONTESTS_SCHEMA.strip())
        await db._db.commit()
    except Exception as e:
        log.warning("[territory] contest schema error: %s", e)


async def get_active_contest(db, zone_id: int) -> Optional[dict]:
    """Return the active contest for a zone, or None."""
    try:
        rows = await db._db.execute_fetchall(
            "SELECT * FROM territory_contests WHERE zone_id = ? AND status = 'active'",
            (zone_id,),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_active_contest: unhandled exception", exc_info=True)
        return None


async def get_contests_for_org(db, org_code: str) -> list[dict]:
    """Return all active contests where org is holder or challenger."""
    try:
        rows = await db._db.execute_fetchall(
            """SELECT * FROM territory_contests
               WHERE (holder_org_code = ? OR challenger_org_code = ?)
               AND status = 'active'""",
            (org_code, org_code),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_contests_for_org: unhandled exception", exc_info=True)
        return []


async def is_in_active_contest(db, zone_id: int,
                                org_a: str, org_b: str) -> bool:
    """
    Return True if org_a and org_b are in an active contest in zone_id.
    Used by PvP gate to allow no-consent combat between rival orgs.
    """
    contest = await get_active_contest(db, zone_id)
    if not contest:
        return False
    orgs = {contest["holder_org_code"], contest["challenger_org_code"]}
    return org_a in orgs and org_b in orgs


async def _declare_contest(db, zone_id: int,
                            holder_org: str, challenger_org: str,
                            session_mgr=None) -> None:
    """
    Declare a territory contest.  Called from check_and_declare_contests().
    Records contest in DB, notifies online players, pings Director digest.
    """
    now = time.time()
    ends_at = now + CONTEST_DURATION_SECS
    try:
        await db._db.execute(
            """INSERT OR IGNORE INTO territory_contests
               (zone_id, holder_org_code, challenger_org_code, started_at, ends_at, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (zone_id, holder_org, challenger_org, now, ends_at),
        )
        await db._db.commit()
    except Exception as e:
        log.warning("[territory] contest declare error: %s", e)
        return

    zone_name = await get_zone_name(db, zone_id)
    holder_name   = holder_org.replace("_", " ").title()
    chall_name    = challenger_org.replace("_", " ").title()

    log.info("[territory] contest declared: %s vs %s in zone %d (%s). Ends in 7 days.",
             challenger_org, holder_org, zone_id, zone_name)

    # Broadcast to all online players
    if session_mgr:
        msg = (
            f"\n  \033[1;31m[TERRITORY CONTEST]\033[0m "
            f"\033[1;37m{chall_name}\033[0m is challenging "
            f"\033[1;37m{holder_name}\033[0m for control of "
            f"\033[1;36m{zone_name}\033[0m.\n"
            f"  The contest ends in 7 days. Combat between these factions "
            f"in {zone_name} requires no consent.\n"
        )
        try:
            for sess in session_mgr.all:
                if sess.is_in_game:
                    await sess.send_line(msg)
        except Exception as e:
            log.warning("[territory] contest broadcast error: %s", e)


async def check_and_declare_contests(db, org_code: str, zone_id: int,
                                      session_mgr=None) -> None:
    """
    After any influence change, check if a new contest should be declared.
    Called from adjust_territory_influence() for all positive deltas.

    Logic:
    - Find the current zone holder (org with most influence + ≥1 claim).
    - If our influence is now ≥ 75% of holder's and we're not the holder,
      and no active contest exists, declare one.
    - Also: if we ARE the holder, check if any rival has reached 75%.
    """
    try:
        # Get all influence in zone
        all_inf = await get_zone_territory_all(db, zone_id)
        if len(all_inf) < 2:
            return  # Need at least two orgs to contest

        # Find holder: org with claims in this zone (by influence, descending)
        zone_claims_by_org: dict[str, int] = {}
        try:
            rows = await db._db.execute_fetchall(
                "SELECT org_code, COUNT(*) as cnt FROM territory_claims WHERE zone_id = ? GROUP BY org_code",
                (zone_id,),
            )
            for r in rows:
                zone_claims_by_org[r["org_code"]] = r["cnt"]
        except Exception:
            log.warning("check_and_declare_contests: unhandled exception", exc_info=True)
            pass

        if not zone_claims_by_org:
            return  # Nobody holds claims — no contest possible

        # Holder = org with claims, highest influence
        holder_org = max(
            zone_claims_by_org.keys(),
            key=lambda o: all_inf.get(o, 0),
            default=None,
        )
        if not holder_org:
            return

        holder_inf = all_inf.get(holder_org, 0)
        if holder_inf == 0:
            return

        # Check if any rival (with ≥ THRESHOLD_FOOTHOLD) reaches the trigger ratio
        existing_contest = await get_active_contest(db, zone_id)
        if existing_contest:
            return  # Already contesting — no new declaration

        for rival_code, rival_inf in all_inf.items():
            if rival_code == holder_org:
                continue
            if rival_inf < THRESHOLD_FOOTHOLD:
                continue
            ratio = rival_inf / holder_inf
            if ratio >= CONTEST_TRIGGER_RATIO:
                # Declare contest: rival is challenging holder
                await _declare_contest(db, zone_id, holder_org, rival_code,
                                        session_mgr=session_mgr)
                return  # Only one contest per zone at a time
    except Exception as e:
        log.warning("[territory] contest check error: %s", e)


async def tick_contest_resolution(db, session_mgr) -> None:
    """
    Hourly tick: check all active contests for expiry and resolve them.

    Resolution rules (design doc §6.1):
    - If challenger influence > holder influence → challenger wins.
      All claims in zone transfer to challenger.
    - If holder influence ≥ challenger → holder wins.
      Challenger loses CONTEST_FAILURE_PENALTY influence.
    - Contest status set to 'resolved' or 'failed'.
    """
    try:
        now = time.time()
        active = await db._db.execute_fetchall(
            "SELECT * FROM territory_contests WHERE status = 'active' AND ends_at <= ?",
            (now,),
        )
        for r in active:
            contest = dict(r)
            zone_id  = contest["zone_id"]
            holder   = contest["holder_org_code"]
            chall    = contest["challenger_org_code"]

            holder_inf = await get_territory_influence(db, holder, zone_id)
            chall_inf  = await get_territory_influence(db, chall, zone_id)
            zone_name  = await get_zone_name(db, zone_id)

            if chall_inf > holder_inf:
                # Challenger wins — transfer all claims in zone
                await _transfer_zone_claims(db, zone_id, holder, chall)
                await db._db.execute(
                    "UPDATE territory_contests SET status = 'resolved' WHERE id = ?",
                    (contest["id"],),
                )
                await db._db.commit()

                winner_name = chall.replace("_", " ").title()
                loser_name  = holder.replace("_", " ").title()
                msg = (
                    f"\n  \033[1;31m[TERRITORY SEIZED]\033[0m "
                    f"\033[1;37m{winner_name}\033[0m has taken control of "
                    f"\033[1;36m{zone_name}\033[0m from "
                    f"\033[1;37m{loser_name}\033[0m.\n"
                )
                log.info("[territory] contest resolved: %s took %s in zone %d",
                         chall, holder, zone_id)
            else:
                # Holder defends — challenger penalized
                await adjust_territory_influence(
                    db, chall, zone_id, -CONTEST_FAILURE_PENALTY,
                    reason="failed contest penalty",
                )
                await db._db.execute(
                    "UPDATE territory_contests SET status = 'failed' WHERE id = ?",
                    (contest["id"],),
                )
                await db._db.commit()

                winner_name = holder.replace("_", " ").title()
                loser_name  = chall.replace("_", " ").title()
                msg = (
                    f"\n  \033[1;33m[TERRITORY DEFENDED]\033[0m "
                    f"\033[1;37m{winner_name}\033[0m has held "
                    f"\033[1;36m{zone_name}\033[0m against "
                    f"\033[1;37m{loser_name}\033[0m's challenge.\n"
                )
                log.info("[territory] contest failed: %s held %s in zone %d",
                         holder, zone_id, zone_id)

            # Broadcast outcome to all online players
            if session_mgr:
                try:
                    for sess in session_mgr.all:
                        if sess.is_in_game:
                            await sess.send_line(msg)
                except Exception as e:
                    log.warning("[territory] contest outcome broadcast error: %s", e)

    except Exception as e:
        log.warning("[territory] contest resolution tick error: %s", e)


async def _transfer_zone_claims(db, zone_id: int,
                                  from_org: str, to_org: str) -> None:
    """
    Transfer all claims in a zone from one org to another.
    Called on contest victory.  Guard NPCs are re-flagged to new owner.
    """
    try:
        rows = await db._db.execute_fetchall(
            "SELECT * FROM territory_claims WHERE zone_id = ? AND org_code = ?",
            (zone_id, from_org),
        )
        for r in rows:
            claim = dict(r)
            await db._db.execute(
                "UPDATE territory_claims SET org_code = ? WHERE id = ?",
                (to_org, claim["id"]),
            )
            # Update guard NPC ai_config to reflect new owner
            if claim.get("guard_npc_id"):
                try:
                    npc = await db.get_npc(claim["guard_npc_id"])
                    if npc:
                        import json as _j
                        ai = _j.loads(npc.get("ai_config_json", "{}") or "{}")
                        ai["guard_for_org"] = to_org
                        ai["faction"] = to_org.replace("_", " ").title()
                        await db.update_npc(
                            claim["guard_npc_id"],
                            ai_config_json=_j.dumps(ai),
                        )
                except Exception as e:
                    log.warning("[territory] guard NPC retag error: %s", e)
        await db._db.commit()
        log.info("[territory] transferred %d claims in zone %d from %s to %s",
                 len(rows), zone_id, from_org, to_org)
    except Exception as e:
        log.warning("[territory] claim transfer error: %s", e)


async def hostile_takeover_claim(db, char: dict, org_code: str,
                                   room_id: int) -> dict:
    """
    Lawless-zone hostile takeover: claim a room whose guard was just killed.
    Requirements (design doc §6.3):
    - Zone must be lawless
    - Attacking org must have 50+ influence in the zone
    - The room must currently be claimed by a rival (not us)
    - The room's guard NPC must be dead / absent (just killed)
    Returns {"ok": bool, "msg": str}.
    """
    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}
    zone_id = room.get("zone_id")
    if not zone_id:
        return {"ok": False, "msg": "This room is not in a zone."}

    # Must be lawless
    sec = await get_zone_security(db, zone_id)
    if sec != "lawless":
        return {"ok": False,
                "msg": "Hostile takeover is only possible in lawless zones."}

    # Must have foothold influence
    influence = await get_territory_influence(db, org_code, zone_id)
    if influence < THRESHOLD_FOOTHOLD:
        return {"ok": False,
                "msg": f"You need {THRESHOLD_FOOTHOLD}+ influence in this zone to seize territory "
                       f"(current: {influence})."}

    # Room must be claimed by a rival
    claim = await get_claim(db, room_id)
    if not claim:
        return {"ok": False, "msg": "This room isn't claimed — use 'faction claim' instead."}
    if claim["org_code"] == org_code:
        return {"ok": False, "msg": "Your organization already controls this room."}

    rival_org = claim["org_code"]

    # Guard must be dead/absent (guard_npc_id should be NULL or NPC deleted)
    if claim.get("guard_npc_id"):
        existing_npc = await db.get_npc(claim["guard_npc_id"])
        if existing_npc:
            npc_cs = existing_npc.get("char_sheet_json", "{}")
            try:
                import json as _j
                cs_dict = _j.loads(npc_cs)
                wl = cs_dict.get("wound_level", 0)
                # wound_level 5+ = incapacitated/dead
                if wl < 5:
                    return {"ok": False,
                            "msg": "The guard still stands. Defeat them first."}
            except Exception:
                log.warning("hostile_takeover_claim: unhandled exception", exc_info=True)
                pass
        # Guard reference exists but NPC is gone — stale ref, allow takeover

    # Check treasury for claim cost
    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": "Unknown organization."}
    if org.get("treasury", 0) < CLAIM_COST:
        return {"ok": False,
                "msg": f"Insufficient treasury. Seizing costs {CLAIM_COST:,}cr "
                       f"(have {org.get('treasury', 0):,}cr)."}

    # Remove the rival's guard NPC if still present (dead guard cleanup)
    if claim.get("guard_npc_id"):
        try:
            await db._db.execute(
                "DELETE FROM npcs WHERE id = ?", (claim["guard_npc_id"],)
            )
        except Exception:
            log.warning("hostile_takeover_claim: unhandled exception", exc_info=True)
            pass

    # Overwrite claim
    new_balance = await db.adjust_org_treasury(org["id"], -CLAIM_COST)
    now = time.time()
    await db._db.execute(
        """UPDATE territory_claims
           SET org_code = ?, claimed_by = ?, claimed_at = ?, guard_npc_id = NULL
           WHERE room_id = ?""",
        (org_code, char["id"], now, room_id),
    )
    await db._db.commit()

    # Influence swing: attacker gains, defender loses
    await adjust_territory_influence(
        db, org_code, zone_id, 10,
        reason=f"hostile takeover by {char.get('name', '?')}")
    await adjust_territory_influence(
        db, rival_org, zone_id, -15,
        reason=f"room seized by {org_code}")

    room_name  = room.get("name", f"Room #{room_id}")
    zone_name  = await get_zone_name(db, zone_id)
    rival_name = rival_org.replace("_", " ").title()

    log.info("[territory] hostile takeover: %s seized room %d (%s) from %s in zone %d",
             org_code, room_id, room_name, rival_org, zone_id)

    return {
        "ok": True,
        "msg": (f"Territory seized: {room_name} taken from {rival_name}. "
                f"Cost: {CLAIM_COST:,}cr. Treasury: {new_balance:,}cr."),
        "rival_org": rival_org,
        "room_name": room_name,
        "zone_name": zone_name,
    }


async def get_contest_status_lines(db, org_code: str) -> list[str]:
    """Return formatted active contest status for an org."""
    contests = await get_contests_for_org(db, org_code)
    if not contests:
        return []

    lines = ["\033[1;37m── Active Contests ──\033[0m"]
    now = time.time()
    for c in contests:
        zone_name   = await get_zone_name(db, c["zone_id"])
        holder      = c["holder_org_code"].replace("_", " ").title()
        chall       = c["challenger_org_code"].replace("_", " ").title()
        secs_left   = max(0, c["ends_at"] - now)
        days_left   = int(secs_left // 86400)
        hours_left  = int((secs_left % 86400) // 3600)
        role        = "Holder" if c["holder_org_code"] == org_code else "Challenger"
        role_color  = "\033[1;36m" if role == "Holder" else "\033[1;31m"

        holder_inf  = await get_territory_influence(db, c["holder_org_code"], c["zone_id"])
        chall_inf   = await get_territory_influence(db, c["challenger_org_code"], c["zone_id"])

        lines.append(
            f"  {zone_name:<30} {role_color}[{role}]\033[0m  "
            f"{holder} {holder_inf} vs {chall} {chall_inf}  "
            f"\033[2m{days_left}d {hours_left}h remaining\033[0m"
        )
    return lines
