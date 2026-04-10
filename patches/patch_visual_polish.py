#!/usr/bin/env python3
"""
Visual Polish Patch
1. Condense NPC display in `look` when 5+ NPCs are present
2. Word-wrap help category listings at 78 columns
3. Visual improvements to character sheet renderer

Apply AFTER: patch_switch_wiring.py (Drop 3)
"""
import os, sys, shutil, ast, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = os.path.join(ROOT, "parser", "builtin_commands.py")
SHEET   = os.path.join(ROOT, "engine", "sheet_renderer.py")

errors = []


def patch_file(path, old, new, label):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        if new in src:
            print(f"  [{label}] Already applied, skipping.")
            return src
        errors.append(f"[{label}] Anchor not found in {os.path.basename(path)}")
        return src
    src = src.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  [{label}] OK")
    return src


def validate(path, label):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    try:
        ast.parse(src)
        print(f"  [{label}] AST valid")
    except SyntaxError as e:
        errors.append(f"[{label}] Syntax error: {e}")


def main():
    # ── Backup ──
    for p in [BUILTIN, SHEET]:
        bak = p + ".bak_visual"
        if not os.path.exists(bak):
            shutil.copy2(p, bak)
            print(f"  Backup: {os.path.basename(bak)}")

    # ════════════════════════════════════════════════════════════
    #  1. Condense NPC display in LookCommand
    #     When 5+ NPCs, show condensed: names only + "(type '+look <name>' ...)"
    #     When <5, show full descriptions as before
    # ════════════════════════════════════════════════════════════

    NPC_OLD = '''        # NPCs in the room
        npcs = await ctx.db.get_npcs_in_room(char["room_id"])
        if npcs and not present:
            await session.send_line("")
        for npc in npcs:
            desc = npc.get("description", "")
            if desc and not desc.startswith("["):
                await session.send_line(
                    f"  {ansi.npc_name(npc['name'])} is here. {desc}"
                )
            else:
                await session.send_line(
                    f"  {ansi.npc_name(npc['name'])} is here."
                )'''

    NPC_NEW = '''        # NPCs in the room
        npcs = await ctx.db.get_npcs_in_room(char["room_id"])
        if npcs:
            if not present:
                await session.send_line("")

            NPC_CONDENSE_THRESHOLD = 5
            if len(npcs) >= NPC_CONDENSE_THRESHOLD:
                # Condensed: group NPC names into wrapped lines
                npc_names = [ansi.npc_name(n["name"]) for n in npcs]
                # Build a comma-separated string and wrap it
                # We need to estimate ANSI-free width for wrapping
                plain_names = [n["name"] for n in npcs]
                # Wrap the plain version, then rebuild with ANSI
                name_str = ", ".join(plain_names)
                indent = "  Also here: "
                subsequent = " " * len("  Also here: ")
                wrapped = textwrap.wrap(
                    name_str, width=session.width - 2,
                    initial_indent=indent,
                    subsequent_indent=subsequent,
                )
                # Re-inject ANSI coloring into the wrapped output
                for wline in wrapped:
                    for pn in plain_names:
                        wline = wline.replace(
                            pn, ansi.npc_name(pn), 1)
                    await session.send_line(wline)
                await session.send_line(
                    f"  {ansi.DIM}(Type 'look <name>' to examine someone.)"
                    f"{ansi.RESET}"
                )
            else:
                # Few NPCs: show full descriptions
                for npc in npcs:
                    desc = npc.get("description", "")
                    if desc and not desc.startswith("["):
                        await session.send_line(
                            f"  {ansi.npc_name(npc['name'])} is here."
                            f" {desc}"
                        )
                    else:
                        await session.send_line(
                            f"  {ansi.npc_name(npc['name'])} is here."
                        )'''

    patch_file(BUILTIN, NPC_OLD, NPC_NEW, "npc_condense")

    # ════════════════════════════════════════════════════════════
    #  2. Word-wrap help category listings
    # ════════════════════════════════════════════════════════════

    HELP_OLD = '''        for cat, cmds in self.CATEGORIES.items():
            # Skip admin categories for non-admins
            if cat in ("Building", "Admin"):
                if not (ctx.session.account
                        and ctx.session.account.get("is_admin", 0)):
                    continue
            cmd_str = ", ".join(
                f"{ansi.BRIGHT_CYAN}{c}{ansi.RESET}" for c in cmds)
            await ctx.session.send_line(
                f"  {ansi.BOLD}{cat:14s}{ansi.RESET} {cmd_str}")'''

    HELP_NEW = '''        for cat, cmds in self.CATEGORIES.items():
            # Skip admin categories for non-admins
            if cat in ("Building", "Admin"):
                if not (ctx.session.account
                        and ctx.session.account.get("is_admin", 0)):
                    continue
            # Word-wrap the command list at terminal width
            plain_str = ", ".join(cmds)
            label = f"  {cat:14s} "
            indent = " " * 17  # align continuation under first cmd
            wrapped = textwrap.wrap(
                plain_str, width=ctx.session.width - 2,
                initial_indent=label,
                subsequent_indent=indent,
            )
            for i, wline in enumerate(wrapped):
                # Re-inject ANSI coloring on command names
                for c in cmds:
                    wline = wline.replace(
                        c, f"{ansi.BRIGHT_CYAN}{c}{ansi.RESET}", 1)
                # Bold the category label on first line
                if i == 0:
                    wline = wline.replace(
                        label, f"  {ansi.BOLD}{cat:14s}{ansi.RESET} ", 1)
                await ctx.session.send_line(wline)'''

    patch_file(BUILTIN, HELP_OLD, HELP_NEW, "help_wordwrap")

    # ════════════════════════════════════════════════════════════
    #  3. Visual improvements to character sheet
    #     - Box-drawing characters for structure
    #     - Tighter spacing
    #     - More distinct section headers
    # ════════════════════════════════════════════════════════════

    # Replace the render_game_sheet function
    SHEET_OLD = '''def render_game_sheet(char_dict, skill_reg, width=W):
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
    return lines'''

    SHEET_NEW = r'''def render_game_sheet(char_dict, skill_reg, width=W):
    """Render in-game character sheet (R&E layout) with box-drawing."""
    from engine.character import Character
    import json as _json
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    # Box-drawing characters
    TL = "\u250c"  # ┌
    TR = "\u2510"  # ┐
    BL = "\u2514"  # └
    BR = "\u2518"  # ┘
    H  = "\u2500"  # ─
    V  = "\u2502"  # │
    LT = "\u251c"  # ├
    RT = "\u2524"  # ┤

    def box_top(w=W):
        return f"{BRIGHT_CYAN}{TL}{H * (w - 2)}{TR}{RESET}"

    def box_bot(w=W):
        return f"{BRIGHT_CYAN}{BL}{H * (w - 2)}{BR}{RESET}"

    def box_mid(w=W):
        return f"{DIM}{LT}{H * (w - 2)}{RT}{RESET}"

    def box_line(text, w=W):
        pad = max(0, w - 4 - _ansi_len(text))
        return f"{DIM}{V}{RESET} {text}{' ' * pad} {DIM}{V}{RESET}"

    def box_empty(w=W):
        return f"{DIM}{V}{' ' * (w - 2)}{V}{RESET}"

    def section_header(title, w=W):
        t = f" {title} "
        bar_len = w - 4 - len(title)
        left = bar_len // 2
        right = bar_len - left
        return (f"{DIM}{LT}{RESET}"
                f"{BRIGHT_CYAN}{H * left}{RESET}"
                f"{BOLD}{BRIGHT_WHITE}{t}{RESET}"
                f"{BRIGHT_CYAN}{H * right}{RESET}"
                f"{DIM}{RT}{RESET}")

    lines = []
    lines.append("")
    lines.append(box_top())

    # ── Title ──
    title = f"{BOLD}{BRIGHT_WHITE}STAR WARS{RESET} {DIM}D6 Character Sheet{RESET}"
    lines.append(box_line(_center(title, W - 4)))

    lines.append(section_header("IDENTITY"))

    # ── Identity ──
    template_str = ""
    if char_dict.get("template"):
        template_str = f"  {DIM}({char_dict['template']}){RESET}"
    lines.append(box_line(
        f"Name: {BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f"    Species: {BRIGHT_YELLOW}{char.species_name}{RESET}"
        f"{template_str}"
    ))

    # ── Points row ──
    cp = char_dict.get("character_points", 0)
    fp = char_dict.get("force_points", 0)
    dsp = char_dict.get("dark_side_points", 0)
    fs = f"{BRIGHT_BLUE}Yes{RESET}" if char.force_sensitive else f"{DIM}No{RESET}"
    lines.append(box_line(
        f"Move: {BRIGHT_WHITE}{char.move}{RESET}"
        f"   Force Pts: {BRIGHT_BLUE}{fp}{RESET}"
        f"   Char Pts: {BRIGHT_GREEN}{cp}{RESET}"
        f"   Force: {fs}"
    ))
    lines.append(box_line(f"Dark Side: {_dsp_pips(dsp)}"))

    # ── Attribute Grid ──
    lines.append(section_header("ATTRIBUTES & SKILLS"))

    left_lines = []
    for attr in LEFT_ATTRS:
        left_lines.extend(_build_attr_block(attr, char, skill_reg, COL - 2))
        left_lines.append("")

    right_lines = []
    for attr in RIGHT_ATTRS:
        right_lines.extend(_build_attr_block(attr, char, skill_reg, COL - 2))
        right_lines.append("")

    merged = _merge_columns(left_lines, right_lines, col_width=COL - 2,
                            gutter="  " + DIM + "\u2502" + RESET + " ")
    for m in merged:
        lines.append(box_line(m))

    # ── Force (if sensitive) ──
    if char.force_sensitive:
        lines.append(section_header("THE FORCE"))
        lines.append(box_line(
            f"Control: {BRIGHT_YELLOW}{char.control}{RESET}"
            f"    Sense: {BRIGHT_YELLOW}{char.sense}{RESET}"
            f"    Alter: {BRIGHT_YELLOW}{char.alter}{RESET}"
        ))

    # ── Wound Status ──
    lines.append(section_header("CONDITION"))
    lines.append(box_line(_wound_display(wound)))

    # ── Weapons Table ──
    lines.append(section_header("EQUIPMENT"))
    lines.append(box_line(
        f"{BOLD}{'Weapon':<22s}{'Dmg':>5s}"
        f"  {'Short':>6s} {'Med':>6s} {'Long':>6s}{RESET}"
    ))
    lines.append(box_line(
        f"{DIM}{'-' * 22}{'-' * 5}  {'-' * 6} {'-' * 6} {'-' * 6}{RESET}"
    ))

    # Show equipped weapon from character data
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
            if w.is_ranged and w.ranges:
                lines.append(box_line(
                    f"{BRIGHT_WHITE}{w.name:<22s}{RESET}"
                    f"{BRIGHT_YELLOW}{w.damage:>5s}{RESET}"
                    f"  {w.ranges[1]:>6d} {w.ranges[2]:>6d} {w.ranges[3]:>6d}"
                ))
            else:
                lines.append(box_line(
                    f"{BRIGHT_WHITE}{w.name:<22s}{RESET}"
                    f"{BRIGHT_YELLOW}{w.damage:>5s}{RESET}"
                    f"  {'Melee':>6s}"
                ))
        else:
            lines.append(box_line(weapon_key))
    else:
        lines.append(box_line(f"{DIM}(no weapons equipped){RESET}"))

    lines.append(box_bot())
    lines.append("")
    return lines'''

    patch_file(SHEET, SHEET_OLD, SHEET_NEW, "sheet_visual")

    # ── Validate ──
    validate(BUILTIN, "builtin_commands.py")
    validate(SHEET, "sheet_renderer.py")

    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    {e}")
        sys.exit(1)
    else:
        print("\n  Visual Polish patch applied successfully!")
        print("    1. NPC condensing: 5+ NPCs show as name list with 'look <name>' hint")
        print("    2. Help word wrap: category listings wrap at terminal width")
        print("    3. Sheet visual: box-drawing borders, section headers, tighter layout")


if __name__ == "__main__":
    main()
