"""Field Kit Drop D' — canonical combat_resolution_event factory.

Per ``combat_mechanics_display_design_v1.1.md`` §6 (engine emission point),
every successful or unsuccessful combat resolution emits a structured
event carrying the full mechanics breakdown the existing two-line
narrative throws away. The web client renders this as a collapsible
inspector panel attached to each combat outcome row. Telnet output is
unchanged — telnet sessions continue to receive the existing two-line
story+mechanics narrative via ``send_line`` / ``broadcast_to_room``,
and the combat_resolution_event is a parallel emission that telnet
ignores.

What this fixes
---------------
Pre-Drop-D' combat output displayed only:

    ▸ Tundra blasts Yenn with blaster — HIT — Wounded!
      (Roll: 17 vs 11 · Damage 14 vs Soak 8 → Wounded)

Most of the data underpinning that sentence — per-die values, the
Wild Die explosion chain, the soak component breakdown, the
provenance of each die in the attacker's pool, the difficulty
breakdown — was computed and then discarded. Drop D' stops
discarding it.

Per the §33 web-first directive (architecture v37), the constraint
that forced the cut (telnet readability) no longer applies on the web
client. Telnet still gets the two-line text; web gets the structured
event.

Schema reconciliation
---------------------
The factory emits the v1.1 schema in ``combat_mechanics_display_design_v1.1.md``
§4. Top-level message type is ``combat_resolution_event`` (not an
extension of ``pose_event`` — see Q1 confirmation in the design).

Three modifications from v1 are folded in here:

1. Per-die ``source`` tag (Q2 mod): every die in the attacker/defender/
   damage pools carries a single-field source enum
   ("skill" | "weapon" | "modifier" | "fp_double") so the inspector
   can group dice visually. Source provenance is composed at this
   factory layer rather than being threaded through ``engine/dice.py``
   (which the Drop D' design explicitly preserves — AC14).
2. Stun-mode 5-way ``outcome_type`` enum: the v1 ``stun_only:bool``
   shape couldn't represent the stun-knockout routing at
   ``engine/combat.py:1186`` ("more serious than stunned" →
   "Stunned — Unconscious!"). v1.1 promotes outcome resolution to a
   discriminated union with the new ``stun_unconscious`` outcome.
3. Telnet ``/verbose`` deferred entirely (Q4 mod): no opt-in toggle.
   Telnet stays at the two-line output; admin debug needs are out of
   scope for D'.

Per-die source provenance composition
-------------------------------------
The combat resolver builds the attacker's pool as
``skill + weapon_bonus + fp_double + modifiers`` with explicit
component sizes. ``RollResult.normal_dice`` is just a flat list of
ints — provenance is composed at the call site by knowing how many
dice came from each component. ``build_attacker_pool_roll()`` accepts
the component sizes and zips them with the rolled dice to produce
the ``source`` list.

What this does NOT cover
------------------------
- Any change to ``engine/dice.py`` — the dice engine API is preserved
  (AC14). All provenance is composed at this layer.
- The 2D stun-duration roll for the "Stunned — Unconscious!" case —
  that's a separate engine ticket per design v1.1 §11. The schema
  reserves ``stun_duration_dice`` / ``stun_duration_unit`` fields;
  this factory leaves them ``None`` until the engine starts emitting
  the duration roll.
- The actual 250ms client-side dedup against the legacy two-line
  narrative — that's a client-side concern and lives in
  ``static/client.html``'s ``handleCombatResolutionEvent``.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Optional, Sequence


# ─────────────────────────────────────────────────────────────────────
# Constants — die sources, outcome types
# ─────────────────────────────────────────────────────────────────────
#
# Source enum for per-die provenance. Single string field per die so
# the wire format stays flat (Q2 mod — see design v1.1 §4.1).

SOURCE_SKILL     = "skill"      # actor's skill rating (e.g. blaster 4D)
SOURCE_WEAPON    = "weapon"     # weapon's bonus damage dice
SOURCE_MODIFIER  = "modifier"   # situational modifier rolled-add (rare)
SOURCE_FP_DOUBLE = "fp_double"  # extra dice from Force Point doubling

VALID_SOURCES = (SOURCE_SKILL, SOURCE_WEAPON, SOURCE_MODIFIER, SOURCE_FP_DOUBLE)

# Outcome type enum (5-way discriminated union — Q2 stun-mode mod fix).
# Each event has exactly one outcome_type; populated fields in
# wound_outcome depend on which one fired.

OUTCOME_NO_DAMAGE        = "no_damage"
OUTCOME_WOUND            = "wound"
OUTCOME_STUN             = "stun"               # stun-mode, margin 1-3, applied as stun-track wound
OUTCOME_STUN_UNCONSCIOUS = "stun_unconscious"   # stun-mode, margin > 3, KO routing
OUTCOME_INCAPACITATED    = "incapacitated"      # wound caused incapacitation (incl. mortally wounded / dead)

VALID_OUTCOMES = (
    OUTCOME_NO_DAMAGE,
    OUTCOME_WOUND,
    OUTCOME_STUN,
    OUTCOME_STUN_UNCONSCIOUS,
    OUTCOME_INCAPACITATED,
)

# Soak component sources. Tracks which contributor produced which
# share of the soak total. Mirrors the breakdown in
# ``engine/combat.py`` resolve loop where soak = strength + armor
# + cp_soak (and shield in space combat).

SOAK_STRENGTH = "strength"
SOAK_ARMOR    = "armor"
SOAK_CP       = "cp_soak"
SOAK_SHIELD   = "shield"

VALID_SOAK_SOURCES = (SOAK_STRENGTH, SOAK_ARMOR, SOAK_CP, SOAK_SHIELD)

# Schema version. Bump on breaking change so the client can detect a
# protocol mismatch and refuse to render rather than silently render
# wrong data.

SCHEMA_VERSION = 1


# ─────────────────────────────────────────────────────────────────────
# Per-die descriptor builders
# ─────────────────────────────────────────────────────────────────────


def make_die(
    value: int,
    source: str,
    *,
    is_wild: bool = False,
    exploded: bool = False,
    explosion_chain: Optional[list[int]] = None,
    dropped: bool = False,
) -> dict:
    """Build a single die descriptor for the v1.1 ``dice[]`` array.

    Args:
        value: Final face value. For an exploded Wild Die this is the
            chain total (matches the convention in
            ``RollResult.wild_die.total``).
        source: One of ``VALID_SOURCES``. Identifies provenance so the
            inspector can group dice visually (Q2 mod — design v1.1
            §4.1).
        is_wild: True for the single Wild Die per pool.
        exploded: True if the Wild Die rolled 6 and exploded. The
            ``value`` here is the chain total; ``explosion_chain``
            carries the individual roll values.
        explosion_chain: Per-roll chain values when exploded. None
            otherwise. Example for a 6→5→2 chain: ``[6, 5, 2]``.
        dropped: True if removed by complication (Wild Die rolled 1
            and the highest normal die was discarded). The ``value``
            for a dropped die is the original face value before
            removal, kept for inspector display.

    Returns:
        Dict matching the ``dice[]`` element shape in design v1.1 §4.

    Raises:
        ValueError: if ``source`` is not in ``VALID_SOURCES``.
    """
    if source not in VALID_SOURCES:
        raise ValueError(
            f"Unknown die source {source!r}; "
            f"expected one of {VALID_SOURCES}"
        )
    return {
        "value": int(value),
        "is_wild": bool(is_wild),
        "exploded": bool(exploded),
        "explosion_chain": list(explosion_chain) if explosion_chain else None,
        "source": source,
        "dropped": bool(dropped),
    }


def build_dice_pool_roll(
    pool_text: str,
    pool_dice: int,
    pool_pips: int,
    total: int,
    dice: Sequence[dict],
    *,
    complication: bool = False,
    exploded: bool = False,
    removed_die_value: Optional[int] = None,
    cp_spent: int = 0,
    cp_rolls: Optional[Sequence[int]] = None,
    cp_bonus: int = 0,
) -> dict:
    """Build a ``DicePoolRoll`` payload (design v1.1 §4 schema).

    The factory accepts pre-tagged ``dice[]`` entries (each built via
    ``make_die()`` so source provenance is preserved) and assembles
    the surrounding metadata.

    Note that ``pips_added`` in the wire format mirrors ``pool_pips``
    explicitly so the client never has to back-derive it from
    ``pool_text``. They will always agree, but the explicit field
    avoids ambiguity if ``pool_text`` is ever serialized in a
    non-canonical form.

    Args:
        pool_text: Display string for the pool (e.g. "5D+2").
        pool_dice: Number of dice in the pool.
        pool_pips: Pip bonus on the pool.
        total: Final summed total (matches ``RollResult.total``).
        dice: Per-die descriptor list (each from ``make_die``).
        complication: ``RollResult.complication``.
        exploded: ``RollResult.exploded``.
        removed_die_value: ``RollResult.removed_die`` (the dropped
            normal die value when a complication fired; ``None``
            otherwise).
        cp_spent: Character Points the actor spent on this roll
            (attacker side). 0 for the defender.
        cp_rolls: Per-die rolled values from CP spending (CP dice
            explode on 6 with no mishap; see ``engine/dice.py``).
        cp_bonus: Total contribution from CP dice.

    Returns:
        Dict matching the ``DicePoolRoll`` shape in design v1.1 §4.
    """
    return {
        "pool_text": pool_text,
        "pool_dice": int(pool_dice),
        "pool_pips": int(pool_pips),
        "total": int(total),
        "dice": list(dice),
        "pips_added": int(pool_pips),
        "complication": bool(complication),
        "exploded": bool(exploded),
        "removed_die_value": removed_die_value,
        "cp_spent": int(cp_spent),
        "cp_rolls": list(cp_rolls) if cp_rolls else [],
        "cp_bonus": int(cp_bonus),
    }


# ─────────────────────────────────────────────────────────────────────
# Per-die source list construction (the central Q2 modification)
# ─────────────────────────────────────────────────────────────────────


def compose_pool_dice(
    roll_result,
    component_sizes: Iterable[tuple[str, int]],
) -> list[dict]:
    """Build the per-die ``dice[]`` array from a RollResult plus a
    component-size sequence describing pool provenance.

    The dice engine returns ``RollResult.normal_dice`` as a flat
    list of ints. The combat resolver knows how the pool was
    composed (skill + weapon + fp_double + modifier) but doesn't
    surface that to the dice engine. This helper bridges the two
    by zipping the flat dice list against a sequence of
    (source, count) pairs supplied by the caller.

    The Wild Die — ``RollResult.wild_die`` — is appended last with
    ``is_wild=True`` and source defaulting to the *first* component
    in ``component_sizes`` (which is conventionally "skill" — the
    Wild Die is part of the skill component per WEG D6 R&E). If a
    pool has no skill component (rare; e.g. raw weapon damage on a
    power-pack-only weapon), the Wild Die source falls back to
    "skill" anyway as the canonical convention.

    Complications and explosion chains are read off the RollResult
    and applied to the relevant die descriptors:

      - Exploded Wild Die: ``exploded=True`` and ``explosion_chain``
        is set to ``wild_die.rolls``; ``value`` is the chain total.
      - Complication: ``RollResult.removed_die`` is appended as a
        dropped normal die with ``dropped=True``. The Wild Die
        itself is rendered with ``value=0`` (matching the engine's
        "Wild Die = 0 AND highest normal die removed" semantics).

    Args:
        roll_result: A ``RollResult`` from ``engine.dice.roll_d6_pool``.
        component_sizes: Sequence of ``(source, count)`` tuples
            describing pool provenance. Sum of counts must equal
            ``len(normal_dice)`` (the Wild Die is handled separately).
            Example for a 5D pool composed as 4D skill + 1D fp_double:
            ``[("skill", 3), ("fp_double", 1)]`` — only 4 normal dice
            because the 5th is the Wild Die.

    Returns:
        List of die descriptors ready to pass to
        ``build_dice_pool_roll(..., dice=...)``.

    Raises:
        ValueError: if the component sizes don't sum to the count of
            normal dice, indicating a provenance bookkeeping bug at
            the call site.
    """
    component_sizes = list(component_sizes)
    if not component_sizes:
        # Defensive: empty pool (e.g. someone declared an action with
        # 0D skill). Return empty list; caller's RollResult.total will
        # be 0 + pips so the inspector still has something to show.
        if roll_result.normal_dice:
            raise ValueError(
                "compose_pool_dice: component_sizes empty but "
                f"normal_dice has {len(roll_result.normal_dice)} entries"
            )
        return []

    expected_normal = sum(count for _, count in component_sizes)
    if expected_normal != len(roll_result.normal_dice):
        raise ValueError(
            f"compose_pool_dice: component_sizes sum to {expected_normal} "
            f"but normal_dice has {len(roll_result.normal_dice)} entries — "
            "provenance bookkeeping bug at the call site"
        )

    dice: list[dict] = []
    cursor = 0
    for source, count in component_sizes:
        if source not in VALID_SOURCES:
            raise ValueError(
                f"compose_pool_dice: unknown source {source!r}; "
                f"expected one of {VALID_SOURCES}"
            )
        for _ in range(count):
            value = roll_result.normal_dice[cursor]
            dice.append(make_die(value, source, is_wild=False))
            cursor += 1

    # Append the Wild Die (always source="skill" per WEG D6 R&E
    # convention — the Wild Die is the skill's chance die).
    wild = roll_result.wild_die
    if wild is not None:
        if roll_result.complication:
            # Wild Die rolled 1 → engine sets total=0 for the wild die
            # and removes the highest normal die. The dropped die is
            # ``RollResult.removed_die``; render it as a normal-source
            # die with dropped=True so the inspector can strike it
            # through.
            wild_descriptor = make_die(
                value=0,
                source=SOURCE_SKILL,
                is_wild=True,
            )
            dice.append(wild_descriptor)
            if roll_result.removed_die is not None:
                # The dropped die — we don't know its source position
                # since the engine just picked the highest normal die.
                # Tag it as SOURCE_SKILL by convention; the inspector's
                # job is to show it as dropped, not to attribute its
                # source precisely. (A future iteration could thread
                # this through if there's UX value, but the dropped
                # die is conceptually a sacrifice, not a contributor.)
                dice.append(make_die(
                    value=roll_result.removed_die,
                    source=SOURCE_SKILL,
                    dropped=True,
                ))
        elif wild.exploded:
            # Exploded chain — value is the chain total, explosion_chain
            # carries the per-roll values.
            dice.append(make_die(
                value=wild.total,
                source=SOURCE_SKILL,
                is_wild=True,
                exploded=True,
                explosion_chain=list(wild.rolls),
            ))
        else:
            # Normal Wild Die roll, no explosion, no complication.
            dice.append(make_die(
                value=wild.total,
                source=SOURCE_SKILL,
                is_wild=True,
            ))

    return dice


# ─────────────────────────────────────────────────────────────────────
# Soak component breakdown
# ─────────────────────────────────────────────────────────────────────


def make_soak_component(
    source: str,
    label: str,
    value: int,
    *,
    rolls: Optional[Sequence[int]] = None,
) -> dict:
    """Build a single soak-component descriptor.

    Args:
        source: One of ``VALID_SOAK_SOURCES``.
        label: Human-readable label (e.g. "Strength 3D", "Armor (Padded
            Vest)", "CP Soak (3 dice)").
        value: Contribution to the soak total. For rolled components
            this is the dice subtotal; for flat components (armor as
            a fixed-pip add) this is the pip value.
        rolls: Per-die rolled values when the component was rolled.
            ``None`` for flat components.

    Returns:
        Dict matching the ``soak.components[]`` element shape in
        design v1.1 §4.

    Raises:
        ValueError: if ``source`` is not in ``VALID_SOAK_SOURCES``.
    """
    if source not in VALID_SOAK_SOURCES:
        raise ValueError(
            f"Unknown soak source {source!r}; "
            f"expected one of {VALID_SOAK_SOURCES}"
        )
    return {
        "source": source,
        "label": label,
        "value": int(value),
        "rolls": list(rolls) if rolls else None,
    }


# ─────────────────────────────────────────────────────────────────────
# Wound outcome (the Q2 stun-mode schema-gap fix lives here)
# ─────────────────────────────────────────────────────────────────────


def build_wound_outcome(
    *,
    outcome_type: str,
    display_name: str,
    wound_level_before: Optional[str] = None,
    wound_level_after: Optional[str] = None,
    wound_level_delta: int = 0,
    stun_duration_dice: Optional[str] = None,
    stun_duration_unit: Optional[str] = None,
    drama_text: Optional[str] = None,
) -> dict:
    """Build a ``WoundOutcome`` payload (design v1.1 §4 + §4.2).

    The 5-way ``outcome_type`` enum drives which other fields are
    populated. The ``stun_only`` and ``stun_unconscious`` booleans
    are derived from ``outcome_type`` so callers can't set them
    inconsistently.

    Args:
        outcome_type: One of ``VALID_OUTCOMES``.
        display_name: The wound text the existing two-line narrative
            shows in the wound slot ("Wounded", "Stunned",
            "Stunned — Unconscious!", "No Damage", etc.).
        wound_level_before: Wound level name before this outcome
            applied. ``None`` for ``no_damage``.
        wound_level_after: Wound level name after this outcome
            applied. ``None`` for ``no_damage``.
        wound_level_delta: Track delta. Positive = worsened.
        stun_duration_dice: Duration roll dice notation (e.g. "2D")
            for ``stun_unconscious``. ``None`` otherwise. The engine
            currently does not roll this — it just emits the label;
            the field is reserved for when a separate engine drop
            adds the duration roll. See design v1.1 §11.
        stun_duration_unit: "rounds" or "minutes" — see the WEG
            fidelity question in design v1.1 §11.
        drama_text: Optional drama narration the engine produces for
            severe wounds.

    Returns:
        Dict matching the ``WoundOutcome`` shape in design v1.1 §4.

    Raises:
        ValueError: if ``outcome_type`` is invalid, or if duration
            fields are populated for non-stun-unconscious outcomes.
    """
    if outcome_type not in VALID_OUTCOMES:
        raise ValueError(
            f"Unknown outcome_type {outcome_type!r}; "
            f"expected one of {VALID_OUTCOMES}"
        )
    if outcome_type != OUTCOME_STUN_UNCONSCIOUS and (
        stun_duration_dice is not None or stun_duration_unit is not None
    ):
        # Defensive: catch a bookkeeping bug where the caller
        # populates duration fields on a non-KO outcome. Lets us
        # tighten the schema without painful debugging when the wire
        # format diverges from the documented branch table.
        raise ValueError(
            f"stun_duration_* fields populated for outcome_type "
            f"{outcome_type!r}, expected only for "
            f"{OUTCOME_STUN_UNCONSCIOUS!r}"
        )
    if stun_duration_unit is not None and stun_duration_unit not in (
        "rounds", "minutes",
    ):
        raise ValueError(
            f"stun_duration_unit must be 'rounds' or 'minutes', "
            f"got {stun_duration_unit!r}"
        )
    return {
        "outcome_type": outcome_type,
        "display_name": display_name,
        # stun_only / stun_unconscious derived from outcome_type so
        # they cannot disagree with the discriminator.
        "stun_only": outcome_type == OUTCOME_STUN,
        "stun_unconscious": outcome_type == OUTCOME_STUN_UNCONSCIOUS,
        "wound_level_before": wound_level_before,
        "wound_level_after": wound_level_after,
        "wound_level_delta": int(wound_level_delta),
        "stun_duration_dice": stun_duration_dice,
        "stun_duration_unit": stun_duration_unit,
        "drama_text": drama_text,
    }


def classify_wound_outcome(
    *,
    hit: bool,
    stun_mode: bool,
    damage_margin: int,
    target_can_act: bool,
) -> str:
    """Decide which ``outcome_type`` enum value applies for the
    parameters the resolve loop computes.

    Mirrors the branch table in ``engine/combat.py:1186``. Kept as a
    pure function so test cases can drive it directly without
    standing up a Combatant fixture.

    Branch table (matches design v1.1 §4.2):

      hit=False                          → no_damage
      hit=True, damage_margin <= 0       → no_damage
      hit=True, stun_mode, margin 1-3    → stun
      hit=True, stun_mode, margin > 3    → stun_unconscious
      hit=True, !stun_mode, !target_can_act after wound application
                                         → incapacitated
      hit=True, !stun_mode, target_can_act
                                         → wound

    Args:
        hit: True if the attack roll cleared the difficulty / opposed
            roll. False short-circuits to no_damage.
        stun_mode: ``CombatAction.stun_mode``.
        damage_margin: ``damage_roll.total - soak_total``.
        target_can_act: Whether the target's wound level still permits
            action after the wound (or stun) was applied. The resolver
            checks ``target.wound_level.can_act`` for the
            "incapacitated" line below the narrative.

    Returns:
        One of ``VALID_OUTCOMES``.
    """
    if not hit:
        return OUTCOME_NO_DAMAGE
    if damage_margin <= 0:
        return OUTCOME_NO_DAMAGE
    if stun_mode:
        return OUTCOME_STUN_UNCONSCIOUS if damage_margin > 3 else OUTCOME_STUN
    if not target_can_act:
        return OUTCOME_INCAPACITATED
    return OUTCOME_WOUND


# ─────────────────────────────────────────────────────────────────────
# Top-level event factory
# ─────────────────────────────────────────────────────────────────────


def make_combat_resolution_event(
    *,
    actor_id: int,
    actor_name: str,
    actor_kind: str,
    is_force_point_active: bool,
    target_id: Optional[int],
    target_name: str,
    target_kind: str,
    skill: str,
    weapon_name: Optional[str],
    range_band: Optional[str],
    stun_mode: bool,
    is_opposed: bool,
    attacker_pool: dict,
    defender_pool: Optional[dict] = None,
    difficulty: Optional[dict] = None,
    damage_pool: Optional[dict] = None,
    soak: Optional[dict] = None,
    hit: bool,
    margin: int,
    damage_margin: int = 0,
    wound_outcome: dict,
    round_num: int = 0,
    combat_id: Optional[int] = None,
    timestamp_ms: Optional[int] = None,
    event_id: Optional[str] = None,
) -> dict:
    """Build the full ``combat_resolution_event`` payload.

    See design v1.1 §4 for field-by-field documentation. This factory
    is deliberately verbose with named parameters so the call site in
    ``engine/combat.py`` is self-documenting — reading the resolver
    later, you can see exactly what gets emitted without having to
    reverse-engineer a positional signature.

    The factory enforces the schema invariants from §4 / §12 (AC12):

      - ``defender_pool`` is non-None iff ``is_opposed=True``
      - ``difficulty`` is non-None iff ``is_opposed=False``
      - ``damage_pool`` and ``soak`` are non-None iff ``hit=True``
      - ``actor_kind`` and ``target_kind`` are restricted to known
        values

    Args:
        actor_id: Character or NPC id of the actor.
        actor_name: Display name of the actor.
        actor_kind: "pc" or "npc".
        is_force_point_active: Whether the actor declared a Force
            Point this round (R&E p52 doubling).
        target_id: Character / NPC / object id; None for AoE or
            environmental targets.
        target_name: Display name of the target.
        target_kind: "pc", "npc", "object", or "environment".
        skill: Skill name used for the attack ("blaster", "brawling",
            "lightsaber", etc.).
        weapon_name: Display name of the weapon, or None for unarmed.
        range_band: "close" / "short" / "medium" / "long", or None for
            melee or non-ranged.
        stun_mode: ``CombatAction.stun_mode``.
        is_opposed: True if the difficulty was rolled by the defender;
            false if it was a static target number.
        attacker_pool: The attacker's ``DicePoolRoll`` (build via
            ``build_dice_pool_roll``).
        defender_pool: The defender's ``DicePoolRoll`` for opposed
            rolls; None for static-target rolls.
        difficulty: Difficulty descriptor for static-target rolls;
            None for opposed rolls. Shape per §4: ``{"number", "label",
            "breakdown"}``.
        damage_pool: Damage ``DicePoolRoll`` when ``hit=True``; None
            otherwise.
        soak: Soak descriptor when ``hit=True``; None otherwise.
            Shape per §4: ``{"total", "components"}``.
        hit: Whether the attack hit.
        margin: ``attack_total - difficulty`` (or
            ``- defender_total`` for opposed).
        damage_margin: ``damage_total - soak_total`` (only meaningful
            on hit; pass 0 on miss).
        wound_outcome: Outcome descriptor (build via
            ``build_wound_outcome``).
        round_num: Current combat round, 0 for ad-hoc resolutions.
        combat_id: FK to ``combat_states.id`` if a tracked combat;
            None for ad-hoc.
        timestamp_ms: Override for tests. Defaults to current time.
        event_id: Override for tests. Defaults to fresh UUID4.

    Returns:
        Dict ready to pass as the ``data`` argument to
        ``session_mgr.broadcast_json_to_room(room_id,
        "combat_resolution_event", data)``.

    Raises:
        ValueError: if any of the §4 schema invariants are violated.
    """
    # Schema invariants from §4 / acceptance criteria AC12.
    if actor_kind not in ("pc", "npc"):
        raise ValueError(
            f"actor_kind must be 'pc' or 'npc', got {actor_kind!r}"
        )
    if target_kind not in ("pc", "npc", "object", "environment"):
        raise ValueError(
            f"target_kind must be one of pc/npc/object/environment, "
            f"got {target_kind!r}"
        )
    if is_opposed and defender_pool is None:
        raise ValueError(
            "is_opposed=True requires defender_pool to be populated"
        )
    if not is_opposed and defender_pool is not None:
        raise ValueError(
            "defender_pool populated but is_opposed=False — must be "
            "either an opposed roll or a static difficulty roll"
        )
    if not is_opposed and difficulty is None:
        raise ValueError(
            "is_opposed=False requires difficulty to be populated"
        )
    if is_opposed and difficulty is not None:
        raise ValueError(
            "difficulty populated but is_opposed=True — opposed rolls "
            "use defender_pool, not a static target number"
        )
    if hit and damage_pool is None:
        raise ValueError("hit=True requires damage_pool to be populated")
    if hit and soak is None:
        raise ValueError("hit=True requires soak to be populated")
    if not hit and (damage_pool is not None or soak is not None):
        raise ValueError(
            "damage_pool / soak populated but hit=False — these "
            "fields only apply when the attack lands"
        )

    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if event_id is None:
        event_id = str(uuid.uuid4())

    return {
        "msg_type": "combat_resolution_event",
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp_ms": timestamp_ms,
        "round_num": int(round_num),
        "combat_id": combat_id,
        "actor": {
            "id": int(actor_id),
            "name": actor_name,
            "kind": actor_kind,
            "is_force_point_active": bool(is_force_point_active),
        },
        "target": {
            "id": target_id,
            "name": target_name,
            "kind": target_kind,
        },
        "action": {
            "skill": skill,
            "weapon_name": weapon_name,
            "range_band": range_band,
            "stun_mode": bool(stun_mode),
            "is_opposed": bool(is_opposed),
        },
        "attacker_pool": attacker_pool,
        "defender_pool": defender_pool,
        "difficulty": difficulty,
        "damage_pool": damage_pool,
        "soak": soak,
        "hit": bool(hit),
        "margin": int(margin),
        "damage_margin": int(damage_margin),
        "wound_outcome": wound_outcome,
    }
