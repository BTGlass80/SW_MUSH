# -*- coding: utf-8 -*-
"""
engine/breaching.py — breaching charges (CRAFT.mines_breaching_split,
breaching half — 2026-06-13).

A `breach <target>` verb (parser/demolitions_commands.py) lets a player
blow open a sealed obstacle with a single-use breaching charge and a
Demolitions skill check vs the obstacle's difficulty. Per the design call:
breaching charges are SAFE (no blast-on-players — they breach obstacles,
not people); placed proximity MINES are a separate, deferred system.

This module is the reusable engine core (mirrors engine/housing.py's
attempt_force_door): pure-ish, failure-tolerant, returns a result dict the
command renders. It does NOT decide WHERE breachable obstacles live —
that placement path is a pending design call (no world-data object-seeding
path exists yet; see TODO CRAFT.breaching_obstacle_placement). The command
operates on a breachable ROOM OBJECT carrying `data.breach_difficulty`,
which is the lowest-risk placement target (the objects table already
supports runtime placement); an admin/builder or a future seeding path
creates the obstacle.

Obstacle object shape (objects table, type 'breachable'):
    {
      "type": "breachable",
      "name": "Sealed Blast Door",
      "room_id": <id>,
      "data": {
        "breach_difficulty": 20,         # Demolitions target number
        "breached_desc": "The blast door hangs open, edges still glowing.",
        "reveal": "...optional flavor shown on success...",
      }
    }

The breaching charge is a single-use item the player carries (crafted from
the `breaching_charge` schematic). It is consumed on a breach ATTEMPT
(success or failure) — a shaped charge is spent once placed and blown,
exactly like the grenade single-use precedent.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

BREACHING_CHARGE_KEY = "breaching_charge"
# Default difficulty if a breachable object omits one (Moderate on the
# WEG ladder — a standard sealed door). Authored obstacles should set
# their own breach_difficulty.
DEFAULT_BREACH_DIFFICULTY = 20


def _carries_breaching_charge(char: dict) -> bool:
    """True if the character holds at least one breaching charge.

    Breaching charges are crafted CONSUMABLES, stored in
    attributes.consumables (the same store stims use), not inventory.items
    — so we query via engine.buffs.has_consumable (the canonical reader)."""
    try:
        from engine.buffs import has_consumable
        return has_consumable(char, BREACHING_CHARGE_KEY)
    except Exception:
        log.debug("[breaching] consumable check failed", exc_info=True)
        return False


def find_breachable(objects: list, target: str) -> Optional[dict]:
    """From a room's objects, return the breachable obstacle matching
    `target` (substring, case-insensitive, on name), or the sole
    breachable obstacle if `target` is empty. None if no match."""
    breachables = [
        o for o in (objects or [])
        if isinstance(o, dict) and o.get("type") == "breachable"
    ]
    if not breachables:
        return None
    t = (target or "").strip().lower()
    if not t:
        return breachables[0] if len(breachables) == 1 else None
    for o in breachables:
        if t in (o.get("name", "") or "").lower():
            return o
    return None


def _obj_data(obj: dict) -> dict:
    raw = obj.get("data", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


async def attempt_breach(db, char: dict, target: str = "") -> dict:
    """Attempt to breach a sealed obstacle in the character's room.

    Flow (mirrors attempt_force_door):
      1. Require a breaching charge in inventory.
      2. Find the breachable object (by `target`, or the sole one).
      3. Consume the charge (a shaped charge is spent on the attempt).
      4. Demolitions check vs the obstacle's breach_difficulty.
      5. On success: delete the obstacle, return its reveal flavor.

    Returns a result dict:
        {"ok": bool, "msg": str, "breached": bool}
    Never raises — any internal error returns a graceful ok=False.
    """
    room_id = char.get("room_id")
    try:
        objects = await db.get_objects_in_room(room_id)
    except Exception:
        log.warning("[breaching] get_objects_in_room failed", exc_info=True)
        return {"ok": False, "msg": "  You can't survey the area right now.",
                "breached": False}

    obstacle = find_breachable(objects, target)
    if obstacle is None:
        breachables = [o for o in (objects or [])
                       if isinstance(o, dict) and o.get("type") == "breachable"]
        if breachables and target:
            return {"ok": False, "breached": False,
                    "msg": "  Nothing breachable here matches '%s'." % target}
        if breachables:  # multiple, no target given
            names = ", ".join(o.get("name", "?") for o in breachables)
            return {"ok": False, "breached": False,
                    "msg": "  Breach what? (%s)" % names}
        return {"ok": False, "breached": False,
                "msg": "  There's nothing here to breach."}

    if not _carries_breaching_charge(char):
        return {"ok": False, "breached": False,
                "msg": "  You need a breaching charge to blow that open."}

    data = _obj_data(obstacle)
    difficulty = int(data.get("breach_difficulty", DEFAULT_BREACH_DIFFICULTY)
                     or DEFAULT_BREACH_DIFFICULTY)
    name = obstacle.get("name", "the obstacle")

    # Consume the charge FIRST — a shaped charge is spent once placed and
    # blown, whether or not the breach succeeds (grenade single-use
    # precedent). consume_consumable decrements attributes.consumables;
    # we persist the attributes blob so the deduction is durable.
    try:
        from engine.buffs import consume_consumable
        consumed = consume_consumable(char, BREACHING_CHARGE_KEY)
        if consumed:
            await db.save_character(
                char["id"], attributes=char.get("attributes"))
    except Exception:
        log.warning("[breaching] charge consume failed", exc_info=True)
        consumed = False
    if not consumed:
        return {"ok": False, "breached": False,
                "msg": "  You need a breaching charge to blow that open."}

    # Demolitions check vs the obstacle difficulty.
    try:
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(char, "demolitions", difficulty)
    except Exception:
        log.warning("[breaching] skill check failed", exc_info=True)
        return {"ok": False, "breached": False,
                "msg": "  The charge fizzles — something went wrong."}

    if not result.success:
        return {
            "ok": True, "breached": False,
            "msg": ("  You set the charge on %s and blow it — but the "
                    "breach fails. (Demolitions %d vs %d.) The charge is "
                    "spent." % (name, result.roll, difficulty)),
        }

    # Success — remove the obstacle, reveal what's behind it.
    try:
        await db.delete_object(obstacle["id"])
    except Exception:
        log.warning("[breaching] obstacle delete failed", exc_info=True)
    reveal = data.get("reveal") or data.get("breached_desc") or (
        "The way is clear.")
    return {
        "ok": True, "breached": True,
        "msg": ("  \033[1;33mThe charge blows %s open!\033[0m "
                "(Demolitions %d vs %d.)\n  %s"
                % (name, result.roll, difficulty, reveal)),
    }
