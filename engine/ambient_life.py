# -*- coding: utf-8 -*-
"""
engine/ambient_life.py — Ambient NPC Life System, Phase 1 (T3.22)
==================================================================
Deterministic ground-side NPC simulation: goals, intra-zone movement, and
rate-limited room-channel lines (departure / arrival / activity).

Mirrors ``engine/npc_space_traffic.py``'s singleton + tick + state-machine
shape, but operates on the ground (rooms + exits) rather than space zones.

Phase 1 scope (decided):
  - Intra-zone movement only (destinations must share the source room's zone_id).
  - Opt-in per NPC: ai_config_json must contain ``ambient_enabled: true``.
  - ZERO mechanical effects: no credit, market, faction, or combat writes.
  - Dim, rate-limited room-channel lines for departure/arrival/activity.
  - PC interaction OUT: the sim never reads which PC is present for targeting.
  - No Ollama (Phase 3).
  - No NPC-NPC interaction (Phase 2).

Hard import ban: this module MUST NOT import from engine.combat,
engine.world_events effects layer, engine.market, engine.credits, or any
faction credit-transfer helper.  All DB writes are:
  - npc_ambient_state (via db accessor functions only)
  - npcs.room_id (via db.update_npc — position only)
"""
from __future__ import annotations

import json
import logging
import random
import time
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# TUNING CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Maximum NPCs processed per tick call.  Keeps the tick's DB work bounded even
# if thousands of ambient-enabled NPCs exist.  Oldest ``last_tick_at`` first.
AMBIENT_TICK_BUDGET: int = 8

# Seconds an NPC spends walking between two rooms (simulated travel time).
MOVE_MIN_SECS: float = 30.0
MOVE_MAX_SECS: float = 90.0

# Seconds an NPC loiters in a room before picking a new destination.
LOITER_MIN_SECS: float = 60.0
LOITER_MAX_SECS: float = 300.0

# Named goal set (used for goal selection + activity line flavouring).
GOAL_SET = frozenset({"work", "socialize", "patrol", "rest", "trade"})

# ─────────────────────────────────────────────────────────────────────────────
# ANSI shortcuts (engine layer — avoid importing full server.ansi)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from server import ansi as _ansi
    _ANSI_DIM   = _ansi.DIM if hasattr(_ansi, "DIM") else "\033[2m"
    _ANSI_RESET = _ansi.RESET if hasattr(_ansi, "RESET") else "\033[0m"
except Exception:
    _ANSI_DIM   = "\033[2m"
    _ANSI_RESET = "\033[0m"


# ─────────────────────────────────────────────────────────────────────────────
# GOAL / ROUTINE TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

# Default routine name when an NPC's ai_config_json has no ``ambient_routine``.
_DEFAULT_ROUTINE = "generic"

# Maps routine_name -> time_of_day -> [goal, ...] (weighted by position; first
# element is most likely).  Goal selection draws uniformly from the list so
# earlier entries are not more likely — the list is simply the allowed set for
# that band; ``select_goal`` can be seeded for determinism in tests.
AMBIENT_ROUTINES: dict[str, dict[str, list[str]]] = {
    "generic": {
        "day":   ["work", "trade", "socialize", "patrol"],
        "dusk":  ["socialize", "rest", "trade"],
        "night": ["rest", "patrol"],
    },
    "merchant": {
        "day":   ["trade", "work", "socialize"],
        "dusk":  ["trade", "rest"],
        "night": ["rest"],
    },
    "guard": {
        "day":   ["patrol", "work"],
        "dusk":  ["patrol", "rest"],
        "night": ["patrol"],
    },
    "socialite": {
        "day":   ["socialize", "trade"],
        "dusk":  ["socialize", "rest"],
        "night": ["rest", "socialize"],
    },
    "worker": {
        "day":   ["work", "work", "trade"],
        "dusk":  ["rest", "socialize"],
        "night": ["rest"],
    },
}

# Activity lines by goal — shown while the NPC is loitering (IDLE state).
_ACTIVITY_LINES: dict[str, list[str]] = {
    "work":      [
        "{name} taps at a datapad, reviewing shipment logs.",
        "{name} sorts through a crate of supplies, muttering quietly.",
        "{name} checks a wall panel and adjusts a setting.",
    ],
    "trade":     [
        "{name} scans the area, eyes sharp for business.",
        "{name} flips a credit chip between their fingers.",
        "{name} studies a list of prices on their datapad.",
    ],
    "socialize": [
        "{name} leans against the wall, watching the crowd.",
        "{name} exchanges a quiet nod with a passerby.",
        "{name} chuckles at something only they seem to find funny.",
    ],
    "patrol":    [
        "{name} paces a slow circuit around the area.",
        "{name} glances toward the exits, then back again.",
        "{name} stands near the entrance, arms loosely crossed.",
    ],
    "rest":      [
        "{name} sits quietly, eyes half-closed.",
        "{name} leans back and stares at the ceiling.",
        "{name} yawns and shifts position.",
    ],
}

_DEPART_LINES: list[str] = [
    "{name} moves off toward the {direction}.",
    "{name} slips away toward the {direction}.",
    "{name} heads out to the {direction}.",
    "{name} strides off through the {direction} exit.",
]

_ARRIVE_LINES: list[str] = [
    "{name} arrives from the {direction}.",
    "{name} wanders in from the {direction}.",
    "{name} steps into the room from the {direction}.",
    "{name} drifts in from the {direction}.",
]


# ─────────────────────────────────────────────────────────────────────────────
# PURE HELPERS  (no I/O; unit-testable)
# ─────────────────────────────────────────────────────────────────────────────

def select_goal(routine: str, time_of_day: str,
                allowed: Optional[frozenset] = None,
                rng: Optional[random.Random] = None) -> str:
    """Return a goal string for an NPC given its routine and current time.

    ``routine``    — key into AMBIENT_ROUTINES (falls back to "generic").
    ``time_of_day``— one of "day", "dusk", "night".
    ``allowed``    — optional explicit override set (replaces AMBIENT_ROUTINES
                     lookup; must be non-empty or we fall back).
    ``rng``        — injectable random.Random for determinism in tests.
    """
    _rng = rng or random
    if allowed:
        pool = list(allowed)
    else:
        tbl = AMBIENT_ROUTINES.get(routine) or AMBIENT_ROUTINES[_DEFAULT_ROUTINE]
        pool = tbl.get(time_of_day) or tbl.get("day") or ["work"]
    return _rng.choice(pool)


def pick_destination_room(
    current_room_id: int,
    home_room_id: Optional[int],
    goal: str,
    zone_exits: list[dict],
    rng: Optional[random.Random] = None,
) -> Optional[int]:
    """Return a destination room_id for an NPC, or None if no valid move.

    ``current_room_id`` — the NPC's current room.
    ``home_room_id``    — the NPC's home room (may be None).
    ``goal``            — current goal ("rest" and "work" bias toward home).
    ``zone_exits``      — list of exit dicts (``to_room_id`` field) that are
                          INTRA-ZONE (caller pre-filters to share zone_id).
    ``rng``             — injectable random.Random.

    Intra-zone constraint: the caller must supply only exits whose destination
    shares the source room's zone_id.  This function does NOT query the DB.
    """
    _rng = rng or random
    if not zone_exits:
        return None

    # ``rest`` and ``work`` goals bias toward home_room_id when available.
    if goal in ("rest", "work") and home_room_id is not None:
        home_exits = [e for e in zone_exits if e["to_room_id"] == home_room_id]
        if home_exits:
            return home_room_id

    # Choose a random intra-zone destination (may be same as current; caller
    # skips a move attempt if dest == current).
    candidate = _rng.choice(zone_exits)
    dest = candidate["to_room_id"]
    # Avoid staying put.
    if dest == current_room_id and len(zone_exits) > 1:
        others = [e for e in zone_exits if e["to_room_id"] != current_room_id]
        dest = _rng.choice(others)["to_room_id"]
    return dest


def templated_depart_line(name: str, direction: str,
                          rng: Optional[random.Random] = None) -> str:
    """Dim ANSI departure room-channel line."""
    _rng = rng or random
    tmpl = _rng.choice(_DEPART_LINES)
    raw = tmpl.format(name=name, direction=direction)
    return f"  {_ANSI_DIM}{raw}{_ANSI_RESET}"


def templated_arrive_line(name: str, direction: str,
                          rng: Optional[random.Random] = None) -> str:
    """Dim ANSI arrival room-channel line."""
    _rng = rng or random
    tmpl = _rng.choice(_ARRIVE_LINES)
    raw = tmpl.format(name=name, direction=direction)
    return f"  {_ANSI_DIM}{raw}{_ANSI_RESET}"


def templated_activity_line(name: str, goal: str,
                            rng: Optional[random.Random] = None) -> str:
    """Dim ANSI activity room-channel line for an idle NPC."""
    _rng = rng or random
    pool = _ACTIVITY_LINES.get(goal) or _ACTIVITY_LINES["work"]
    raw = _rng.choice(pool).format(name=name)
    return f"  {_ANSI_DIM}{raw}{_ANSI_RESET}"


# ─────────────────────────────────────────────────────────────────────────────
# NPC STATE ENUM
# ─────────────────────────────────────────────────────────────────────────────

class AmbientState(Enum):
    IDLE   = "idle"    # loitering in current room
    MOVING = "moving"  # simulated transit between two rooms


# ─────────────────────────────────────────────────────────────────────────────
# AMBIENT LIFE MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class AmbientLifeManager:
    """Ground-side ambient NPC simulation manager.

    Called every AMBIENT_LIFE_TICK_INTERVAL seconds from the tick scheduler.
    Operates only on NPCs with ``ambient_enabled: true`` in their ai_config_json.
    All credit / market / faction / combat writes are forbidden (see module
    docstring).
    """

    def __init__(self):
        # In-memory state per NPC (supplement to the DB npc_ambient_state row).
        # Maps npc_id -> {"state": AmbientState, "state_entered_at": float,
        #                  "dest_room_id": int|None, "move_duration": float,
        #                  "loiter_until": float, "goal": str, "name": str,
        #                  "home_room_id": int|None, "routine": str}
        self._npcs: dict[int, dict] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    async def tick(self, db, session_mgr) -> None:
        """Main tick: bootstrap eligible NPCs, then process budget-bounded work."""
        now = time.time()
        from engine.world_time import global_time_of_day
        time_of_day = global_time_of_day(now)

        # 1. Bootstrap: find ambient-enabled NPCs not yet tracked.
        await self._bootstrap(db, now)

        # 2. Sort tracked NPCs by last_tick_at (oldest first) for fairness.
        if not self._npcs:
            return

        ordered = sorted(
            self._npcs.keys(),
            key=lambda nid: self._npcs[nid].get("last_tick_at", 0.0),
        )
        budget = AMBIENT_TICK_BUDGET
        for npc_id in ordered[:budget]:
            try:
                await self._tick_npc(npc_id, db, session_mgr, now, time_of_day)
            except Exception:
                log.exception("[ambient_life] tick_npc failed for npc_id=%d", npc_id)

    # ── Bootstrap ──────────────────────────────────────────────────────────────

    async def _bootstrap(self, db, now: float) -> None:
        """Lazy-load NPCs whose ai_config_json has ambient_enabled=true.

        Uses SQLite json_extract (JSON1 extension) mirroring engine/contest.py
        precedent. Any NPC already tracked is skipped. A newly found NPC gets:
          - npc_ambient_state row ensured (idempotent INSERT OR IGNORE).
          - In-memory tracking entry created from the DB state row.
        """
        try:
            rows = await db.get_ambient_enabled_npc_rows()
        except Exception:
            log.exception("[ambient_life] bootstrap query failed")
            return

        bootstrapped = 0
        for row in rows:
            npc_id = row["id"]
            if npc_id in self._npcs:
                continue
            if bootstrapped >= AMBIENT_TICK_BUDGET:
                break  # bound cold-start work; remaining NPCs bootstrap next tick
            bootstrapped += 1

            # Ensure the ambient_state row exists.
            await db.ambient_state_ensure_row(npc_id)

            # Parse ai_config for routine + home_room_id.
            try:
                ai_cfg = json.loads(row["ai_config_json"] or "{}")
            except Exception:
                ai_cfg = {}

            routine = ai_cfg.get("ambient_routine", _DEFAULT_ROUTINE)
            if routine not in AMBIENT_ROUTINES:
                routine = _DEFAULT_ROUTINE

            home_room_id = ai_cfg.get("home_room_id") or row.get("room_id")

            # Read existing state row.
            state_row = await db.ambient_state_get(npc_id)
            current_room_id = (state_row or {}).get("current_room_id") or row.get("room_id")

            # Initialise ambient_state.current_room_id if missing.
            if state_row and not state_row.get("current_room_id") and current_room_id:
                await db.ambient_state_update(npc_id, current_room_id=current_room_id)

            self._npcs[npc_id] = {
                "state":          AmbientState.IDLE,
                "state_entered_at": now,
                "dest_room_id":   None,
                "move_duration":  0.0,
                "loiter_until":   now + random.uniform(LOITER_MIN_SECS, LOITER_MAX_SECS),
                "goal":           "work",
                "name":           row["name"],
                "home_room_id":   home_room_id,
                "routine":        routine,
                "last_tick_at":   0.0,
                "current_room_id": current_room_id,
            }
            log.debug("[ambient_life] bootstrapped NPC %d (%s) routine=%s",
                      npc_id, row["name"], routine)

    # ── Per-NPC tick ───────────────────────────────────────────────────────────

    async def _tick_npc(self, npc_id: int, db, session_mgr,
                        now: float, time_of_day: str) -> None:
        """State machine for one NPC."""
        mem = self._npcs.get(npc_id)
        if mem is None:
            return

        mem["last_tick_at"] = now

        if mem["state"] == AmbientState.MOVING:
            await self._tick_moving(npc_id, mem, db, session_mgr, now)
        else:
            await self._tick_idle(npc_id, mem, db, session_mgr, now, time_of_day)

        # Persist last_tick_at so oldest-first ordering is stable across reloads.
        await db.ambient_state_update(npc_id, last_tick_at=now)

    async def _tick_idle(self, npc_id: int, mem: dict, db, session_mgr,
                         now: float, time_of_day: str) -> None:
        """IDLE: loiter until loiter_until, then pick a destination and depart."""
        if now < mem["loiter_until"]:
            # Still loitering — nothing to do this tick.
            return

        # Pick a new goal.
        mem["goal"] = select_goal(mem["routine"], time_of_day)

        current_room_id = mem["current_room_id"]
        if not current_room_id:
            # No known position; nothing to do.
            mem["loiter_until"] = now + random.uniform(LOITER_MIN_SECS, LOITER_MAX_SECS)
            return

        # Gather intra-zone exits.
        zone_exits = await self._intra_zone_exits(current_room_id, db)
        dest = pick_destination_room(
            current_room_id,
            mem["home_room_id"],
            mem["goal"],
            zone_exits,
        )
        if dest is None or dest == current_room_id:
            # Nowhere to go; loiter longer.
            mem["loiter_until"] = now + random.uniform(LOITER_MIN_SECS, LOITER_MAX_SECS)
            return

        # Find the exit direction label for the narrative line.
        direction = _direction_to(current_room_id, dest, zone_exits)

        # Broadcast departure line to the source room.
        depart_line = templated_depart_line(mem["name"], direction)
        try:
            await session_mgr.broadcast_to_room(current_room_id, depart_line)
        except Exception:
            log.debug("[ambient_life] broadcast_to_room depart failed npc %d", npc_id)

        # Transition to MOVING.
        move_dur = random.uniform(MOVE_MIN_SECS, MOVE_MAX_SECS)
        mem["state"]          = AmbientState.MOVING
        mem["state_entered_at"] = now
        mem["dest_room_id"]   = dest
        mem["move_duration"]  = move_dur

        # Write dest + move start into DB state row.
        await db.ambient_state_update(
            npc_id,
            dest_room_id=dest,
            move_started_at=now,
            move_duration=move_dur,
            current_goal=mem["goal"],
            activity="moving",
        )

    async def _tick_moving(self, npc_id: int, mem: dict, db, session_mgr,
                           now: float) -> None:
        """MOVING: wait for move_duration, then arrive at dest."""
        elapsed = now - mem["state_entered_at"]
        if elapsed < mem["move_duration"]:
            return  # still in transit

        dest = mem["dest_room_id"]
        if dest is None:
            # Corrupt state — reset to IDLE.
            mem["state"]       = AmbientState.IDLE
            mem["loiter_until"] = now + random.uniform(LOITER_MIN_SECS, LOITER_MAX_SECS)
            return

        # Arrive at destination.
        old_room = mem["current_room_id"]
        mem["current_room_id"] = dest
        mem["dest_room_id"]    = None
        mem["state"]           = AmbientState.IDLE
        mem["loiter_until"]    = now + random.uniform(LOITER_MIN_SECS, LOITER_MAX_SECS)

        # Figure out arrival direction label (reverse of departure).
        # We use "the corridor" as a generic fallback — arrival direction
        # requires knowing the exit direction from the destination side, which
        # needs an additional DB fetch.  Use a simple fallback to stay cheap.
        arrive_dir = await self._reverse_direction(dest, old_room, db)

        arrive_line = templated_arrive_line(mem["name"], arrive_dir)

        # Write new position to both npc_ambient_state and npcs.room_id (so
        # look/get_npcs_in_room shows the NPC in the right room).
        try:
            await db.ambient_state_update(
                npc_id,
                current_room_id=dest,
                dest_room_id=None,
                move_started_at=None,
                activity=mem["goal"],
            )
        except Exception:
            log.exception("[ambient_life] ambient_state_update on arrival npc %d", npc_id)

        try:
            await db.update_npc(npc_id, room_id=dest)
        except Exception:
            log.exception("[ambient_life] update_npc room_id on arrival npc %d", npc_id)

        # Broadcast arrival line to destination room.
        try:
            await session_mgr.broadcast_to_room(dest, arrive_line)
        except Exception:
            log.debug("[ambient_life] broadcast_to_room arrive failed npc %d", npc_id)

    # ── DB helpers ─────────────────────────────────────────────────────────────

    async def _intra_zone_exits(self, room_id: int, db) -> list[dict]:
        """Return exits from room_id whose destination shares the same zone_id.

        Intra-zone constraint: ambient NPCs do not cross zone boundaries.
        Exits with no zone_id on their destination default to allowing movement
        (zone_id IS NULL rooms are treated as same-zone to avoid blocking NPCs
        in sparse world data).
        """
        try:
            exits = await db.get_exits(room_id)
            if not exits:
                return []

            # Fetch the source room's zone_id once.
            src_room = await db.get_room(room_id)
            src_zone = (src_room or {}).get("zone_id") if src_room else None

            intra = []
            for ex in exits:
                dest_id = ex.get("to_room_id")
                if not dest_id:
                    continue
                if src_zone is None:
                    # No zone on source — allow any exit.
                    intra.append(ex)
                    continue
                dest_room = await db.get_room(dest_id)
                dest_zone = (dest_room or {}).get("zone_id") if dest_room else None
                if dest_zone is None or dest_zone == src_zone:
                    intra.append(ex)
            return intra
        except Exception:
            log.exception("[ambient_life] _intra_zone_exits failed for room %d", room_id)
            return []

    async def _reverse_direction(self, dest_room_id: int,
                                 from_room_id: Optional[int], db) -> str:
        """Return the direction label on the exit FROM dest TO from_room (for
        the arrival narrative).  Falls back to "the corridor" if not found."""
        if from_room_id is None:
            return "the corridor"
        try:
            exits = await db.get_exits(dest_room_id)
            for ex in exits:
                if ex.get("to_room_id") == from_room_id:
                    return ex.get("direction") or "the corridor"
        except Exception:
            pass
        return "the corridor"


def _direction_to(from_room_id: int, to_room_id: int,
                  exits: list[dict]) -> str:
    """Find the direction label for the exit from from_room to to_room in
    the pre-fetched exits list.  Falls back to "the corridor"."""
    for ex in exits:
        if ex.get("to_room_id") == to_room_id:
            return ex.get("direction") or "the corridor"
    return "the corridor"


# ─────────────────────────────────────────────────────────────────────────────
# MODULE SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_ambient_life_manager: Optional[AmbientLifeManager] = None


def get_ambient_life_manager() -> AmbientLifeManager:
    """Return the module-level AmbientLifeManager singleton (lazy init)."""
    global _ambient_life_manager
    if _ambient_life_manager is None:
        _ambient_life_manager = AmbientLifeManager()
    return _ambient_life_manager


def reset_ambient_life_manager() -> None:
    """Reset the singleton.  TEST ISOLATION ONLY — never call from production."""
    global _ambient_life_manager
    _ambient_life_manager = None
