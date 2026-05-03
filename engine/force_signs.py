# -*- coding: utf-8 -*-
"""
engine/force_signs.py — Force-sign trigger seam (PG.3.gates.b).

Per ``progression_gates_and_consequences_design_v1.md`` §2.3 and §2.4:

  - After the 50-hour playtime gate is cleared, characters
    accumulate Force-signs through ambient play. Once
    ``force_signs_accumulated >= 5``, the Hermit NPC appears and
    invites the character to the Village (Act 1 unlock).

  - Predisposition (set at chargen, see PG.3.gates.a) controls how
    fast signs accrue post-gate. High predisposition → 5 signs in
    ~10 hours of play. Low predisposition → ~30 hours of play.

  - Pre-gate (i.e. before 50 hours of playtime), no Force-signs
    fire — playtime is the hard gate. Predisposition still affects
    *flavor density* (vivid dreams, déjà vu) during this phase, but
    that's a separate Director concern; this module only deals with
    the mechanical sign counter.

This module ships the **engine seam**, not the content wiring.

  - Pure helpers: ``maybe_emit_force_sign``,
    ``get_force_sign_state``, ``has_received_invitation``.
  - Tunables exposed as module constants so PG.4.polish can move
    them to era.yaml without touching call sites.

What's deferred to the Village quest engine drop (separate session):

  - Wiring ``force_sign_seeds`` from
    ``data/worlds/clone_wars/quests/jedi_village.yaml`` into the
    trigger seam (those seeds describe content sites — shrine
    rooms, lucky-dodge combat resolutions, rest dreams — but the
    quest engine that consumes them doesn't exist yet).
  - The Hermit NPC AI flow that runs when a character hits 5 signs.
  - Updating the Village YAML's ``prerequisites`` block to drop the
    chargen-Track-A language now that the FS checkbox is gone.

Until that drop ships, this module is consultable but inert in
terms of player-facing effect — the counter increments correctly,
``has_received_invitation`` flips at 5, but no Hermit NPC reacts.
That's deliberate: this drop is the foundation; the Village quest
engine is a future drop that uses it.

See PG.3.gates.b's tick handler ``maybe_emit_force_sign_tick`` in
``server/tick_handlers_progression.py`` for the per-character
periodic check this module powers.
"""
from __future__ import annotations

import logging
import random
from typing import Mapping, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tunables — can move to era.yaml in PG.4.polish
# ─────────────────────────────────────────────────────────────────────────────

# Number of Force-signs required before the Hermit invitation fires.
# Per design §2.3, this is unchanged from the existing Village design.
FORCE_SIGNS_FOR_INVITATION: int = 5

# Per-tick base probability that a sign fires for an eligible character,
# when called by the periodic trigger seam. The expected value is tuned
# so that at predisposition=0.0 a player accrues ~1 sign per ~6 hours
# of play, and at predisposition=1.0, ~1 sign per ~2 hours of play.
#
# Reasoning on the cadence:
#   - Tick handler runs every 60s (the playtime heartbeat does too).
#   - Base p = 0.0028 → expected 1 sign per ~360 ticks (6h) at p_d=0.
#   - At p_d=1.0 we triple via the predisposition multiplier, giving
#     ~1 sign per ~2h.
#   - At 5 signs to invitation, total post-gate time-to-invitation
#     ranges from ~10h (p_d=1.0) to ~30h (p_d=0.0), matching design §2.4.
#
# Tunable; the design itself calls for tuning from observed conversion data.
BASE_SIGN_PROBABILITY_PER_TICK: float = 0.0028

# Predisposition multiplier scaling. Multiplier = 1.0 + (p_d * scale).
# scale=2.0 → p_d=0.0 keeps base, p_d=1.0 triples. p_d=0.5 doubles.
PREDISPOSITION_SCALING: float = 2.0


# ─────────────────────────────────────────────────────────────────────────────
# Read-only state helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_force_sign_state(char: Mapping) -> dict:
    """Summarize a character's Force-sign progression in one dict.

    Useful for admin/debug commands and Director consultation. All
    values are read-only snapshots; nothing here mutates state.

    Args:
        char: a character dict (must include ``play_time_seconds``,
            ``force_predisposition``, ``force_signs_accumulated``).
            Missing fields default safely.

    Returns:
        dict with keys:
          - ``play_time_seconds``     int
          - ``predisposition``        float (0.0–1.0)
          - ``signs_accumulated``     int
          - ``signs_required``        int (= FORCE_SIGNS_FOR_INVITATION)
          - ``gate_passed``           bool (50-hour playtime gate)
          - ``invitation_received``   bool (signs >= threshold)
          - ``effective_probability`` float (per-tick p when eligible)
    """
    from engine.jedi_gating import is_force_gate_passed

    pt = int(char.get("play_time_seconds") or 0)
    pd = float(char.get("force_predisposition") or 0.0)
    signs = int(char.get("force_signs_accumulated") or 0)

    return {
        "play_time_seconds": pt,
        "predisposition": pd,
        "signs_accumulated": signs,
        "signs_required": FORCE_SIGNS_FOR_INVITATION,
        "gate_passed": is_force_gate_passed(char),
        "invitation_received": signs >= FORCE_SIGNS_FOR_INVITATION,
        "effective_probability": _effective_probability(pd),
    }


def has_received_invitation(char: Mapping) -> bool:
    """True iff this character has accumulated enough Force-signs to
    have been invited to the Village (Act 1 trigger).

    Pure read of ``force_signs_accumulated``; does not check whether
    the Hermit NPC has actually fired the invitation dialog (that's
    the future Village quest engine's job).
    """
    signs = char.get("force_signs_accumulated")
    if signs is None:
        return False
    try:
        return int(signs) >= FORCE_SIGNS_FOR_INVITATION
    except (TypeError, ValueError):
        return False


def _effective_probability(predisposition: float) -> float:
    """Compute the per-tick sign probability for a given predisposition.

    Returns BASE * (1 + predisposition * PREDISPOSITION_SCALING),
    clamped to [0, 1] for safety. Pure function; module-level so
    tests can verify the math without mocking RNG.
    """
    pd = max(0.0, min(1.0, float(predisposition)))
    multiplier = 1.0 + (pd * PREDISPOSITION_SCALING)
    return min(1.0, max(0.0, BASE_SIGN_PROBABILITY_PER_TICK * multiplier))


# ─────────────────────────────────────────────────────────────────────────────
# Trigger seam — the per-tick check
# ─────────────────────────────────────────────────────────────────────────────

# Sentinel return values for maybe_emit_force_sign so callers can
# distinguish "didn't fire" from "fired" from "ineligible / already
# invited" without inspecting state separately.
class SignOutcome:
    NOT_ELIGIBLE_PRE_GATE   = "pre_gate"
    ALREADY_INVITED         = "already_invited"
    ROLLED_NO_SIGN          = "no_sign"
    SIGN_EMITTED            = "sign"
    SIGN_THRESHOLD_HIT      = "invitation_unlocked"


async def maybe_emit_force_sign(
    db,
    char_id: int,
    char: Optional[Mapping] = None,
    *,
    rng: Optional[random.Random] = None,
) -> str:
    """Roll once for a Force-sign for the given character.

    Caller decides the cadence (typically the per-minute progression
    tick). This function is responsible for:

      1. Eligibility — character has cleared the 50-hour gate.
      2. Saturation  — character has not already received the
         invitation (signs >= FORCE_SIGNS_FOR_INVITATION).
      3. Probabilistic roll — base * predisposition multiplier.
      4. Atomic increment of ``force_signs_accumulated`` on success.
      5. Threshold detection — if this sign hits the invitation
         threshold exactly, return the corresponding sentinel so
         the caller can fire the Hermit invitation flow.

    Args:
        db: connected ``db.database.Database``.
        char_id: PC character row id.
        char: optional character dict snapshot. If None, the function
            will fetch the row itself; passing a dict avoids the
            roundtrip when the caller already has it cached.
        rng: optional ``random.Random`` instance for deterministic
            tests. Defaults to the stdlib singleton.

    Returns:
        One of the SignOutcome sentinels.
    """
    if char is None:
        rows = await db._db.execute_fetchall(
            "SELECT play_time_seconds, force_predisposition, "
            "force_signs_accumulated FROM characters WHERE id = ?",
            (char_id,),
        )
        if not rows:
            log.warning(
                "maybe_emit_force_sign: char_id=%d not found", char_id,
            )
            return SignOutcome.NOT_ELIGIBLE_PRE_GATE
        char = dict(rows[0])

    # 1. Eligibility — the 50-hour gate must have closed for sign
    #    rolls to even occur. Pre-gate, predisposition only affects
    #    Director flavor density (handled elsewhere).
    from engine.jedi_gating import is_force_gate_passed
    if not is_force_gate_passed(char):
        return SignOutcome.NOT_ELIGIBLE_PRE_GATE

    # 2. Saturation — once invited, no further signs roll. The
    #    invitation is the trigger; the post-invitation Village quest
    #    has its own state machine and doesn't need more signs.
    signs = int(char.get("force_signs_accumulated") or 0)
    if signs >= FORCE_SIGNS_FOR_INVITATION:
        return SignOutcome.ALREADY_INVITED

    # 3. Probabilistic roll.
    pd = float(char.get("force_predisposition") or 0.0)
    p = _effective_probability(pd)
    r = (rng or random).random()
    if r >= p:
        return SignOutcome.ROLLED_NO_SIGN

    # 4. Atomic increment.
    await db._db.execute(
        "UPDATE characters SET force_signs_accumulated = "
        "force_signs_accumulated + 1 WHERE id = ?",
        (char_id,),
    )
    await db._db.commit()
    new_count = signs + 1

    log.info(
        "[force_signs] char_id=%d emitted sign #%d (p=%.4f, pd=%.2f)",
        char_id, new_count, p, pd,
    )

    # 5. Threshold detection.
    if new_count >= FORCE_SIGNS_FOR_INVITATION:
        return SignOutcome.SIGN_THRESHOLD_HIT
    return SignOutcome.SIGN_EMITTED
