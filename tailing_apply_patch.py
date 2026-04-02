"""
Persistent Tailing — engine/starships.py patch
Applies three changes:
  1. resolve_space_attack gains attacker_ship_id / target_ship_id optional params
     and awards +1D attack pool when the attacker has a confirmed tail position.
  2. [TAIL +1D] tag injected into miss narrative and hit damage narratives.
  3. New EvadeResult dataclass + resolve_evade() function added before SpaceGrid.

Run from project root:
    python3 tailing_apply_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("engine", "starships.py")

# ── Patch 1 ──────────────────────────────────────────────────────────────────
# Add attacker_ship_id / target_ship_id params to resolve_space_attack
# and insert tailing bonus block.

OLD_SIGNATURE = '''\
def resolve_space_attack(
    attacker_skill: DicePool,
    weapon: ShipWeapon,
    attacker_scale: int,
    target_pilot_skill: DicePool,
    target_maneuverability: DicePool,
    target_hull: DicePool,
    target_shields: DicePool,
    target_scale: int,
    num_actions: int = 1,
    range_band: SpaceRange = SpaceRange.SHORT,
    relative_position: str = RelativePosition.FRONT,
) -> SpaceCombatResult:'''

NEW_SIGNATURE = '''\
def resolve_space_attack(
    attacker_skill: DicePool,
    weapon: ShipWeapon,
    attacker_scale: int,
    target_pilot_skill: DicePool,
    target_maneuverability: DicePool,
    target_hull: DicePool,
    target_shields: DicePool,
    target_scale: int,
    num_actions: int = 1,
    range_band: SpaceRange = SpaceRange.SHORT,
    relative_position: str = RelativePosition.FRONT,
    attacker_ship_id: int = None,
    target_ship_id: int = None,
) -> SpaceCombatResult:'''

# The unique anchor for the tailing bonus insertion point.
# We insert AFTER the multi-action penalty line and BEFORE the scale modifier comment.
OLD_AFTER_PENALTY = '''\
    attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

    # Scale modifier for to-hit'''

NEW_AFTER_PENALTY = '''\
    attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

    # Tailing bonus: +1D attack when attacker is confirmed on target's tail.
    # Requires both ship IDs so we can verify the symmetric position pair.
    tailing_bonus = False
    if (relative_position == RelativePosition.FRONT
            and attacker_ship_id is not None
            and target_ship_id is not None):
        _grid = get_space_grid()
        if _grid.get_position(target_ship_id, attacker_ship_id) == RelativePosition.REAR:
            attack_pool = DicePool(attack_pool.dice + 1, attack_pool.pips)
            tailing_bonus = True

    # Scale modifier for to-hit'''

# Also need to thread tailing_bonus into the narrative strings.
# The hit narrative and miss narrative both need a tail tag.
# Anchor: the miss narrative return (unique enough).
OLD_MISS_NARRATIVE = '''\
    if not result.hit:
        result.narrative = (
            f"  Shot misses at {range_label} range! "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total}) "
            f"= {total_difficulty})"
        )
        return result'''

NEW_MISS_NARRATIVE = '''\
    if not result.hit:
        tail_tag = " [TAIL +1D]" if tailing_bonus else ""
        result.narrative = (
            f"  Shot misses at {range_label} range!{tail_tag} "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total}) "
            f"= {total_difficulty})"
        )
        return result'''

# ── Patch 2 ──────────────────────────────────────────────────────────────────
# Inject tailing_bonus tag into hit damage narratives.
# Anchor: the 'else:' block that starts the physical damage chain — unique in file.
# We prepend a _tail_tag variable and thread it into the Light/Heavy/Severe/Destroyed
# narratives (the non-absorbed branches that actually represent a damaging hit).

OLD_PHYSICAL_DAMAGE = '''\
    else:
        # Physical damage
        if margin <= 0:
            result.narrative = (
                f"  Hit absorbed by shields/hull. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
            )
        elif margin <= 5:
            result.hull_damage = 1
            result.systems_hit = ["shields"]
            result.narrative = (
                f"  Light hit! Shields damaged. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 10:
            result.hull_damage = 2
            import random
            system = random.choice(["engines", "weapons", "shields", "sensors"])
            result.systems_hit = [system]
            result.narrative = (
                f"  Heavy hit! {system.title()} damaged! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 15:
            result.hull_damage = 4
            result.systems_hit = ["engines", "weapons"]
            result.narrative = (
                f"  Severe damage! Multiple systems hit! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        else:
            result.hull_damage = 99
            result.narrative = (
                f"  DESTROYED! Hull breach! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )'''

NEW_PHYSICAL_DAMAGE = '''\
    else:
        # Physical damage
        _tail_tag = " [TAIL +1D]" if tailing_bonus else ""
        if margin <= 0:
            result.narrative = (
                f"  Hit absorbed by shields/hull. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
            )
        elif margin <= 5:
            result.hull_damage = 1
            result.systems_hit = ["shields"]
            result.narrative = (
                f"  Light hit!{_tail_tag} Shields damaged. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 10:
            result.hull_damage = 2
            import random
            system = random.choice(["engines", "weapons", "shields", "sensors"])
            result.systems_hit = [system]
            result.narrative = (
                f"  Heavy hit!{_tail_tag} {system.title()} damaged! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 15:
            result.hull_damage = 4
            result.systems_hit = ["engines", "weapons"]
            result.narrative = (
                f"  Severe damage!{_tail_tag} Multiple systems hit! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        else:
            result.hull_damage = 99
            result.narrative = (
                f"  DESTROYED!{_tail_tag} Hull breach! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )'''

# ── Patch 3 ──────────────────────────────────────────────────────────────────
# Add EvadeResult dataclass and resolve_evade() function.
# Injected right before the SpaceGrid class definition (unique anchor).

EVADE_INJECTION_ANCHOR = '''\
class SpaceGrid:'''

EVADE_CODE = '''\
# ── Evade Resolution ─────────────────────────────────────────────────────────

@dataclass
class EvadeResult:
    """Result of an evasive maneuver attempt."""
    success: bool = False
    roll_total: int = 0
    difficulty: int = 0
    all_tails_broken: bool = False
    narrative: str = ""


def resolve_evade(
    pilot_skill: DicePool,
    maneuverability: DicePool,
    engine_state: str = "working",
    num_actions: int = 1,
) -> EvadeResult:
    """
    Resolve an evasive maneuver roll (Persistent Tailing / Priority B).

    The pilot throws the ship into violent evasive maneuvers, attempting to
    break ALL tail locks simultaneously.  Uses pilot skill + ship maneuverability
    vs a Moderate (10) base difficulty.

    Engine damage modifiers (Star Warriors Section 17 adaptation):
      - 'damaged'   → +5 difficulty
      - 'destroyed' → impossible; auto-fail with flavour narrative

    On success, all position pairs involving this ship are reset to FRONT by
    the caller (EvadeCommand reads all_tails_broken and clears the SpaceGrid).
    """
    result = EvadeResult()

    # Destroyed engines: cannot maneuver at all
    if engine_state == "destroyed":
        result.narrative = (
            "  Engines destroyed — evasive maneuvers impossible! "
            "You're a sitting duck."
        )
        return result

    # Build difficulty
    base_diff = 10
    engine_penalty = 5 if engine_state == "damaged" else 0
    result.difficulty = base_diff + engine_penalty

    # Build pilot pool: skill + ship maneuverability
    pool = DicePool(
        pilot_skill.dice + maneuverability.dice,
        pilot_skill.pips + maneuverability.pips,
    )
    pool = apply_multi_action_penalty(pool, num_actions)

    roll = roll_d6_pool(pool)
    result.roll_total = roll.total

    engine_note = " (damaged engines +5)" if engine_penalty else ""
    diff_display = f"{result.difficulty}{engine_note}"

    if roll.total >= result.difficulty:
        result.success = True
        result.all_tails_broken = True
        result.narrative = (
            f"  Evasive maneuvers successful! All pursuit positions broken. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
    else:
        result.narrative = (
            f"  Evasive maneuvers failed — still being tailed! "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )

    return result


class SpaceGrid:'''


def apply_patches(src: str) -> str:
    out = src

    # Patch 1a: signature
    if OLD_SIGNATURE not in out:
        raise ValueError("Patch 1a anchor not found (resolve_space_attack signature)")
    out = out.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)

    # Patch 1b: tailing bonus block
    if OLD_AFTER_PENALTY not in out:
        raise ValueError("Patch 1b anchor not found (after apply_multi_action_penalty)")
    out = out.replace(OLD_AFTER_PENALTY, NEW_AFTER_PENALTY, 1)

    # Patch 1c: miss narrative tail tag
    if OLD_MISS_NARRATIVE not in out:
        raise ValueError("Patch 1c anchor not found (miss narrative)")
    out = out.replace(OLD_MISS_NARRATIVE, NEW_MISS_NARRATIVE, 1)

    # Patch 2: hit damage tail tag
    if OLD_PHYSICAL_DAMAGE not in out:
        print("  NOTE: Physical damage chain anchor not found — skipping hit tag patch.")
        print("        The tailing bonus dice will still apply; only the tag is absent.")
    else:
        out = out.replace(OLD_PHYSICAL_DAMAGE, NEW_PHYSICAL_DAMAGE, 1)

    # Patch 3: EvadeResult + resolve_evade injection
    if EVADE_INJECTION_ANCHOR not in out:
        raise ValueError("Patch 3 anchor not found (class SpaceGrid)")
    out = out.replace(EVADE_INJECTION_ANCHOR, EVADE_CODE, 1)

    return out


def main():
    if not os.path.exists(TARGET):
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"Read {len(src)} bytes from {TARGET}")

    try:
        patched = apply_patches(src)
    except ValueError as e:
        print(f"PATCH FAILED: {e}")
        sys.exit(1)

    # Syntax check
    try:
        ast.parse(patched)
        print("Syntax check: PASSED")
    except SyntaxError as e:
        print(f"SYNTAX ERROR after patching: {e}")
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"Patched {TARGET} successfully.")
    print()
    print("Changes applied:")
    print("  1. resolve_space_attack: +attacker_ship_id / target_ship_id params")
    print("  2. resolve_space_attack: +1D tailing bonus when on confirmed tail")
    print("  3. resolve_space_attack: [TAIL +1D] tag in miss + hit damage narratives")
    print("  4. EvadeResult dataclass + resolve_evade() added before SpaceGrid")


if __name__ == "__main__":
    main()
