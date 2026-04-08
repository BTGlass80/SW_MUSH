#!/usr/bin/env python3
"""
Drop 2 — Skill Integration Patch for parser/space_commands.py
Patches:
  1. CoordinateCommand: route through resolve_coordinate_check()
  2. DamConCommand: route through resolve_repair_check(), fix kwarg bugs
     - Fixes: get_weapon_repair_skill() missing scale arg
     - Fixes: resolve_damage_control() called with wrong kwargs
     - Replaces with resolve_repair_check() from skill_checks.py
"""
import os
import sys
import shutil
import ast

TARGET = os.path.join("parser", "space_commands.py")
BACKUP = TARGET + ".pre_skill_patch_bak"


def read_file(path):
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def safe_replace(source, old, new, label):
    """Try LF version first, then CRLF."""
    if old in source:
        result = source.replace(old, new, 1)
        print(f"  [OK] {label}")
        return result
    old_crlf = old.replace("\n", "\r\n")
    if old_crlf in source:
        new_crlf = new.replace("\n", "\r\n")
        result = source.replace(old_crlf, new_crlf, 1)
        print(f"  [OK] {label} (CRLF)")
        return result
    print(f"  [FAIL] {label} — anchor not found!")
    return None


def main():
    if not os.path.exists(TARGET):
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    source = read_file(TARGET)

    # Backup
    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup: {BACKUP}")

    # ── Patch 1: CoordinateCommand ──
    OLD_COORD = '''\
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("commander") != char_id:
            await ctx.session.send_line("  Only the commander can coordinate the crew.")
            return
        # Command skill check
        from engine.character import Character, SkillRegistry
        from engine.dice import roll_d6_pool
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        cmd_pool = char_obj.get_skill_pool("command", sr)
        roll = roll_d6_pool(cmd_pool)
        difficulty = 12  # Moderate
        if roll.total >= difficulty:
            # Record coordination bonus
            crew["_coordinated"] = True
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_GREEN}[COMMAND]{ansi.RESET} "
                f"{ctx.session.character['name']} rallies the crew! "
                f"(Command: {roll.total} vs {difficulty}) "
                f"+1 to all crew rolls this round.")
        else:
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_YELLOW}[COMMAND]{ansi.RESET} "
                f"{ctx.session.character['name']}'s coordination attempt falls flat. "
                f"(Command: {roll.total} vs {difficulty})")'''

    NEW_COORD = '''\
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("commander") != char_id:
            await ctx.session.send_line("  Only the commander can coordinate the crew.")
            return
        # Command skill check via centralised engine
        from engine.skill_checks import resolve_coordinate_check
        result = resolve_coordinate_check(ctx.session.character, difficulty=12)

        if result["success"]:
            # Record coordination bonus (+2 on crit, +1 normal)
            crew["_coord_bonus"] = 2 if result["critical"] else 1
            crew["_coordinated"] = True
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
            color = ansi.BRIGHT_GREEN
        elif result["fumble"]:
            # Fumble: -1 penalty
            crew["_coord_bonus"] = -1
            crew["_coordinated"] = True
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
            color = ansi.BRIGHT_RED
        else:
            color = ansi.BRIGHT_YELLOW

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[COMMAND]{ansi.RESET} "
            f"{ctx.session.character['name']}: {result['message']}")'''

    patched = safe_replace(source, OLD_COORD, NEW_COORD, "CoordinateCommand → resolve_coordinate_check")
    if patched is None:
        print("ABORT: Could not patch CoordinateCommand.")
        sys.exit(1)
    source = patched

    # ── Patch 2: DamConCommand repair resolution ──
    # Replace from "# ── Look up repair skill ──" through the broadcast block
    OLD_DAMCON = '''\
        # ── Look up repair skill ──
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")

        if matched == "weapons":
            skill_name = get_weapon_repair_skill()
        else:
            skill_name = get_repair_skill_name(template.scale)

        repair_pool = char_obj.get_skill_pool(
            skill_name.replace("_", " "), sr
        )

        # Check if in combat (other ships in space nearby)
        in_combat = not ship["docked_at"]

        # ── Resolve the repair ──
        result = resolve_damage_control(
            repair_skill=repair_pool,
            system_name=matched,
            current_state=current_state,
            ship_scale=template.scale,
            in_combat=in_combat,
            num_actions=1,
        )

        # ── Apply results to database ──
        if result.success:
            if matched == "hull":
                new_dmg = max(0, ship.get("hull_damage", 0) - result.hull_repaired)
                await ctx.db.update_ship(ship["id"], hull_damage=new_dmg)
            else:
                systems[matched] = True
                await ctx.db.update_ship(
                    ship["id"], systems=json.dumps(systems)
                )
        elif result.permanent_failure:
            systems[matched] = "destroyed"
            await ctx.db.update_ship(
                ship["id"], systems=json.dumps(systems)
            )

        # ── Broadcast result ──
        if result.success:
            color = ansi.BRIGHT_GREEN
            tag = "REPAIR"
        elif result.permanent_failure:
            color = ansi.BRIGHT_RED
            tag = "REPAIR CRITICAL"
        else:
            color = ansi.BRIGHT_YELLOW
            tag = "REPAIR"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[{tag}]{ansi.RESET} "
            f"{ctx.session.character['name']} works on {matched}: "
            f"{result.narrative.strip()}"
        )'''

    NEW_DAMCON = '''\
        # ── Look up repair skill ──
        if matched == "weapons":
            skill_name = get_weapon_repair_skill(template.scale)
        else:
            skill_name = get_repair_skill_name(template.scale)
        # Normalise underscores for skill lookup
        skill_name = skill_name.replace("_", " ")

        # Difficulty: base + combat penalty
        from engine.starships import REPAIR_DIFFICULTIES as _RD
        base_diff = _RD.get(matched, 20)
        in_combat = not ship["docked_at"]
        effective_diff = base_diff + (5 if in_combat else 0)

        # ── Resolve via centralised skill check engine ──
        from engine.skill_checks import resolve_repair_check
        result = resolve_repair_check(
            ctx.session.character,
            skill_name,
            effective_diff,
            is_hull=(matched == "hull"),
        )

        # ── Apply results to database ──
        if result["success"]:
            if matched == "hull":
                new_dmg = max(0, ship.get("hull_damage", 0) - result["hull_repaired"])
                await ctx.db.update_ship(ship["id"], hull_damage=new_dmg)
            else:
                systems[matched] = True
                await ctx.db.update_ship(
                    ship["id"], systems=json.dumps(systems)
                )
        elif result["catastrophic"]:
            systems[matched] = "destroyed"
            await ctx.db.update_ship(
                ship["id"], systems=json.dumps(systems)
            )

        # ── Broadcast result ──
        if result["success"]:
            color = ansi.BRIGHT_GREEN
            tag = "REPAIR"
        elif result["catastrophic"]:
            color = ansi.BRIGHT_RED
            tag = "REPAIR CRITICAL"
        elif result["partial"]:
            color = ansi.BRIGHT_CYAN
            tag = "REPAIR"
        else:
            color = ansi.BRIGHT_YELLOW
            tag = "REPAIR"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[{tag}]{ansi.RESET} "
            f"{ctx.session.character['name']} works on {matched}: "
            f"{result['message'].strip()}"
        )'''

    patched = safe_replace(source, OLD_DAMCON, NEW_DAMCON, "DamConCommand → resolve_repair_check")
    if patched is None:
        print("ABORT: Could not patch DamConCommand.")
        sys.exit(1)
    source = patched

    # ── Patch 3: Remove unused imports (resolve_damage_control no longer called) ──
    # We keep it in the import list for now since ShipRepairCommand delegates to DamConCommand.
    # No import changes needed — resolve_damage_control is still available but unused.

    # ── Validate syntax ──
    try:
        ast.parse(source)
        print("  [OK] ast.parse passed")
    except SyntaxError as e:
        print(f"  [FAIL] SyntaxError: {e}")
        sys.exit(1)

    # ── Write ──
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(source)

    print(f"\nDone. {TARGET} patched successfully.")
    print("  - CoordinateCommand now uses resolve_coordinate_check()")
    print("  - DamConCommand now uses resolve_repair_check()")
    print("  - Fixed: get_weapon_repair_skill() now passes template.scale")
    print("  - Fixed: resolve_damage_control() wrong kwargs replaced entirely")


if __name__ == "__main__":
    main()
