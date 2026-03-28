"""
Character sheet renderer - ANSI-colored, 78-char wide.
Layout based on the official WEG Star Wars 2nd Edition character sheet:
  - Header: name, species, template
  - 2-column attribute grid (DEX/KNO/MEC left, PER/STR/TEC right)
  - Skills listed under each attribute with totals
  - Weapons table with damage and range bands
  - Footer: Move, FP, DSP, CP, wound status
"""
import re
from engine.dice import DicePool
from engine.character import Character, SkillRegistry, ATTRIBUTE_NAMES, WoundLevel
from engine.species import Species
from server.ansi import (
    BOLD, RESET, CYAN, YELLOW, GREEN, RED, DIM, WHITE,
    BRIGHT_WHITE, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN, BRIGHT_RED,
    BRIGHT_BLUE, BRIGHT_MAGENTA,
)

W = 78  # Total sheet width
COL = 37  # Column width
GUTTER = "  "  # 2-char divider
# Left/Right attribute layout matches R&E character sheet
LEFT_ATTRS = ["dexterity", "knowledge", "mechanical"]
RIGHT_ATTRS = ["perception", "strength", "technical"]


def _ansi_len(text):
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def _pad(text, width):
    return text + " " * max(0, width - _ansi_len(text))


def _bar(char="=", color=BRIGHT_CYAN, width=W):
    return f"{color}{char * width}{RESET}"


def _center(text, width=W):
    pad = max(0, width - _ansi_len(text))
    return " " * (pad // 2) + text


def _attr_header(name, pool, col_width=COL):
    """DEXTERITY          3D+1"""
    label = f"{BOLD}{BRIGHT_WHITE}{name.upper()}{RESET}"
    val = f"{BRIGHT_YELLOW}{str(pool)}{RESET}"
    gap = max(1, col_width - len(name) - len(str(pool)))
    return f"{label}{' ' * gap}{val}"


def _skill_line(name, total_pool, col_width=COL):
    """  Blaster              5D+1"""
    val = f"{BRIGHT_GREEN}{str(total_pool)}{RESET}"
    gap = max(1, col_width - len(name) - 2 - len(str(total_pool)))
    return f"  {CYAN}{name}{RESET}{' ' * gap}{val}"


def _build_attr_block(attr_name, char, skill_reg, col_width=COL,
                      species=None, show_range=False,
                      attributes=None, skills=None):
    """Build lines for one attribute + its skills."""
    lines = []

    if char:
        pool = char.get_attribute(attr_name)
    elif attributes:
        pool = attributes.get(attr_name, DicePool(0, 0))
    else:
        pool = DicePool(0, 0)

    # Attribute header
    hdr = _attr_header(attr_name, pool, col_width)
    if show_range and species:
        r = species.attributes.get(attr_name)
        if r:
            hdr += f" {DIM}({r.min_pool}-{r.max_pool}){RESET}"
    lines.append(hdr)

    # Skills
    for sd in skill_reg.skills_for_attribute(attr_name):
        bonus = None
        if char:
            bonus = char.skills.get(sd.key)
        elif skills:
            bonus = skills.get(sd.key)
        if bonus:
            total = pool + bonus
            lines.append(_skill_line(sd.name, total, col_width))

    return lines


def _merge_columns(left_lines, right_lines, col_width=COL, gutter=GUTTER):
    result = []
    max_len = max(len(left_lines), len(right_lines))
    for i in range(max_len):
        left = left_lines[i] if i < len(left_lines) else ""
        right = right_lines[i] if i < len(right_lines) else ""
        result.append(f"{_pad(left, col_width)}{gutter}{right}")
    return result


def _wound_display(wound_level):
    """Wound checkboxes matching R&E sheet."""
    levels = [
        ("Stunned", WoundLevel.STUNNED),
        ("Wounded", WoundLevel.WOUNDED),
        ("W.Twice", WoundLevel.WOUNDED_TWICE),
        ("Incap.", WoundLevel.INCAPACITATED),
        ("Mortal", WoundLevel.MORTALLY_WOUNDED),
    ]
    parts = []
    for label, wl in levels:
        if wound_level >= wl:
            parts.append(f"{BRIGHT_RED}[X]{label}{RESET}")
        else:
            parts.append(f"{DIM}[ ]{label}{RESET}")
    return " ".join(parts)


def _dsp_pips(dsp):
    """Dark Side Points 1-6 as filled/empty markers."""
    return " ".join(
        f"{BRIGHT_RED}*{RESET}" if i < dsp else f"{DIM}o{RESET}"
        for i in range(6)
    )


# ═══════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════

def render_game_sheet(char_dict, skill_reg):
    """Render in-game character sheet (R&E layout)."""
    from engine.character import Character
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}STAR WARS{RESET} {DIM}Character Sheet{RESET}"
    ))
    lines.append(_bar("-", DIM))

    # ── Identity ──
    template_str = ""
    if char_dict.get("template"):
        template_str = f"  {DIM}({char_dict['template']}){RESET}"
    lines.append(
        f"  Name: {BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f"    Species: {BRIGHT_YELLOW}{char.species_name}{RESET}"
        f"{template_str}"
    )

    # ── Points row ──
    cp = char_dict.get("character_points", 0)
    fp = char_dict.get("force_points", 0)
    dsp = char_dict.get("dark_side_points", 0)
    fs = "Yes" if char.force_sensitive else "No"
    lines.append(
        f"  Move: {BRIGHT_WHITE}{char.move}{RESET}"
        f"   Force Pts: {BRIGHT_BLUE}{fp}{RESET}"
        f"   Char Pts: {BRIGHT_GREEN}{cp}{RESET}"
        f"   Force Sensitive: {BRIGHT_BLUE}{fs}{RESET}"
    )
    lines.append(f"  Dark Side: {_dsp_pips(dsp)}")
    lines.append(_bar("-", DIM))

    # ── Attribute Grid ──
    left_lines = []
    for attr in LEFT_ATTRS:
        left_lines.extend(_build_attr_block(attr, char, skill_reg, COL))
        left_lines.append("")

    right_lines = []
    for attr in RIGHT_ATTRS:
        right_lines.extend(_build_attr_block(attr, char, skill_reg, COL))
        right_lines.append("")

    lines.extend(_merge_columns(left_lines, right_lines))

    # ── Force (if sensitive) ──
    if char.force_sensitive:
        lines.append(_bar("-", DIM))
        lines.append(
            f"  {BOLD}{BRIGHT_BLUE}THE FORCE{RESET}"
            f"    Control: {BRIGHT_YELLOW}{char.control}{RESET}"
            f"    Sense: {BRIGHT_YELLOW}{char.sense}{RESET}"
            f"    Alter: {BRIGHT_YELLOW}{char.alter}{RESET}"
        )

    # ── Wound Status ──
    lines.append(_bar("-", DIM))
    lines.append(f"  {_wound_display(wound)}")

    # ── Weapons Table ──
    lines.append(_bar("-", DIM))
    lines.append(
        f"  {BOLD}{'Weapon':<22s}{'Dmg':>5s}"
        f"  {'Short':>6s} {'Med':>6s} {'Long':>6s}{RESET}"
    )
    lines.append(f"  {DIM}{'-'*22}{'-'*5}  {'-'*6} {'-'*6} {'-'*6}{RESET}")

    # Show equipped weapon from character data
    import json as _json
    equip_data = char_dict.get("equipment", "{}")
    if isinstance(equip_data, str):
        try:
            equip_data = _json.loads(equip_data)
        except Exception:
            equip_data = {}
    weapon_key = equip_data.get("weapon", "") if isinstance(equip_data, dict) else ""
    if weapon_key:
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        w = wr.get(weapon_key)
        if w:
            if w.is_ranged and w.ranges:
                lines.append(
                    f"  {BRIGHT_WHITE}{w.name:<22s}{RESET}"
                    f"{BRIGHT_YELLOW}{w.damage:>5s}{RESET}"
                    f"  {w.ranges[1]:>6d} {w.ranges[2]:>6d} {w.ranges[3]:>6d}"
                )
            else:
                lines.append(
                    f"  {BRIGHT_WHITE}{w.name:<22s}{RESET}"
                    f"{BRIGHT_YELLOW}{w.damage:>5s}{RESET}"
                    f"  {'Melee':>6s}"
                )
        else:
            lines.append(f"  {weapon_key}")
    else:
        lines.append(f"  {DIM}(no weapons equipped){RESET}")

    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append("")
    return lines


def render_creation_sheet(
    name, species, attributes, skills, skill_reg,
    attr_pips_total, attr_pips_spent, skill_pips_total, skill_pips_spent,
):
    """Render sheet during character creation with budget tracking."""
    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}STAR WARS{RESET} {DIM}Character Creation{RESET}"
    ))
    lines.append(_bar("-", DIM))

    # Identity
    sp_name = species.name if species else "???"
    lines.append(
        f"  Name: {BOLD}{BRIGHT_WHITE}{name or '???'}{RESET}"
        f"    Species: {BRIGHT_YELLOW}{sp_name}{RESET}"
    )

    # Budget
    attr_left = attr_pips_total - attr_pips_spent
    skill_left = skill_pips_total - skill_pips_spent
    ac = BRIGHT_GREEN if attr_left == 0 else (BRIGHT_RED if attr_left < 0 else BRIGHT_YELLOW)
    sc = BRIGHT_GREEN if skill_left == 0 else (BRIGHT_RED if skill_left < 0 else BRIGHT_YELLOW)
    lines.append(
        f"  Attr: {ac}{_pips_to_dice(attr_pips_spent)}{RESET}"
        f"/{_pips_to_dice(attr_pips_total)}"
        f" {DIM}({_pips_to_dice(attr_left)} left){RESET}"
        f"    Skills: {sc}{_pips_to_dice(skill_pips_spent)}{RESET}"
        f"/{_pips_to_dice(skill_pips_total)}"
        f" {DIM}({_pips_to_dice(skill_left)} left){RESET}"
    )
    lines.append(_bar("-", DIM))

    # ── Attribute Grid ──
    left_lines = []
    for attr in LEFT_ATTRS:
        left_lines.extend(_build_attr_block(
            attr, None, skill_reg, COL,
            species=species, show_range=True,
            attributes=attributes, skills=skills,
        ))
        left_lines.append("")

    right_lines = []
    for attr in RIGHT_ATTRS:
        right_lines.extend(_build_attr_block(
            attr, None, skill_reg, COL,
            species=species, show_range=True,
            attributes=attributes, skills=skills,
        ))
        right_lines.append("")

    lines.extend(_merge_columns(left_lines, right_lines))

    # Special abilities
    if species and species.special_abilities:
        lines.append(_bar("-", DIM))
        lines.append(f"  {BOLD}Special Abilities:{RESET}")
        for ab in species.special_abilities:
            desc = ab.description[:50] + "..." if len(ab.description) > 50 else ab.description
            lines.append(f"    {BRIGHT_MAGENTA}{ab.name}{RESET}: {DIM}{desc}{RESET}")

    if species:
        lines.append(f"  {BOLD}Move:{RESET} {species.move}")

    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append("")
    return lines


def render_status_line(attr_pips_left, skill_pips_left):
    """One-line budget status after every creation command."""
    ac = BRIGHT_GREEN if attr_pips_left == 0 else (BRIGHT_RED if attr_pips_left < 0 else BRIGHT_YELLOW)
    sc = BRIGHT_GREEN if skill_pips_left == 0 else (BRIGHT_RED if skill_pips_left < 0 else BRIGHT_YELLOW)
    return (
        f"  {DIM}[{RESET}"
        f" Attr: {ac}{_pips_to_dice(attr_pips_left)}{RESET} left"
        f" {DIM}|{RESET}"
        f" Skills: {sc}{_pips_to_dice(skill_pips_left)}{RESET} left"
        f" {DIM}]{RESET}"
    )


def _pips_to_dice(pips):
    if pips < 0:
        return f"-{_pips_to_dice(-pips)}"
    d = pips // 3
    p = pips % 3
    return f"{d}D+{p}" if p > 0 else f"{d}D"
