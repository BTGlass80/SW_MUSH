# -*- coding: utf-8 -*-
"""
engine/security.py — Security zone system for SW_MUSH.

Three security tiers (Star Wars flavour, not EVE names):

  SECURED    — Imperial-patrolled city core.  No player combat.
               NPC aggro also suppressed (except faction-hostile areas).
               Example: Mos Eisley market row, cantina, bank, clinic.

  CONTESTED  — Back alleys, docking bays, outskirts.  NPC combat live.
               PvP requires mutual consent (challenge/accept flow).
               Example: most of existing Mos Eisley outside the core.

  LAWLESS    — Deep desert, Nar Shaddaa underworld, Kessel.  Full open
               PvP.  No restrictions.  High risk, high reward.
               Example: Jundland Wastes, Kessel mines, Nar Shaddaa streets.

Security is stored in zone.properties["security"] and inherits through the
zone hierarchy via the existing get_room_property() mechanism.  Rooms can
override with room.properties["security"].  Default (no value) = CONTESTED.

Director AI can call set_security_override(zone_id, level) to temporarily
shift effective security (e.g. Imperial crackdown, criminal surge).
Overrides are transient (in-memory, lost on restart — intentional).
"""

import enum
import logging

log = logging.getLogger(__name__)


class SecurityLevel(enum.Enum):
    SECURED   = "secured"    # No combat
    CONTESTED = "contested"  # NPC combat + consensual PvP
    LAWLESS   = "lawless"    # Full open PvP


# ── Transient Director overrides ────────────────────────────────────────────
# Maps zone_id (int) → SecurityLevel override.
# Never written to DB.  Cleared on restart.
_overrides: dict[int, SecurityLevel] = {}


def set_security_override(zone_id: int, level: SecurityLevel | None) -> None:
    """Set (or clear with None) a transient security override for a zone."""
    if level is None:
        _overrides.pop(zone_id, None)
    else:
        _overrides[zone_id] = level
    log.info("[security] zone %s override → %s", zone_id, level)


def clear_all_overrides() -> None:
    _overrides.clear()


# ── Core lookup ─────────────────────────────────────────────────────────────

async def get_effective_security(room_id: int, db) -> SecurityLevel:
    """
    Return the effective security level for a room.

    Resolution order:
      1. Transient Director override on the room's zone_id.
      2. Room/zone property "security" via get_room_property().
      3. Default: CONTESTED (safest default for unset content).
    """
    # Resolve zone_id for override check
    room = await db.get_room(room_id)
    if room:
        zone_id = room.get("zone_id")
        if zone_id and zone_id in _overrides:
            return _overrides[zone_id]

    # Property inheritance
    raw = await db.get_room_property(room_id, "security")
    if raw:
        try:
            return SecurityLevel(raw.lower())
        except ValueError:
            log.warning("[security] unknown security value %r on room %s", raw, room_id)

    return SecurityLevel.CONTESTED


# ── Convenience helpers ──────────────────────────────────────────────────────

async def is_combat_allowed(room_id: int, db) -> bool:
    """True if any combat (NPC or player) is allowed in this room."""
    level = await get_effective_security(room_id, db)
    return level != SecurityLevel.SECURED


async def is_pvp_allowed(room_id: int, db) -> bool:
    """True if unrestricted PvP is allowed (LAWLESS only)."""
    level = await get_effective_security(room_id, db)
    return level == SecurityLevel.LAWLESS


def security_label(level: SecurityLevel) -> str:
    """Short ANSI-coloured label for display in 'look' output."""
    labels = {
        SecurityLevel.SECURED:   "\033[1;34m[SECURED]\033[0m",
        SecurityLevel.CONTESTED: "\033[1;33m[CONTESTED]\033[0m",
        SecurityLevel.LAWLESS:   "\033[1;31m[LAWLESS]\033[0m",
    }
    return labels.get(level, "")


def security_refuse_msg(level: SecurityLevel, target_is_npc: bool) -> str:
    """Return the refusal message shown when combat is blocked."""
    if level == SecurityLevel.SECURED:
        if target_is_npc:
            return (
                "\033[1;33mImperial security patrols this area. "
                "The guards would be on you before you could draw.\033[0m"
            )
        return (
            "\033[1;33mImperial security is too heavy here. "
            "You'd be gunned down before you drew.\033[0m"
        )
    return "\033[1;33mCombat is not permitted here.\033[0m"
