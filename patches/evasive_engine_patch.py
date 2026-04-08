"""
Evasive Maneuvers — engine/starships.py patch
Applies two changes:

  1. SpaceGrid.__init__: adds _maneuver_bonuses dict
  2. SpaceGrid: adds set_maneuver_bonus() / get_and_consume_maneuver_bonus() methods
     after get_speed()
  3. resolve_space_attack: reads and consumes maneuver bonus from SpaceGrid when
     target_ship_id is provided, adding it to the attack difficulty.

Run from project root:
    python3 evasive_engine_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("engine", "starships.py")

# ── Patch 1 ───────────────────────────────────────────────────────────────────
# SpaceGrid.__init__: add _maneuver_bonuses dict

OLD_INIT = '''\
    def __init__(self):
        # {(min_id, max_id): SpaceRange}
        self._ranges: dict[tuple[int, int], SpaceRange] = {}
        # {(attacker_id, target_id): RelativePosition}
        self._positions: dict[tuple[int, int], str] = {}
        # {ship_id: speed} for speed advantage calculations
        self._speeds: dict[int, int] = {}'''

NEW_INIT = '''\
    def __init__(self):
        # {(min_id, max_id): SpaceRange}
        self._ranges: dict[tuple[int, int], SpaceRange] = {}
        # {(attacker_id, target_id): RelativePosition}
        self._positions: dict[tuple[int, int], str] = {}
        # {ship_id: speed} for speed advantage calculations
        self._speeds: dict[int, int] = {}
        # {ship_id: int} — evasive maneuver bonus added to attacker difficulty this round
        # Consumed (zeroed) when first attack resolves against this ship
        self._maneuver_bonuses: dict[int, int] = {}'''

# ── Patch 2 ───────────────────────────────────────────────────────────────────
# Add set_maneuver_bonus / get_and_consume_maneuver_bonus after get_speed()

OLD_GET_SPEED = '''\
    def get_speed(self, ship_id: int) -> int:
        return self._speeds.get(ship_id, 5)
'''

NEW_GET_SPEED = '''\
    def get_speed(self, ship_id: int) -> int:
        return self._speeds.get(ship_id, 5)

    def set_maneuver_bonus(self, ship_id: int, bonus: int):
        """Set an evasive maneuver difficulty bonus for this ship for the current round."""
        self._maneuver_bonuses[ship_id] = bonus

    def get_and_consume_maneuver_bonus(self, ship_id: int) -> int:
        """Return the maneuver bonus for this ship and zero it (one-shot per round)."""
        return self._maneuver_bonuses.pop(ship_id, 0)
'''

# ── Patch 3 ───────────────────────────────────────────────────────────────────
# resolve_space_attack: consume maneuver bonus and add to total_difficulty.
# Anchor: the unique block that builds total_difficulty from range_mod + defense_roll.

OLD_DIFFICULTY = '''\
    # Total difficulty: range modifier + defense roll
    range_mod = int(range_band)
    total_difficulty = range_mod + defense_roll.total

    result.attack_roll = attack_roll.total
    result.defense_roll = total_difficulty
    result.hit = attack_roll.total >= total_difficulty

    range_label = range_band.label

    if not result.hit:
        tail_tag = " [TAIL +1D]" if tailing_bonus else ""
        result.narrative = (
            f"  Shot misses at {range_label} range!{tail_tag} "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total}) "
            f"= {total_difficulty})"
        )
        return result'''

NEW_DIFFICULTY = '''\
    # Total difficulty: range modifier + defense roll + evasive maneuver bonus
    range_mod = int(range_band)
    maneuver_bonus = 0
    if target_ship_id is not None:
        maneuver_bonus = get_space_grid().get_and_consume_maneuver_bonus(target_ship_id)
    total_difficulty = range_mod + defense_roll.total + maneuver_bonus

    result.attack_roll = attack_roll.total
    result.defense_roll = total_difficulty
    result.hit = attack_roll.total >= total_difficulty

    range_label = range_band.label

    if not result.hit:
        tail_tag = " [TAIL +1D]" if tailing_bonus else ""
        evade_tag = f" + Evade({maneuver_bonus})" if maneuver_bonus else ""
        result.narrative = (
            f"  Shot misses at {range_label} range!{tail_tag} "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total})"
            f"{evade_tag} = {total_difficulty})"
        )
        return result'''


def apply_patches(src: str) -> str:
    out = src

    if OLD_INIT not in out:
        raise ValueError("Patch 1 anchor not found (SpaceGrid.__init__)")
    out = out.replace(OLD_INIT, NEW_INIT, 1)

    if OLD_GET_SPEED not in out:
        raise ValueError("Patch 2 anchor not found (get_speed / resolve_maneuver)")
    out = out.replace(OLD_GET_SPEED, NEW_GET_SPEED, 1)

    if OLD_DIFFICULTY not in out:
        raise ValueError("Patch 3 anchor not found (total_difficulty block)")
    out = out.replace(OLD_DIFFICULTY, NEW_DIFFICULTY, 1)

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
    print("  1. SpaceGrid.__init__: added _maneuver_bonuses dict")
    print("  2. SpaceGrid: added set_maneuver_bonus() / get_and_consume_maneuver_bonus()")
    print("  3. resolve_space_attack: consumes maneuver bonus into total_difficulty")


if __name__ == "__main__":
    main()
