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
# _overrides: zone_id (int) → SecurityLevel  (legacy, room-level)
# _env_overrides: zone environment key (str) → SecurityLevel  (Director-driven)
# Neither is written to DB — cleared on restart (intentional).
_overrides: dict[int, SecurityLevel] = {}
_env_overrides: dict[str, SecurityLevel] = {}


def set_security_override(zone_id: int, level: SecurityLevel | None) -> None:
    """Set (or clear with None) a transient security override for a zone."""
    if level is None:
        _overrides.pop(zone_id, None)
    else:
        _overrides[zone_id] = level
    log.info("[security] zone %s override → %s", zone_id, level)


def set_security_override_by_env(zone_env: str, level: SecurityLevel | None) -> None:
    """
    Set (or clear with None) a Director-driven security override keyed by
    zone environment string (e.g. 'spaceport', 'cantina', 'jabba').
    Called by the Director after each faction turn or influence update.
    """
    if level is None:
        _env_overrides.pop(zone_env, None)
    else:
        _env_overrides[zone_env] = level
    log.info("[security] env-zone %r override → %s", zone_env, level)


def clear_all_overrides() -> None:
    _overrides.clear()
    _env_overrides.clear()


# ── Core lookup ─────────────────────────────────────────────────────────────

async def get_effective_security(room_id: int, db, character: dict = None) -> SecurityLevel:
    """
    Return the effective security level for a room.

    Resolution order:
      1. Transient Director override on the room's zone_id (int).
      2. Director env override on the zone environment key (string).
      3. Director live influence thresholds (criminal surge / crackdown).
      4. Room/zone property "security" via get_room_property().
      5. Default: CONTESTED.

    After base resolution, if `character` is provided:
      6. Territory claim upgrade: if room is claimed by character's org,
         lawless → contested (members are safer in claimed territory).
    """
    room = await db.get_room(room_id)
    zone_env = ""

    if room:
        zone_id = room.get("zone_id")

        # 1. Integer zone_id override (admin @security command)
        if zone_id and zone_id in _overrides:
            base = _overrides[zone_id]
            return _apply_claim_upgrade(base, room_id, character, db)

        # Resolve zone environment key for steps 2–3
        if zone_id:
            try:
                zone = await db.get_zone(zone_id)
                if zone:
                    props = zone.get("properties", "{}")
                    if isinstance(props, str):
                        import json as _j
                        try:
                            props = _j.loads(props)
                        except Exception:
                            props = {}
                    zone_env = props.get("environment", "")
            except Exception:
                log.warning("get_effective_security: unhandled exception", exc_info=True)
                pass

    # 2. Env-key override set explicitly by Director
    if zone_env and zone_env in _env_overrides:
        base = _env_overrides[zone_env]
        return await _apply_claim_upgrade(base, room_id, character, db)

    # 3. Director live influence thresholds
    if zone_env:
        try:
            from engine.director import get_director
            director = get_director()
            zs = director.get_zone_state(zone_env)
            if zs:
                base_raw = await db.get_room_property(room_id, "security") or "contested"
                try:
                    base = SecurityLevel(base_raw.lower())
                except ValueError:
                    base = SecurityLevel.CONTESTED
                base = _apply_director_overlay(base, zs)
                return await _apply_claim_upgrade(base, room_id, character, db)
        except Exception:
            pass  # Director unavailable — fall through

    # 4. Property inheritance
    raw = await db.get_room_property(room_id, "security")
    if raw:
        try:
            base = SecurityLevel(raw.lower())
            return await _apply_claim_upgrade(base, room_id, character, db)
        except ValueError:
            log.warning("[security] unknown security value %r on room %s", raw, room_id)

    base = SecurityLevel.CONTESTED
    return await _apply_claim_upgrade(base, room_id, character, db)


def _apply_director_overlay(base: SecurityLevel, zs) -> SecurityLevel:
    """
    Shift base security level based on Director influence thresholds.

    Criminal surge (criminal >= 80): downgrade one tier.
    Imperial crackdown (imperial >= 75): upgrade one tier.
    Martial law (imperial >= 90): force SECURED regardless.
    Both rules apply in sequence — crackdown can partially cancel a surge.
    """
    result = base

    # Criminal surge — underworld fills vacuum
    if getattr(zs, "criminal", 0) >= 80:
        if result == SecurityLevel.SECURED:
            result = SecurityLevel.CONTESTED
        elif result == SecurityLevel.CONTESTED:
            result = SecurityLevel.LAWLESS

    # Imperial crackdown — raise one tier
    if getattr(zs, "imperial", 0) >= 75:
        if result == SecurityLevel.LAWLESS:
            result = SecurityLevel.CONTESTED
        elif result == SecurityLevel.CONTESTED:
            result = SecurityLevel.SECURED

    # Martial law — extreme dominance
    if getattr(zs, "imperial", 0) >= 90:
        result = SecurityLevel.SECURED

    return result


async def _apply_claim_upgrade(base: SecurityLevel, room_id: int,
                                character: dict | None, db) -> SecurityLevel:
    """
    If the room is claimed by the character's org, upgrade lawless → contested.
    This means org members are safer in their claimed territory.
    """
    if character is None:
        return base
    if base != SecurityLevel.LAWLESS:
        return base  # Only lawless gets upgraded

    char_org = character.get("faction_id", "independent")
    if not char_org or char_org == "independent":
        return base

    try:
        from engine.territory import is_room_claimed_by
        if await is_room_claimed_by(db, room_id, char_org):
            return SecurityLevel.CONTESTED
    except Exception:
        log.warning("_apply_claim_upgrade: unhandled exception", exc_info=True)
        pass
    return base


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
