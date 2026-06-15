# -*- coding: utf-8 -*-
"""
engine/contest.py — Region-keyed contest state machine.

SYN.3 (2026-05-25) — Full contest engine for the Contestable
Wilderness pivot. Per ``contestable_wilderness_design_v2.md`` §2.4
and §3.3.

Originally split into SYN.3.a (schema + engine half) and SYN.3.b
(culminating fight + caller retargets + Drop 6D physical deletion);
landed as a combined drop per Brian's roll-up call.

The Drop 6D zone-keyed contest engine has been physically retired
in the same drop — twelve surfaces deleted from engine/territory.py.
The five caller retargets (server/session.py HUD, parser/combat_commands.py
PvP gate, parser/combat_commands.py guard-kill block,
parser/faction_commands.py::_cmd_seize, server/tick_handlers_economy.py)
all now point at this module.

What ships in SYN.3 (full pivot)
────────────────────────────────
* ``region_contests`` + ``region_contest_cooldowns`` schema
* ``ensure_region_contest_schema(db)`` — wired into
  ``engine/territory.py::ensure_territory_schema``
* Public query surfaces:
    - ``get_active_region_contest(db, slug)``
    - ``get_org_region_contests(db, org_code)``
    - ``is_region_in_active_contest(db, slug, org_a, org_b)``
    - ``is_org_on_contest_cooldown(db, slug, org_code)``
* Mutating surfaces:
    - ``declare_region_contest(db, slug, defender, challenger, session_mgr)``
    - ``check_and_declare_region_contests(db, org_code, slug, session_mgr)``
    - ``tick_region_contest_resolution(db, session_mgr)`` — two-phase tick:
        (1) at accumulation_ends_at → spawn Anchor NPC + reinforcements
        (2) at ends_at → defender wins by default (Anchor not killed)
    - ``on_npc_killed_in_combat(db, npc_id, killer_char, room_id,
        session_mgr)`` — culminating-fight kill detection; wired into
        the combat NPC-death hook in parser/combat_commands.py
    - ``apply_contest_influence_multipliers(...)`` — pure helper used
      by ``adjust_territory_influence`` when ``region_slug`` is passed
* Pure rules (no DB):
    - ``compute_anchor_hp(defender_influence)``
    - ``compute_anchor_reinforcements(challenger_influence)``
    - ``compute_outnumbered_defender_multiplier(def_count, chall_count)``
* Display:
    - ``get_region_contest_status_lines(db, org_code)``

Design invariants
─────────────────
* One active contest per region (``UNIQUE(region_slug, status)``
  enforced via partial-unique on the ``active`` rows).
* Defender slot is NULL for un-owned-region seize contests.
* Contest duration: 7 days. Accumulation phase: total - 4 hours.
  Culminating fight: final 4 hours of day 7.
* 14-day post-loss cooldown enforced per (region_slug, org_code).
* CONTESTED never promotes to SECURED through contest outcomes.

Notes on influence accounting
─────────────────────────────
Per the SYN.1.a docstring on ``claim_region``, influence remains
zone-keyed in HEAD ("transitional rule for SYN.1; SYN.3 will make
this strictly per-region once influence is region-keyed"). Per-region
influence is a deeper refactor not landed yet. The 75% trigger
ratio compares challenger vs defender influence in the *parent zone*
of the region.

The failure-penalty influence slash (25 points off the losing
challenger) is applied at the zone level for the same reason.

Influence doubling (2×) + outnumbered-defender bonus (1.5×) is
applied at the influence-adjustment seam in
``engine/territory.py::adjust_territory_influence`` when callers
pass the ``region_slug`` kwarg. Domain hooks that increment
influence on missions/bounties/harvests are responsible for passing
the region context where applicable — those hooks land in SYN.5
(espionage-as-influence) and SYN.6 (harvest). SYN.3 ships the
multiplier mechanism; the consumers wire up later.

Logging
───────
All state transitions log at INFO with ``[contest]`` prefix.
Exception paths log at WARNING with ``exc_info=True`` for postmortem.
"""
from __future__ import annotations


import logging
import json
import time
from typing import Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants — per design §2.4
# ──────────────────────────────────────────────────────────────────────

# Total contest duration: 7 real-time days from declaration.
REGION_CONTEST_DURATION_SECS = 7 * 24 * 3600

# Culminating fight window: final 4 hours of day 7. Anchor spawns at
# the start of this window; killing-blow on Anchor wins the contest.
REGION_CONTEST_CULMINATING_SECS = 4 * 3600

# Accumulation phase: everything BEFORE the culminating window. The
# design wording "Days 1-6" is a calendar shorthand — the precise
# split is (7 days - 4 hours) of accumulation, then the final 4
# hours are the culminating fight. This makes
# accumulation_ends_at = started_at + ACCUMULATION_SECS and
# ends_at = started_at + DURATION_SECS, with the gap between them
# being exactly the culminating window.
REGION_CONTEST_ACCUMULATION_SECS = (
    REGION_CONTEST_DURATION_SECS - REGION_CONTEST_CULMINATING_SECS
)

# Sanity invariant: accumulation + culminating == total duration.
assert REGION_CONTEST_ACCUMULATION_SECS + REGION_CONTEST_CULMINATING_SECS \
       == REGION_CONTEST_DURATION_SECS, \
    "contest phase split must sum to total duration"

# Challenger vs defender influence ratio (in parent zone) that
# auto-triggers a contest declaration when the region is held by a
# rival. Per design §2.4 first bullet.
REGION_CONTEST_TRIGGER_RATIO = 0.75

# Influence floor for the challenger before auto-trigger fires.
# Avoids declaring contests on noise-level influence shifts.
# Matches the legacy CONTEST gate of THRESHOLD_FOOTHOLD (50).
REGION_CONTEST_MIN_CHALLENGER_INFLUENCE = 50

# Influence penalty for a failed challenge. Per design §2.4
# "Contest resolution" — loser's influence slashed by 25.
REGION_CONTEST_FAILURE_PENALTY = 25

# Cooldown after a lost contest. Per design §2.4 — "an org that
# loses a contest cannot challenge the same region again for 14
# days." Symmetric: applies to both defender-loss and challenger-loss.
REGION_CONTEST_COOLDOWN_SECS = 14 * 24 * 3600

# Region Anchor NPC — pure-rule constants used by the HP/tier scaling.
# Per design §2.4 "Day 7, final 4 hours: Culminating fight".

# Base HP of the Region Anchor NPC. Defender influence above 50
# adds +1 HP per point (per design's worked example: defender 90
# influence → 100 + (90-50) = 140 HP).
REGION_ANCHOR_BASE_HP = 100

# Defender-influence floor for HP scaling: only influence ABOVE
# this floor contributes to bonus HP.
REGION_ANCHOR_HP_FLOOR_INFLUENCE = 50

# Challenger-influence floor for reinforcement tier scaling: only
# challenger influence above this threshold pulls in extra Tier-1
# reinforcement NPCs alongside the Anchor.
REGION_ANCHOR_REINFORCEMENT_THRESHOLD = 100

# +1 reinforcement NPC per N points of challenger influence above
# the threshold. Per design's worked example.
REGION_ANCHOR_REINFORCEMENT_PER = 25

# Lane D2 (GG11 §8B): the challenger org's Violence Index modulates how
# many bodies it commits to the culminating fight. Bands mirror
# ``engine.organizations.violence_descriptor`` exactly so the mechanical
# effect and the narrated posture stay legible together: a "bloody"
# challenger (>=70) brings +1 reinforcement, a "range war" challenger
# (>=85) brings +2. A None / sub-"bloody" posture is unchanged
# (backward-compatible). The bonus only applies to a challenger that
# already fields reinforcements by influence — posture scales a real
# force, it does not manufacture one from nothing.
REGION_CONTEST_BLOODY_VI = 70
REGION_CONTEST_RANGE_WAR_VI = 85

# Outnumbered-defender bonus multiplier (anti-zerg, Albion lesson).
# Applied to defender's influence-gain rate during accumulation
# when challenger faction has more registered members than the
# defender. Per design §2.4 "Outnumbered-defender bonus".
OUTNUMBERED_DEFENDER_INFLUENCE_MULTIPLIER = 1.5


# ──────────────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────────────
#
# ``region_contests``
#   One row per contest event. ``status`` transitions:
#     'active' → 'resolved_challenger' (challenger killed Anchor)
#     'active' → 'resolved_defender'   (defender held; Anchor survived
#                                       OR no kill in culminating window)
#     'active' → 'failed'              (administrative cancellation,
#                                       region became invalid mid-contest,
#                                       etc — exception state)
#   ``UNIQUE(region_slug, status)`` lets us enforce "at most one
#   active contest per region" via the (region_slug, 'active') row.
#   Resolved/failed rows accumulate as the contest history log.
#   ``defender_org_code`` is NULL for un-owned-region seize contests.
#
# ``region_contest_cooldowns``
#   Per (region_slug, org_code), the unix-time when the org may
#   re-challenge that region. Set on contest resolution for the
#   losing side.

REGION_CONTEST_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS region_contests (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    region_slug          TEXT    NOT NULL,
    defender_org_code    TEXT,
    challenger_org_code  TEXT    NOT NULL,
    zone_id              INTEGER,
    started_at           REAL    NOT NULL,
    accumulation_ends_at REAL    NOT NULL,
    ends_at              REAL    NOT NULL,
    anchor_landmark_id   INTEGER,
    anchor_npc_id        INTEGER,
    status               TEXT    NOT NULL DEFAULT 'active',
    UNIQUE(region_slug, status)
);
CREATE INDEX IF NOT EXISTS idx_region_contests_region
    ON region_contests(region_slug);
CREATE INDEX IF NOT EXISTS idx_region_contests_status
    ON region_contests(status);
CREATE INDEX IF NOT EXISTS idx_region_contests_challenger
    ON region_contests(challenger_org_code);
CREATE INDEX IF NOT EXISTS idx_region_contests_defender
    ON region_contests(defender_org_code);
CREATE TABLE IF NOT EXISTS region_contest_cooldowns (
    region_slug    TEXT NOT NULL,
    org_code       TEXT NOT NULL,
    cooldown_until REAL NOT NULL,
    PRIMARY KEY (region_slug, org_code)
);
CREATE INDEX IF NOT EXISTS idx_region_contest_cooldowns_org
    ON region_contest_cooldowns(org_code);
"""


async def ensure_region_contest_schema(db) -> None:
    """Create the region contest tables. Idempotent.

    Called from ``engine/territory.py::ensure_territory_schema`` at
    boot. Safe to call repeatedly — every statement is
    ``CREATE TABLE IF NOT EXISTS`` or ``CREATE INDEX IF NOT EXISTS``.
    """
    try:
        for stmt in REGION_CONTEST_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception as e:
        log.warning("[contest] schema create error: %s", e, exc_info=True)


# ──────────────────────────────────────────────────────────────────────
# Pure rules — Anchor HP/tier scaling, outnumbered multiplier
# ──────────────────────────────────────────────────────────────────────
#
# These are unit-testable in isolation (no DB). They are also called
# by SYN.3.b for the Anchor spawn flow.

def compute_anchor_hp(defender_influence: int) -> int:
    """Compute the Region Anchor NPC's HP from defender influence.

    Per design §2.4: Anchor base HP = 100, +1 HP per defender
    influence point ABOVE 50.

    Examples:
        defender_influence=50  → 100 HP  (floor)
        defender_influence=90  → 140 HP  (design worked example)
        defender_influence=150 → 200 HP  (cap of influence: 150)
        defender_influence=20  → 100 HP  (below floor → floor)
        defender_influence=0   → 100 HP  (un-owned region defender)
    """
    inf = int(defender_influence) if defender_influence is not None else 0
    bonus = max(0, inf - REGION_ANCHOR_HP_FLOOR_INFLUENCE)
    return REGION_ANCHOR_BASE_HP + bonus


def compute_anchor_reinforcements(
    challenger_influence: int,
    challenger_violence_index: Optional[int] = None,
) -> int:
    """Compute extra Tier-1 reinforcement NPCs alongside the Anchor.

    Per design §2.4:
        Challenger below 50 influence: Anchor stays tier2 (0 reinforce).
        Challenger above 100: +1 reinforce per 25 influence above 100.

    Lane D2 (GG11 §8B): ``challenger_violence_index`` modulates the
    influence-derived count. A "bloody"-band challenger (VI >= 70) brings
    +1; a "range war"-band challenger (VI >= 85) brings +2. The posture
    bonus only applies once the challenger already fields reinforcements
    by influence (a base of 0 stays 0 — posture scales a real force, it
    does not manufacture one). ``None`` (the default) leaves the count at
    its pre-D2 value, so existing callers are unaffected.

    Examples (no posture / posture=None — pre-D2 behaviour preserved):
        challenger_influence=40   → 0 reinforce  (below 50 floor)
        challenger_influence=80   → 0 reinforce  (between 50 and 100)
        challenger_influence=100  → 0 reinforce  (at threshold)
        challenger_influence=125  → 1 reinforce
        challenger_influence=149  → 1 reinforce  (24 above, not 25)
        challenger_influence=150  → 2 reinforce  (influence cap)

    Examples (with posture):
        influence=150, VI=88  → 4 reinforce  (2 + 2 range-war bonus)
        influence=125, VI=72  → 2 reinforce  (1 + 1 bloody bonus)
        influence=125, VI=40  → 1 reinforce  (sub-bloody → no bonus)
        influence=80,  VI=95  → 0 reinforce  (below floor → no bonus)
    """
    inf = int(challenger_influence) if challenger_influence is not None else 0
    if inf <= REGION_ANCHOR_REINFORCEMENT_THRESHOLD:
        base = 0
    else:
        over = inf - REGION_ANCHOR_REINFORCEMENT_THRESHOLD
        base = over // REGION_ANCHOR_REINFORCEMENT_PER
    if base <= 0:
        return base
    vi = challenger_violence_index
    if isinstance(vi, (int, float)) and not isinstance(vi, bool):
        if vi >= REGION_CONTEST_RANGE_WAR_VI:
            base += 2
        elif vi >= REGION_CONTEST_BLOODY_VI:
            base += 1
    return base


def compute_outnumbered_defender_multiplier(
    defender_member_count: int,
    challenger_member_count: int,
) -> float:
    """Compute defender's influence-gain multiplier during accumulation.

    Per design §2.4: if challenger faction has more registered
    members than defender, defender's influence-gain rate is 1.5×.
    Otherwise 1.0× (no bonus).

    Examples:
        defender=5, challenger=8 → 1.5  (defender outnumbered)
        defender=5, challenger=5 → 1.0  (equal, no bonus)
        defender=8, challenger=5 → 1.0  (defender has more, no bonus)
        defender=0, challenger=1 → 1.5  (any deficit triggers)
    """
    d = int(defender_member_count) if defender_member_count is not None else 0
    c = int(challenger_member_count) if challenger_member_count is not None else 0
    if c > d:
        return OUTNUMBERED_DEFENDER_INFLUENCE_MULTIPLIER
    return 1.0


# ──────────────────────────────────────────────────────────────────────
# Violence Index → turf-dispute narration (Lane D2)
# ──────────────────────────────────────────────────────────────────────
#
# The challenger org's Violence Index colours both the contest mechanics
# (the reinforcement count, above) and the player-facing narration (the
# declaration broadcast + the ``faction status`` contest line). The clause
# map is keyed on ``violence_descriptor``'s band labels so the narrated
# intensity always tracks the mechanical posture.

_CONTEST_POSTURE_CLAUSE = {
    "surgical":  "Expect a contained, surgical operation.",
    "pointed":   "Expect a pointed, disciplined fight.",
    "heated":    "Expect heated, escalating violence.",
    "bloody":    "Expect a bloody fight with little restraint.",
    "range war": "Expect an all-out range war.",
}


async def _org_violence_index(db, org_code: Optional[str]) -> Optional[int]:
    """Best-effort lookup of an org's Violence Index (0-100), or None.

    Used by the contest narration + reinforcement seams. Tolerant of a
    missing org, a DB without ``get_organization``, or any read error —
    returns None so the caller silently falls back to posture-free
    behaviour (the contest still declares/resolves; it just isn't
    coloured by posture)."""
    if not org_code:
        return None
    try:
        from engine.organizations import get_org_violence_index
        org = await db.get_organization(org_code)
        return get_org_violence_index(org)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# Query surfaces
# ──────────────────────────────────────────────────────────────────────

async def get_active_region_contest(db, region_slug: str) -> Optional[dict]:
    """Return the active contest row for a region, or None.

    There is at most one active contest per region (enforced by the
    ``UNIQUE(region_slug, status)`` constraint on the 'active' row).
    """
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_contests "
            "WHERE region_slug = ? AND status = 'active'",
            (region_slug,),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_active_region_contest: unhandled exception",
                    exc_info=True)
        return None


async def get_org_region_contests(db, org_code: str) -> list[dict]:
    """Return all active contests where org_code is defender or challenger."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_contests "
            "WHERE (defender_org_code = ? OR challenger_org_code = ?) "
            "AND status = 'active' "
            "ORDER BY started_at",
            (org_code, org_code),
        )
        return [dict(r) for r in rows]
    except Exception:
        log.warning("get_org_region_contests: unhandled exception",
                    exc_info=True)
        return []


async def is_region_in_active_contest(
    db, region_slug: str, org_a: str, org_b: str,
) -> bool:
    """True if org_a and org_b are in an active contest for the region.

    Used by PvP gates: in a contested region, faction-vs-faction
    combat between the two contestants requires no consent (the
    contest *is* the consent). Per design §2.4 "Cross-faction PvP at
    landmarks in the contested region does not require consent".

    Both orderings are accepted (org_a as defender / org_b as
    challenger and vice versa).
    """
    contest = await get_active_region_contest(db, region_slug)
    if not contest:
        return False
    if not org_a or not org_b or org_a == org_b:
        return False
    parties = {
        contest.get("defender_org_code"),
        contest.get("challenger_org_code"),
    }
    parties.discard(None)
    return org_a in parties and org_b in parties


async def is_org_on_contest_cooldown(
    db, region_slug: str, org_code: str,
) -> bool:
    """True if org_code is on post-loss cooldown for this region.

    Per design §2.4 "Cooldown: an org that loses a contest cannot
    challenge the same region again for 14 days."

    Stale cooldowns (cooldown_until <= now) return False and are
    *not* eagerly cleaned — they're inert past their expiry and
    accumulate harmlessly. A future maintenance tick may sweep them.
    """
    try:
        rows = await db.fetchall(
            "SELECT cooldown_until FROM region_contest_cooldowns "
            "WHERE region_slug = ? AND org_code = ?",
            (region_slug, org_code),
        )
        if not rows:
            return False
        return float(rows[0]["cooldown_until"]) > time.time()
    except Exception:
        log.warning("is_org_on_contest_cooldown: unhandled exception",
                    exc_info=True)
        return False


# ──────────────────────────────────────────────────────────────────────
# Declaration
# ──────────────────────────────────────────────────────────────────────

async def declare_region_contest(
    db,
    region_slug: str,
    defender_org_code: Optional[str],
    challenger_org_code: str,
    *,
    zone_id: Optional[int] = None,
    session_mgr=None,
) -> dict:
    """Declare a contest on a region.

    Two paths (per design §2.4 contest triggers):

    1. **Rival-held region**: region is owned by ``defender_org_code``,
       a different org ``challenger_org_code`` challenges. Pass the
       owner as ``defender_org_code``.
    2. **Un-owned region seize**: region is un-owned; an org with
       Foothold+ influence wishes to seize it. Pass
       ``defender_org_code=None``. (Defender slot in DB stores NULL.)

    Validates:
      * Challenger is non-empty and not 'independent'.
      * Defender (if non-None) is different from challenger.
      * No active contest already exists for this region.
      * Challenger is not on cooldown for this region.

    On success, inserts a row into ``region_contests`` with status
    'active' and broadcasts a [REGION CONTEST] line to all online
    players (if ``session_mgr`` is provided).

    Returns ``{"ok": bool, "msg": str, "contest_id": int | None}``.

    Note: this surface does NOT validate that the challenger has
    sufficient influence — that's the caller's responsibility
    (``check_and_declare_region_contests`` for auto-trigger;
    a parser command for un-owned seize). The validation kept here
    is the data-integrity floor (well-formed inputs + uniqueness).
    """
    # ── input validation ──────────────────────────────────────────
    if not challenger_org_code or challenger_org_code == "independent":
        return {"ok": False,
                "msg": "Independent characters cannot challenge regions.",
                "contest_id": None}

    if defender_org_code == challenger_org_code:
        return {"ok": False,
                "msg": "An organisation cannot contest itself.",
                "contest_id": None}

    # ── uniqueness check ──────────────────────────────────────────
    existing = await get_active_region_contest(db, region_slug)
    if existing:
        return {
            "ok": False,
            "msg": (f"A contest is already active in {region_slug} "
                    f"(ends in {_secs_to_human(existing['ends_at'] - time.time())})."),
            "contest_id": None,
        }

    # ── cooldown check ────────────────────────────────────────────
    if await is_org_on_contest_cooldown(db, region_slug, challenger_org_code):
        return {
            "ok": False,
            "msg": (f"Your organisation is on cooldown for {region_slug}. "
                    f"You lost a recent contest here — wait out the 14-day "
                    f"period before re-challenging."),
            "contest_id": None,
        }

    # ── insert row ────────────────────────────────────────────────
    now = time.time()
    accumulation_ends_at = now + REGION_CONTEST_ACCUMULATION_SECS
    ends_at = now + REGION_CONTEST_DURATION_SECS

    try:
        await db.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
            (region_slug, defender_org_code, challenger_org_code,
             zone_id, now, accumulation_ends_at, ends_at),
        )
        await db.commit()
    except Exception as e:
        log.warning("[contest] declare insert failed: %s", e, exc_info=True)
        return {"ok": False,
                "msg": "Contest declaration failed (database error).",
                "contest_id": None}

    # Fetch the inserted row's id (sqlite last_insert_rowid via re-select)
    contest_id: Optional[int] = None
    try:
        rows = await db.fetchall(
            "SELECT id FROM region_contests "
            "WHERE region_slug = ? AND status = 'active'",
            (region_slug,),
        )
        if rows:
            contest_id = int(rows[0]["id"])
    except Exception:
        log.warning("[contest] declare id-readback failed", exc_info=True)

    # ── logging + narrative broadcast ─────────────────────────────
    defender_display = (
        defender_org_code.replace("_", " ").title()
        if defender_org_code else "(un-owned)"
    )
    challenger_display = challenger_org_code.replace("_", " ").title()

    log.info(
        "[contest] declared: %s challenges %s for region %s "
        "(zone=%s, ends_at=%.0f)",
        challenger_org_code, defender_org_code or "(un-owned)",
        region_slug, str(zone_id), ends_at,
    )

    if session_mgr is not None:
        # Per design §2.4 — contest visible to all online players.
        # Lane D2: colour the announcement by the challenger's posture.
        _chal_vi = await _org_violence_index(db, challenger_org_code)
        _posture_clause = ""
        if _chal_vi is not None:
            from engine.organizations import violence_descriptor
            _posture_clause = _CONTEST_POSTURE_CLAUSE.get(
                violence_descriptor(_chal_vi), "")
        msg = (
            f"\n  \033[1;31m[REGION CONTEST]\033[0m "
            f"\033[1;37m{challenger_display}\033[0m is challenging "
            f"\033[1;37m{defender_display}\033[0m for control of "
            f"\033[1;36m{region_slug}\033[0m.\n"
            f"  The contest ends in 7 days. The culminating fight begins "
            f"4 hours before resolution.\n"
            + (f"  \033[2m{_posture_clause}\033[0m\n"
               if _posture_clause else "")
        )
        try:
            for sess in session_mgr.all:
                if getattr(sess, "is_in_game", False):
                    await sess.send_line(msg)
        except Exception as e:
            log.warning("[contest] broadcast error: %s", e, exc_info=True)

    return {
        "ok": True,
        "msg": (f"Contest declared on {region_slug}: "
                f"{challenger_display} vs {defender_display}. "
                f"Resolution in 7 days."),
        "contest_id": contest_id,
    }


def _secs_to_human(secs: float) -> str:
    """Format a remaining-seconds count as 'Xd Yh' for player display."""
    s = max(0, int(secs))
    days = s // 86400
    hours = (s % 86400) // 3600
    if days > 0:
        return f"{days}d {hours}h"
    minutes = (s % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ──────────────────────────────────────────────────────────────────────
# Auto-trigger — rival-held region 75% ratio path
# ──────────────────────────────────────────────────────────────────────

async def check_and_declare_region_contests(
    db,
    challenger_org_code: str,
    region_slug: str,
    *,
    session_mgr=None,
) -> Optional[dict]:
    """Auto-trigger a contest if the 75% threshold is now crossed.

    Called by influence-tick hooks (SYN.3.b wires this — SYN.3.a
    ships the function but no production caller invokes it yet).

    Logic — rival-held region only:
      * Look up region owner via ``engine/territory.py::get_region_owner``.
      * If region is un-owned, return None (un-owned-seize is a
        parser-command-driven flow, not an auto-trigger).
      * If region's owner is the challenger itself, return None.
      * Check existing active contest — if one exists, return None.
      * Check cooldown — if challenger is on cooldown for this
        region, return None.
      * Compute challenger / defender influence ratio in the
        region's parent zone (via territory.py helpers).
      * If challenger influence >= MIN floor AND
        ratio >= TRIGGER (0.75), declare contest with the current
        owner as defender.

    Returns the declared contest dict (from
    ``declare_region_contest``) on declaration, None otherwise.

    Note: the un-owned-region seize path is intentionally NOT
    handled here. An org with Foothold+ influence in an un-owned
    region must declare via an explicit parser command — there's
    no spontaneous auto-trigger for un-owned regions (design §2.4
    second bullet implies player intent).
    """
    # Lazy import to avoid a cycle with territory.py
    try:
        from engine.territory import (
            get_region_owner,
            _get_region_zone,
            get_territory_influence,
        )
    except Exception:
        log.warning("[contest] cannot import territory helpers",
                    exc_info=True)
        return None

    if not challenger_org_code or challenger_org_code == "independent":
        return None

    owner = await get_region_owner(db, region_slug)
    if not owner:
        # Un-owned region — auto-trigger does not apply.
        return None

    defender_org = owner["org_code"]
    if defender_org == challenger_org_code:
        # Already own this region; no contest possible against self.
        return None

    if await get_active_region_contest(db, region_slug):
        return None

    if await is_org_on_contest_cooldown(db, region_slug, challenger_org_code):
        return None

    zone_id = await _get_region_zone(db, region_slug)
    if zone_id is None:
        return None

    challenger_inf = await get_territory_influence(
        db, challenger_org_code, zone_id)
    if challenger_inf < REGION_CONTEST_MIN_CHALLENGER_INFLUENCE:
        return None

    defender_inf = await get_territory_influence(
        db, defender_org, zone_id)
    if defender_inf <= 0:
        # Defender has no influence — ratio is undefined / infinite.
        # Trigger only if challenger is well above the floor; this
        # is the practical edge-case where an owner has decayed to
        # zero influence but still holds the region.
        if challenger_inf >= REGION_CONTEST_MIN_CHALLENGER_INFLUENCE:
            return await declare_region_contest(
                db, region_slug, defender_org, challenger_org_code,
                zone_id=zone_id, session_mgr=session_mgr,
            )
        return None

    ratio = challenger_inf / defender_inf
    if ratio < REGION_CONTEST_TRIGGER_RATIO:
        return None

    return await declare_region_contest(
        db, region_slug, defender_org, challenger_org_code,
        zone_id=zone_id, session_mgr=session_mgr,
    )


# ──────────────────────────────────────────────────────────────────────
# Resolution tick — two-phase culminating fight
# ──────────────────────────────────────────────────────────────────────

async def tick_region_contest_resolution(db, session_mgr=None) -> None:
    """Two-phase contest tick (hourly).

    Phase A — Anchor spawn:
      For each active contest where ``now >= accumulation_ends_at``
      AND ``anchor_npc_id IS NULL`` (Anchor not yet spawned):
        * Pick a contested landmark from the region.
        * Spawn the Region Anchor NPC (tier-2, defender-flavored,
          HP-scaled by defender influence per ``compute_anchor_hp``).
        * Spawn ``compute_anchor_reinforcements(challenger_influence)``
          tier-1 reinforcement NPCs alongside.
        * Record ``anchor_npc_id`` + ``anchor_landmark_id`` on the
          contest row.
        * Broadcast ``[CULMINATING FIGHT]`` to all online players.

    Phase B — Expiry resolution:
      For each active contest where ``now >= ends_at``:
        * If Anchor still alive (or never spawned due to data error),
          defender wins by default. Challenger pays the 25-influence
          failure penalty + 14-day cooldown.
        * Anchor-kill outcomes don't pass through this tick —
          ``on_npc_killed_in_combat`` resolves them immediately via
          ``_resolve_challenger_win``.

    Errors are caught per-contest; one bad row won't bring down the
    whole tick.
    """
    now = time.time()

    # Phase A — Anchor spawn for contests entering the culminating window.
    try:
        spawning = await db.fetchall(
            "SELECT * FROM region_contests "
            "WHERE status = 'active' "
            "  AND accumulation_ends_at <= ? "
            "  AND anchor_npc_id IS NULL "
            "  AND ends_at > ?",
            (now, now),
        )
    except Exception:
        log.warning("[contest] tick: phase A fetch failed", exc_info=True)
        spawning = []

    for r in spawning:
        contest = dict(r)
        try:
            await _spawn_region_anchor(db, contest, session_mgr=session_mgr)
        except Exception:
            log.warning("[contest] anchor spawn failed for region=%s",
                        contest.get("region_slug"), exc_info=True)

    # Phase B — Expiry resolution (defender win by default).
    try:
        expired = await db.fetchall(
            "SELECT * FROM region_contests "
            "WHERE status = 'active' AND ends_at <= ?",
            (now,),
        )
    except Exception:
        log.warning("[contest] tick: phase B fetch failed", exc_info=True)
        return

    for r in expired:
        contest = dict(r)
        await _resolve_defender_win(db, contest, session_mgr=session_mgr)


async def _despawn_contest_anchor(db, contest: dict) -> None:
    """Delete a resolved contest's Region Anchor NPC + its reinforcements.

    Without this, every contest that reached the culminating fight orphaned
    1-5 permanent hostile NPCs in the landmark room: the Anchor is created via
    ``db.create_npc`` and never registered in ``region_garrison``, so
    ``dismiss_region_garrison`` (which only deletes garrison-table rows) could
    never reach it, and no reaper tick exists. Called from BOTH resolution
    paths (defender-win + challenger-win), which between them cover every
    outcome (tick-expiry, killing-blow, no-clear-killer). Best-effort: a delete
    failure logs but never blocks resolution.
    """
    anchor_id = contest.get("anchor_npc_id")
    contest_id = contest.get("id")
    if anchor_id:
        try:
            await db.delete_npc(int(anchor_id))
        except Exception:
            log.warning("[contest] anchor despawn failed (npc=%s)", anchor_id,
                        exc_info=True)
    if contest_id is not None:
        try:
            await db.execute(
                "DELETE FROM npcs WHERE "
                "json_extract(ai_config_json, '$.anchor_reinforcement_for') = ?",
                (int(contest_id),),
            )
            await db.commit()
        except Exception:
            log.warning("[contest] reinforcement despawn failed (contest=%s)",
                        contest_id, exc_info=True)


async def _resolve_defender_win(
    db, contest: dict, *, session_mgr=None,
) -> None:
    """Mark a contest as defender-won, apply penalty + cooldown.

    Used both by the SYN.3.a placeholder tick (when contest expires
    without a kill) and as the fallback path in SYN.3.b's
    culminating-fight tick.
    """
    contest_id = contest["id"]
    region_slug = contest["region_slug"]
    challenger_org = contest["challenger_org_code"]
    defender_org = contest.get("defender_org_code")
    zone_id = contest.get("zone_id")

    # Mark resolved — compare-and-swap on status='active' so a concurrent
    # killing-blow challenger-win at the ends_at boundary cannot be double-
    # resolved (the second writer sees rowcount 0 and bails before applying a
    # duplicate penalty/cooldown/despawn).
    try:
        cur = await db.execute(
            "UPDATE region_contests SET status = 'resolved_defender' "
            "WHERE id = ? AND status = 'active'",
            (contest_id,),
        )
        await db.commit()
    except Exception:
        log.warning("[contest] resolve update failed", exc_info=True)
        return
    if getattr(cur, "rowcount", 1) == 0:
        log.info("[contest] defender-win skipped: contest %s already resolved",
                 contest_id)
        return

    # Apply failure penalty to challenger (zone-keyed influence in
    # the region's parent zone, transitional).
    if zone_id is not None:
        try:
            from engine.territory import adjust_territory_influence
            await adjust_territory_influence(
                db, challenger_org, zone_id,
                -REGION_CONTEST_FAILURE_PENALTY,
                reason=f"failed region contest of {region_slug}",
            )
        except Exception:
            log.warning("[contest] penalty influence adjust failed",
                        exc_info=True)

    # Set cooldown
    await _set_contest_cooldown(db, region_slug, challenger_org)

    # Log + broadcast
    defender_display = (
        defender_org.replace("_", " ").title()
        if defender_org else "the un-owned region"
    )
    challenger_display = challenger_org.replace("_", " ").title()

    log.info(
        "[contest] resolved (defender-win): region=%s challenger=%s "
        "defender=%s",
        region_slug, challenger_org, defender_org or "(none)",
    )

    if session_mgr is not None:
        msg = (
            f"\n  \033[1;33m[REGION DEFENDED]\033[0m "
            f"\033[1;37m{defender_display}\033[0m holds "
            f"\033[1;36m{region_slug}\033[0m against "
            f"\033[1;37m{challenger_display}\033[0m's challenge.\n"
        )
        try:
            for sess in session_mgr.all:
                if getattr(sess, "is_in_game", False):
                    await sess.send_line(msg)
        except Exception:
            log.warning("[contest] resolve broadcast failed",
                        exc_info=True)

    # Despawn the Anchor + reinforcements now the contest is over.
    await _despawn_contest_anchor(db, contest)


async def _set_contest_cooldown(
    db, region_slug: str, org_code: str,
) -> None:
    """UPSERT a 14-day cooldown for (region_slug, org_code)."""
    cooldown_until = time.time() + REGION_CONTEST_COOLDOWN_SECS
    try:
        await db.execute(
            """INSERT INTO region_contest_cooldowns
               (region_slug, org_code, cooldown_until)
               VALUES (?, ?, ?)
               ON CONFLICT(region_slug, org_code) DO UPDATE SET
                 cooldown_until = excluded.cooldown_until""",
            (region_slug, org_code, cooldown_until),
        )
        await db.commit()
    except Exception:
        log.warning("[contest] cooldown upsert failed", exc_info=True)


# ──────────────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────────────

async def get_region_contest_status_lines(
    db, org_code: str,
) -> list[str]:
    """Return formatted active region-contest lines for an org.

    Empty list if the org has no active contests. Mirrors the
    presentation style of the legacy ``get_contest_status_lines``
    (which is region-named-but-actually-zone-keyed in HEAD; SYN.3.b
    retires that function).

    Format:
        ── Active Region Contests ──
          <region_slug>            [Defender]   <chall> vs <def>   <T>d <H>h remaining
    """
    contests = await get_org_region_contests(db, org_code)
    if not contests:
        return []

    lines = ["\033[1;37m── Active Region Contests ──\033[0m"]
    now = time.time()
    for c in contests:
        region_slug = c["region_slug"]
        defender = c.get("defender_org_code")
        challenger = c["challenger_org_code"]
        defender_display = (defender.replace("_", " ").title()
                            if defender else "(un-owned)")
        challenger_display = challenger.replace("_", " ").title()

        # Role from the perspective of the org we're rendering for
        if defender == org_code:
            role = "Defender"
            role_color = "\033[1;36m"
        else:
            role = "Challenger"
            role_color = "\033[1;31m"

        secs_left = max(0.0, float(c["ends_at"]) - now)
        # Are we in the culminating window?
        in_culminating = now >= float(c["accumulation_ends_at"])
        phase_tag = (" \033[1;31m[ANCHOR PHASE]\033[0m"
                     if in_culminating else "")

        # Lane D2: challenger posture tag (GG11 §8B). Best-effort; a
        # None VI (or a posture-free challenger) shows no tag.
        _vi = await _org_violence_index(db, challenger)
        posture_tag = ""
        if _vi is not None:
            from engine.organizations import violence_descriptor
            _pc = ("\033[1;31m" if _vi >= REGION_CONTEST_BLOODY_VI
                   else "\033[2m")
            posture_tag = f" {_pc}[{violence_descriptor(_vi)}]\033[0m"

        lines.append(
            f"  {region_slug:<32} {role_color}[{role}]\033[0m  "
            f"{challenger_display} vs {defender_display}  "
            f"\033[2m{_secs_to_human(secs_left)} remaining\033[0m"
            f"{phase_tag}{posture_tag}"
        )
    return lines


# ──────────────────────────────────────────────────────────────────────
# Region Anchor NPC — templates + spawn flow (SYN.3.b)
# ──────────────────────────────────────────────────────────────────────
#
# Per design §2.4 "Day 7, final 4 hours: Culminating fight":
#   * Anchor is a Tier-2-class spawn (multiplayer-capable),
#     flavored to the defending faction.
#   * Anchor's HP scales with the defender's accumulated influence
#     (compute_anchor_hp). Maps to WEG D6 stat-dice boosts on STR
#     (damage soak) and dodge — WEG D6 doesn't track raw HP, but
#     a defender-influence-buffed Anchor is mechanically equivalent
#     to one that takes more hits before dying.
#   * Anchor's tier scales with the challenger's accumulated
#     influence (compute_anchor_reinforcements). Extra Tier-1 NPCs
#     spawn alongside as reinforcements.
#   * Defender-flavored: Hutt warlord for Hutt, Republic Commander
#     for Republic, etc. Falls back to ``_default`` for un-owned
#     regions and unknown orgs.
#
# Kill detection: parser/combat_commands.py invokes
# ``on_npc_killed_in_combat`` when any NPC's wound_level hits >= 5.
# That handler checks if the dead NPC is a contest Anchor and
# resolves via ``_resolve_challenger_win`` if so.

_REGION_ANCHOR_TEMPLATES = {
    # ── GCW ──────────────────────────────────────────────────────
    "empire": {
        "name_prefix": "Imperial Sector Commander",
        "species": "Human",
        "description": (
            "A grim-faced sector commander in pristine Imperial uniform "
            "directs nearby troopers with sharp gestures. A polished "
            "command baton hangs at their hip; a heavy holstered pistol "
            "rides the other side. Their eyes never stop moving."
        ),
        "weapon": "Heavy Blaster Pistol (5D+1)",
        "faction": "Galactic Empire",
    },
    "rebel": {
        "name_prefix": "Alliance Strike Commander",
        "species": "Human",
        "description": (
            "A scarred Alliance commander with the bearing of someone who "
            "has won a dozen impossible fights. Sleek battle armor, a "
            "modified rifle slung across the back, and a quiet certainty "
            "in their stance."
        ),
        "weapon": "Modified Blaster Rifle (5D+2)",
        "faction": "Rebel Alliance",
    },
    "hutt": {
        "name_prefix": "Hutt Warlord",
        "species": "Hutt",
        "description": (
            "A massive Hutt sprawled on a repulsor-platform throne, "
            "flanked by personal Gamorrean guards. The Warlord watches "
            "with hooded eyes, one slug-thick hand resting on a heavy "
            "pistol designed for those who weigh half a tonne."
        ),
        "weapon": "Heavy Holdout Blaster (5D)",
        "faction": "Hutt Cartel",
    },
    "bh_guild": {
        "name_prefix": "Guild Master Hunter",
        "species": "Human",
        "description": (
            "A masked Master Hunter in worn Mandalorian-pattern armor. "
            "Multiple weapons hang from a bandolier; a jetpack arcs over "
            "the shoulder. The Guild crest is etched into the breastplate "
            "above a long row of kill notches."
        ),
        "weapon": "Heavy Blaster Rifle (6D)",
        "faction": "Bounty Hunters' Guild",
    },
    # ── CW ──────────────────────────────────────────────────────
    "republic": {
        "name_prefix": "Republic Sector Commander",
        "species": "Clone Trooper",
        "description": (
            "A clone commander in customized Phase II armor — kama, "
            "macrobinoculars, paired pistols. The Republic crest is "
            "stenciled across the shoulder in fresh blue. Their voice "
            "is calm and absolute."
        ),
        "weapon": "DC-17 Twin Pistols (5D+1)",
        "faction": "Galactic Republic",
    },
    "cis": {
        "name_prefix": "CIS Tactical Droid",
        "species": "T-Series Tactical Droid",
        "description": (
            "A T-series tactical droid stands amid a row of B1s, its "
            "narrow head swiveling to track every potential threat. "
            "The Separatist hex is painted across its slim torso plate. "
            "It speaks in clipped, calculating bursts."
        ),
        "weapon": "Heavy Blaster Rifle (5D+1)",
        "faction": "Confederacy",
    },
    "jedi_order": {
        "name_prefix": "Jedi Master Sentinel",
        "species": "Human",
        "description": (
            "A Jedi Master in tan robes, a lightsaber held lightly in "
            "one hand. They have the stillness of someone who has "
            "looked into the Force for a very long time, and the "
            "balance of someone who has fought their way out of it."
        ),
        "weapon": "Lightsaber (6D)",
        "faction": "Jedi Order",
    },
    "hutt_cartel": {
        "name_prefix": "Hutt Warlord",
        "species": "Hutt",
        "description": (
            "A massive Hutt sprawled on a repulsor-platform throne, "
            "flanked by personal Gamorrean guards. The Warlord watches "
            "with hooded eyes, one slug-thick hand resting on a heavy "
            "pistol designed for those who weigh half a tonne."
        ),
        "weapon": "Heavy Holdout Blaster (5D)",
        "faction": "Hutt Cartel",
    },
    "bounty_hunters_guild": {
        "name_prefix": "Guild Master Hunter",
        "species": "Human",
        "description": (
            "A masked Master Hunter in worn Mandalorian-pattern armor. "
            "Multiple weapons hang from a bandolier; a jetpack arcs over "
            "the shoulder. The Guild crest is etched into the breastplate "
            "above a long row of kill notches."
        ),
        "weapon": "Heavy Blaster Rifle (6D)",
        "faction": "Bounty Hunters' Guild",
    },
    "_default": {
        "name_prefix": "Region Anchor",
        "species": "Human",
        "description": (
            "A heavyset enforcer in mismatched armor stands at the heart "
            "of this place, watching every entrance. Whoever pays them "
            "is paying well — they look ready to die for it."
        ),
        "weapon": "Heavy Blaster Pistol (5D)",
        "faction": "Independent",
    },
}


def _anchor_hp_tier(anchor_hp: int) -> str:
    """Bucket Anchor HP into a tier label for stat scaling.

    Returns one of: 'basic', 'strong', 'hardened', 'fortress'.
    HP comes from ``compute_anchor_hp(defender_influence)`` and lies
    in the inclusive range [100, 200].

    The tiers shape the Anchor template's dice (str/dodge primarily) —
    WEG D6 doesn't track raw HP, so a higher-influence-buffed Anchor
    materializes as stronger soak rolls and dodges.
    """
    if anchor_hp >= 175:
        return "fortress"
    if anchor_hp >= 150:
        return "hardened"
    if anchor_hp >= 125:
        return "strong"
    return "basic"


# Stat boost matrix per HP tier. STR drives WEG D6 damage soak;
# dodge drives miss rate. Together they approximate "harder to kill".
_ANCHOR_TIER_STATS = {
    "basic": {
        "dex": "4D",   "str": "4D",   "per": "3D+2",
        "blaster": "6D",  "dodge": "5D",
        "brawling": "5D", "search": "4D", "intimidation": "5D",
    },
    "strong": {
        "dex": "4D+1", "str": "5D",   "per": "4D",
        "blaster": "6D+2", "dodge": "5D+2",
        "brawling": "5D+2", "search": "4D", "intimidation": "5D+1",
    },
    "hardened": {
        "dex": "4D+2", "str": "6D",   "per": "4D+1",
        "blaster": "7D", "dodge": "6D+1",
        "brawling": "6D+1", "search": "4D+1", "intimidation": "6D",
    },
    "fortress": {
        "dex": "5D",   "str": "7D",   "per": "4D+2",
        "blaster": "7D+2", "dodge": "7D",
        "brawling": "7D", "search": "4D+2", "intimidation": "6D+2",
    },
}


def _build_anchor_sheet(tmpl: dict, anchor_hp: int) -> dict:
    """Build the char_sheet_json dict for a Region Anchor NPC.

    Includes an ``anchor_target_hp`` field for display/narrative —
    the actual kill detection uses ``wound_level >= 5`` like any other
    NPC, but the recorded HP value lets the contest status line show
    "Anchor: 140 HP" etc.
    """
    tier = _anchor_hp_tier(anchor_hp)
    stats = _ANCHOR_TIER_STATS[tier]
    return {
        "attributes": {
            "dexterity":  stats["dex"],
            "knowledge":  "3D",
            "mechanical": "3D",
            "perception": stats["per"],
            "strength":   stats["str"],
            "technical":  "3D",
        },
        "skills": {
            "blaster":      stats["blaster"],
            "dodge":        stats["dodge"],
            "brawling":     stats["brawling"],
            "search":       stats["search"],
            "intimidation": stats["intimidation"],
        },
        "weapon":            tmpl["weapon"],
        "species":           tmpl["species"],
        "wound_level":       0,
        "move":              10,
        "force_points":      1,
        "character_points":  3,
        "dark_side_points":  0,
        # Contest metadata — narrative + display only
        "anchor_target_hp":  int(anchor_hp),
        "anchor_tier":       tier,
    }


def _build_anchor_ai(tmpl: dict, org_code: Optional[str],
                     region_slug: str, contest_id: int) -> dict:
    """Build the ai_config dict for a Region Anchor NPC."""
    faction = tmpl["faction"] if org_code else "Region defender"
    return {
        "personality": (
            f"A {faction} Region Anchor. Defends the heart of "
            f"{region_slug} against the challenging faction. Tactical, "
            f"unyielding, formidable. Speaks in short, weighted lines."
        ),
        "knowledge": [
            f"Anchor for the {region_slug} region contest",
            f"Defending for {org_code or 'no current owner'}",
            "Will not retreat from this landmark",
        ],
        "faction":           tmpl["faction"],
        "dialogue_style":    "terse",
        "hostile":           True,
        "combat_behavior":   "aggressive",
        "model_tier":        2,                # Tier-2 NPC per design §2.4
        "temperature":       0.7,
        "max_tokens":        120,
        "anchor_for_region": region_slug,
        "anchor_contest_id": int(contest_id),
        "anchor_org":        org_code,
    }


async def _spawn_region_anchor(
    db, contest: dict, *, session_mgr=None,
) -> Optional[int]:
    """Spawn the Region Anchor NPC + optional reinforcements.

    Pre-conditions:
      * Contest is 'active'.
      * ``now >= accumulation_ends_at``.
      * ``contest.anchor_npc_id`` is None (idempotency check).
      * Region has at least one landmark.

    Selects one landmark uniformly at random for the Anchor; the
    contest's ``anchor_landmark_id`` records the choice so other
    callers can route players there.

    Reinforcements (per ``compute_anchor_reinforcements(challenger_inf)``)
    spawn at the *same* landmark. They use the existing
    ``engine/territory.py::_GUARD_TEMPLATES`` to stay flavor-consistent
    with the defender's faction; un-owned-region contests get
    ``_default`` reinforcements.

    Returns the spawned Anchor's npc_id, or None on failure (no
    landmarks, NPC creation failure, etc — failure is non-fatal:
    the contest stays active, falls through to defender-win-by-
    default at ``ends_at``).
    """
    # Lazy imports to avoid cycle with engine.territory.
    try:
        from engine.territory import (
            _get_region_landmarks,
            _GUARD_TEMPLATES,
            _build_guard_sheet,
            _build_guard_ai,
            get_territory_influence,
        )
    except Exception:
        log.warning("[contest] anchor spawn: import failed", exc_info=True)
        return None

    contest_id = contest["id"]
    region_slug = contest["region_slug"]
    defender_org = contest.get("defender_org_code")
    challenger_org = contest["challenger_org_code"]
    zone_id = contest.get("zone_id")

    # Idempotency, defense-in-depth: if this contest already has a pinned
    # Anchor, don't spawn a second one. Phase A's `anchor_npc_id IS NULL` SQL
    # filter is the primary guard; this catches a stale / re-entrant dict.
    if contest.get("anchor_npc_id"):
        return int(contest["anchor_npc_id"])

    # Pick a landmark
    landmarks = await _get_region_landmarks(db, region_slug)
    if not landmarks:
        log.warning("[contest] anchor spawn: no landmarks for %s",
                    region_slug)
        return None

    import random as _r
    landmark_id = _r.choice(landmarks)

    # Resolve defender + challenger influence for stat scaling
    defender_inf = 0
    challenger_inf = 0
    if zone_id is not None:
        try:
            if defender_org:
                defender_inf = await get_territory_influence(
                    db, defender_org, zone_id)
            challenger_inf = await get_territory_influence(
                db, challenger_org, zone_id)
        except Exception:
            log.warning("[contest] anchor spawn: influence read failed",
                        exc_info=True)

    anchor_hp = compute_anchor_hp(defender_inf)
    # Lane D2: a high-posture challenger commits more bodies to the
    # culminating fight (GG11 §8B). Best-effort VI lookup; None → the
    # pre-D2 influence-only count.
    challenger_vi = await _org_violence_index(db, challenger_org)
    reinforce_count = compute_anchor_reinforcements(challenger_inf, challenger_vi)

    # Anchor template — flavored to defender (un-owned → _default)
    tmpl_key = defender_org if defender_org else "_default"
    tmpl = _REGION_ANCHOR_TEMPLATES.get(
        tmpl_key, _REGION_ANCHOR_TEMPLATES["_default"])

    # Per-contest-unique name so create_npc's (name, room_id) de-dup guard
    # can't silently hand back a leftover Anchor from a prior contest on the
    # same landmark (belt-and-suspenders with despawn-on-resolution).
    anchor_name = f"{tmpl['name_prefix']} of {region_slug} (#{contest_id})"
    sheet = _build_anchor_sheet(tmpl, anchor_hp)
    ai = _build_anchor_ai(tmpl, defender_org, region_slug, contest_id)

    try:
        anchor_npc_id = await db.create_npc(
            name=anchor_name,
            room_id=landmark_id,
            species=tmpl["species"],
            description=tmpl["description"],
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai),
        )
    except Exception as e:
        log.warning("[contest] anchor create_npc failed: %s", e,
                    exc_info=True)
        return None

    # Pin Anchor identity to the contest row
    try:
        await db.execute(
            "UPDATE region_contests "
            "SET anchor_npc_id = ?, anchor_landmark_id = ? "
            "WHERE id = ?",
            (int(anchor_npc_id), int(landmark_id), int(contest_id)),
        )
        await db.commit()
    except Exception:
        # The Anchor NPC exists but couldn't be pinned to the contest row.
        # Leaving it would orphan an unkillable-for-resolution hostile AND let
        # the next tick (anchor_npc_id still NULL) spawn a SECOND anchor. Remove
        # the orphan and bail; the next tick re-spawns cleanly.
        log.warning("[contest] anchor pin to contest failed; removing orphan",
                    exc_info=True)
        try:
            await db.delete_npc(int(anchor_npc_id))
        except Exception:
            log.warning("[contest] orphan anchor cleanup failed",
                        exc_info=True)
        return None

    # Reinforcement NPCs — share the Anchor's landmark
    reinforce_ids = []
    if reinforce_count > 0:
        guard_tmpl_key = defender_org if defender_org else "_default"
        guard_tmpl = _GUARD_TEMPLATES.get(
            guard_tmpl_key, _GUARD_TEMPLATES["_default"])
        for i in range(reinforce_count):
            r_name = f"{guard_tmpl['name_prefix']} (Anchor #{i + 1})"
            try:
                r_sheet = _build_guard_sheet(guard_tmpl)
                r_ai = _build_guard_ai(
                    guard_tmpl, defender_org or "independent")
                r_ai["anchor_reinforcement_for"] = int(contest_id)
                r_id = await db.create_npc(
                    name=r_name,
                    room_id=landmark_id,
                    species=guard_tmpl["species"],
                    description=guard_tmpl["description"],
                    char_sheet_json=json.dumps(r_sheet),
                    ai_config_json=json.dumps(r_ai),
                )
                reinforce_ids.append(int(r_id))
            except Exception:
                log.warning("[contest] reinforcement spawn failed",
                            exc_info=True)
                continue
        try:
            await db.commit()
        except Exception:
            log.debug(
                "[contest] commit after reinforcement spawn failed; "
                "scheduled tasks may roll back",
                exc_info=True,
            )

    log.info(
        "[contest] anchor spawned: contest=%d region=%s "
        "anchor_npc=%d landmark=%d hp=%d reinforce=%d",
        contest_id, region_slug, anchor_npc_id, landmark_id,
        anchor_hp, len(reinforce_ids),
    )

    # Broadcast culminating-fight start
    if session_mgr is not None:
        defender_display = (
            defender_org.replace("_", " ").title()
            if defender_org else "the un-owned region"
        )
        challenger_display = challenger_org.replace("_", " ").title()
        msg = (
            f"\n  \033[1;31m[CULMINATING FIGHT]\033[0m The "
            f"\033[1;37m{anchor_name}\033[0m has taken position in "
            f"\033[1;36m{region_slug}\033[0m.\n"
            f"  \033[1;37m{challenger_display}\033[0m must break the "
            f"Anchor within 4 hours or "
            f"\033[1;37m{defender_display}\033[0m holds the region.\n"
            f"  Anchor HP: {anchor_hp}. "
            f"Reinforcements: {len(reinforce_ids)}.\n"
        )
        try:
            for sess in session_mgr.all:
                if getattr(sess, "is_in_game", False):
                    await sess.send_line(msg)
        except Exception:
            log.warning("[contest] anchor broadcast failed",
                        exc_info=True)

    return int(anchor_npc_id)


# ──────────────────────────────────────────────────────────────────────
# Anchor kill detection + challenger-win resolution
# ──────────────────────────────────────────────────────────────────────

async def on_npc_killed_in_combat(
    db, npc_id: int, killer_char: Optional[dict],
    room_id: Optional[int], *, session_mgr=None,
) -> Optional[dict]:
    """Combat NPC-death hook — check for Anchor kill.

    Wired into ``parser/combat_commands.py``'s NPC-death block.
    Looks up any active contest where ``anchor_npc_id == npc_id``;
    if one exists, resolves it as a challenger win — the killer's
    faction takes the region (or the un-owned region is seized).

    Returns the resolved contest dict (with status='resolved_challenger')
    on a positive match; None otherwise. Callers may use the return
    value to broadcast extra narrative; the function itself already
    broadcasts the [REGION SEIZED] line.

    The killer_char may be None (e.g. NPC-on-NPC kill, environmental
    death) — in that case the Anchor still dies but no ownership
    transfer happens; the contest is marked 'failed' (admin-style
    exception) and the challenger pays the penalty (challenger
    failure to land the killing blow). This is a corner case; the
    overwhelming majority of Anchor kills will have a player killer.
    """
    if not npc_id:
        return None

    try:
        rows = await db.fetchall(
            "SELECT * FROM region_contests "
            "WHERE status = 'active' AND anchor_npc_id = ?",
            (int(npc_id),),
        )
    except Exception:
        log.warning("[contest] anchor kill lookup failed", exc_info=True)
        return None

    if not rows:
        return None

    contest = dict(rows[0])

    # Determine the winning org. Killer's faction wins. If killer has
    # no faction or is independent or somehow matches the defender,
    # treat as a defender win (challenger failed to land a clean kill).
    killer_org = None
    if killer_char is not None:
        if isinstance(killer_char, dict):
            killer_org = killer_char.get("faction_id")
        else:
            killer_org = getattr(killer_char, "faction_id", None)

    challenger_org = contest["challenger_org_code"]
    defender_org = contest.get("defender_org_code")

    # If the killer is the challenger, they win.
    if killer_org and killer_org == challenger_org:
        await _resolve_challenger_win(
            db, contest, killer_org, session_mgr=session_mgr)
        return await _refetch_contest(db, contest["id"])

    # If the killer is the defender, they win (challenger failed —
    # defender NPC killed defender NPC is impossible in practice
    # since Anchor IS the defender NPC; this branch handles e.g. a
    # third-party killer registered as defender_org).
    if killer_org and defender_org and killer_org == defender_org:
        await _resolve_defender_win(db, contest, session_mgr=session_mgr)
        return await _refetch_contest(db, contest["id"])

    # Independent / no faction / unclear: defender wins by default.
    # The kill happened but nobody represented the challenger — the
    # contest fails for the challenger, defender holds.
    log.info(
        "[contest] anchor died without clear faction killer: "
        "contest=%d killer_org=%r — defender wins by default",
        contest["id"], killer_org,
    )
    await _resolve_defender_win(db, contest, session_mgr=session_mgr)
    return await _refetch_contest(db, contest["id"])


async def _refetch_contest(db, contest_id: int) -> Optional[dict]:
    """Refetch a contest row by id (post-resolution status read)."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (int(contest_id),),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        return None


async def _resolve_challenger_win(
    db, contest: dict, winning_org: str, *, session_mgr=None,
) -> None:
    """Mark a contest as challenger-won: transfer ownership.

    Per design §2.4 "Contest resolution":
      * Killing-blow faction wins.
      * Ownership transfers cleanly if challenger wins.
      * Guards dismiss; resource yields cut over.
      * Defender (if any) gets the 25-influence penalty + 14-day
        cooldown — symmetric with defender-win's challenger penalty.

    For an un-owned-region seize: no prior ownership to transfer;
    INSERT a fresh row. No defender to penalize, but the contest
    is recorded as resolved_challenger.
    """
    contest_id = contest["id"]
    region_slug = contest["region_slug"]
    defender_org = contest.get("defender_org_code")
    zone_id = contest.get("zone_id")

    # Mark resolved — compare-and-swap on status='active' so a concurrent
    # tick-expiry defender-win at the ends_at boundary cannot double-resolve
    # (the second writer sees rowcount 0 and bails). The Anchor +
    # reinforcements are despawned at the end via _despawn_contest_anchor.
    try:
        cur = await db.execute(
            "UPDATE region_contests SET status = 'resolved_challenger' "
            "WHERE id = ? AND status = 'active'",
            (contest_id,),
        )
        await db.commit()
    except Exception:
        log.warning("[contest] challenger-win update failed",
                    exc_info=True)
        return
    if getattr(cur, "rowcount", 1) == 0:
        log.info("[contest] challenger-win skipped: contest %s already resolved",
                 contest_id)
        return

    # Transfer region ownership
    try:
        from engine.territory import (
            dismiss_region_garrison,
            spawn_region_garrison,
        )
        # Drop old garrison (if any) — reflects the old owner losing
        # the region. The new owner spawns a fresh garrison.
        if defender_org:
            try:
                await dismiss_region_garrison(db, region_slug)
            except Exception:
                log.warning("[contest] defender garrison dismiss failed",
                            exc_info=True)

        # Upsert ownership row
        now = time.time()
        upkeep = 3000  # mirrors claim_region's REGION_WEEKLY_MAINT +
                      # REGION_GARRISON_WEEKLY
        # We don't have a char_id for the "claimer" in a contest-win
        # case; record the contest_id as the synthetic claimed_by.
        # The schema only requires claimed_by NOT NULL — convention is
        # the player char id, but contest wins use the contest id with
        # a negative sign sentinel so audit log can tell them apart.
        claimed_by_sentinel = -int(contest_id)
        await db.execute(
            """INSERT INTO region_ownership
               (region_slug, org_code, zone_id, claimed_by,
                claimed_at, maintenance)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(region_slug) DO UPDATE SET
                 org_code = excluded.org_code,
                 claimed_by = excluded.claimed_by,
                 claimed_at = excluded.claimed_at""",
            (region_slug, winning_org, zone_id, claimed_by_sentinel,
             now, upkeep),
        )
        await db.commit()

        # Spawn new garrison for the winning org
        try:
            await spawn_region_garrison(db, winning_org, region_slug)
        except Exception:
            log.warning("[contest] new garrison spawn failed",
                        exc_info=True)
    except Exception:
        log.warning("[contest] ownership transfer failed", exc_info=True)

    # Apply penalty + cooldown to defender (if there was one)
    if defender_org and zone_id is not None:
        try:
            from engine.territory import adjust_territory_influence
            await adjust_territory_influence(
                db, defender_org, zone_id,
                -REGION_CONTEST_FAILURE_PENALTY,
                reason=f"lost region contest of {region_slug}",
            )
        except Exception:
            log.warning("[contest] defender penalty failed",
                        exc_info=True)
        await _set_contest_cooldown(db, region_slug, defender_org)

    log.info(
        "[contest] resolved (challenger-win): region=%s winner=%s "
        "former_defender=%s",
        region_slug, winning_org, defender_org or "(none, was un-owned)",
    )

    # Broadcast outcome
    if session_mgr is not None:
        winner_display = winning_org.replace("_", " ").title()
        defender_display = (
            defender_org.replace("_", " ").title()
            if defender_org else "no prior owner"
        )
        msg = (
            f"\n  \033[1;31m[REGION SEIZED]\033[0m "
            f"\033[1;37m{winner_display}\033[0m has taken control of "
            f"\033[1;36m{region_slug}\033[0m from "
            f"\033[1;37m{defender_display}\033[0m by killing the "
            f"Region Anchor.\n"
        )
        try:
            for sess in session_mgr.all:
                if getattr(sess, "is_in_game", False):
                    await sess.send_line(msg)
        except Exception:
            log.warning("[contest] seize broadcast failed",
                        exc_info=True)

    # Despawn the (now-dead) Anchor row + its reinforcements.
    await _despawn_contest_anchor(db, contest)


# ──────────────────────────────────────────────────────────────────────
# Influence-doubling + outnumbered-defender multiplier
# ──────────────────────────────────────────────────────────────────────

async def apply_contest_influence_multipliers(
    db, org_code: str, region_slug: str, base_delta: int,
) -> int:
    """Compute the multiplied influence delta during an active contest.

    Called by ``engine/territory.py::adjust_territory_influence`` when
    a caller passes ``region_slug``. Returns the new delta, or the
    original if no multipliers apply.

    Rules (design §2.4):
      * If a contest is active for ``region_slug`` AND ``org_code`` is
        one of the contestants AND ``base_delta > 0``: apply **2×**
        influence doubling.
      * If the org is the defender AND defender's member count is less
        than challenger's: additionally apply the **1.5× outnumbered
        bonus** to the defender's positive deltas.

    Negative deltas (penalties, decay) pass through unchanged.

    Returns the multiplied integer delta. Multiplier order:
    delta → 2× (if in contest) → 1.5× (if defender outnumbered)
    → round to int.
    """
    if base_delta <= 0:
        return base_delta

    contest = await get_active_region_contest(db, region_slug)
    if not contest:
        return base_delta

    contestants = {contest.get("defender_org_code"),
                   contest.get("challenger_org_code")}
    contestants.discard(None)
    if org_code not in contestants:
        return base_delta

    # 2× doubling for both sides
    multiplied = float(base_delta) * 2.0

    # Outnumbered-defender bonus on top, defender-side only
    defender_org = contest.get("defender_org_code")
    if defender_org and org_code == defender_org:
        try:
            def_count = await _count_org_members(db, defender_org)
            chall_count = await _count_org_members(
                db, contest["challenger_org_code"])
            multiplier = compute_outnumbered_defender_multiplier(
                def_count, chall_count)
            multiplied *= multiplier
        except Exception:
            log.warning("[contest] outnumbered multiplier failed",
                        exc_info=True)

    return int(round(multiplied))


async def _count_org_members(db, org_code: str) -> int:
    """Count members of an org via the memberships table.

    Used by ``apply_contest_influence_multipliers`` to compute the
    outnumbered-defender bonus. Reads ``memberships`` joined with
    ``organizations`` (membership keys on org_id, not org_code).
    Returns 0 on missing data / errors (treated as "no members"
    which yields 1.0× multiplier — safe default).
    """
    try:
        rows = await db.fetchall(
            "SELECT COUNT(*) AS c FROM memberships m "
            "JOIN organizations o ON o.id = m.org_id "
            "WHERE o.code = ?",
            (org_code,),
        )
        if not rows:
            return 0
        return int(rows[0]["c"]) if rows[0]["c"] is not None else 0
    except Exception:
        log.warning("[contest] member count failed for %s", org_code,
                    exc_info=True)
        return 0


# ──────────────────────────────────────────────────────────────────────
# Admin / exception path
# ──────────────────────────────────────────────────────────────────────

async def cancel_region_contest(
    db, contest_id: int, *, session_mgr=None, reason: str = "",
) -> dict:
    """Cancel an active contest (admin / exception path).

    Sets status to 'failed' (the exception state, as documented in
    the schema comment). No penalties applied; no cooldown set. Used
    by:
      * Admin command if a contest is declared in error.
      * Future automated path if the region becomes invalid mid-contest
        (e.g. landmarks all deleted, region YAML pulled, etc).

    Returns ``{"ok": bool, "msg": str}``.
    """
    try:
        rows = await db.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (int(contest_id),),
        )
    except Exception:
        return {"ok": False, "msg": "Contest lookup failed."}

    if not rows:
        return {"ok": False, "msg": f"No contest with id {contest_id}."}

    contest = dict(rows[0])
    if contest["status"] != "active":
        return {"ok": False,
                "msg": f"Contest {contest_id} is not active "
                       f"(status: {contest['status']})."}

    try:
        await db.execute(
            "UPDATE region_contests SET status = 'failed' WHERE id = ?",
            (int(contest_id),),
        )
        await db.commit()
    except Exception:
        return {"ok": False, "msg": "Contest cancel update failed."}

    log.info("[contest] cancelled: id=%d region=%s reason=%r",
             contest_id, contest["region_slug"], reason)

    if session_mgr is not None:
        msg = (
            f"\n  \033[1;33m[CONTEST CANCELLED]\033[0m The contest "
            f"over \033[1;36m{contest['region_slug']}\033[0m has been "
            f"cancelled. {reason}\n"
        )
        try:
            for sess in session_mgr.all:
                if getattr(sess, "is_in_game", False):
                    await sess.send_line(msg)
        except Exception:
            log.debug(
                "[contest] cancel broadcast failed for one or more "
                "sessions; cancellation already committed",
                exc_info=True,
            )

    return {"ok": True,
            "msg": f"Contest {contest_id} cancelled."}


# ──────────────────────────────────────────────────────────────────────
# Public exports
# ──────────────────────────────────────────────────────────────────────

__all__ = [
    # Constants
    "REGION_CONTEST_DURATION_SECS",
    "REGION_CONTEST_ACCUMULATION_SECS",
    "REGION_CONTEST_CULMINATING_SECS",
    "REGION_CONTEST_TRIGGER_RATIO",
    "REGION_CONTEST_MIN_CHALLENGER_INFLUENCE",
    "REGION_CONTEST_FAILURE_PENALTY",
    "REGION_CONTEST_COOLDOWN_SECS",
    "REGION_ANCHOR_BASE_HP",
    "REGION_ANCHOR_HP_FLOOR_INFLUENCE",
    "REGION_ANCHOR_REINFORCEMENT_THRESHOLD",
    "REGION_ANCHOR_REINFORCEMENT_PER",
    "OUTNUMBERED_DEFENDER_INFLUENCE_MULTIPLIER",
    # Schema
    "REGION_CONTEST_SCHEMA_SQL",
    "ensure_region_contest_schema",
    # Pure rules
    "compute_anchor_hp",
    "compute_anchor_reinforcements",
    "compute_outnumbered_defender_multiplier",
    # Queries
    "get_active_region_contest",
    "get_org_region_contests",
    "is_region_in_active_contest",
    "is_org_on_contest_cooldown",
    # Declaration
    "declare_region_contest",
    "check_and_declare_region_contests",
    # Resolution
    "tick_region_contest_resolution",
    "on_npc_killed_in_combat",
    "cancel_region_contest",
    # Influence multipliers
    "apply_contest_influence_multipliers",
    # Display
    "get_region_contest_status_lines",
]
