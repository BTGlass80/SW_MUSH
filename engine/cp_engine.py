# -*- coding: utf-8 -*-
"""
engine/cp_engine.py  --  Character Point (CP) progression economy.

Tick Economy
------------
  200 ticks = 1 CP  (v23: was 300)
  Weekly hard cap: 400 ticks (v23: was 300)
  Admin flag: characters hitting the cap 3+ consecutive weeks are flagged.

Four income sources (in priority order):
  1. Passive participation trickle  -- floor; 10 ticks/day if online at all
  2. Scene completion bonus         -- pose-count reward at scene close
  3. Kudos                          -- dominant; 3/week, 35 ticks each, 7-day rolling lockout
  4. AI evaluator trickle           -- lowest priority; graceful-drop when GPU busy

Target progression: ~1 CP per 10-12 days for an active player.
3D→5D advancement: ~7 months.

Public API
----------
  get_cp_engine()                              -> CPEngine singleton
  CPEngine.tick(db, session_mgr)               -> called every game tick (1s)
  CPEngine.award_scene_bonus(db, char_id, pose_count) -> call on scene close
  CPEngine.award_kudos(db, giver_id, target_id) -> call from kudos command
  CPEngine.award_ai_trickle(db, char_id, ticks) -> call from AI eval result
  CPEngine.get_status(db, char_id)             -> returns status dict for cpstatus cmd
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

TICKS_PER_CP = 200              # v23: was 300 — target ~1 CP/week for active players

# Weekly cap
WEEKLY_CAP_TICKS = 400          # v23: was 300 — room for active RPers to progress
WEEK_SECONDS = 7 * 24 * 3600

# Passive participation (source 1)
PASSIVE_TICKS_PER_DAY = 10      # v23: was 5 — stronger floor for small populations
DAY_SECONDS = 24 * 3600

# Scene completion bonus (source 2)
SCENE_MIN_POSES = 3             # Minimum poses to qualify for a bonus
SCENE_TICKS_PER_POSE = 2        # Ticks per pose above the minimum
SCENE_MAX_TICKS = 60            # Cap per scene (30 poses = ceiling)
SCENE_COOLDOWN_SECONDS = 600    # 10 min between scene bonuses for same char

# Kudos (source 3)
KUDOS_TICKS = 35                # Ticks per kudos received
KUDOS_PER_WEEK = 3              # Max kudos a char can receive per 7-day window
KUDOS_LOCKOUT_SECONDS = 7 * 24 * 3600  # 7-day rolling lockout per giver→target pair

# AI evaluator trickle (source 4)
AI_MAX_TICKS_PER_EVAL = 15      # Maximum ticks from a single AI evaluation
AI_EVAL_FLOOR = 0               # Never negative

# Admin flag threshold
ADMIN_CAP_FLAG_WEEKS = 3        # Flag if cap hit this many consecutive weeks

# Passive trickle: how often the tick loop checks (every N game ticks = N seconds)
PASSIVE_CHECK_INTERVAL = 3600   # Check once per in-game hour (3600 ticks)


# ── Singleton ─────────────────────────────────────────────────────────────────

_cp_engine: "CPEngine | None" = None


def get_cp_engine() -> "CPEngine":
    global _cp_engine
    if _cp_engine is None:
        _cp_engine = CPEngine()
    return _cp_engine


# ── Engine ────────────────────────────────────────────────────────────────────

class CPEngine:
    """
    Manages the CP tick economy.

    All state that needs persistence lives in the DB (cp_ticks and kudos_log
    tables).  In-memory state is transient and safe to lose on restart.
    """

    def __init__(self):
        self._tick_counter: int = 0          # Counts game ticks since start
        self._passive_checked: set[int] = set()  # char_ids checked this hour

    # ── Game tick hook ────────────────────────────────────────────────────────

    async def tick(self, db, session_mgr) -> None:
        """Called every game tick (1 second).  Handles passive trickle."""
        self._tick_counter += 1

        # Run passive check once per PASSIVE_CHECK_INTERVAL ticks
        if self._tick_counter % PASSIVE_CHECK_INTERVAL != 0:
            return

        # Reset hourly tracking set
        self._passive_checked.clear()

        now = time.time()
        for session in list(session_mgr.all):
            char = getattr(session, "character", None)
            if not char:
                continue
            char_id = char.get("id")
            if not char_id or char_id in self._passive_checked:
                continue
            self._passive_checked.add(char_id)

            try:
                await self._maybe_award_passive(db, char_id, now)
            except Exception:
                log.debug("CP passive tick failed for char %s", char_id, exc_info=True)

    async def _maybe_award_passive(self, db, char_id: int, now: float) -> None:
        """Award passive trickle if not already awarded today."""
        row = await db.cp_get_row(char_id)
        if row is None:
            await db.cp_ensure_row(char_id)
            row = await db.cp_get_row(char_id)

        last_passive = row.get("last_passive_ts", 0) or 0
        if now - last_passive < DAY_SECONDS:
            return  # Already awarded today

        # Check weekly cap
        ticks = _safe_int(row.get("ticks_this_week", 0))
        if ticks >= WEEKLY_CAP_TICKS:
            return

        to_award = min(PASSIVE_TICKS_PER_DAY, WEEKLY_CAP_TICKS - ticks)
        await _award_ticks(db, char_id, to_award, "passive", now,
                           update_passive_ts=True)
        log.debug("CP passive: char %d +%d ticks", char_id, to_award)

    # ── Scene completion bonus ────────────────────────────────────────────────

    async def award_scene_bonus(self, db, char_id: int, pose_count: int) -> dict:
        """
        Award scene completion bonus.

        Call this when a player closes/completes a scene.
        pose_count = number of poses the character contributed.

        Returns {"ticks": int, "message": str, "capped": bool}
        """
        if pose_count < SCENE_MIN_POSES:
            return {"ticks": 0, "message": "Scene too short for a bonus.", "capped": False}

        now = time.time()
        row = await _ensure_row(db, char_id)

        # Cooldown check
        last_scene = row.get("last_scene_ts", 0) or 0
        if now - last_scene < SCENE_COOLDOWN_SECONDS:
            remaining = int(SCENE_COOLDOWN_SECONDS - (now - last_scene))
            return {
                "ticks": 0,
                "message": f"Scene bonus on cooldown ({remaining//60}m {remaining%60}s remaining).",
                "capped": False,
            }

        # Weekly cap check
        ticks_this_week = _safe_int(row.get("ticks_this_week", 0))
        if ticks_this_week >= WEEKLY_CAP_TICKS:
            return {
                "ticks": 0,
                "message": "Weekly tick cap reached. Scene bonus not awarded.",
                "capped": True,
            }

        # Calculate bonus
        bonus_poses = max(0, pose_count - SCENE_MIN_POSES)
        raw_ticks = bonus_poses * SCENE_TICKS_PER_POSE
        raw_ticks = min(raw_ticks, SCENE_MAX_TICKS)
        ticks = min(raw_ticks, WEEKLY_CAP_TICKS - ticks_this_week)

        if ticks <= 0:
            return {"ticks": 0, "message": "No scene ticks to award.", "capped": False}

        await _award_ticks(db, char_id, ticks, "scene", now, update_scene_ts=True)

        capped = (ticks_this_week + ticks) >= WEEKLY_CAP_TICKS
        msg = f"Scene bonus: +{ticks} ticks ({pose_count} poses)."
        if capped:
            msg += " Weekly cap reached."
        return {"ticks": ticks, "message": msg, "capped": capped}

    # ── Kudos ─────────────────────────────────────────────────────────────────

    async def award_kudos(self, db, giver_id: int, target_id: int) -> dict:
        """
        One player gives kudos to another.

        Rules:
          - Can't kudos yourself
          - 7-day rolling lockout per giver→target pair
          - Target can receive max KUDOS_PER_WEEK kudos in a rolling 7-day window
          - Awards KUDOS_TICKS ticks to target (subject to weekly cap)

        Returns {"success": bool, "message": str, "ticks_awarded": int}
        """
        if giver_id == target_id:
            return {"success": False, "message": "You cannot give kudos to yourself.", "ticks_awarded": 0}

        now = time.time()

        # Check giver→target lockout
        lockout_key = f"{giver_id}:{target_id}"
        last_gave = await db.kudos_last_given(giver_id, target_id)
        if last_gave and (now - last_gave) < KUDOS_LOCKOUT_SECONDS:
            hours_remaining = int((KUDOS_LOCKOUT_SECONDS - (now - last_gave)) / 3600)
            return {
                "success": False,
                "message": f"You already gave kudos to this player recently. "
                           f"({hours_remaining}h remaining on lockout)",
                "ticks_awarded": 0,
            }

        # Check target weekly kudos cap
        kudos_this_week = await db.kudos_count_received_this_week(target_id)
        if kudos_this_week >= KUDOS_PER_WEEK:
            return {
                "success": False,
                "message": "That player has already received their maximum kudos this week.",
                "ticks_awarded": 0,
            }

        # Check target tick cap
        row = await _ensure_row(db, target_id)
        ticks_this_week = _safe_int(row.get("ticks_this_week", 0))
        if ticks_this_week >= WEEKLY_CAP_TICKS:
            # Log kudos even if capped — still a recognition event
            await db.kudos_log(giver_id, target_id, KUDOS_TICKS, now)
            return {
                "success": True,
                "message": "Kudos logged, but the recipient has hit their weekly tick cap.",
                "ticks_awarded": 0,
            }

        ticks = min(KUDOS_TICKS, WEEKLY_CAP_TICKS - ticks_this_week)
        await _award_ticks(db, target_id, ticks, "kudos", now)
        await db.kudos_log(giver_id, target_id, ticks, now)

        return {
            "success": True,
            "message": f"Kudos awarded! +{ticks} ticks.",
            "ticks_awarded": ticks,
        }

    # ── AI evaluator trickle ──────────────────────────────────────────────────

    async def award_ai_trickle(self, db, char_id: int, ticks: int) -> dict:
        """
        Award AI evaluation bonus ticks.  Graceful-drop: never raises.
        ticks should be in range [0, AI_MAX_TICKS_PER_EVAL].

        Returns {"ticks_awarded": int, "dropped": bool}
        """
        try:
            ticks = max(AI_EVAL_FLOOR, min(ticks, AI_MAX_TICKS_PER_EVAL))
            if ticks == 0:
                return {"ticks_awarded": 0, "dropped": False}

            row = await _ensure_row(db, char_id)
            ticks_this_week = _safe_int(row.get("ticks_this_week", 0))
            if ticks_this_week >= WEEKLY_CAP_TICKS:
                return {"ticks_awarded": 0, "dropped": False}

            ticks = min(ticks, WEEKLY_CAP_TICKS - ticks_this_week)
            await _award_ticks(db, char_id, ticks, "ai_eval", time.time())
            return {"ticks_awarded": ticks, "dropped": False}

        except Exception:
            log.debug("CP AI trickle dropped for char %d", char_id, exc_info=True)
            return {"ticks_awarded": 0, "dropped": True}

    # ── Status query ──────────────────────────────────────────────────────────

    async def get_status(self, db, char_id: int) -> dict:
        """
        Return a status dict for the cpstatus command.

        {
            "ticks_total": int,       # Lifetime ticks
            "ticks_this_week": int,   # Ticks earned this rolling 7-day window
            "weekly_cap": int,        # Always WEEKLY_CAP_TICKS
            "cp_available": int,      # character_points from characters table
            "ticks_to_next_cp": int,  # How many ticks until next CP conversion
            "kudos_received_week": int,
            "kudos_remaining_week": int,
            "cap_hit_streak": int,    # Consecutive weeks at cap (admin info)
        }
        """
        try:
            row = await _ensure_row(db, char_id)
        except Exception:
            row = {}

        ticks_total = _safe_int(row.get("ticks_total", 0))
        ticks_this_week = _safe_int(row.get("ticks_this_week", 0))
        cp_available = await _get_cp(db, char_id)
        ticks_to_next = TICKS_PER_CP - (ticks_total % TICKS_PER_CP)
        if ticks_to_next == TICKS_PER_CP:
            ticks_to_next = 0  # Exactly on a boundary

        kudos_received = await db.kudos_count_received_this_week(char_id)

        return {
            "ticks_total": ticks_total,
            "ticks_this_week": ticks_this_week,
            "weekly_cap": WEEKLY_CAP_TICKS,
            "cp_available": cp_available,
            "ticks_to_next_cp": ticks_to_next,
            "kudos_received_week": kudos_received,
            "kudos_remaining_week": max(0, KUDOS_PER_WEEK - kudos_received),
            "cap_hit_streak": _safe_int(row.get("cap_hit_streak", 0)),
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _ensure_row(db, char_id: int) -> dict:
    """Get or create cp_ticks row for character."""
    row = await db.cp_get_row(char_id)
    if row is None:
        await db.cp_ensure_row(char_id)
        row = await db.cp_get_row(char_id)
    return row or {}


async def _award_ticks(
    db,
    char_id: int,
    ticks: int,
    source: str,
    now: float,
    update_passive_ts: bool = False,
    update_scene_ts: bool = False,
) -> None:
    """
    Core tick award function.

    1. Updates cp_ticks row (ticks_total, ticks_this_week, weekly window reset).
    2. Converts accumulated ticks → CP when threshold crossed.
    3. Flags characters at cap for admin review.
    4. Optionally updates last_passive_ts or last_scene_ts.
    """
    row = await _ensure_row(db, char_id)
    week_start = row.get("week_start_ts", 0) or 0

    # Roll over weekly window if needed
    ticks_this_week = _safe_int(row.get("ticks_this_week", 0))
    cap_hit_streak = _safe_int(row.get("cap_hit_streak", 0))

    if (now - week_start) >= WEEK_SECONDS:
        # New week — check if previous week hit the cap
        if ticks_this_week >= WEEKLY_CAP_TICKS:
            cap_hit_streak += 1
        else:
            cap_hit_streak = 0
        ticks_this_week = 0
        week_start = now

    ticks_total_before = _safe_int(row.get("ticks_total", 0))
    ticks_total_after = ticks_total_before + ticks
    ticks_this_week_after = ticks_this_week + ticks

    # Build update payload
    updates: dict = {
        "ticks_total": ticks_total_after,
        "ticks_this_week": ticks_this_week_after,
        "week_start_ts": week_start,
        "cap_hit_streak": cap_hit_streak,
        "last_source": source,
        "last_award_ts": now,
    }
    if update_passive_ts:
        updates["last_passive_ts"] = now
    if update_scene_ts:
        updates["last_scene_ts"] = now

    await db.cp_update_row(char_id, **updates)

    # Convert ticks to CP
    cp_before = ticks_total_before // TICKS_PER_CP
    cp_after = ticks_total_after // TICKS_PER_CP
    cp_gained = cp_after - cp_before
    if cp_gained > 0:
        await db.cp_add_character_points(char_id, cp_gained)
        log.info("CP award: char %d +%d CP (ticks %d→%d)",
                 char_id, cp_gained, ticks_total_before, ticks_total_after)

    # Admin flag
    if cap_hit_streak >= ADMIN_CAP_FLAG_WEEKS:
        log.warning(
            "CP admin flag: char_id=%d hit weekly cap %d consecutive weeks "
            "(possible farming)",
            char_id, cap_hit_streak,
        )


async def _get_cp(db, char_id: int) -> int:
    """Read current character_points from characters table."""
    try:
        char = await db.get_character(char_id)
        return char.get("character_points", 0) if char else 0
    except Exception:
        log.warning("get_character_points failed", exc_info=True)
        return 0


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0
