"""
Persistent Tailing — parser/space_commands.py patch
Applies two changes:
  1. FireCommand: passes attacker_ship_id and target_ship_id into resolve_space_attack
     so the engine can apply the tailing bonus.
  2. EvadeCommand: full rewrite — replaces the flavor-only broadcast with a real
     contested pilot roll using the new resolve_evade() engine function.

Run from project root:
    python3 tailing_parser_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("parser", "space_commands.py")

# ── Patch 1 ───────────────────────────────────────────────────────────────────
# FireCommand: thread ship IDs into resolve_space_attack call.
# Anchor: the existing resolve_space_attack call in FireCommand.execute.

OLD_FIRE_CALL = '''\
        result = resolve_space_attack(
            attacker_skill=gunnery_pool, weapon=weapon,
            attacker_scale=template.scale_value,
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(target_template.maneuverability),
            target_hull=DicePool.parse(target_template.hull),
            target_shields=DicePool.parse(target_template.shields),
            target_scale=target_template.scale_value,
            range_band=rng,
            relative_position=rel_pos)'''

NEW_FIRE_CALL = '''\
        result = resolve_space_attack(
            attacker_skill=gunnery_pool, weapon=weapon,
            attacker_scale=template.scale_value,
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(target_template.maneuverability),
            target_hull=DicePool.parse(target_template.hull),
            target_shields=DicePool.parse(target_template.shields),
            target_scale=target_template.scale_value,
            range_band=rng,
            relative_position=rel_pos,
            attacker_ship_id=ship["id"],
            target_ship_id=target_ship["id"])'''

# ── Patch 2 ───────────────────────────────────────────────────────────────────
# EvadeCommand: replace the current execute() body with a real dice roll.
# Anchor: the full current execute method body.

OLD_EVADE_EXECUTE = '''\
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't evade while docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can evade.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        maneuver = template.maneuverability if template else "1D"
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} throws the ship into evasive maneuvers! "
            f"(Maneuverability: {maneuver})")


class SpawnShipCommand(BaseCommand):'''

NEW_EVADE_EXECUTE = '''\
    async def execute(self, ctx):
        from engine.starships import resolve_evade, EvadeResult
        from engine.character import Character, SkillRegistry

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't evade while docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can evade.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Unknown ship template.")
            return

        # Build pilot pool
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
        maneuver_pool = DicePool.parse(template.maneuverability)

        # Check engine state
        systems = _get_systems(ship)
        engine_state = systems.get("engines", "working")
        if isinstance(engine_state, bool):
            engine_state = "working" if engine_state else "damaged"

        result = resolve_evade(
            pilot_skill=pilot_pool,
            maneuverability=maneuver_pool,
            engine_state=engine_state,
            num_actions=1,
        )

        # Broadcast to bridge
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} throws the ship into evasive maneuvers! "
            f"{result.narrative.strip()}"
        )

        # On success, reset all position pairs involving this ship
        if result.all_tails_broken:
            grid = get_space_grid()
            ship_id = ship["id"]
            # Collect all ships that have a position relationship with us
            partners = [
                other_id for other_id in grid._positions
                if ship_id in grid._positions[other_id]
                   or other_id == ship_id
            ]
            for other_id in partners:
                if other_id != ship_id:
                    grid.set_position(ship_id, other_id, RelativePosition.FRONT)
                    grid.set_position(other_id, ship_id, RelativePosition.FRONT)


class SpawnShipCommand(BaseCommand):'''

# ── Patch 3 ───────────────────────────────────────────────────────────────────
# Add EvadeResult + resolve_evade to the imports from engine.starships.

OLD_STARSHIPS_IMPORT = '''\
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control,
)'''

NEW_STARSHIPS_IMPORT = '''\
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control, resolve_evade, EvadeResult,
)'''


def apply_patches(src: str) -> str:
    out = src

    # Patch 3: imports first (so inline imports in execute() are actually redundant
    # but harmless — they'll still work either way)
    if OLD_STARSHIPS_IMPORT not in out:
        print("  NOTE: Import block anchor not found — skipping import patch.")
        print("        resolve_evade / EvadeResult are imported inline in execute().")
    else:
        out = out.replace(OLD_STARSHIPS_IMPORT, NEW_STARSHIPS_IMPORT, 1)

    # Patch 1: fire call ship IDs
    if OLD_FIRE_CALL not in out:
        raise ValueError("Patch 1 anchor not found (resolve_space_attack call in FireCommand)")
    out = out.replace(OLD_FIRE_CALL, NEW_FIRE_CALL, 1)

    # Patch 2: EvadeCommand execute rewrite
    if OLD_EVADE_EXECUTE not in out:
        raise ValueError("Patch 2 anchor not found (EvadeCommand.execute body)")
    out = out.replace(OLD_EVADE_EXECUTE, NEW_EVADE_EXECUTE, 1)

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
    print("  1. FireCommand.execute: attacker_ship_id + target_ship_id passed to resolve_space_attack")
    print("  2. EvadeCommand.execute: full rewrite — real pilot roll, position reset on success")
    print("  3. Top-level import: resolve_evade + EvadeResult added (if anchor found)")
