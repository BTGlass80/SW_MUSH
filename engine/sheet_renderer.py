# -*- coding: utf-8 -*-
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
from engine.text_format import Fmt
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


def render_brief_sheet(char_dict, skill_reg, width=W):
    """Condensed view: attribute + skills wrapped to width."""
    from engine.character import Character
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN, width))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f"  {DIM}({char.species_name}){RESET}",
        width,
    ))
    lines.append(_bar("-", DIM, width))

    ATTR_COL = 14   # "DEXTERITY     "
    POOL_COL = 6    # " 3D+1 "
    INDENT = " " * (ATTR_COL + POOL_COL + 2)   # indent for skill wrap continuation

    for attr_name in LEFT_ATTRS + RIGHT_ATTRS:
        pool = char.get_attribute(attr_name)

        # Gather trained skills as short tokens
        skill_parts = []
        for sd in skill_reg.skills_for_attribute(attr_name):
            bonus = char.skills.get(sd.key)
            if bonus:
                total = pool + bonus
                # Plain-text length for wrapping calculations
                skill_parts.append(
                    (f"{CYAN}{sd.name}{RESET} {BRIGHT_GREEN}{total}{RESET}",
                     f"{sd.name} {total}")  # (colored, plain) pair
                )

        attr_prefix = (
            f"  {BOLD}{BRIGHT_WHITE}{attr_name.upper():<{ATTR_COL}}{RESET}"
            f" {BRIGHT_YELLOW}{str(pool):>{POOL_COL - 1}}{RESET} "
        )
        prefix_plain_len = 2 + ATTR_COL + 1 + POOL_COL  # "  DEXTERITY      3D+1 "

        if not skill_parts:
            lines.append(attr_prefix)
            continue

        # Wrap skill tokens so no line exceeds `width`
        # First line starts after the attr prefix; continuation lines use INDENT
        current_line_colored = []
        current_line_len = prefix_plain_len + 1  # +1 for "["
        first_line = True

        for colored, plain in skill_parts:
            token_len = len(plain) + 2  # ", " separator
            if current_line_colored and current_line_len + token_len > width - 1:
                # Flush current line
                sep = f"{DIM},{RESET} "
                joined = sep.join(current_line_colored)
                if first_line:
                    lines.append(f"{attr_prefix}[{joined}")
                    first_line = False
                else:
                    lines.append(f"{INDENT} {joined}")
                current_line_colored = [colored]
                current_line_len = len(INDENT) + 1 + len(plain)
            else:
                current_line_colored.append(colored)
                current_line_len += token_len

        # Flush last line
        sep = f"{DIM},{RESET} "
        joined = sep.join(current_line_colored)
        if first_line:
            lines.append(f"{attr_prefix}[{joined}]")
        else:
            lines.append(f"{INDENT} {joined}]")

    # Force (if sensitive)
    if char.force_sensitive:
        lines.append(
            f"  {BRIGHT_BLUE}Force{RESET}"
            f"  C:{BRIGHT_YELLOW}{char.control}{RESET}"
            f"  S:{BRIGHT_YELLOW}{char.sense}{RESET}"
            f"  A:{BRIGHT_YELLOW}{char.alter}{RESET}"
        )

    # Scars (if any)
    try:
        from engine.scars import format_scars_display
        scar_lines = format_scars_display(char_dict)
        if scar_lines:
            lines.extend(scar_lines)
    except Exception:
        pass  # graceful-drop if scars module not available

    # Footer: wound + points
    cp = char_dict.get("character_points", 0)
    fp = char_dict.get("force_points", 0)
    lines.append(
        f"  {_wound_display(wound)}"
        f"  CP:{BRIGHT_GREEN}{cp}{RESET}"
        f"  FP:{BRIGHT_BLUE}{fp}{RESET}"
    )
    lines.append(_bar("=", BRIGHT_CYAN, width))
    lines.append("")
    return lines


def render_skills_sheet(char_dict, skill_reg, width=W):
    """Skills-only view grouped by attribute."""
    from engine.character import Character
    char = Character.from_db_dict(char_dict)
    w = min(width, W)

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN, w))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f" {DIM}— Skills{RESET}",
        w,
    ))
    lines.append(_bar("-", DIM, w))

    any_skills = False
    for attr_name in LEFT_ATTRS + RIGHT_ATTRS:
        pool = char.get_attribute(attr_name)
        attr_skills = []
        for sd in skill_reg.skills_for_attribute(attr_name):
            bonus = char.skills.get(sd.key)
            if bonus:
                total = pool + bonus
                attr_skills.append((sd.name, str(total)))
        if attr_skills:
            any_skills = True
            lines.append(
                f"  {BOLD}{BRIGHT_WHITE}{attr_name.upper()}{RESET}"
                f" {DIM}({pool}){RESET}"
            )
            for sname, sval in attr_skills:
                gap = max(1, 30 - len(sname))
                lines.append(
                    f"    {CYAN}{sname}{RESET}"
                    f"{' ' * gap}{BRIGHT_GREEN}{sval}{RESET}"
                )
            lines.append("")

    if not any_skills:
        lines.append(f"  {DIM}No trained skills.{RESET}")

    lines.append(_bar("=", BRIGHT_CYAN, w))
    lines.append("")
    return lines


def render_combat_sheet(char_dict, skill_reg, width=W):
    """Combat-relevant stats: wounds, weapon, soak, combat skills."""
    from engine.character import Character
    import json as _json
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))
    w = width

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN, w))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f" {DIM}— Combat Stats{RESET}",
        w,
    ))
    lines.append(_bar("-", DIM, w))

    # Wound status
    lines.append(f"  {_wound_display(wound)}")
    lines.append("")

    # Soak (Strength)
    str_pool = char.get_attribute("strength")
    lines.append(
        f"  {BOLD}Soak:{RESET}  {BRIGHT_YELLOW}{str_pool}{RESET}"
        f"  {DIM}(Strength){RESET}"
    )

    # Combat skills
    dex_pool = char.get_attribute("dexterity")
    combat_skills = ["blaster", "dodge", "brawling_parry", "melee_combat",
                     "melee_parry", "grenade", "missile_weapons",
                     "vehicle_blasters", "starship_gunnery", "lightsaber"]
    found = []
    for sk_key in combat_skills:
        bonus = char.skills.get(sk_key)
        if bonus:
            sd = skill_reg.get(sk_key) if hasattr(skill_reg, 'get') else None
            name = sd.name if sd else sk_key.replace("_", " ").title()
            attr_for = skill_reg.get_attribute_for(sk_key) if hasattr(skill_reg, 'get_attribute_for') else "dexterity"
            base = char.get_attribute(attr_for) if attr_for else dex_pool
            total = base + bonus
            found.append((name, str(total)))

    if found:
        lines.append("")
        lines.append(f"  {BOLD}Combat Skills:{RESET}")
        for sname, sval in found:
            gap = max(1, 28 - len(sname))
            lines.append(
                f"    {CYAN}{sname}{RESET}"
                f"{' ' * gap}{BRIGHT_GREEN}{sval}{RESET}"
            )

    # Equipped weapon
    lines.append("")
    equip_data = char_dict.get("equipment", "{}")
    if isinstance(equip_data, str):
        try:
            equip_data = _json.loads(equip_data)
        except Exception:
            equip_data = {}
    weapon_key = equip_data.get("key", "") if isinstance(equip_data, dict) else ""
    if weapon_key:
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        w = wr.get(weapon_key)
        if w:
            range_str = ""
            if w.is_ranged and w.ranges:
                range_str = (f"  S:{w.ranges[1]}  M:{w.ranges[2]}  L:{w.ranges[3]}")
            else:
                range_str = "  Melee"
            lines.append(
                f"  {BOLD}Weapon:{RESET}  {BRIGHT_WHITE}{w.name}{RESET}"
                f"  Dmg:{BRIGHT_YELLOW}{w.damage}{RESET}"
                f"{range_str}"
            )
        else:
            lines.append(f"  {BOLD}Weapon:{RESET}  {weapon_key}")
    else:
        lines.append(f"  {BOLD}Weapon:{RESET}  {DIM}(none equipped){RESET}")

    # Move
    lines.append(f"  {BOLD}Move:{RESET}   {BRIGHT_WHITE}{char.move}{RESET}")

    # Force Points
    fp = char_dict.get("force_points", 0)
    if fp:
        lines.append(f"  {BOLD}Force Pts:{RESET} {BRIGHT_BLUE}{fp}{RESET}")

    lines.append(_bar("=", BRIGHT_CYAN, w))
    lines.append("")
    return lines

def render_game_sheet(char_dict, skill_reg, width=W):
    """Render in-game character sheet — compact, box-drawn layout."""
    from engine.character import Character
    import json as _json
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    w = width
    col = (w - 2) // 2  # two columns with 2-char gutter

    H = "\u2500"   # ─
    SEP  = f"{BRIGHT_CYAN}{H * w}{RESET}"
    THIN = f"{DIM}{H * w}{RESET}"

    lines = []
    lines.append(SEP)

    # ── Title ──
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}STAR WARS{RESET} {DIM}D6 Character Sheet{RESET}", w
    ))
    lines.append(THIN)

    # ── Identity & points ──
    template_str = ""
    if char_dict.get("template"):
        template_str = f"  {DIM}({char_dict['template']}){RESET}"
    cp = char_dict.get("character_points", 0)
    fp = char_dict.get("force_points", 0)
    dsp = char_dict.get("dark_side_points", 0)
    fs = f"{BRIGHT_BLUE}Yes{RESET}" if char.force_sensitive else f"{DIM}No{RESET}"

    lines.append(
        f"  {BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f"  {BRIGHT_YELLOW}{char.species_name}{RESET}"
        f"{template_str}"
        f"    Move:{BRIGHT_WHITE}{char.move}{RESET}"
        f"  FP:{BRIGHT_BLUE}{fp}{RESET}"
        f"  CP:{BRIGHT_GREEN}{cp}{RESET}"
        f"  Force:{fs}"
    )
    if dsp > 0:
        lines.append(f"  Dark Side: {_dsp_pips(dsp)}")

    # ── Attribute Grid ──
    lines.append(THIN)

    left_lines = []
    for attr in LEFT_ATTRS:
        left_lines.extend(_build_attr_block(attr, char, skill_reg, col))

    right_lines = []
    for attr in RIGHT_ATTRS:
        right_lines.extend(_build_attr_block(attr, char, skill_reg, col))

    lines.extend(_merge_columns(left_lines, right_lines, col_width=col))

    # ── Force (if sensitive) ──
    if char.force_sensitive:
        lines.append(THIN)
        lines.append(
            f"  {BOLD}{BRIGHT_BLUE}FORCE{RESET}"
            f"   Control:{BRIGHT_YELLOW}{char.control}{RESET}"
            f"   Sense:{BRIGHT_YELLOW}{char.sense}{RESET}"
            f"   Alter:{BRIGHT_YELLOW}{char.alter}{RESET}"
        )

    # ── Wound Status ──
    lines.append(THIN)
    lines.append(f"  {_wound_display(wound)}")

    # ── Equipped Weapon ──
    equip_data = char_dict.get("equipment", "{}")
    if isinstance(equip_data, str):
        try:
            equip_data = _json.loads(equip_data)
        except Exception:
            equip_data = {}
    weapon_key = equip_data.get("key", "") if isinstance(equip_data, dict) else ""
    if weapon_key:
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        w_obj = wr.get(weapon_key)
        if w_obj:
            if w_obj.is_ranged and w_obj.ranges:
                lines.append(
                    f"  {BOLD}Weapon:{RESET} {BRIGHT_WHITE}{w_obj.name}{RESET}"
                    f"  {BRIGHT_YELLOW}{w_obj.damage}{RESET}"
                    f"  {DIM}S:{RESET}{w_obj.ranges[1]}"
                    f" {DIM}M:{RESET}{w_obj.ranges[2]}"
                    f" {DIM}L:{RESET}{w_obj.ranges[3]}"
                )
            else:
                lines.append(
                    f"  {BOLD}Weapon:{RESET} {BRIGHT_WHITE}{w_obj.name}{RESET}"
                    f"  {BRIGHT_YELLOW}{w_obj.damage}{RESET}  Melee"
                )
        else:
            lines.append(f"  {BOLD}Weapon:{RESET} {weapon_key}")
    else:
        lines.append(f"  {BOLD}Weapon:{RESET} {DIM}(none){RESET}")

    # ── Worn Armor ──
    armor_key = equip_data.get("armor", "") if isinstance(equip_data, dict) else ""
    if armor_key:
        from engine.weapons import get_weapon_registry as _wr_get
        wr2 = _wr_get()
        a = wr2.get(armor_key)
        if a and a.is_armor:
            dex_note = f"  {DIM}DEX {a.dexterity_penalty}{RESET}" if a.dexterity_penalty else ""
            lines.append(
                f"  {BOLD}Armor:{RESET}  {BRIGHT_WHITE}{a.name}{RESET}"
                f"  E:{a.protection_energy} P:{a.protection_physical}{dex_note}"
            )
        else:
            lines.append(f"  {BOLD}Armor:{RESET}  {armor_key}")

    lines.append(SEP)
    return lines


def render_creation_sheet(
    name, species, attributes, skills, skill_reg,
    attr_pips_total, attr_pips_spent, skill_pips_total, skill_pips_spent,
    width=W,
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
            desc = ab.description  # Full description, no truncation
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


# ═══════════════════════════════════════════════════════════════════
#  STRUCTURED PAYLOAD (GUI sheet redesign)
# ═══════════════════════════════════════════════════════════════════
#
#  These builders are the WebSocket-side counterpart to render_*().  The
#  text renderers above are still used for Telnet and as a fallback path
#  on WS errors.  The web client receives `build_sheet_payload(...)` over
#  a `sheet_data` event and renders the themed slide-in panel without any
#  ANSI parsing.
#
#  Payload schema (mirrors prototype/sheet-data.jsx SAMPLE_CHAR shape):
#
#    {
#      "identity":        {name, species, template, gender, homeworld,
#                          age, height, hair, eyes, move, description},
#      "points":          {cp, fp, dsp, force_sensitive, credits},
#      "wound":           {level, label, penalty},
#      "attributes":      {dexterity: {d, p}, knowledge: {d, p}, ...},
#      "skills":          {blaster: {bonus: {d, p},
#                                     total: {d, p},
#                                     attr: "dexterity",
#                                     tags: ["combat", ...]}, ...},
#      "specializations": [{skill, name, bonus: {d, p}, total: {d, p}}],
#      "force":           {control: {d, p}, sense: {d, p}, alter: {d, p},
#                          powers: [{key, name, skills, base_diff,
#                                    dark_side, description}, ...]} | None,
#      "advantages":      [],     # populated when advantages DB lands
#      "disadvantages":   [],     # populated when disadvantages DB lands
#      "weapon":          {key, name, damage, ranges} | None,
#      "armor":           {key, name, energy, physical, dex_pen} | None,
#      "inventory":       [{name, qty}],
#      "background":      "",     # filled from pc_narrative when present
#      "notes":           "",     # filled when notes table lands
#      "chargen_notes":   "",     # NEW: characters table column
#      "skill_count":     <int>,  # convenience: trained skill total
#    }
#
#  DicePools serialize as {"d": <dice>, "p": <pips>} so the JSX renderer
#  can call poolToStr() identically to the mock data.
# ═══════════════════════════════════════════════════════════════════


def _pool_to_dict(pool):
    """Serialize a DicePool to {d, p} for the JSON payload.

    Mirrors the shape used in prototype/sheet-data.jsx so the JSX
    poolToStr() helper works without modification.
    """
    if pool is None:
        return {"d": 0, "p": 0}
    return {"d": int(getattr(pool, "dice", 0)),
            "p": int(getattr(pool, "pips", 0))}


def _wound_label_and_penalty(wound):
    """Return ('STUNNED', '-1D')-style strings for the payload."""
    # Map WoundLevel to UI ladder labels (matches WOUND_RUNGS in
    # prototype/sheet-data.jsx — 7 rungs, 0=HEALTHY .. 6=KILLED).
    labels = [
        ("HEALTHY", ""),
        ("STUNNED", "-1D"),
        ("WOUNDED", "-1D"),
        ("WOUNDED TWICE", "-2D"),
        ("INCAPACITATED", "—"),
        ("MORTALLY WOUNDED", "—"),
        ("KILLED", "—"),
    ]
    idx = int(wound) if wound is not None else 0
    if 0 <= idx < len(labels):
        return labels[idx]
    return ("HEALTHY", "")


# Cache of skill-tag lookup so the payload can mark each trained skill
# with its tags ("combat", "social", "piloting", ...) for the GUI tabs.
# Keys here are the underscored wire form to match the payload.
_SKILL_TAG_CACHE: dict = {}


def _load_skill_tags():
    """Lazy-load skill tag mapping from data/skill_descriptions.yaml.

    The catalog is a few KB and rarely changes — load once and cache.
    Returns dict: underscored_skill_key -> list[str] of tags.
    """
    global _SKILL_TAG_CACHE
    if _SKILL_TAG_CACHE:
        return _SKILL_TAG_CACHE
    import os
    try:
        import yaml as _yaml
    except ImportError:
        return {}
    here = os.path.dirname(os.path.abspath(__file__))
    yaml_path = os.path.join(
        os.path.dirname(here), "data", "skill_descriptions.yaml"
    )
    if not os.path.exists(yaml_path):
        return {}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
    except Exception:
        return {}
    tags = {}
    for parent_attr, attr_block in (raw.get("skills") or {}).items():
        if not isinstance(attr_block, dict):
            continue
        for skill_key, skill_data in attr_block.items():
            if not isinstance(skill_data, dict):
                continue
            t = skill_data.get("tags") or []
            if isinstance(t, list):
                tags[skill_key.lower()] = [str(x) for x in t]
    _SKILL_TAG_CACHE = tags
    return tags


def build_sheet_payload(char_dict, skill_reg):
    """Build a structured dict describing the character for the GUI sheet.

    Sibling of render_game_sheet().  Reuses the same data assembly logic
    (Character.from_db_dict, skill_reg.skills_for_attribute) but emits a
    JSON-serializable dict instead of ANSI text lines.

    Args:
        char_dict: DB row dict from db.get_character() (string-encoded
            JSON for attributes/skills/equipment).
        skill_reg: A SkillRegistry loaded from data/skills.yaml.

    Returns:
        A dict matching the schema documented above.  All fields are
        always present so the client renderer doesn't need optional-key
        guards.  Pools are {d, p} dicts, not strings.
    """
    import json as _json
    from engine.character import Character, ATTRIBUTE_NAMES, WoundLevel

    char = Character.from_db_dict(char_dict)
    wound_level = WoundLevel(char_dict.get("wound_level", 0))
    wound_label, wound_pen = _wound_label_and_penalty(wound_level)

    # ── Identity ───────────────────────────────────────────────────
    # gender/homeworld/age/height/hair/eyes don't exist in the
    # characters table today — emit empty strings so the client's
    # optional-bio panel renders cleanly when those columns land.
    identity = {
        "name":        char.name,
        "species":     char.species_name,
        "template":    char.template or "",
        "gender":      char_dict.get("gender", ""),
        "homeworld":   char_dict.get("homeworld", ""),
        "age":         char_dict.get("age", ""),
        "height":      char_dict.get("height", ""),
        "hair":        char_dict.get("hair", ""),
        "eyes":        char_dict.get("eyes", ""),
        "move":        char.move,
        "description": char.description or "",
    }

    # ── Points ─────────────────────────────────────────────────────
    points = {
        "cp":               int(char.character_points or 0),
        "fp":               int(char.force_points or 0),
        "dsp":              int(char.dark_side_points or 0),
        "force_sensitive":  bool(char.force_sensitive),
        "credits":          int(char.credits or 0),
    }

    # ── Wound ──────────────────────────────────────────────────────
    wound = {
        "level":   int(wound_level.value if hasattr(wound_level, "value") else wound_level),
        "label":   wound_label,
        "penalty": wound_pen,
    }

    # ── Attributes ─────────────────────────────────────────────────
    attributes = {
        a: _pool_to_dict(char.get_attribute(a))
        for a in ATTRIBUTE_NAMES
    }

    # ── Skills (trained only — bonus > 0) ──────────────────────────
    # Each skill carries the parent attribute and skill-tag list so the
    # client can group/filter without consulting a parallel registry.
    # Keys are normalized to the underscored form ("space_transports")
    # so they match the convention used in data/skill_descriptions.yaml
    # and the dashboard's SKILL_DESC lookup.  The registry stores keys
    # as "space transports" (lowercased name with spaces).
    skill_tags = _load_skill_tags()
    skills = {}
    for sd in skill_reg.all_skills():
        bonus = char.skills.get(sd.key)
        if bonus and (bonus.dice > 0 or bonus.pips > 0):
            attr_pool = char.get_attribute(sd.attribute)
            total = attr_pool + bonus
            wire_key = sd.key.replace(" ", "_")
            skills[wire_key] = {
                "bonus":   _pool_to_dict(bonus),
                "total":   _pool_to_dict(total),
                "attr":    sd.attribute,
                "tags":    list(skill_tags.get(wire_key, [])),
            }

    # ── Specializations ────────────────────────────────────────────
    # Character.specializations is dict[str, DicePool].  Spec keys
    # follow the convention "<skill>:<spec_name>" (engine/character
    # treats them as bonuses on top of the parent skill).  We surface
    # both the spec_key and a human-readable name; total = parent
    # skill total + spec bonus.
    specializations = []
    for spec_key, spec_bonus in char.specializations.items():
        if not spec_bonus:
            continue
        # Best-effort split: "blaster:blaster_pistol" → parent "blaster"
        if ":" in spec_key:
            parent_skill, spec_name = spec_key.split(":", 1)
        else:
            parent_skill, spec_name = spec_key, spec_key
        parent_def = skill_reg.get(parent_skill)
        if parent_def:
            attr_pool = char.get_attribute(parent_def.attribute)
            parent_bonus = char.skills.get(parent_def.key)
            parent_total = attr_pool + parent_bonus if parent_bonus else attr_pool
            spec_total = parent_total + spec_bonus
        else:
            spec_total = spec_bonus
        specializations.append({
            "skill":  parent_skill.replace(" ", "_"),
            "name":   spec_name.replace("_", " ").title(),
            "bonus":  _pool_to_dict(spec_bonus),
            "total":  _pool_to_dict(spec_total),
        })

    # ── Force ──────────────────────────────────────────────────────
    # Powers list comes from list_powers_for_char(), which gates each
    # power on the required force skills (≥1D in control / sense /
    # alter).  Engine doesn't track per-character "learned" powers —
    # in WEG D6 R&E, having the gating skill = knowing the power.
    force = None
    if char.force_sensitive:
        powers_list = []
        try:
            from engine.force_powers import list_powers_for_char
            for p in list_powers_for_char(char):
                powers_list.append({
                    "key":         p.key,
                    "name":        p.name,
                    "skills":      list(p.skills),
                    "base_diff":   int(p.base_diff),
                    "dark_side":   bool(p.dark_side),
                    "combat_only": bool(getattr(p, "combat_only", False)),
                    "target":      getattr(p, "target", "self"),
                    "description": p.description or "",
                })
        except Exception:
            powers_list = []
        force = {
            "control": _pool_to_dict(char.control),
            "sense":   _pool_to_dict(char.sense),
            "alter":   _pool_to_dict(char.alter),
            "powers":  powers_list,
        }

    # ── Advantages / Disadvantages ─────────────────────────────────
    # Not yet schema-backed; emit empty arrays so the right rail's
    # HOOKS panel renders consistently across all characters.  The
    # client falls back to the background string when these are empty.
    advantages = []
    disadvantages = []

    # ── Weapon / Armor ─────────────────────────────────────────────
    weapon_payload = None
    armor_payload = None
    equip_data = char_dict.get("equipment", "{}")
    if isinstance(equip_data, str):
        try:
            equip_data = _json.loads(equip_data)
        except (ValueError, TypeError):
            equip_data = {}
    if isinstance(equip_data, dict):
        weapon_key = equip_data.get("weapon", "") or ""
        armor_key = equip_data.get("armor", "") or ""
        if weapon_key:
            try:
                from engine.weapons import get_weapon_registry
                wr = get_weapon_registry()
                w_obj = wr.get(weapon_key)
                if w_obj:
                    weapon_payload = {
                        "key":    weapon_key,
                        "name":   w_obj.name,
                        "damage": w_obj.damage,
                        "ranges": list(w_obj.ranges) if w_obj.ranges else [],
                    }
                else:
                    weapon_payload = {
                        "key": weapon_key, "name": weapon_key,
                        "damage": "", "ranges": [],
                    }
            except Exception:
                weapon_payload = {
                    "key": weapon_key, "name": weapon_key,
                    "damage": "", "ranges": [],
                }
        if armor_key:
            try:
                from engine.weapons import get_weapon_registry
                wr = get_weapon_registry()
                a_obj = wr.get(armor_key)
                if a_obj:
                    armor_payload = {
                        "key":      armor_key,
                        "name":     a_obj.name,
                        "energy":   a_obj.protection_energy or "",
                        "physical": a_obj.protection_physical or "",
                        "dex_pen":  a_obj.dexterity_penalty or "",
                    }
                else:
                    armor_payload = {
                        "key": armor_key, "name": armor_key,
                        "energy": "", "physical": "", "dex_pen": "",
                    }
            except Exception:
                armor_payload = {
                    "key": armor_key, "name": armor_key,
                    "energy": "", "physical": "", "dex_pen": "",
                }

    # ── Inventory ──────────────────────────────────────────────────
    inv_data = char_dict.get("inventory", "[]")
    if isinstance(inv_data, str):
        try:
            inv_data = _json.loads(inv_data)
        except (ValueError, TypeError):
            inv_data = []
    inventory = []
    if isinstance(inv_data, list):
        for item in inv_data:
            if isinstance(item, dict):
                inventory.append({
                    "name": str(item.get("name", "")),
                    "qty":  int(item.get("qty", 1) or 1),
                })
            elif isinstance(item, str) and item:
                inventory.append({"name": item, "qty": 1})

    # ── Background / notes / chargen_notes ─────────────────────────
    # background lives in pc_narrative (separate fetch); SheetCommand
    # hydrates that field before calling the builder, so we just read
    # it off the dict here.  chargen_notes lives on characters.
    background = char_dict.get("background", "") or ""
    notes = char_dict.get("notes", "") or ""
    chargen_notes = char_dict.get("chargen_notes", "") or ""

    return {
        "identity":        identity,
        "points":          points,
        "wound":           wound,
        "attributes":      attributes,
        "skills":          skills,
        "specializations": specializations,
        "force":           force,
        "advantages":      advantages,
        "disadvantages":   disadvantages,
        "weapon":          weapon_payload,
        "armor":           armor_payload,
        "inventory":       inventory,
        "background":      background,
        "notes":           notes,
        "chargen_notes":   chargen_notes,
        "skill_count":     len(skills),
    }


def build_skill_descriptions_payload(yaml_path=None):
    """Load data/skill_descriptions.yaml as a flat lookup dict.

    Returns:
        {
          "attributes": {dexterity: {description, short, gameplay_note,
                                     icon}, ...},
          "skills":     {blaster: {description, game_use, tags, priority,
                                   tip, attribute}, ...},
        }

    The client caches this on connect so the dashboard's right-rail
    drawer can display rich tooltips without round-tripping per skill.
    Skills from the YAML are flattened (the YAML groups them under
    parent attributes); each skill record has its parent attribute
    folded in as `attribute`.

    Returns an empty payload (with the shape preserved) if the YAML is
    missing or malformed — the client falls back to plain skill names.
    """
    import os
    try:
        import yaml as _yaml
    except ImportError:
        return {"attributes": {}, "skills": {}}

    if yaml_path is None:
        # Default location — same convention as SheetCommand uses for
        # data/skills.yaml.
        here = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.join(
            os.path.dirname(here), "data", "skill_descriptions.yaml"
        )
    if not os.path.exists(yaml_path):
        return {"attributes": {}, "skills": {}}

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
    except Exception:
        return {"attributes": {}, "skills": {}}

    out_attrs = {}
    for attr_name, attr_data in (raw.get("attributes") or {}).items():
        if not isinstance(attr_data, dict):
            continue
        out_attrs[attr_name.lower()] = {
            "description":   (attr_data.get("description") or "").strip(),
            "short":         (attr_data.get("short") or "").strip(),
            "gameplay_note": (attr_data.get("gameplay_note") or "").strip(),
            "icon":          (attr_data.get("icon") or "").strip(),
        }

    out_skills = {}
    skills_section = raw.get("skills") or {}
    for parent_attr, attr_block in skills_section.items():
        if not isinstance(attr_block, dict):
            continue
        for skill_key, skill_data in attr_block.items():
            if not isinstance(skill_data, dict):
                continue
            tags = skill_data.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            out_skills[skill_key.lower()] = {
                "description": (skill_data.get("description") or "").strip(),
                "game_use":    (skill_data.get("game_use") or "").strip(),
                "tip":         (skill_data.get("tip") or "").strip(),
                "tags":        [str(t) for t in tags],
                "priority":    (skill_data.get("priority") or "").strip(),
                "attribute":   parent_attr.lower(),
            }

    return {"attributes": out_attrs, "skills": out_skills}
