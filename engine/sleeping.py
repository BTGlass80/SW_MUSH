# -*- coding: utf-8 -*-
"""
engine/sleeping.py — Sleeping Character Vulnerability (Tier 3 Feature #16)

When a character disconnects in a non-SECURED room and doesn't own
a housing unit there, they are flagged as "sleeping" in their character
attributes. Sleeping characters can be pickpocketed by other players.

On reconnect, the sleeping flag is cleared and any theft events are
reported to the player.

Sleeping in a secured zone, in your own housing room, or in a faction-
claimed room (if you're a member) is safe — no sleeping flag set.

The `pickpocket <player>` command targets sleeping characters:
  - Pickpocket (Dexterity) check vs. sleeper's Perception at -2D
  - Success: steal 5-25% of their credits (randomized)
  - Fumble: you're flagged in the room ("Someone was rifling through
    X's belongings")
  - Only works in CONTESTED or LAWLESS zones
  - 10-minute cooldown per target
"""

import json
import logging
import random
import time

log = logging.getLogger(__name__)

# Maximum credit theft percentage range
THEFT_PCT_MIN = 5
THEFT_PCT_MAX = 25
# Cooldown between pickpocket attempts on the same target
PICKPOCKET_COOLDOWN = 600  # 10 minutes


async def set_sleeping(char: dict, db, room_id: int) -> bool:
    """
    Check if the character should be flagged as sleeping in this room.
    Returns True if the flag was set, False if the room is safe.
    """
    try:
        # Check security level
        from engine.security import get_effective_security, SecurityLevel
        sec = await get_effective_security(room_id, db, character=char)
        if sec == SecurityLevel.SECURED:
            return False  # Safe — no sleeping vulnerability

        # Check if character owns housing here
        try:
            from engine.housing import get_housing_for_room
            h = await get_housing_for_room(db, room_id)
            if h and h.get("char_id") == char.get("id"):
                return False  # Safe — own home
        except Exception:
            pass  # Housing module unavailable — continue

        # Check if room is claimed by character's faction
        char_org = char.get("faction_id", "independent")
        if char_org and char_org != "independent":
            try:
                from engine.territory import is_room_claimed_by
                if await is_room_claimed_by(db, room_id, char_org):
                    return False  # Safe — faction territory
            except Exception as _e:
                log.debug("silent except in engine/sleeping.py:66: %s", _e, exc_info=True)

        # Not safe — flag as sleeping
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        attrs["sleeping"] = {
            "room_id": room_id,
            "since": time.time(),
            "theft_log": attrs.get("sleeping", {}).get("theft_log", []),
        }
        char["attributes"] = json.dumps(attrs)
        await db.save_character(char["id"], attributes=char["attributes"])
        log.info("[sleeping] %s flagged as sleeping in room %d", char.get("name"), room_id)
        return True

    except Exception:
        log.warning("[sleeping] set_sleeping failed", exc_info=True)
        return False


async def clear_sleeping(char: dict, db) -> list:
    """
    Clear the sleeping flag and return any theft events that occurred.
    Returns a list of theft event dicts: [{thief_name, credits_stolen, ts}]
    """
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        sleeping = attrs.pop("sleeping", None)
        if not sleeping:
            return []

        theft_log = sleeping.get("theft_log", [])

        char["attributes"] = json.dumps(attrs)
        await db.save_character(char["id"], attributes=char["attributes"])

        if theft_log:
            log.info("[sleeping] %s wakes up — %d theft(s) while sleeping",
                     char.get("name"), len(theft_log))

        return theft_log

    except Exception:
        log.warning("[sleeping] clear_sleeping failed", exc_info=True)
        return []


def is_sleeping(char: dict) -> bool:
    """Check if a character is currently flagged as sleeping."""
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        return bool(attrs.get("sleeping"))
    except Exception:
        return False


async def attempt_pickpocket(
    thief: dict, target_char: dict, db, session_mgr=None
) -> dict:
    """
    Attempt to pickpocket a sleeping character.

    Returns dict with keys:
      ok: bool — whether the theft succeeded
      msg: str — message to show the thief
      room_msg: str|None — message to broadcast to the room (on fumble)
    """
    from engine.skill_checks import perform_skill_check

    target_name = target_char.get("name", "someone")

    # Verify target is actually sleeping
    if not is_sleeping(target_char):
        return {
            "ok": False,
            "msg": f"  {target_name} is not asleep. You can't pickpocket an alert target.",
            "room_msg": None,
        }

    # Check security zone
    room_id = target_char.get("room_id")
    if room_id:
        from engine.security import get_effective_security, SecurityLevel
        sec = await get_effective_security(room_id, db)
        if sec == SecurityLevel.SECURED:
            return {
                "ok": False,
                "msg": "  Security is too tight here. You can't pickpocket in a secured zone.",
                "room_msg": None,
            }

    # Cooldown check
    try:
        from engine.cooldowns import check_cooldown, set_cooldown
        cd_key = f"pickpocket_{target_char['id']}"
        remaining = check_cooldown(thief["id"], cd_key)
        if remaining > 0:
            mins = int(remaining / 60) + 1
            return {
                "ok": False,
                "msg": f"  You need to wait {mins} more minute(s) before targeting {target_name} again.",
                "room_msg": None,
            }
    except Exception:
        pass  # Cooldown module unavailable — skip

    # Skill check: thief's Pickpocket (Dexterity) vs sleeper's Perception at -2D
    # Build a modified target perception for the opposed check
    thief_result = perform_skill_check(thief, "pickpocket", 10)

    # Sleeper rolls Perception at -2D disadvantage
    target_perception = 0
    try:
        from engine.skill_checks import perform_skill_check
        # Roll the sleeper's perception, but we only need the roll value
        # Use a dummy difficulty — we just want the roll number
        sleeper_result = perform_skill_check(target_char, "perception", 99)
        # Apply -2D penalty: subtract ~7 from their roll (2D avg)
        target_perception = max(1, sleeper_result.roll - 7)
    except Exception:
        target_perception = 5  # Fallback: sleeping target barely aware

    # Set cooldown regardless of outcome
    try:
        from engine.cooldowns import set_cooldown
        set_cooldown(thief["id"], f"pickpocket_{target_char['id']}",
                     PICKPOCKET_COOLDOWN)
    except Exception as _e:
        log.debug("silent except in engine/sleeping.py:211: %s", _e, exc_info=True)

    thief_name = thief.get("name", "someone")

    if thief_result.fumble:
        # Fumble: caught red-handed
        return {
            "ok": False,
            "msg": (
                f"  \033[1;31mFumble!\033[0m You knock something over, making "
                f"a loud noise. Everyone in the area is now alerted."
            ),
            "room_msg": (
                f"  \033[1;33m{thief_name} was caught rifling through "
                f"{target_name}'s belongings while they slept!\033[0m"
            ),
        }

    if not thief_result.success or thief_result.roll <= target_perception:
        # Failed: you didn't find anything
        return {
            "ok": False,
            "msg": (
                f"  You carefully search {target_name}'s pockets but come up empty. "
                f"They stir slightly in their sleep."
            ),
            "room_msg": None,
        }

    # Success: steal credits
    target_credits = target_char.get("credits", 0)
    if target_credits <= 0:
        return {
            "ok": True,
            "msg": f"  You search {target_name}'s pockets... they're completely broke.",
            "room_msg": None,
        }

    steal_pct = random.randint(THEFT_PCT_MIN, THEFT_PCT_MAX) / 100.0
    stolen_amount = max(1, int(target_credits * steal_pct))

    # Transfer credits
    target_char["credits"] -= stolen_amount
    thief["credits"] = thief.get("credits", 0) + stolen_amount
    await db.save_character(target_char["id"], credits=target_char["credits"])
    await db.save_character(thief["id"], credits=thief["credits"])

    # Log theft in target's sleeping record
    try:
        attrs = target_char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        sleeping = attrs.get("sleeping", {})
        theft_log = sleeping.get("theft_log", [])
        theft_log.append({
            "thief_name": thief_name,
            "credits_stolen": stolen_amount,
            "ts": time.time(),
        })
        # Cap at 10 entries
        if len(theft_log) > 10:
            theft_log = theft_log[-10:]
        sleeping["theft_log"] = theft_log
        attrs["sleeping"] = sleeping
        target_char["attributes"] = json.dumps(attrs)
        await db.save_character(target_char["id"],
                                attributes=target_char["attributes"])
    except Exception:
        log.warning("[sleeping] theft log update failed", exc_info=True)

    # Achievement hook
    try:
        from engine.achievements import check_achievement
        await check_achievement(thief, "pickpocket", db)
    except Exception as _e:
        log.debug("silent except in engine/sleeping.py:286: %s", _e, exc_info=True)

    crit_str = " \033[1;32m(Critical success!)\033[0m" if thief_result.critical_success else ""
    return {
        "ok": True,
        "msg": (
            f"  \033[1;32mSuccess!\033[0m{crit_str} You carefully lift "
            f"\033[1;33m{stolen_amount:,} credits\033[0m from {target_name}'s pockets. "
            f"(Balance: {thief['credits']:,} cr)"
        ),
        "room_msg": None,
    }
