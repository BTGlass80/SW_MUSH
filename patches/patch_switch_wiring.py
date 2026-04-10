#!/usr/bin/env python3
"""
Drop 3 — Switch Wiring Patch
Adds /brief, /skills, /combat switches to +sheet
Adds /rolls, /status switches to +combat (absorbs CombatRollsCommand)

Apply AFTER: patch_parser_infra, patch_alias_sweep, patch_help_system
"""
import os, sys, shutil, ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = os.path.join(ROOT, "parser", "builtin_commands.py")
COMBAT  = os.path.join(ROOT, "parser", "combat_commands.py")
SHEET   = os.path.join(ROOT, "engine", "sheet_renderer.py")

errors = []


def patch_file(path, old, new, label):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        # Maybe already patched?
        if new in src or (label == "sheet_renderer_brief" and "render_brief_sheet" in src):
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
    for p in [BUILTIN, COMBAT, SHEET]:
        bak = p + ".bak_drop3"
        if not os.path.exists(bak):
            shutil.copy2(p, bak)
            print(f"  Backup: {os.path.basename(bak)}")

    # ════════════════════════════════════════════════════════════
    #  1. Add render_brief_sheet, render_skills_sheet,
    #     render_combat_sheet to sheet_renderer.py
    # ════════════════════════════════════════════════════════════

    SHEET_ANCHOR = "# ═══════════════════════════════════════════\n#  PUBLIC API\n# ═══════════════════════════════════════════"

    SHEET_NEW = '''# ═══════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════


def render_brief_sheet(char_dict, skill_reg, width=W):
    """Condensed one-line-per-attribute view."""
    from engine.character import Character
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f"  {DIM}({char.species_name}){RESET}"
    ))
    lines.append(_bar("-", DIM))

    # One line per attribute: DEXTERITY 3D+2 [Blaster 5D+1, Dodge 4D+2]
    for attr_name in LEFT_ATTRS + RIGHT_ATTRS:
        pool = char.get_attribute(attr_name)
        # Gather trained skills
        skill_parts = []
        for sd in skill_reg.skills_for_attribute(attr_name):
            bonus = char.skills.get(sd.key)
            if bonus:
                total = pool + bonus
                skill_parts.append(f"{CYAN}{sd.name}{RESET} {BRIGHT_GREEN}{total}{RESET}")
        skill_str = ""
        if skill_parts:
            skill_str = f"  [{', '.join(skill_parts)}]"
        lines.append(
            f"  {BOLD}{BRIGHT_WHITE}{attr_name.upper():<14s}{RESET}"
            f" {BRIGHT_YELLOW}{str(pool):>5s}{RESET}"
            f"{skill_str}"
        )

    # Force (if sensitive)
    if char.force_sensitive:
        lines.append(
            f"  {BRIGHT_BLUE}Force{RESET}"
            f"  C:{BRIGHT_YELLOW}{char.control}{RESET}"
            f"  S:{BRIGHT_YELLOW}{char.sense}{RESET}"
            f"  A:{BRIGHT_YELLOW}{char.alter}{RESET}"
        )

    # Footer: wound + points
    cp = char_dict.get("character_points", 0)
    fp = char_dict.get("force_points", 0)
    lines.append(
        f"  {_wound_display(wound)}"
        f"  CP:{BRIGHT_GREEN}{cp}{RESET}"
        f"  FP:{BRIGHT_BLUE}{fp}{RESET}"
    )
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append("")
    return lines


def render_skills_sheet(char_dict, skill_reg, width=W):
    """Skills-only view grouped by attribute."""
    from engine.character import Character
    char = Character.from_db_dict(char_dict)

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f" {DIM}— Skills{RESET}"
    ))
    lines.append(_bar("-", DIM))

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

    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append("")
    return lines


def render_combat_sheet(char_dict, skill_reg, width=W):
    """Combat-relevant stats: wounds, weapon, soak, combat skills."""
    from engine.character import Character
    import json as _json
    char = Character.from_db_dict(char_dict)
    wound = WoundLevel(char_dict.get("wound_level", 0))

    lines = []
    lines.append("")
    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append(_center(
        f"{BOLD}{BRIGHT_WHITE}{char.name}{RESET}"
        f" {DIM}— Combat Stats{RESET}"
    ))
    lines.append(_bar("-", DIM))

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

    lines.append(_bar("=", BRIGHT_CYAN))
    lines.append("")
    return lines'''

    patch_file(SHEET, SHEET_ANCHOR, SHEET_NEW, "sheet_renderer_views")

    # ════════════════════════════════════════════════════════════
    #  2. Wire SheetCommand with /brief, /skills, /combat switches
    # ════════════════════════════════════════════════════════════

    SHEET_CMD_OLD = '''class SheetCommand(BaseCommand):
    key = "+sheet"
    aliases = ["sheet", "score", "stats", "+score", "+stats", "sc"]
    help_text = "View your character sheet."
    usage = "sheet"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        from engine.sheet_renderer import render_game_sheet
        import os
        from engine.character import SkillRegistry
        skill_reg = SkillRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            skill_reg.load_file(skills_path)

        lines = render_game_sheet(char, skill_reg)
        for line in lines:
            await ctx.session.send_line(line)'''

    SHEET_CMD_NEW = '''class SheetCommand(BaseCommand):
    key = "+sheet"
    aliases = ["sheet", "score", "stats", "+score", "+stats", "sc"]
    help_text = "View your character sheet."
    usage = "+sheet [/brief|/skills|/combat]"
    valid_switches = ["brief", "skills", "combat"]

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        import os
        from engine.character import SkillRegistry
        skill_reg = SkillRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            skill_reg.load_file(skills_path)

        # Dispatch by switch
        if "brief" in ctx.switches:
            from engine.sheet_renderer import render_brief_sheet
            lines = render_brief_sheet(char, skill_reg)
        elif "skills" in ctx.switches:
            from engine.sheet_renderer import render_skills_sheet
            lines = render_skills_sheet(char, skill_reg)
        elif "combat" in ctx.switches:
            from engine.sheet_renderer import render_combat_sheet
            lines = render_combat_sheet(char, skill_reg)
        else:
            from engine.sheet_renderer import render_game_sheet
            lines = render_game_sheet(char, skill_reg)

        for line in lines:
            await ctx.session.send_line(line)'''

    patch_file(BUILTIN, SHEET_CMD_OLD, SHEET_CMD_NEW, "sheet_switches")

    # ════════════════════════════════════════════════════════════
    #  3. Wire CombatStatusCommand with /rolls, /status switches
    #     and thin-redirect CombatRollsCommand
    # ════════════════════════════════════════════════════════════

    COMBAT_STATUS_OLD = '''class CombatStatusCommand(BaseCommand):
    key = "+combat"
    aliases = ["combat", "cs", "+cs"]
    help_text = "Show current combat status."
    usage = "combat"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        lines = combat.get_status()
        for line in lines:
            await ctx.session.send_line(ansi.combat_msg(line))'''

    COMBAT_STATUS_NEW = '''class CombatStatusCommand(BaseCommand):
    key = "+combat"
    aliases = ["combat", "cs", "+cs"]
    help_text = "Show current combat status."
    usage = "+combat [/rolls|/status]"
    valid_switches = ["rolls", "status"]

    async def execute(self, ctx: CommandContext):
        if "rolls" in ctx.switches:
            return await self._show_rolls(ctx)
        # Default (no switch or /status): show status
        return await self._show_status(ctx)

    async def _show_status(self, ctx):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        lines = combat.get_status()
        for line in lines:
            await ctx.session.send_line(ansi.combat_msg(line))

    async def _show_rolls(self, ctx):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        rolls = getattr(combat, "_last_initiative_rolls", {})
        if not rolls:
            await ctx.session.send_line("  No initiative rolls recorded yet.")
            return

        await ctx.session.send_line(
            ansi.combat_msg(f"Initiative rolls \\u2014 Round {combat.round_num}:")
        )
        for name, display in rolls.items():
            await ctx.session.send_line(f"  {name}: {display}")'''

    patch_file(COMBAT, COMBAT_STATUS_OLD, COMBAT_STATUS_NEW, "combat_switches")

    # Thin-redirect CombatRollsCommand to use the switch
    ROLLS_OLD = '''class CombatRollsCommand(BaseCommand):
    key = "combat rolls"
    aliases = ["crolls"]
    help_text = "Show the detailed initiative roll breakdown for this round."
    usage = "combat rolls"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        rolls = getattr(combat, "_last_initiative_rolls", {})
        if not rolls:
            await ctx.session.send_line("  No initiative rolls recorded yet.")
            return

        await ctx.session.send_line(
            ansi.combat_msg(f"Initiative rolls \\u2014 Round {combat.round_num}:")
        )
        for name, display in rolls.items():
            await ctx.session.send_line(f"  {name}: {display}")'''

    ROLLS_NEW = '''class CombatRollsCommand(BaseCommand):
    key = "crolls"
    aliases = ["combat rolls"]
    help_text = "Show the detailed initiative roll breakdown for this round."
    usage = "crolls  (or +combat/rolls)"

    async def execute(self, ctx: CommandContext):
        ctx.switches = ["rolls"]
        cmd = CombatStatusCommand()
        await cmd.execute(ctx)'''

    patch_file(COMBAT, ROLLS_OLD, ROLLS_NEW, "combat_rolls_redirect")

    # ── Validate ──
    validate(SHEET, "sheet_renderer.py")
    validate(BUILTIN, "builtin_commands.py")
    validate(COMBAT, "combat_commands.py")

    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    {e}")
        sys.exit(1)
    else:
        print("\n  Drop 3 (Switch Wiring) applied successfully!")
        print("    +sheet/brief  — condensed one-line-per-attribute view")
        print("    +sheet/skills — skill list only, grouped by attribute")
        print("    +sheet/combat — combat-relevant stats")
        print("    +combat/rolls — initiative roll breakdown (absorbs CombatRollsCommand)")


if __name__ == "__main__":
    main()
