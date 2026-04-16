# -*- coding: utf-8 -*-
"""
engine/achievements.py — Achievement tracking engine for SW_MUSH.

Tracks player milestones across all game systems, providing guided
progression for new players and long-term goals for veterans.

Public API
----------
  load_achievements()                   -> load YAML definitions (called at boot)
  check_achievement(db, char_id, event, count, session) -> check & award
  get_achievements_status(db, char_id)  -> returns full status dict
  get_achievement_summary(db, char_id)  -> returns (completed, total) counts
"""

import logging
import os
import time
from typing import Optional

import yaml

log = logging.getLogger(__name__)

# ── Module State ──────────────────────────────────────────────────────────────

_ACHIEVEMENTS: list[dict] = []
_BY_KEY: dict[str, dict] = {}
_BY_EVENT: dict[str, list[dict]] = {}

# ── Category Display Order ────────────────────────────────────────────────────

CATEGORY_ORDER = [
    "combat", "space", "economy", "crafting",
    "social", "exploration", "smuggling", "force",
]

CATEGORY_LABELS = {
    "combat": "Combat",
    "space": "Space",
    "economy": "Economy",
    "crafting": "Crafting",
    "social": "Social",
    "exploration": "Exploration",
    "smuggling": "Smuggling",
    "force": "Force",
}

# ── Loading ───────────────────────────────────────────────────────────────────


def load_achievements() -> int:
    """
    Load achievement definitions from data/achievements.yaml.
    Returns number of achievements loaded.
    """
    global _ACHIEVEMENTS, _BY_KEY, _BY_EVENT

    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "achievements.yaml",
    )
    if not os.path.exists(yaml_path):
        log.warning("achievements.yaml not found at %s", yaml_path)
        return 0

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        log.error("Failed to parse achievements.yaml", exc_info=True)
        return 0

    raw = data.get("achievements", [])
    if not raw:
        log.warning("No achievements found in achievements.yaml")
        return 0

    _ACHIEVEMENTS = []
    _BY_KEY = {}
    _BY_EVENT = {}

    for entry in raw:
        key = entry.get("key")
        if not key:
            continue
        ach = {
            "key": key,
            "name": entry.get("name", key),
            "description": entry.get("description", ""),
            "category": entry.get("category", "misc"),
            "icon": entry.get("icon", "●"),
            "cp_reward": entry.get("cp_reward", 0),
            "trigger": entry.get("trigger", {}),
            "requires": entry.get("requires"),
        }
        _ACHIEVEMENTS.append(ach)
        _BY_KEY[key] = ach

        event = ach["trigger"].get("event", "")
        if event:
            _BY_EVENT.setdefault(event, []).append(ach)

    log.info("[achievements] Loaded %d achievements (%d events tracked)",
             len(_ACHIEVEMENTS), len(_BY_EVENT))
    return len(_ACHIEVEMENTS)


def get_all_achievements() -> list[dict]:
    """Return all loaded achievement definitions."""
    return list(_ACHIEVEMENTS)


def get_achievement(key: str) -> Optional[dict]:
    """Return a single achievement definition by key."""
    return _BY_KEY.get(key)


# ── Core Check Logic ─────────────────────────────────────────────────────────


async def check_achievement(
    db,
    char_id: int,
    event: str,
    count: int = 1,
    session=None,
    **kwargs,
) -> list[dict]:
    """
    Called from game systems when an achievement-relevant event occurs.

    Args:
        db:       Database instance
        char_id:  Character who triggered the event
        event:    Event name (e.g. "combat_victory", "ship_launch")
        count:    How much to increment (default 1)
        session:  Optional session for sending notifications
        **kwargs: Extra filters (e.g. zone="kessel")

    Returns:
        List of newly completed achievement dicts (usually empty or 1 item).

    Examples:
        await check_achievement(db, char_id, "combat_victory")
        await check_achievement(db, char_id, "mission_credits_earned", count=500)
        await check_achievement(db, char_id, "smuggling_complete", zone="kessel")
    """
    relevant = _BY_EVENT.get(event, [])
    if not relevant:
        return []

    newly_completed = []

    for ach in relevant:
        try:
            # Check kwargs filters (e.g. zone match)
            trigger = ach["trigger"]
            if not _matches_filters(trigger, kwargs):
                continue

            # Check prerequisite
            if ach.get("requires"):
                prereq = await _get_progress_row(db, char_id, ach["requires"])
                if not prereq or not prereq.get("completed"):
                    continue

            # Get or create progress row
            row = await _get_progress_row(db, char_id, ach["key"])
            if row and row.get("completed"):
                continue  # Already completed

            current_progress = (row["progress"] if row else 0) + count
            target = trigger.get("count", 1)

            if current_progress >= target:
                # Complete the achievement
                await _complete_achievement(db, char_id, ach, current_progress)
                newly_completed.append(ach)

                # Send notification
                if session:
                    await _notify_achievement(session, ach)
            else:
                # Update progress
                await _upsert_progress(db, char_id, ach["key"],
                                       current_progress, completed=False)

        except Exception:
            log.warning("Achievement check failed for %s / char %d",
                        ach["key"], char_id, exc_info=True)

    return newly_completed


def _matches_filters(trigger: dict, kwargs: dict) -> bool:
    """Check if kwargs match any trigger filters (zone, etc.)."""
    for filter_key in ("zone",):
        if filter_key in trigger:
            if kwargs.get(filter_key) != trigger[filter_key]:
                return False
    return True


async def _complete_achievement(db, char_id: int, ach: dict,
                                final_progress: int) -> None:
    """Mark achievement as complete, award CP."""
    await _upsert_progress(db, char_id, ach["key"],
                           final_progress, completed=True)

    # Award CP directly (not through tick economy — milestone rewards
    # bypass the weekly cap)
    cp_reward = ach.get("cp_reward", 0)
    if cp_reward > 0:
        try:
            await db.cp_add_character_points(char_id, cp_reward)
            log.info("Achievement CP: char %d +%d CP for '%s'",
                     char_id, cp_reward, ach["key"])
        except Exception:
            log.warning("Failed to award CP for achievement %s",
                        ach["key"], exc_info=True)

    log.info("Achievement completed: char %d — %s (%s)",
             char_id, ach["name"], ach["key"])


async def _notify_achievement(session, ach: dict) -> None:
    """Send the achievement unlocked notification to the player."""
    cp_text = f"  Reward: {ach['cp_reward']} CP\n" if ach.get("cp_reward") else ""
    msg = (
        f"\n"
        f"  \033[1;33m★ ACHIEVEMENT UNLOCKED: {ach['icon']} "
        f"{ach['name']} ★\033[0m\n"
        f"  \033[0;37m{ach['description']}\033[0m\n"
        f"{cp_text}"
    )
    try:
        await session.send_line(msg)

        # Send web client event
        if hasattr(session, "send_json"):
            await session.send_json({
                "type": "achievement_unlocked",
                "key": ach["key"],
                "name": ach["name"],
                "description": ach["description"],
                "icon": ach["icon"],
                "cp_reward": ach.get("cp_reward", 0),
                "category": ach.get("category", "misc"),
            })
    except Exception:
        log.debug("Achievement notify failed", exc_info=True)


async def notify_room_achievement(db, char_id: int, ach: dict,
                                  room_id: int, session_manager) -> None:
    """Broadcast achievement completion to the room (celebratory)."""
    try:
        char = await db.get_character(char_id)
        if not char:
            return
        char_name = char.get("name", "Someone")
        msg = (
            f"  \033[1;33m{char_name} earned: "
            f"{ach['icon']} {ach['name']}\033[0m"
        )
        # Broadcast to room via session manager
        if session_manager and hasattr(session_manager, "sessions"):
            for s in session_manager.sessions.values():
                if (hasattr(s, "character") and s.character
                        and s.character.get("current_room") == room_id
                        and s.character.get("id") != char_id):
                    try:
                        await s.send_line(msg)
                    except Exception as _e:
                        log.debug("silent except in engine/achievements.py:275: %s", _e, exc_info=True)
    except Exception:
        log.debug("Room achievement broadcast failed", exc_info=True)


# ── Status Query ─────────────────────────────────────────────────────────────


async def get_achievements_status(db, char_id: int) -> dict:
    """
    Return full achievement status for a character.

    Returns:
        {
            "achievements": [
                {
                    "key": str,
                    "name": str,
                    "description": str,
                    "category": str,
                    "icon": str,
                    "cp_reward": int,
                    "progress": int,
                    "target": int,
                    "completed": bool,
                    "completed_at": float or None,
                    "locked": bool,  # prerequisite not met
                },
                ...
            ],
            "completed_count": int,
            "total_count": int,
        }
    """
    # Fetch all progress rows for this character
    progress_map = await _get_all_progress(db, char_id)

    result = []
    completed_count = 0

    for ach in _ACHIEVEMENTS:
        key = ach["key"]
        row = progress_map.get(key, {})
        is_completed = bool(row.get("completed"))
        progress = row.get("progress", 0)
        target = ach["trigger"].get("count", 1)

        # Check if locked (prerequisite not met)
        locked = False
        if ach.get("requires"):
            prereq_row = progress_map.get(ach["requires"], {})
            if not prereq_row.get("completed"):
                locked = True

        if is_completed:
            completed_count += 1

        result.append({
            "key": key,
            "name": ach["name"],
            "description": ach["description"],
            "category": ach.get("category", "misc"),
            "icon": ach.get("icon", "●"),
            "cp_reward": ach.get("cp_reward", 0),
            "progress": progress,
            "target": target,
            "completed": is_completed,
            "completed_at": row.get("completed_at"),
            "locked": locked,
        })

    return {
        "achievements": result,
        "completed_count": completed_count,
        "total_count": len(_ACHIEVEMENTS),
    }


async def get_achievement_summary(db, char_id: int) -> tuple[int, int]:
    """Return (completed_count, total_count) for quick display."""
    try:
        rows = await db.fetchall(
            "SELECT COUNT(*) as cnt FROM character_achievements "
            "WHERE char_id = ? AND completed = 1",
            (char_id,),
        )
        completed = rows[0]["cnt"] if rows else 0
    except Exception:
        completed = 0
    return completed, len(_ACHIEVEMENTS)


# ── DB Helpers ───────────────────────────────────────────────────────────────


async def _get_progress_row(db, char_id: int, key: str) -> Optional[dict]:
    """Fetch a single progress row."""
    try:
        rows = await db.fetchall(
            "SELECT progress, completed, completed_at "
            "FROM character_achievements "
            "WHERE char_id = ? AND achievement_key = ?",
            (char_id, key),
        )
        if rows:
            return dict(rows[0])
    except Exception:
        log.debug("_get_progress_row failed for char %d key %s",
                  char_id, key, exc_info=True)
    return None


async def _get_all_progress(db, char_id: int) -> dict:
    """Fetch all progress rows for a character, keyed by achievement_key."""
    result = {}
    try:
        rows = await db.fetchall(
            "SELECT achievement_key, progress, completed, completed_at "
            "FROM character_achievements WHERE char_id = ?",
            (char_id,),
        )
        for row in rows:
            result[row["achievement_key"]] = dict(row)
    except Exception:
        log.debug("_get_all_progress failed for char %d",
                  char_id, exc_info=True)
    return result


async def _upsert_progress(db, char_id: int, key: str,
                           progress: int, completed: bool) -> None:
    """Insert or update a progress row."""
    completed_at = time.time() if completed else None
    try:
        await db.execute(
            "INSERT INTO character_achievements "
            "(char_id, achievement_key, progress, completed, completed_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(char_id, achievement_key) DO UPDATE SET "
            "progress = excluded.progress, "
            "completed = excluded.completed, "
            "completed_at = COALESCE(character_achievements.completed_at, "
            "excluded.completed_at)",
            (char_id, key, progress, 1 if completed else 0, completed_at),
        )
        await db.commit()
    except Exception:
        log.warning("_upsert_progress failed for char %d key %s",
                    char_id, key, exc_info=True)


# ── Convenience Wrappers (for hook sites) ────────────────────────────────────

async def on_combat_victory(db, char_id: int, session=None):
    """Hook: player won a combat encounter."""
    return await check_achievement(db, char_id, "combat_victory",
                                   session=session)

async def on_attack_hit(db, char_id: int, session=None):
    """Hook: player landed a successful attack."""
    return await check_achievement(db, char_id, "attack_hit",
                                   session=session)

async def on_survived_wound(db, char_id: int, session=None):
    """Hook: player survived being wounded."""
    return await check_achievement(db, char_id, "survived_wound",
                                   session=session)

async def on_survived_mortal_wound(db, char_id: int, session=None):
    """Hook: player survived a Mortally Wounded result."""
    return await check_achievement(db, char_id, "survived_mortal_wound",
                                   session=session)

async def on_ship_launch(db, char_id: int, session=None):
    """Hook: player launched a ship."""
    return await check_achievement(db, char_id, "ship_launch",
                                   session=session)

async def on_hyperspace_complete(db, char_id: int, session=None):
    """Hook: player completed a hyperspace jump."""
    return await check_achievement(db, char_id, "hyperspace_complete",
                                   session=session)

async def on_ship_destroyed(db, char_id: int, session=None):
    """Hook: player destroyed a hostile ship."""
    return await check_achievement(db, char_id, "ship_destroyed",
                                   session=session)

async def on_anomaly_salvaged(db, char_id: int, session=None):
    """Hook: player salvaged an anomaly."""
    return await check_achievement(db, char_id, "anomaly_salvaged",
                                   session=session)

async def on_planet_visited(db, char_id: int, session=None,
                            planets_count: int = 0):
    """Hook: player visited a new planet. Pass total planets visited."""
    return await check_achievement(db, char_id, "planets_visited",
                                   count=planets_count, session=session)

async def on_room_visited(db, char_id: int, total_rooms: int,
                          session=None):
    """Hook: track total unique rooms visited."""
    # We set count = total_rooms and use _upsert directly since this is
    # a "high-water mark" type achievement (total, not incremental)
    for ach in _BY_EVENT.get("rooms_visited", []):
        try:
            row = await _get_progress_row(db, char_id, ach["key"])
            if row and row.get("completed"):
                continue
            target = ach["trigger"].get("count", 1)
            if total_rooms >= target:
                await _complete_achievement(db, char_id, ach, total_rooms)
                if session:
                    await _notify_achievement(session, ach)
            else:
                await _upsert_progress(db, char_id, ach["key"],
                                       total_rooms, completed=False)
        except Exception:
            log.debug("Room visit achievement check failed", exc_info=True)
    return []

async def on_mission_credits_earned(db, char_id: int, amount: int,
                                    session=None):
    """Hook: player earned credits from a mission/bounty/job."""
    return await check_achievement(db, char_id, "mission_credits_earned",
                                   count=amount, session=session)

async def on_trade_goods_sold(db, char_id: int, session=None):
    """Hook: player sold trade goods."""
    return await check_achievement(db, char_id, "trade_goods_sold",
                                   session=session)

async def on_mission_complete(db, char_id: int, session=None):
    """Hook: player completed a mission board job."""
    return await check_achievement(db, char_id, "mission_complete",
                                   session=session)

async def on_sabacc_win(db, char_id: int, session=None):
    """Hook: player won a sabacc hand."""
    return await check_achievement(db, char_id, "sabacc_win",
                                   session=session)

async def on_item_crafted(db, char_id: int, quality: int = 0,
                          session=None):
    """Hook: player crafted an item. If quality >= 90, also fires masterwork."""
    results = await check_achievement(db, char_id, "item_crafted",
                                      session=session)
    if quality >= 90:
        results += await check_achievement(db, char_id, "craft_masterwork",
                                           session=session)
    return results

async def on_experiment_success(db, char_id: int, session=None):
    """Hook: player successfully experimented on a weapon."""
    return await check_achievement(db, char_id, "experiment_success",
                                   session=session)

async def on_pc_conversation(db, char_id: int, session=None):
    """Hook: player spoke with another PC present."""
    return await check_achievement(db, char_id, "pc_conversation",
                                   session=session)

async def on_scene_completed(db, char_id: int, session=None):
    """Hook: player completed an RP scene."""
    return await check_achievement(db, char_id, "scene_completed",
                                   session=session)

async def on_org_rank_reached(db, char_id: int, rank_level: int,
                              session=None):
    """Hook: player reached a rank in an organization."""
    # This is a high-water mark — set progress to rank_level
    for ach in _BY_EVENT.get("org_rank_reached", []):
        try:
            row = await _get_progress_row(db, char_id, ach["key"])
            if row and row.get("completed"):
                continue
            target = ach["trigger"].get("count", 1)
            if rank_level >= target:
                await _complete_achievement(db, char_id, ach, rank_level)
                if session:
                    await _notify_achievement(session, ach)
            else:
                await _upsert_progress(db, char_id, ach["key"],
                                       rank_level, completed=False)
        except Exception:
            log.debug("Org rank achievement check failed", exc_info=True)
    return []

async def on_kudos_received(db, char_id: int, total_kudos: int,
                            session=None):
    """Hook: player received a kudos. Pass lifetime total."""
    for ach in _BY_EVENT.get("kudos_received", []):
        try:
            row = await _get_progress_row(db, char_id, ach["key"])
            if row and row.get("completed"):
                continue
            target = ach["trigger"].get("count", 1)
            if total_kudos >= target:
                await _complete_achievement(db, char_id, ach, total_kudos)
                if session:
                    await _notify_achievement(session, ach)
            else:
                await _upsert_progress(db, char_id, ach["key"],
                                       total_kudos, completed=False)
        except Exception:
            log.debug("Kudos achievement check failed", exc_info=True)
    return []

async def on_smuggling_complete(db, char_id: int, session=None, **kwargs):
    """Hook: player completed a smuggling delivery."""
    return await check_achievement(db, char_id, "smuggling_complete",
                                   session=session, **kwargs)

async def on_force_power_used(db, char_id: int, session=None):
    """Hook: player used a Force power successfully."""
    return await check_achievement(db, char_id, "force_power_used",
                                   session=session)

async def on_dark_side_point(db, char_id: int, session=None):
    """Hook: player earned a Dark Side Point."""
    return await check_achievement(db, char_id, "dark_side_point",
                                   session=session)

async def on_dark_side_atoned(db, char_id: int, session=None):
    """Hook: player atoned for a Dark Side Point."""
    return await check_achievement(db, char_id, "dark_side_atoned",
                                   session=session)
