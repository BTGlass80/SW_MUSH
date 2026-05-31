# -*- coding: utf-8 -*-
"""
engine/city_guard_runtime.py — Phase 7b runtime hooks for city guards.

Phase 7 (May 23 2026, earlier today) shipped:
  - player_city_guards table + assignment/removal API
  - `guards_active(city)` helper (False in grace)
  - `city_guard_for_city_id` ai_config tag distinguishing city
    guards from territory guards

Phase 7b (May 23 2026, prior drop) wired the runtime behavior the
Phase 6 mail body promises and the design v1.2 §7.2 trigger conditions:

  - **Grace gate**: a city guard in a city whose treasury has
    depleted (`grace_started_at != 0`) stops engaging. Matches
    the Phase 6 mail body line "Week 1: NPC guards stop
    functioning".
  - **Banished-entry trigger**: when a banished player enters a
    city room that contains a city guard, the guard engages.
    Per design §7.2 second bullet.

Phase 7c (this drop, May 23 2026) closes the remaining §7.2
triggers:

  - **Bountied-entry trigger** (on-entry, piggybacks on Phase 7b
    path): a guard engages when the entering character has an
    active PC bounty in state='claimed' whose `claimed_by` is a
    citizen of the guard's city org. Per design §7.2 third bullet.
  - **Attacked-a-citizen trigger** (combat-round, new code path):
    when a non-citizen attacks a citizen in a city room during
    a combat round, any city guards stationed in that room are
    auto-joined to the active combat. Per design §7.2 first
    bullet ("attacked a citizen in this combat session").

Phase 7c is feature-complete for design §7.2.

Design principle
----------------
The runtime helpers in this module are **read-only over NPC
state**. We do not mutate the NPC's `ai_config_json` to set
`hostile: True` for a banished entry — that would persist
across sessions and require cleanup on the banishment expiry.
Instead, the entry check (`check_room_hostiles`) is extended
to run `should_city_guard_engage(db, npc_row, entering_char)`
and add the guard to the hostile list only when the trigger
fires. The guard's stored `hostile` flag stays False.

This keeps the data layer immutable for guard NPCs — the only
write to a guard NPC's row is `delete_npc` (via
`remove_city_guard`). All engagement decisions are evaluated
at query time.

Failure semantics
-----------------
The helpers are fail-soft: any exception during the city
lookup / banishment check / grace evaluation logs at debug and
returns the safe default (False — guard does not engage). A
broken city-guard read MUST NOT block the broader hostile-NPCs
check, which serves all other NPCs in the room.

Per HANDOFF_MAY23_CITIES_PHASE7B_RUNTIME.md.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Identity helpers ────────────────────────────────────────────────────────


def parse_npc_ai_config(npc_row: dict) -> dict:
    """Best-effort parse of an NPC row's ai_config_json.

    Returns the parsed dict, or an empty dict if parsing fails
    or the field is absent. Tolerant of either string-encoded
    JSON (the on-disk shape) or already-parsed dict (test
    fixtures sometimes pass the latter).
    """
    raw = (npc_row or {}).get("ai_config_json", "{}")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def city_guard_city_id(npc_row: dict) -> Optional[int]:
    """Return the city_id this NPC is a city guard for, or None.

    Phase 7 tags every newly-assigned city guard with
    ``ai_config["city_guard_for_city_id"] = <city_id>``. A None
    return means the NPC is not a city guard (or its ai_config
    is malformed beyond recovery).
    """
    cfg = parse_npc_ai_config(npc_row)
    val = cfg.get("city_guard_for_city_id")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def is_city_guard(npc_row: dict) -> bool:
    """Convenience: True iff this NPC is a Phase 7 city guard."""
    return city_guard_city_id(npc_row) is not None


# ── Engagement trigger ──────────────────────────────────────────────────────


async def should_city_guard_engage(
    db, npc_row: dict, entering_char: dict,
) -> bool:
    """Return True iff a city guard should engage an entering
    character.

    Triggers (per design v1.2 §7.2):
      - Entering character is currently banished from this city.
      - Entering character has an active bounty claimed by a
        citizen of this city (Phase 7c, May 23 2026).

    Both triggers require the city to be healthy
    (``guards_active`` is True) — grace overrides all engagement.

    Returns False (safe default) when:
      - NPC is not a city guard.
      - City lookup fails or city is dissolved.
      - City is in any grace stage (``guards_active(city)`` is
        False).
      - Entering character is not banished AND has no bounty
        claimed by a citizen.
      - The entering char dict lacks an id.
      - Any DB lookup raises.

    The check is deliberately conservative: when in doubt, the
    guard does NOT engage. This matches design §7.2's principle
    that "Cities are public spaces by default" — false-positive
    engagement is the more user-hostile failure mode.
    """
    try:
        city_id = city_guard_city_id(npc_row)
        if city_id is None:
            return False

        char_id = (entering_char or {}).get("id")
        if char_id is None:
            return False

        # Late import — engine.player_cities is the orchestrator
        # and importing it at module load would create a cycle
        # if engine.player_cities ever wants to call into this
        # module. The deferred import is paid once per call but
        # only when an NPC has the city-guard tag, which is rare.
        from engine import player_cities as pc

        city = await pc.get_city_by_id(db, int(city_id))
        if city is None:
            return False
        if city.get("state") == "dissolved":
            return False
        if not pc.guards_active(city):
            return False

        # Phase 7b trigger: banished entry.
        if await pc.is_banished(db, int(city_id), int(char_id)):
            return True

        # Phase 7c trigger: bounty claimed by a citizen.
        if await _has_bounty_claimed_by_citizen(
            db, int(char_id), city,
        ):
            return True

        return False
    except Exception as e:
        log.debug(
            "[city_guard_runtime] should_city_guard_engage "
            "failed (safe default = False): %s", e, exc_info=True,
        )
        return False


# ── Hostile-list integration ────────────────────────────────────────────────


async def filter_for_city_guard_engagement(
    db, hostile_npc_rows: list, entering_char: dict,
    room_npc_rows: Optional[list] = None,
) -> list:
    """Adjust a hostile-NPC list for city-guard engagement rules.

    The standard `engine.npc_combat_ai.check_room_hostiles` builds
    its list from `is_hostile(ai_config)`. City guards have
    `hostile: False` in their stored AI (they're public-space
    guards, not attack-on-sight). This helper folds in the
    Phase 7b trigger:

      - Removes any city guard from `hostile_npc_rows` whose
        city is in grace (consistency with the disable-on-grace
        promise — even if some external surface accidentally
        added a city guard to the hostile list, grace overrides).
      - Adds any city guard NOT already in `hostile_npc_rows` if
        `should_city_guard_engage` returns True for that
        (guard, entering_char) pair.

    `hostile_npc_rows`: the list returned by `check_room_hostiles`
    (or any compatible list of npc row dicts).
    `entering_char`: the character entering the room.
    `room_npc_rows`: the full set of NPCs in the room (needed
    so we can find city guards that aren't already hostile).
    If omitted, the helper only does the grace-removal pass.

    Returns a NEW list — the input is not mutated.

    Fail-soft: any exception during evaluation falls through
    with the original list returned. Logs at debug.
    """
    try:
        # First pass: drop in-grace city guards from the hostile
        # list. We re-check `should_city_guard_engage` for each
        # city guard already in the list — if it returns False,
        # it gets dropped.
        keep: list = []
        for row in hostile_npc_rows:
            if is_city_guard(row):
                if await should_city_guard_engage(
                    db, row, entering_char,
                ):
                    keep.append(row)
                # else: drop — guard is a city guard but
                # shouldn't engage this entry
            else:
                keep.append(row)

        # Second pass: scan room_npc_rows for city guards that
        # aren't already in `keep` and SHOULD engage.
        if room_npc_rows is not None:
            keep_ids = {r.get("id") for r in keep
                        if r.get("id") is not None}
            for row in room_npc_rows:
                rid = row.get("id")
                if rid is None or rid in keep_ids:
                    continue
                if not is_city_guard(row):
                    continue
                if await should_city_guard_engage(
                    db, row, entering_char,
                ):
                    keep.append(row)
                    keep_ids.add(rid)

        return keep
    except Exception as e:
        log.debug(
            "[city_guard_runtime] "
            "filter_for_city_guard_engagement failed "
            "(returning original list): %s", e, exc_info=True,
        )
        return list(hostile_npc_rows)


# ── Phase 7c (May 23 2026): combat-round triggers ─────────────────────


async def _has_bounty_claimed_by_citizen(
    db, target_char_id: int, city: dict,
) -> bool:
    """Return True iff there is an active or claimed PC bounty
    against ``target_char_id`` whose ``claimed_by`` is currently
    a member of the city's founding org.

    Per design v1.2 §7.2 third engage bullet:
        "The non-citizen has an active bounty claimed by a
         citizen BH"

    "Citizen" = member of the city's org. "Claimed" = state =
    'claimed' AND claimed_by is set. An unclaimed active bounty
    does NOT trigger — the design specifies that a citizen BH
    must have staked their claim.

    Fail-soft: returns False on any exception (logged at debug).
    """
    try:
        org_id = int(city.get("org_id") or 0)
        if not org_id:
            return False

        # Find any claimed bounty against this target. The
        # bounty table is indexed on (target_id, state).
        rows = await db.fetchall(
            "SELECT claimed_by FROM pc_bounties "
            "WHERE target_id = ? AND state = 'claimed' "
            "AND claimed_by IS NOT NULL",
            (int(target_char_id),),
        )
        if not rows:
            return False

        # Check if any claimant is a member of the city's org.
        # Usually 1 claim per target (claim is exclusive), so
        # this is a single membership lookup.
        for row in rows:
            claimant_id = row.get("claimed_by")
            if claimant_id is None:
                continue
            try:
                m = await db.get_membership(
                    int(claimant_id), org_id)
                if m and m.get("standing") != "expelled":
                    return True
            except Exception:
                # One bad claimant lookup shouldn't poison the
                # whole check; skip and try the next.
                log.debug(
                    "[city_guard_runtime] membership check "
                    "failed for claimant %s in org %s",
                    claimant_id, org_id, exc_info=True,
                )
                continue
        return False
    except Exception as e:
        log.debug(
            "[city_guard_runtime] _has_bounty_claimed_by_"
            "citizen failed (safe default = False): %s",
            e, exc_info=True,
        )
        return False


async def _is_citizen_of(db, city: dict, char_id: int) -> bool:
    """Helper: is `char_id` a current member of the city's org?

    Used by the attacked-citizen trigger. Returns False on any
    exception or if the char is not a member.
    """
    try:
        org_id = int(city.get("org_id") or 0)
        if not org_id:
            return False
        m = await db.get_membership(int(char_id), org_id)
        if not m:
            return False
        return m.get("standing") != "expelled"
    except Exception:
        log.debug(
            "[city_guard_runtime] _is_citizen_of failed "
            "(safe default = False)", exc_info=True,
        )
        return False


async def should_engage_attacker_of_citizen(
    db, npc_row: dict, attacker_char_id: int,
    attacks_made: set,
) -> bool:
    """Return True iff an attacker has attacked at least one
    citizen of this city guard's city in the current combat
    session.

    ``attacks_made`` is the ``CombatInstance.attacks_made``
    set — tuples of ``(attacker_id, target_id)`` recorded on
    every attack attempt. Phase 7c's combat-round trigger
    (design v1.2 §7.2, second engage bullet).

    Returns False (safe default) when:
      - NPC is not a city guard.
      - City lookup fails / city is dissolved / city is in grace.
      - The attacker has not attacked anyone in the combat yet.
      - None of the attacker's targets are citizens of this
        guard's city.
      - Any DB lookup raises.

    Note: the attacker himself can be a citizen — guards still
    engage him for attacking another citizen. (Sibling fights
    summon the cops; design says nothing exempts citizens.)
    """
    try:
        city_id = city_guard_city_id(npc_row)
        if city_id is None:
            return False

        # Filter the attacks set to ones this attacker made
        attacker_targets = {
            tgt for (atk, tgt) in (attacks_made or set())
            if int(atk) == int(attacker_char_id)
        }
        if not attacker_targets:
            return False

        from engine import player_cities as pc
        city = await pc.get_city_by_id(db, int(city_id))
        if city is None:
            return False
        if city.get("state") == "dissolved":
            return False
        if not pc.guards_active(city):
            return False

        for tgt_id in attacker_targets:
            if await _is_citizen_of(db, city, int(tgt_id)):
                return True
        return False
    except Exception as e:
        log.debug(
            "[city_guard_runtime] "
            "should_engage_attacker_of_citizen failed "
            "(safe default = False): %s", e, exc_info=True,
        )
        return False


async def evaluate_combat_round_triggers(
    db, room_id: int, combatant_ids: list,
    attacks_made: set, room_npc_rows: list,
) -> list:
    """Scan a room's NPC roster and return the list of city
    guards that should now join an active combat.

    Called by the combat-resolver after each round (per
    Phase 7c integration in ``parser/combat_commands.py``).

    For each city guard NPC in the room that is NOT already in
    the combat, evaluate the two combat-round triggers:
      - Attacked-a-citizen-in-this-combat-session
      - Bountied-target-claimed-by-citizen-BH (re-evaluated
        each round in case a bounty gets claimed mid-fight)

    Returns: list of NPC row dicts to add to the combat.
    Empty list if no triggers fire.

    City lookups are cached per ``city_id`` so multiple guards
    from the same city share one DB read. The cached city is
    passed inline to the per-combatant checks to avoid
    duplicate lookups inside the inner predicates.

    Fail-soft: returns the empty list on any internal exception
    so a broken trigger check never blocks combat resolution.
    """
    try:
        if not room_npc_rows:
            return []
        engaged_set = set(int(i) for i in (combatant_ids or []))
        to_add: list = []

        # Cache city lookups per city_id — multiple guards from
        # the same city would otherwise hammer the city row.
        city_cache: dict = {}

        async def _city_of(npc_row):
            cid = city_guard_city_id(npc_row)
            if cid is None:
                return None
            if cid in city_cache:
                return city_cache[cid]
            from engine import player_cities as pc
            try:
                c = await pc.get_city_by_id(db, int(cid))
            except Exception:
                c = None
            city_cache[cid] = c
            return c

        from engine import player_cities as pc

        for guard_row in room_npc_rows:
            if not is_city_guard(guard_row):
                continue
            gid = guard_row.get("id")
            if gid is None or int(gid) in engaged_set:
                continue

            city = await _city_of(guard_row)
            if city is None:
                continue
            if city.get("state") == "dissolved":
                continue
            if not pc.guards_active(city):
                continue

            # Walk every combatant — does this guard have a
            # reason to engage any of them? Both predicates
            # below accept a pre-resolved city dict so no
            # redundant city/grace lookups occur inside.
            engaged_for_this_guard = False
            attacks = attacks_made or set()
            for ch_id in combatant_ids:
                # Skip checking against the guard itself
                if int(ch_id) == int(gid):
                    continue

                # Trigger A: attacker-of-citizen — has this
                # combatant attacked any citizen of `city`?
                attacker_targets = {
                    tgt for (atk, tgt) in attacks
                    if int(atk) == int(ch_id)
                }
                if attacker_targets:
                    hit_citizen = False
                    for tgt_id in attacker_targets:
                        if await _is_citizen_of(
                            db, city, int(tgt_id),
                        ):
                            hit_citizen = True
                            break
                    if hit_citizen:
                        engaged_for_this_guard = True
                        break

                # Trigger B: bountied target claimed by citizen
                # (re-evaluated mid-combat in case a citizen BH
                # claims the bounty after combat starts)
                if await _has_bounty_claimed_by_citizen(
                    db, int(ch_id), city,
                ):
                    engaged_for_this_guard = True
                    break

            if engaged_for_this_guard:
                to_add.append(guard_row)

        return to_add
    except Exception as e:
        log.debug(
            "[city_guard_runtime] "
            "evaluate_combat_round_triggers failed "
            "(no guards added): %s", e, exc_info=True,
        )
        return []
