"""
Hazard Table — parser/space_commands.py patch
Applies two changes:

  1. EvadeCommand.execute: full rewrite — real pilot roll using resolve_evade(),
     hazard table triggered on miss by 5+.

  2. _resolve_maneuver_cmd: replace the failure broadcast with a hazard-aware
     version that triggers roll_hazard_table() on miss by 5+ and applies damage.

Run from project root:
    python3 hazard_parser_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("parser", "space_commands.py")

# ── Patch 1 ───────────────────────────────────────────────────────────────────
# EvadeCommand.execute: rewrite from flavor-only to real dice + hazard.

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
            f"(Maneuverability: {maneuver})")'''

NEW_EVADE_EXECUTE = '''\
    async def execute(self, ctx):
        from engine.starships import resolve_evade, roll_hazard_table
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

        # Broadcast roll result
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} throws the ship into evasive maneuvers! "
            f"{result.narrative.strip()}"
        )

        if result.all_tails_broken:
            # Reset all position pairs involving this ship
            grid = get_space_grid()
            ship_id = ship["id"]
            partners = list(
                {k[1] for k in grid._positions if k[0] == ship_id}
                | {k[0] for k in grid._positions if k[1] == ship_id}
            )
            for other_id in partners:
                if other_id != ship_id:
                    grid.set_position(ship_id, other_id, RelativePosition.FRONT)
                    grid.set_position(other_id, ship_id, RelativePosition.FRONT)

        elif not result.success and not result.narrative.startswith("  Engines"):
            # Hazard check: miss by 5+ triggers hazard table
            margin = result.difficulty - result.roll_total
            if margin >= 5:
                hazard = roll_hazard_table(systems)
                await ctx.session_mgr.broadcast_to_room(
                    ship["bridge_room_id"],
                    hazard.narrative
                )
                if hazard.systems_damaged or hazard.hull_damage:
                    updates = {}
                    if hazard.hull_damage:
                        updates["hull_damage"] = (
                            ship.get("hull_damage", 0) + hazard.hull_damage
                        )
                    if hazard.systems_damaged:
                        for s in hazard.systems_damaged:
                            systems[s] = "damaged"
                        updates["systems"] = json.dumps(systems)
                    if updates:
                        await ctx.db.update_ship(ship["id"], **updates)'''

# ── Patch 2 ───────────────────────────────────────────────────────────────────
# _resolve_maneuver_cmd failure branch: add hazard check.

OLD_FAILURE_BRANCH = '''\
    else:
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} attempts a {maneuver_name} — failed! "
            f"Wasted action. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )


class JinkCommand(BaseCommand):'''

NEW_FAILURE_BRANCH = '''\
    else:
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} attempts a {maneuver_name} — failed! "
            f"Wasted action. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
        # Hazard check: miss by 5+ triggers hazard table
        margin = total_diff - roll.total
        if margin >= 5:
            from engine.starships import roll_hazard_table
            systems = _get_systems(ship)
            hazard = roll_hazard_table(systems)
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                hazard.narrative
            )
            if hazard.systems_damaged or hazard.hull_damage:
                updates = {}
                if hazard.hull_damage:
                    updates["hull_damage"] = (
                        ship.get("hull_damage", 0) + hazard.hull_damage
                    )
                if hazard.systems_damaged:
                    for s in hazard.systems_damaged:
                        systems[s] = "damaged"
                    updates["systems"] = json.dumps(systems)
                if updates:
                    await ctx.db.update_ship(ship["id"], **updates)


class JinkCommand(BaseCommand):'''

# ── Patch 3 ───────────────────────────────────────────────────────────────────
# Add roll_hazard_table + HazardResult to top-level starships import.

OLD_IMPORT = '''\
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control, resolve_evade, EvadeResult,
)'''

NEW_IMPORT = '''\
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control, resolve_evade, EvadeResult,
    roll_hazard_table, HazardResult,
)'''


def apply_patches(src: str) -> str:
    out = src

    # Patch 3: imports (best-effort)
    if OLD_IMPORT in out:
        out = out.replace(OLD_IMPORT, NEW_IMPORT, 1)
    else:
        print("  NOTE: Import anchor not found — roll_hazard_table imported inline only.")

    # Patch 1: EvadeCommand rewrite
    if OLD_EVADE_EXECUTE not in out:
        raise ValueError("Patch 1 anchor not found (EvadeCommand.execute body)")
    out = out.replace(OLD_EVADE_EXECUTE, NEW_EVADE_EXECUTE, 1)

    # Patch 2: _resolve_maneuver_cmd failure branch
    if OLD_FAILURE_BRANCH not in out:
        raise ValueError("Patch 2 anchor not found (_resolve_maneuver_cmd failure branch)")
    out = out.replace(OLD_FAILURE_BRANCH, NEW_FAILURE_BRANCH, 1)

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
    print("  1. EvadeCommand.execute: real pilot roll + hazard on miss by 5+")
    print("  2. _resolve_maneuver_cmd: hazard table on miss by 5+")
    print("  3. Top-level import: roll_hazard_table + HazardResult added")


if __name__ == "__main__":
    main()
