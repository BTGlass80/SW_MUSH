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

    Resolution order (SYN.2, 2026-05-24):
      1. Transient Director override on the room's zone_id (int).
      2. Director env override on the zone environment key (string).
      3. Director live influence thresholds (criminal surge / crackdown).
      4. **Wilderness region ownership branch** (NEW in SYN.2). If the
         room has ``wilderness_region_id`` set, resolve security from
         the region's ``default_security`` plus owner status:
           - Region owned + char in owning org → LAWLESS upgrades to
             CONTESTED (citadel upgrade). CONTESTED stays CONTESTED.
           - Region owned + char NOT in owning org → base stands.
             (Hostile territory.)
           - Region un-owned → base stands.
         Terminal for wilderness rooms; skips steps 5-6 (still
         runs ``_finalize`` for SECMOD.1 faction-override + city
         upgrade, which are no-ops for typical wilderness rooms
         and meaningful for wilderness-anchored city citizens).
      5. Room/zone property "security" via get_room_property().
      6. Default: CONTESTED.

    After base resolution, ``_finalize`` applies:
      - ``_apply_faction_override`` (SECMOD.1): hostile PC in
        faction-secured room → LAWLESS.
      - ``_apply_city_upgrade``: citizen in their own city → upgrade.
    The legacy ``_apply_claim_upgrade`` step retired in SYN.2 along
    with the per-room claim system (see contestable_wilderness_design_v2.md
    §3.2 + §6).
    """
    room = await db.get_room(room_id)
    zone_env = ""

    if room:
        zone_id = room.get("zone_id")

        # 1. Integer zone_id override (admin @security command)
        if zone_id and zone_id in _overrides:
            base = _overrides[zone_id]
            # DROP-2 SECURITY FIX (May 2026): _apply_claim_upgrade is
            # async; the four sibling call sites in this function
            # await it correctly, but this admin-override branch was
            # missing the await. Symptoms: the coroutine object was
            # returned in place of a SecurityLevel, callers got a
            # truthy non-SecurityLevel value, and the override
            # effectively didn't apply (callers fell through to the
            # un-overridden security tier with a RuntimeWarning).
            # Caught by smoke CX1 driving set_security_override.
            #
            # SECMOD.1 (May 22 2026): routed through _finalize so the
            # faction-override resolver step runs before claim-upgrade.
            return await _finalize(base, room, room_id, character, db)

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
        return await _finalize(base, room, room_id, character, db)

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
                return await _finalize(base, room, room_id, character, db)
        except Exception:
            pass  # Director unavailable — fall through

    # 4. Wilderness region ownership branch (SYN.2, 2026-05-24).
    # Per contestable_wilderness_design_v2.md §2.3: if the room is a
    # wilderness landmark (carries wilderness_region_id), resolve
    # security from the region's default_security + ownership state.
    # Terminal for wilderness rooms — skips the city-map fallback.
    if room and room.get("wilderness_region_id"):
        try:
            region_state = await _get_wilderness_region_state(room, db)
            if region_state is not None:
                base = _apply_wilderness_ownership(
                    region_state["default_security"], character, region_state,
                )
                return await _finalize(base, room, room_id, character, db)
        except Exception:
            log.warning(
                "get_effective_security: wilderness branch error", exc_info=True,
            )
            # Fall through to city-map path on error — graceful

    # 5. Property inheritance
    raw = await db.get_room_property(room_id, "security")
    if raw:
        try:
            base = SecurityLevel(raw.lower())
            return await _finalize(base, room, room_id, character, db)
        except ValueError:
            log.warning("[security] unknown security value %r on room %s", raw, room_id)

    base = SecurityLevel.CONTESTED
    return await _finalize(base, room, room_id, character, db)


# ── Wilderness branch helpers (SYN.2, 2026-05-24) ────────────────────────────

async def _get_wilderness_region_state(room: dict, db) -> dict | None:
    """Look up the wilderness region's security + ownership state.

    Args:
      room: The room dict containing ``wilderness_region_id``.
      db: Database adapter.

    Returns:
      A dict with shape
        ``{"slug": str, "default_security": SecurityLevel,
           "owner_org": str | None}``
      or None if the region isn't found in ``wilderness_regions``
      (e.g. world hasn't been built yet, or a stale
      ``wilderness_region_id`` on a hand-built room).

    The lookup is two reads:
      1. ``wilderness_regions.default_security`` for the base tier.
      2. ``region_ownership.org_code`` for the owner (or None).
    """
    slug = room.get("wilderness_region_id")
    if not slug:
        return None

    # Read default_security from the wilderness_regions registry
    try:
        rows = await db.fetchall(
            "SELECT default_security FROM wilderness_regions WHERE slug = ?",
            (slug,),
        )
    except Exception:
        log.warning("_get_wilderness_region_state: registry read failed",
                    exc_info=True)
        return None
    if not rows:
        # Region isn't registered. The room carries the slug
        # (probably from a manual write) but the writer hasn't run.
        # Graceful fallback: treat as un-owned lawless.
        return None

    default_raw = (rows[0]["default_security"] or "lawless").lower()
    try:
        default_security = SecurityLevel(default_raw)
    except ValueError:
        log.warning(
            "[security/wilderness] unknown default_security %r for region %r — "
            "falling back to LAWLESS",
            default_raw, slug,
        )
        default_security = SecurityLevel.LAWLESS

    # Read owner from region_ownership (SYN.1.a). Absent row → un-owned.
    owner_org = None
    try:
        rows = await db.fetchall(
            "SELECT org_code FROM region_ownership WHERE region_slug = ?",
            (slug,),
        )
        if rows:
            owner_org = rows[0]["org_code"]
    except Exception:
        log.warning("_get_wilderness_region_state: ownership read failed",
                    exc_info=True)

    return {
        "slug": slug,
        "default_security": default_security,
        "owner_org": owner_org,
    }


def _apply_wilderness_ownership(
    base: SecurityLevel, character: dict | None, region_state: dict,
) -> SecurityLevel:
    """Apply the wilderness region's ownership rule to ``base``.

    Per ``contestable_wilderness_design_v2.md`` §2.3:

      * Region owned AND character in owning org → citadel upgrade
        (LAWLESS → CONTESTED). CONTESTED stays CONTESTED (no further
        promotion; SECURED is impossible in wilderness by design).
      * Region owned AND character NOT in owning org → base stands.
        (Hostile territory — outsiders take the frontier risk.)
      * Region un-owned → base stands.
      * No character context (NPC observers, system queries) → base
        stands.

    The function is pure (no DB I/O); the caller (the step 4 branch)
    handles the DB reads. This separation makes the rule unit-testable
    without DB setup.
    """
    owner_org = region_state.get("owner_org")
    if not owner_org:
        return base  # un-owned

    if character is None:
        return base  # no character context

    char_org = character.get("faction_id", "independent")
    if not char_org or char_org == "independent":
        return base  # independent PCs get no faction-based upgrade

    if char_org != owner_org:
        return base  # hostile territory: base stands

    # Citadel upgrade: LAWLESS → CONTESTED. Other tiers unchanged.
    if base == SecurityLevel.LAWLESS:
        return SecurityLevel.CONTESTED
    return base


def _apply_director_overlay(base: SecurityLevel, zs) -> SecurityLevel:
    """
    Shift base security level based on Director influence thresholds.

    Underworld surge (underworld axis >= 80): downgrade one tier.
    Authority crackdown (authority axis >= 75): upgrade one tier.
    Martial law (authority axis >= 90): force SECURED regardless.
    Both rules apply in sequence — crackdown can partially cancel a surge.

    Reads the era-resolved alert axes via ZoneState.get_faction so it works
    on the native CW faction set (republic/cis/hutt_cartel) instead of the
    retired GCW attribute names (DIRECTOR.zonestate_cw_faction_axis).
    """
    from engine.director import ALERT_AXIS

    def _axis(role: str) -> int:
        # ZoneState exposes get_faction; fall back to a bare attr/0 for any
        # duck-typed stub passed in tests.
        getter = getattr(zs, "get_faction", None)
        if callable(getter):
            return getter(ALERT_AXIS[role])
        return getattr(zs, ALERT_AXIS[role], 0)

    result = base

    # Underworld surge — criminal element fills the vacuum
    if _axis("underworld") >= 80:
        if result == SecurityLevel.SECURED:
            result = SecurityLevel.CONTESTED
        elif result == SecurityLevel.CONTESTED:
            result = SecurityLevel.LAWLESS

    # Authority crackdown — raise one tier
    if _axis("authority") >= 75:
        if result == SecurityLevel.LAWLESS:
            result = SecurityLevel.CONTESTED
        elif result == SecurityLevel.CONTESTED:
            result = SecurityLevel.SECURED

    # Martial law — extreme authority dominance
    if _axis("authority") >= 90:
        result = SecurityLevel.SECURED

    return result


async def _apply_faction_override(base: SecurityLevel,
                                   room: dict | None,
                                   character: dict | None,
                                   db) -> SecurityLevel:
    """
    SECMOD.1 (security_zones_design_v1.md §3.2): if the room carries a
    ``faction_override``, and the base level is SECURED, and the
    character is Hostile or Unfriendly to that faction, downgrade to
    LAWLESS.

    Rationale (from design §3.2):
        Imperial Garrison interior → lawless for non-Imperials
        Rebel safehouse           → lawless for Imperial-aligned PCs
        Hutt palace interior      → contested for everyone

    Substrate decisions:

    1. **Only SECURED gets downgraded.** A CONTESTED or LAWLESS room
       already permits combat; downgrading would be a no-op
       (CONTESTED → LAWLESS would *enable* PvP without consent in a
       contested faction stronghold, which is a separate design call).
       This matches the design doc's wording: "the security level
       effectively becomes contested or lawless for players who don't
       belong" — applied as a one-step downgrade to LAWLESS from
       SECURED. The CONTESTED case in the design fiction maps to a
       Hutt palace, which the design itself says is "contested for
       everyone" — so the BASE is already CONTESTED for those rooms;
       the override doesn't have to downgrade further.

    2. **No character → no downgrade.** Director-driven and
       admin-issued security overrides resolve without a character
       context; the faction-override rule is per-character by
       definition, so it skips when ``character is None``.

    3. **Standing tiers come from REP_TIERS in engine/organizations.py.**
       Hostile is rep ≤ -50; Unfriendly is rep -49..-25. Anything ≥ -24
       (wary, unknown, recognized, etc.) is NOT downgraded — wary PCs
       are merely watched, not treated as enemies of the faction.

    4. **Fail-soft.** If org lookup raises, log and fall through to
       the base level. Better to leak occasional access than to
       silently break every secured-zone check on a transient
       organizations-layer hiccup.

    5. **Room dict may be None.** Callers in get_effective_security
       always have it (they loaded it for zone_id resolution), but
       the parameter is typed as Optional so future callers without
       a pre-loaded room don't need a stub fetch.
    """
    if base != SecurityLevel.SECURED:
        return base
    if character is None or not room:
        return base

    override = room.get("faction_override")
    if not override:
        return base

    try:
        from engine.organizations import get_char_faction_rep
        rep = await get_char_faction_rep(character, override, db)
        # Hostile (rep ≤ -50) or Unfriendly (-49..-25) → downgrade.
        # See REP_TIERS in engine/organizations.py for the canonical
        # tier table.
        if rep <= -25:
            return SecurityLevel.LAWLESS
    except Exception:
        log.warning(
            "_apply_faction_override: unhandled exception "
            "(room=%s, override=%r)",
            room.get("id"), override, exc_info=True,
        )
    return base


async def _apply_city_upgrade(base: SecurityLevel, room_id: int,
                               character: dict | None, db) -> SecurityLevel:
    """
    Player Cities Phase 5 (May 22 2026) §6.2: city rooms upgrade for
    citizens.

    Citizen upgrades (read via engine.player_cities.is_citizen):
      - CONTESTED → SECURED  (city rooms in contested zones are
                              safe for citizens)
      - LAWLESS   → CONTESTED (city rooms in lawless zones become
                              consent-PvP for citizens; non-
                              citizens still get full lawless)

    Non-citizens (including guests and outsiders) get NO upgrade.
    Banished users are non-citizens by definition (banishment
    supersedes membership per Phase 3 get_city_role).

    This is the most-permissive last word in the _finalize chain:
    even if faction-override downgraded SECURED → LAWLESS, the
    city upgrade can lift the character back up. That's the correct
    behavior: a citizen inside their own city should be safer than
    a hostile faction's downgrade can make them.

    Fail-soft: any exception in the city lookup falls through to
    the base level so a transient cities-layer hiccup doesn't
    silently weaken security for everyone else.
    """
    if character is None:
        return base
    # Only CONTESTED and LAWLESS get upgraded; SECURED stays.
    if base not in (SecurityLevel.CONTESTED, SecurityLevel.LAWLESS):
        return base

    try:
        from engine.player_cities import get_city_for_room, is_citizen
        city = await get_city_for_room(db, int(room_id))
        if not city:
            return base
        if not await is_citizen(db, character, city):
            return base
        # Citizen — apply the upgrade.
        if base == SecurityLevel.CONTESTED:
            return SecurityLevel.SECURED
        if base == SecurityLevel.LAWLESS:
            return SecurityLevel.CONTESTED
    except Exception:
        log.warning(
            "_apply_city_upgrade: unhandled exception "
            "(room=%s); failing through",
            room_id, exc_info=True,
        )
    return base


async def _finalize(base: SecurityLevel,
                     room: dict | None,
                     room_id: int,
                     character: dict | None,
                     db) -> SecurityLevel:
    """
    Apply the post-resolve chain: faction-override first, then
    city-upgrade. SYN.2 (2026-05-24): the claim-upgrade step retired
    along with ``_apply_claim_upgrade`` — wilderness region ownership
    is handled directly in ``get_effective_security`` step 4
    (terminal for wilderness chars). City-map rooms reach this
    finalize chain via steps 5-6; wilderness rooms also pass through
    here so the city-upgrade step still applies for city citizens
    whose city happens to be anchored at a wilderness landmark
    (SYN.4 makes this the universal case).

    Order matters — the faction-override downgrade (SECURED →
    LAWLESS) runs first; the city upgrade is most-permissive last
    so a citizen inside their own city gets the strongest available
    security tier.
    """
    base = await _apply_faction_override(base, room, character, db)
    base = await _apply_city_upgrade(base, room_id, character, db)
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
                "\033[1;33mHeavy security patrols this area. "
                "The guards would be on you before you could draw.\033[0m"
            )
        return (
            "\033[1;33mSecurity here is too heavy. "
            "You'd be gunned down before you drew.\033[0m"
        )
    return "\033[1;33mCombat is not permitted here.\033[0m"
