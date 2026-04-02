"""
Hazard Table — engine/starships.py patch
Injects HazardResult dataclass and roll_hazard_table() function
immediately before format_ship_status().

Run from project root:
    python3 hazard_engine_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("engine", "starships.py")

# Unique anchor: the line immediately before format_ship_status
OLD_ANCHOR = '''\
def format_ship_status(template: ShipTemplate, instance: ShipInstance = None) -> list[str]:
    """Format a ship template/instance as a status display."""'''

NEW_ANCHOR = '''\
# -- Hazard Table (Star Warriors Section 7, adapted for D6 R&E) --

@dataclass
class HazardResult:
    """Result of a hazard table roll after a bad maneuver."""
    roll: int = 0                       # 2d6 result
    systems_damaged: list = None        # Systems that become "damaged"
    hull_damage: int = 0                # Direct hull damage points
    narrative: str = ""                 # Broadcast message

    def __post_init__(self):
        if self.systems_damaged is None:
            self.systems_damaged = []

    @property
    def has_effect(self) -> bool:
        return bool(self.systems_damaged) or self.hull_damage > 0


# Hazard table: 2d6 roll -> (primary_system, secondary_system_or_None, hull_damage, flavour)
# Roll 7 is always no effect (Star Warriors 7.38).
# Adapted from Star Warriors Hazard Table rows B-G, columns 2-12.
_HAZARD_TABLE = {
    2:  (["engines"],              "shields",   0, "Control systems surge — multiple failures!"),
    3:  (["shields"],              "engines",   0, "Power coupling overloads!"),
    4:  (["engines"],              "weapons",   0, "Structural stress tears at the drive!"),
    5:  (["shields"],              None,        0, "Shield emitter overloads!"),
    6:  (["engines"],              None,        0, "Gyro destabilizes — handling sluggish!"),
    7:  ([],                       None,        0, "Close call — no serious damage!"),
    8:  (["weapons"],              None,        0, "Fire control feedback — guns offline!"),
    9:  (["sensors"],              None,        0, "Sensor array shaken loose!"),
    10: (["engines"],              "shields",   0, "Drive stutters under the stress!"),
    11: ([],                       None,        1, "Frame stress — hull integrity compromised!"),
    12: (["hyperdrive", "engines"],None,        0, "Critical stress — drive systems hit!"),
}


def roll_hazard_table(systems: dict) -> HazardResult:
    """
    Roll on the Hazard Table (Star Warriors Section 7, adapted).

    Called when a pilot fails an evasive maneuver roll by 5 or more.
    Only damages systems that are currently 'working' — already-damaged
    systems can't be made worse by a hazard (they're already failing).

    Args:
        systems: Current ship systems dict (from DB JSON).

    Returns:
        HazardResult with narrative and damage to apply.
    """
    import random
    roll = random.randint(1, 6) + random.randint(1, 6)

    entry = _HAZARD_TABLE.get(roll, _HAZARD_TABLE[7])
    primary_list, secondary, hull_dmg, flavour = entry

    result = HazardResult(roll=roll, hull_damage=hull_dmg, narrative="")

    # Only damage working systems
    def _is_working(sys_name: str) -> bool:
        val = systems.get(sys_name, True)
        return val is True or val == "working"

    damaged = []
    for sys_name in primary_list:
        if _is_working(sys_name):
            damaged.append(sys_name)

    if secondary and _is_working(secondary):
        damaged.append(secondary)

    result.systems_damaged = damaged

    # Build narrative
    dmg_parts = []
    if damaged:
        dmg_parts.append(f"{', '.join(s.title() for s in damaged)} damaged")
    if hull_dmg:
        dmg_parts.append(f"+{hull_dmg} hull damage")
    if not dmg_parts:
        dmg_parts.append("no systems affected")

    result.narrative = (
        f"  {ansi.BRIGHT_RED}[HAZARD]{ansi.RESET} "
        f"Roll {roll}: {flavour} "
        f"({', '.join(dmg_parts)}.)"
    )

    return result


def format_ship_status(template: ShipTemplate, instance: ShipInstance = None) -> list[str]:
    """Format a ship template/instance as a status display."""'''


def apply_patches(src: str) -> str:
    if OLD_ANCHOR not in src:
        raise ValueError("Anchor not found (format_ship_status header)")
    return src.replace(OLD_ANCHOR, NEW_ANCHOR, 1)


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
    print("  1. HazardResult dataclass added")
    print("  2. roll_hazard_table() function added before format_ship_status")


if __name__ == "__main__":
    main()
