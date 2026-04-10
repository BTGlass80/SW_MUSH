#!/usr/bin/env python3
"""
drop12a_starships_patch.py  --  Space Expansion v2 Drop 12 (Part A)
Ship Customization Engine  —  engine/starships.py

Changes:
  1. ShipTemplate gains `mod_slots: int = 3` field
  2. ShipRegistry.load_file() reads `mod_slots` from YAML
  3. New function `get_effective_stats(template, systems)` —
     computes live stats with installed modifications applied.
     Called at read-time by combat and display commands (Drop 12b).

Max boost limits (WEG R&E p88-90):
  speed          : +2 max
  maneuverability: +1D+2 max (5 pips)
  hull           : +1D+2 max (5 pips)
  shields        : +1D+2 max (5 pips)
  fire_control   : +1D+2 max per weapon (5 pips)
  sensors        : +1D max (3 pips)
  hyperdrive     : -1.0 min (faster multiplier)

Usage:
    python drop12a_starships_patch.py [--dry-run]
"""

import ast
import os
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv
BASE = os.getcwd()

TARGET = os.path.join(BASE, "engine", "starships.py")


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    dst = path + ".bak_drop12a"
    shutil.copy2(path, dst)
    print(f"  backup → {dst}")


def validate(content, label=""):
    try:
        ast.parse(content)
        print(f"  ✓ AST OK{': ' + label if label else ''}")
    except SyntaxError as e:
        print(f"  ✗ SYNTAX ERROR{': ' + label if label else ''}: {e}")
        lines = content.splitlines()
        lo = max(0, e.lineno - 3)
        hi = min(len(lines), e.lineno + 2)
        for i in range(lo, hi):
            print(f"    {i+1}: {lines[i]}")
        sys.exit(1)


def patch(content, old, new, label):
    if old not in content:
        print(f"  ✗ ANCHOR NOT FOUND: {label}")
        sys.exit(1)
    result = content.replace(old, new, 1)
    validate(result, label)
    print(f"  ✓ PATCHED: {label}")
    return result


# ── Patch 1: add mod_slots to ShipTemplate dataclass ─────────────────────────

OLD_TEMPLATE = """@dataclass
class ShipTemplate:
    \"\"\"Ship template loaded from YAML.\"\"\"
    key: str
    name: str
    nickname: str = ""
    scale: str = "starfighter"
    hull: str = "4D"
    shields: str = "0D"
    speed: int = 5
    maneuverability: str = "1D"
    crew: int = 1
    passengers: int = 0
    cargo: int = 0
    consumables: str = ""
    hyperdrive: int = 0
    hyperdrive_backup: int = 0
    cost: int = 0
    weapons: list[ShipWeapon] = field(default_factory=list)

    @property
    def scale_value(self) -> int:
        return SCALE_CAPITAL if self.scale == "capital" else SCALE_STARFIGHTER"""

NEW_TEMPLATE = """@dataclass
class ShipTemplate:
    \"\"\"Ship template loaded from YAML.\"\"\"
    key: str
    name: str
    nickname: str = ""
    scale: str = "starfighter"
    hull: str = "4D"
    shields: str = "0D"
    speed: int = 5
    maneuverability: str = "1D"
    crew: int = 1
    passengers: int = 0
    cargo: int = 0
    consumables: str = ""
    hyperdrive: int = 0
    hyperdrive_backup: int = 0
    cost: int = 0
    weapons: list[ShipWeapon] = field(default_factory=list)
    mod_slots: int = 3  # Number of available modification slots (Drop 12)

    @property
    def scale_value(self) -> int:
        return SCALE_CAPITAL if self.scale == "capital" else SCALE_STARFIGHTER"""

# ── Patch 2: load mod_slots from YAML in ShipRegistry.load_file() ────────────

OLD_LOADER = """            template = ShipTemplate(
                key=key,
                name=entry.get("name", key),
                nickname=entry.get("nickname", ""),
                scale=entry.get("scale", "starfighter"),
                hull=entry.get("hull", "4D"),
                shields=entry.get("shields", "0D"),
                speed=entry.get("speed", 5),
                maneuverability=entry.get("maneuverability", "1D"),
                crew=entry.get("crew", 1),
                passengers=entry.get("passengers", 0),
                cargo=entry.get("cargo", 0),
                consumables=entry.get("consumables", ""),
                hyperdrive=entry.get("hyperdrive", 0),
                hyperdrive_backup=entry.get("hyperdrive_backup", 0),
                cost=entry.get("cost", 0),
                weapons=weapons,
            )"""

NEW_LOADER = """            template = ShipTemplate(
                key=key,
                name=entry.get("name", key),
                nickname=entry.get("nickname", ""),
                scale=entry.get("scale", "starfighter"),
                hull=entry.get("hull", "4D"),
                shields=entry.get("shields", "0D"),
                speed=entry.get("speed", 5),
                maneuverability=entry.get("maneuverability", "1D"),
                crew=entry.get("crew", 1),
                passengers=entry.get("passengers", 0),
                cargo=entry.get("cargo", 0),
                consumables=entry.get("consumables", ""),
                hyperdrive=entry.get("hyperdrive", 0),
                hyperdrive_backup=entry.get("hyperdrive_backup", 0),
                cost=entry.get("cost", 0),
                weapons=weapons,
                mod_slots=entry.get("mod_slots", 3),
            )"""

# ── Patch 3: add get_effective_stats() after get_weapon_repair_skill() ────────

OLD_ANCHOR = """def get_weapon_repair_skill(scale: str) -> str:
    \"\"\"Return the weapon-specific repair skill for a ship's scale.\"\"\"
    if scale == "capital":
        return "capital ship weapon repair"
    return "starship weapon repair\""""

NEW_ANCHOR = """def get_weapon_repair_skill(scale: str) -> str:
    \"\"\"Return the weapon-specific repair skill for a ship's scale.\"\"\"
    if scale == "capital":
        return "capital ship weapon repair"
    return "starship weapon repair"


# ─────────────────────────────────────────────────────────────────────────────
# Ship Modification Engine  (Drop 12)
# ─────────────────────────────────────────────────────────────────────────────

# Maximum pip boosts per stat (WEG R&E p88-90: max +1D+2 = 5 pips).
# Speed is measured in integer units, hyperdrive as a float multiplier.
_MOD_MAX_PIPS = {
    "maneuverability": 5,
    "hull":            5,
    "shields":         5,
    "fire_control":    5,  # per weapon slot
    "sensors":         3,  # +1D max
}
_MOD_MAX_SPEED      = 2    # +2 speed max
_MOD_MIN_HYPERDRIVE = 0.5  # halved at most


def _pip_count(dice_str: str) -> int:
    \"\"\"Convert a dice string like '2D+1' to total pips (D=3 pips).\"\"\"
    if not dice_str:
        return 0
    s = dice_str.strip().upper()
    dice, pips = 0, 0
    if "D" in s:
        parts = s.split("D")
        try:
            dice = int(parts[0]) if parts[0] else 0
        except ValueError:
            dice = 0
        pip_part = parts[1].replace("+", "").replace(" ", "") if len(parts) > 1 else ""
        try:
            pips = int(pip_part) if pip_part else 0
        except ValueError:
            pips = 0
    else:
        try:
            pips = int(s)
        except ValueError:
            pips = 0
    return dice * 3 + pips


def _pips_to_dice_str(total_pips: int) -> str:
    \"\"\"Convert total pips back to a dice string like '2D+1'.\"\"\"
    if total_pips <= 0:
        return "0D"
    d = total_pips // 3
    p = total_pips % 3
    if p == 0:
        return f"{d}D"
    return f"{d}D+{p}"


def _quality_factor(quality: int) -> float:
    \"\"\"
    Convert component quality to a stat boost multiplier.
    Quality 80+ → 1.0 (full boost)
    Quality 60-79 → 0.75
    Quality <60  → 0.5
    \"\"\"
    if quality >= 80:
        return 1.0
    if quality >= 60:
        return 0.75
    return 0.5


def get_effective_stats(template: "ShipTemplate", systems: dict) -> dict:
    \"\"\"
    Compute effective ship stats by applying installed modifications.

    Returns a dict with the same keys as ShipTemplate fields that
    can be modified (speed, maneuverability, hull, shields, hyperdrive,
    and per-weapon fire_control overrides).

    Callers should fall back to template values for any key not present.

    Args:
        template: The base ShipTemplate from the registry.
        systems:  The ship's parsed systems JSON dict.

    Returns:
        {
            "speed":            int,
            "maneuverability":  str,   e.g. "2D+1"
            "hull":             str,
            "shields":          str,
            "hyperdrive":       int,   (effective multiplier, min 1 due to int floor)
            "hyperdrive_float": float, (fractional effective multiplier)
            "weapon_fc":        dict[int, str],  # weapon index → effective fire_control
            "sensors_bonus":    int,   # additional sensor pips
            "mods_installed":   int,
            "slots_used":       int,
            "slots_total":      int,
            "cargo_used_by_mods": int, # tons consumed by mods
        }
    \"\"\"
    mods: list = systems.get("modifications", [])

    # Start from template base values
    speed          = template.speed
    maneuver_pips  = _pip_count(template.maneuverability)
    hull_pips      = _pip_count(template.hull)
    shield_pips    = _pip_count(template.shields)
    hyperdrive_f   = float(template.hyperdrive) if template.hyperdrive else 0.0
    sensors_bonus  = 0
    weapon_fc      = {}  # weapon_slot_index → extra pips
    cargo_used     = 0

    for mod in mods:
        if not isinstance(mod, dict):
            continue
        stat_target  = mod.get("stat_target", "")
        stat_boost   = mod.get("stat_boost", 1)    # pips or speed units
        quality      = mod.get("quality", 80)
        cargo_weight = mod.get("cargo_weight", 10)
        weapon_slot  = mod.get("weapon_slot", None)

        effective_boost = max(1, round(stat_boost * _quality_factor(quality)))
        cargo_used += cargo_weight

        if stat_target == "speed":
            speed = min(template.speed + _MOD_MAX_SPEED,
                        speed + effective_boost)

        elif stat_target == "maneuverability":
            cap = _pip_count(template.maneuverability) + _MOD_MAX_PIPS["maneuverability"]
            maneuver_pips = min(cap, maneuver_pips + effective_boost)

        elif stat_target == "hull":
            cap = _pip_count(template.hull) + _MOD_MAX_PIPS["hull"]
            hull_pips = min(cap, hull_pips + effective_boost)

        elif stat_target == "shields":
            cap = _pip_count(template.shields) + _MOD_MAX_PIPS["shields"]
            shield_pips = min(cap, shield_pips + effective_boost)

        elif stat_target == "fire_control":
            slot = int(weapon_slot) if weapon_slot is not None else 0
            current = weapon_fc.get(slot, 0)
            cap = _pip_count(
                template.weapons[slot].fire_control
                if slot < len(template.weapons) else "0D"
            ) + _MOD_MAX_PIPS["fire_control"]
            base_fc = _pip_count(
                template.weapons[slot].fire_control
                if slot < len(template.weapons) else "0D"
            )
            weapon_fc[slot] = min(cap - base_fc, current + effective_boost)

        elif stat_target == "sensors":
            sensors_bonus = min(3, sensors_bonus + effective_boost)

        elif stat_target == "hyperdrive" and hyperdrive_f > 0:
            # Boost reduces hyperdrive multiplier (lower = faster)
            # stat_boost stored as pips; each pip = -0.25 multiplier
            reduction = effective_boost * 0.25
            hyperdrive_f = max(_MOD_MIN_HYPERDRIVE, hyperdrive_f - reduction)

    # Clamp maneuverability/hull/shields to base (no negative mods reduce below base)
    maneuver_pips = max(_pip_count(template.maneuverability), maneuver_pips)
    hull_pips     = max(_pip_count(template.hull), hull_pips)
    shield_pips   = max(_pip_count(template.shields), shield_pips)

    # Build weapon_fc strings (extra pips only, applied in combat code)
    weapon_fc_str = {
        slot: _pips_to_dice_str(extra)
        for slot, extra in weapon_fc.items()
        if extra > 0
    }

    return {
        "speed":              speed,
        "maneuverability":    _pips_to_dice_str(maneuver_pips),
        "hull":               _pips_to_dice_str(hull_pips),
        "shields":            _pips_to_dice_str(shield_pips),
        "hyperdrive":         max(1, int(round(hyperdrive_f))) if hyperdrive_f > 0 else 0,
        "hyperdrive_float":   hyperdrive_f,
        "weapon_fc":          weapon_fc_str,
        "sensors_bonus":      sensors_bonus,
        "mods_installed":     len(mods),
        "slots_used":         len(mods),
        "slots_total":        template.mod_slots,
        "cargo_used_by_mods": cargo_used,
    }


def format_mods_display(template: "ShipTemplate", systems: dict) -> list:
    \"\"\"
    Return ANSI-formatted lines for +ship/mods output.
    \"\"\"
    _BOLD  = "\\033[1m"
    _DIM   = "\\033[2m"
    _CYAN  = "\\033[0;36m"
    _GREEN = "\\033[1;32m"
    _RESET = "\\033[0m"

    mods: list = systems.get("modifications", [])
    effective = get_effective_stats(template, systems)
    slots_used  = effective["slots_used"]
    slots_total = effective["slots_total"]
    cargo_used  = effective["cargo_used_by_mods"]

    lines = [
        f"{_BOLD}{'=' * 56}{_RESET}",
        f"  {_BOLD}INSTALLED MODIFICATIONS{_RESET}  —  {template.name}",
        f"  {_DIM}Slots: {slots_used}/{slots_total}   "
        f"Cargo consumed: {cargo_used}t{_RESET}",
        f"  {_DIM}{'-' * 54}{_RESET}",
    ]

    if not mods:
        lines.append(f"  {_DIM}No modifications installed.{_RESET}")
    else:
        for i, mod in enumerate(mods):
            if not isinstance(mod, dict):
                continue
            q = mod.get("quality", 0)
            name  = mod.get("component_name", mod.get("component_key", "Unknown"))
            stat  = mod.get("stat_target", "?")
            boost = mod.get("stat_boost", 1)
            cw    = mod.get("cargo_weight", 0)
            inst  = mod.get("installed_by", "?")
            qcolor = _GREEN if q >= 80 else _DIM
            factor = _quality_factor(q)
            eff = max(1, round(boost * factor))
            lines.append(
                f"  [{i}] {_BOLD}{name}{_RESET}  "
                f"{_CYAN}+{eff} {stat}{_RESET}  "
                f"{qcolor}Q:{q}%{_RESET}  "
                f"{_DIM}{cw}t  by {inst}{_RESET}"
            )

    # Show effective stat summary
    lines += [
        f"  {_DIM}{'-' * 54}{_RESET}",
        f"  {_BOLD}Effective Stats:{_RESET}",
        f"    Speed {effective['speed']}  "
        f"Maneuver {effective['maneuverability']}  "
        f"Hull {effective['hull']}  "
        f"Shields {effective['shields']}",
    ]
    if effective["sensors_bonus"] > 0:
        lines.append(f"    Sensors bonus: +{effective['sensors_bonus']} pips")
    if effective["hyperdrive_float"] > 0 and effective["hyperdrive_float"] != template.hyperdrive:
        lines.append(
            f"    Hyperdrive: x{effective['hyperdrive_float']:.2f} "
            f"(base x{template.hyperdrive})"
        )
    lines.append(f"{_BOLD}{'=' * 56}{_RESET}")
    return lines"""


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Drop 12a — starships.py: mod_slots + get_effective_stats ===\n")
    if DRY_RUN:
        print("DRY RUN — no files modified.\n")

    content = read(TARGET)

    content = patch(content, OLD_TEMPLATE, NEW_TEMPLATE,
                    "ShipTemplate.mod_slots field")
    content = patch(content, OLD_LOADER,   NEW_LOADER,
                    "ShipRegistry loads mod_slots from YAML")
    content = patch(content, OLD_ANCHOR,   NEW_ANCHOR,
                    "get_effective_stats() + format_mods_display()")

    if not DRY_RUN:
        backup(TARGET)
        write(TARGET, content)
        print(f"\n  Written: {TARGET}")
    else:
        print("\n  (dry run — not written)")

    print("\n=== Drop 12a complete ===")


if __name__ == "__main__":
    main()
