# -*- coding: utf-8 -*-
"""engine/wow_combat_hooks.py — Weight of War runtime hooks for
ground combat (WoW.3a, May 24 2026).

This module is the seam between ground-combat resolution
(`parser/combat_commands.py`) and the Weight-of-War substrate
(`engine/weight_of_war.py`). It intentionally lives outside both:

  - Keeping it out of `engine/combat.py` means the combat
    dataclasses don't grow Jedi-specific fields. The combat module
    stays generic; Weight-of-War is an opt-in observer.
  - Keeping it out of `engine/weight_of_war.py` means the substrate
    doesn't need to know about Combatant/CombatInstance shapes —
    those are parser-side concerns.

Two public functions:

  - ``credit_kill_for_jedi(db, combat, jedi_char, npc_id)`` —
    credit a kill to a Jedi PC, deduped within the fight and
    capped at +3 Weight per fight per Jedi. Idempotent on
    (jedi_id, npc_id) — calling it twice for the same pair is a
    no-op (the second call returns 0).
  - ``is_in_retreat(char)`` — read the ``wow_retreat_active``
    attribute set by ``parser/wow_counsel_retreat.py::RetreatCommand``.
    Defensive against missing/corrupt attributes JSON.

Per design v1.0 §4.1 ("Authorizing an attack-first action +1 per
instance") combined with the May 23 handoff scope decision
("Killing a sentient enemy −1 Weight per casualty, capped at −3
per fight for the responsible Jedi"), this module implements the
**kill-credit reading**, which is the more conservative and more
mechanically anchored of the two readings. The handoff text is
the canonical scope; the design doc is the canonical caps.

Note that the design speaks in terms of "casualty" and "the
responsible Jedi". Responsibility here = the combatant
identified by ``Combatant.last_attacker_id`` on the dead NPC.
That attribution chain is the same one used by
``engine.death.on_pc_death`` for BH-Guild insurance, so a single
source of truth governs both bounty mechanics and Weight
mechanics.

Note: this is the runtime hook for the killing path only.
Combat-zone fatigue, civilian casualties, surrendering enemies,
and the other §4 triggers ship in later WoW.3 sub-drops once
their substrate hooks exist (e.g. there's no surrender mechanic
yet to detect "killed an enemy who was surrendering").
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


# Per design §4.1 (the handoff scope reading): per-fight cap on
# kill-credit Weight for a single Jedi. Subsequent kills in the
# same fight do NOT accrue Weight numerically — Director AI may
# still acknowledge them narratively post-launch.
KILL_CREDIT_PER_KILL = 1
KILL_CREDIT_PER_FIGHT_CAP = 3

# Trigger type label written to the weight_of_war_events log.
# Keep this consistent across calls so post-launch +history
# weight can group "combat_kill" events together.
_TRIGGER_TYPE = "combat_kill"


# ─────────────────────────────────────────────────────────────────
# Retreat state — read from char.attributes JSON
# ─────────────────────────────────────────────────────────────────

_RETREAT_ATTR_KEY = "wow_retreat_active"

# Standard refusal text used by every command that gates on
# retreat. Centralizing here means a single edit changes the
# message for all gated surfaces (attack, challenge, accept, ...).
RETREAT_REFUSAL_MESSAGE = (
    "  You have withdrawn from active duty. To take "
    "up arms again, end your retreat with +return."
)


def is_in_retreat(char: dict) -> bool:
    """Return True iff this character is currently in WoW retreat.

    The retreat flag is stored in the character's ``attributes``
    JSON blob (set by ``RetreatCommand``, cleared by
    ``ReturnCommand``). The flag is opt-in — characters that
    never call ``+retreat`` always return False here.

    Defensive against:
      - ``char`` being None or non-dict → False
      - ``attributes`` missing or non-string → False
      - JSON corruption → False (logged at debug)
      - The attribute being set to anything falsy → False
    """
    if not isinstance(char, dict):
        return False
    raw = char.get("attributes")
    if not raw:
        return False
    if isinstance(raw, dict):
        return bool(raw.get(_RETREAT_ATTR_KEY))
    if not isinstance(raw, str):
        return False
    try:
        attrs = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        log.debug(
            "[wow_combat_hooks] is_in_retreat: malformed "
            "attributes JSON for char id=%s",
            char.get("id"), exc_info=True,
        )
        return False
    if not isinstance(attrs, dict):
        return False
    return bool(attrs.get(_RETREAT_ATTR_KEY))


async def refuse_if_in_retreat(ctx) -> bool:
    """Shared retreat-refusal gate for combat-initiation commands.

    Returns True if the command should abort (the refusal line
    has already been sent to the session). Returns False if the
    command should continue normally.

    Used by AttackCommand, ChallengeCommand, AcceptCommand —
    every surface that initiates ground combat against another
    actor. Dodge/parry/flee and other in-combat actions are NOT
    gated: a Jedi mid-fight who declared retreat fights to finish.

    Dual gate (defense in depth): refuses only when both
    ``is_jedi_pc(char)`` AND ``is_in_retreat(char)`` are true.
    Non-Jedi with the flag set (data anomaly or admin toggle)
    are not gated — the retreat surface in
    ``parser/wow_counsel_retreat.py`` is is_jedi_pc-gated at
    issuance, so the flag should never appear on a non-Jedi.
    The duplicate check makes the gate symmetric with the
    issuance check.

    Fail-soft: any exception logs at debug and returns False
    (i.e. allow the command to proceed). The retreat gate must
    never block a fight by virtue of breaking; the safer wrong
    answer is "let them attack."
    """
    try:
        sess = getattr(ctx, "session", None)
        char = getattr(sess, "character", None) if sess else None
        if not char:
            return False
        # Late import to keep this module's import graph light.
        from engine.weight_of_war import is_jedi_pc
        if not is_jedi_pc(char):
            return False
        if not is_in_retreat(char):
            return False
        # Both gates fired — send the refusal and signal abort.
        await sess.send_line(RETREAT_REFUSAL_MESSAGE)
        return True
    except Exception:
        log.debug(
            "[wow_combat_hooks] refuse_if_in_retreat failed; "
            "allowing command to proceed", exc_info=True,
        )
        return False


# ─────────────────────────────────────────────────────────────────
# Per-fight kill credit
# ─────────────────────────────────────────────────────────────────

# Internal attribute name stamped on the CombatInstance to track
# which (jedi_id, npc_id) pairs have already been credited and
# how much Weight has been credited to each Jedi so far in this
# fight. Stashing state on the instance object (rather than a
# module-level dict) means it's garbage-collected with the
# combat — no leak when CombatInstance is dropped from
# _active_combats.
_CREDITS_ATTR = "_wow_kill_credits"
_TOTAL_ATTR = "_wow_kill_totals"


def _get_credits(combat) -> set:
    """Return the set of (jedi_id, npc_id) pairs already credited
    in this fight. Lazily initialized on the instance."""
    s = getattr(combat, _CREDITS_ATTR, None)
    if s is None:
        s = set()
        setattr(combat, _CREDITS_ATTR, s)
    return s


def _get_totals(combat) -> dict:
    """Return the per-Jedi totals dict {jedi_id: weight_credited}
    for this fight. Lazily initialized."""
    d = getattr(combat, _TOTAL_ATTR, None)
    if d is None:
        d = {}
        setattr(combat, _TOTAL_ATTR, d)
    return d


async def credit_kill_for_jedi(
    db, combat, jedi_char: dict, npc_id: int,
    *, now: Optional[float] = None,
) -> int:
    """Credit a Jedi PC with Weight for killing an NPC.

    Idempotent on (jedi_id, npc_id): calling twice for the same
    pair returns 0 the second time. Per-fight cap is
    ``KILL_CREDIT_PER_FIGHT_CAP`` (default 3); once a Jedi has
    been credited that much Weight in this fight, subsequent
    kills are tracked-but-no-op.

    Returns the actual Weight delta applied (typically 1, or 0
    if duplicate/capped/non-Jedi).

    Fail-soft: any unexpected error returns 0 and logs at debug.
    The combat loop must never crash on a Weight hook.
    """
    try:
        # Gate: must be a Jedi PC. Non-Jedi PCs don't accrue
        # Weight from kills — the substrate is Jedi-only by
        # design §2.
        from engine.weight_of_war import is_jedi_pc, accrue_weight
        if not is_jedi_pc(jedi_char):
            return 0
        jedi_id = jedi_char.get("id")
        if jedi_id is None:
            return 0
        if npc_id is None:
            return 0

        # Dedupe on the pair. A target that bleeds out over
        # multiple rounds should still only credit the killing
        # Jedi once.
        pair = (int(jedi_id), int(npc_id))
        credits = _get_credits(combat)
        if pair in credits:
            return 0
        credits.add(pair)

        # Per-fight cap check.
        totals = _get_totals(combat)
        already = totals.get(int(jedi_id), 0)
        if already >= KILL_CREDIT_PER_FIGHT_CAP:
            log.debug(
                "[wow_combat_hooks] per-fight kill credit cap "
                "reached for Jedi %s (already=%d); "
                "subsequent kill on npc %s is narratively "
                "acknowledged but not scored.",
                jedi_id, already, npc_id,
            )
            return 0

        # Compute the delta to actually request from the
        # substrate. Per-kill is 1, but if a single call would
        # push us past the fight cap (it can't with current
        # constants, but the math is here for safety) we clamp.
        headroom = KILL_CREDIT_PER_FIGHT_CAP - already
        request = min(KILL_CREDIT_PER_KILL, headroom)

        # Delegate to the substrate. accrue_weight enforces the
        # weekly cap and the global 200 hard cap; this hook only
        # enforces the per-fight cap. accrue_weight returns the
        # actual delta applied (could be 0 if the weekly cap is
        # already hit elsewhere).
        applied = await accrue_weight(
            db,
            char_id=int(jedi_id),
            delta=request,
            trigger_type=_TRIGGER_TYPE,
            description=(
                f"Killed NPC {npc_id} in ground combat "
                f"(room {getattr(combat, 'room_id', '?')})."
            ),
            now=now,
        )
        # Track what actually landed against the per-fight cap.
        # If accrue_weight returned 0 (weekly cap reached or
        # already at WEIGHT_MAX), we don't bump the per-fight
        # tally — the per-fight cap should reflect *credited*
        # Weight, not *attempted* Weight.
        if applied > 0:
            totals[int(jedi_id)] = already + applied
        return applied
    except Exception:
        log.debug(
            "[wow_combat_hooks] credit_kill_for_jedi failed "
            "(safe default = 0)", exc_info=True,
        )
        return 0
